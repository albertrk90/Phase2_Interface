"""Stage E: stereo geometry analysis (host-side, no camera access).

Functions used by rectify_stereo.py after a capture, and an offline mode that applies
a saved calibration to previously captured raw pairs:

    .venv\\Scripts\\python.exe stereo_geometry.py --calibration results\\calibration_user_<id>_<stamp>.json ^
        --pair <left.png> <right.png> [--pair ...] --label <name> [--alpha 0 --alpha 1]

What it measures:
  * calibration summary: intrinsics, 14-coefficient distortion, extrinsics, baseline,
    stored rectification rotations, pinhole and distortion-aware field of view
  * host rectification (OpenCV, from the calibration) for given alpha values:
    valid-pixel fraction, inscribed valid rectangle, effective field of view
  * residual vertical disparity from matched SIFT features (ratio test, mutual check,
    MAGSAC epipolar consistency, disparity sign/range). Too few or poorly spread
    matches give "insufficient", not a score.
  * for device-rectified frames: the rectified camera matrix actually used, fitted from
    raw<->rectified matches of the same frame, with the fit residual (how well the device
    output agrees with the calibration model)

Guide-line comparison images are analysis aids only. They are never meant for participants.
"""

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

RESULTS_DIR = Path(__file__).resolve().parent / "results"
MIN_INLIERS = 50          # below this, no vertical-disparity score is reported
MIN_GRID_CELLS = 5        # of a 3 x 3 grid, each with >= 3 matches
EPIPOLAR_THRESH_PX = 1.5  # MAGSAC threshold for the epipolar consistency check


def _stats(values):
    if values is None or len(values) == 0:
        return None
    a = np.abs(np.asarray(values, dtype=float))
    return {"n": int(a.size), "median": float(np.median(a)), "p95": float(np.percentile(a, 95)),
            "max": float(a.max()), "mean": float(a.mean())}


# --- calibration -------------------------------------------------------------------------------

def calibration_summary(dai, calib_path, width, height):
    """Read-only summary of a saved calibration JSON (the same data the device rectifies with)."""
    c = dai.CalibrationHandler(str(calib_path))
    left, right = c.getStereoLeftCameraId(), c.getStereoRightCameraId()
    out = {"source": str(calib_path), "size": [width, height], "left_socket": str(left), "right_socket": str(right)}
    raw = json.loads(Path(calib_path).read_text(encoding="utf-8"))
    out["stereoEnableDistortionCorrection"] = raw.get("stereoEnableDistortionCorrection")
    for name, sock in (("left", left), ("right", right)):
        K = np.array(c.getCameraIntrinsics(sock, width, height), dtype=float)
        D = np.array(c.getDistortionCoefficients(sock), dtype=float)
        out[name] = {"K": K.tolist(), "D": D.tolist(), "distortion_model": str(c.getDistortionModel(sock)),
                     "fov_pinhole_deg": float(c.getFov(sock, False)), "fov_spec_deg": float(c.getFov(sock, True)),
                     **raw_fov(K, D, width, height)}
    E = np.array(c.getCameraExtrinsics(left, right), dtype=float)
    out["R_left_to_right"], out["T_left_to_right_cm"] = E[:3, :3].tolist(), E[:3, 3].tolist()
    out["baseline_cm"] = float(c.getBaselineDistance(right, left, False))
    out["stored_rect_R_left"] = np.array(c.getStereoLeftRectificationRotation(), dtype=float).tolist()
    out["stored_rect_R_right"] = np.array(c.getStereoRightRectificationRotation(), dtype=float).tolist()
    return out


def raw_fov(K, D, width, height):
    """Field of view of the raw image, accounting for lens distortion (edge pixels undistorted)."""
    cx, cy = K[0, 2], K[1, 2]
    pts = np.array([[[0.0, cy]], [[width - 1.0, cy]], [[cx, 0.0]], [[cx, height - 1.0]]], dtype=np.float64)
    n = cv2.undistortPointsIter(pts, K, D, None, None, (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 200, 1e-9)).reshape(-1, 2)
    h = math.degrees(math.atan(-n[0, 0]) + math.atan(n[1, 0]))
    v = math.degrees(math.atan(-n[2, 1]) + math.atan(n[3, 1]))
    return {"fov_distortion_aware_deg": {"horizontal": h, "vertical": v}}


def rotation_angle_deg(Ra, Rb):
    R = np.asarray(Ra) @ np.asarray(Rb).T
    return float(math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2)))))


# --- rectification maps, valid area, field of view ----------------------------------------------

def rect_maps(K, D, R, P, size):
    return cv2.initUndistortRectifyMap(np.asarray(K), np.asarray(D), np.asarray(R), np.asarray(P)[:3, :3], size, cv2.CV_32FC1)


def valid_mask(mapx, mapy, size):
    w, h = size
    return (mapx >= 0) & (mapx <= w - 1) & (mapy >= 0) & (mapy <= h - 1)


def inscribed_rect(mask):
    """Largest axis-aligned rectangle (greedy shrink) containing only valid pixels; [x0, y0, x1, y1] inclusive."""
    y0, y1, x0, x1 = 0, mask.shape[0] - 1, 0, mask.shape[1] - 1
    while y0 < y1 and x0 < x1:
        sides = {"top": (~mask[y0, x0:x1 + 1]).sum(), "bottom": (~mask[y1, x0:x1 + 1]).sum(),
                 "left": (~mask[y0:y1 + 1, x0]).sum(), "right": (~mask[y0:y1 + 1, x1]).sum()}
        worst = max(sides, key=sides.get)
        if sides[worst] == 0:
            return [int(x0), int(y0), int(x1), int(y1)]
        if worst == "top":
            y0 += 1
        elif worst == "bottom":
            y1 -= 1
        elif worst == "left":
            x0 += 1
        else:
            x1 -= 1
    return None


def area_report(mask, Knew):
    """Valid fraction, inscribed rectangle and effective field of view of a rectified view."""
    h, w = mask.shape
    fx, fy, cx, cy = Knew[0][0], Knew[1][1], Knew[0][2], Knew[1][2]
    rect = inscribed_rect(mask)
    row, col = mask[int(round(cy))], mask[:, int(round(cx))]
    xs, ys = np.flatnonzero(row), np.flatnonzero(col)

    def span(lo, hi, f, c):
        return math.degrees(math.atan((hi - c) / f) - math.atan((lo - c) / f))

    out = {"valid_fraction": float(mask.mean()),
           "black_border_fraction": float(1 - mask.mean()),
           "inscribed_valid_rect": rect,
           "inscribed_valid_rect_size": [rect[2] - rect[0] + 1, rect[3] - rect[1] + 1] if rect else None,
           "fov_full_output_deg": {"horizontal": span(-0.5, w - 0.5, fx, cx), "vertical": span(-0.5, h - 0.5, fy, cy)},
           "fov_valid_central_row_col_deg": {"horizontal": span(xs[0], xs[-1], fx, cx) if xs.size else None,
                                             "vertical": span(ys[0], ys[-1], fy, cy) if ys.size else None}}
    if rect:
        out["fov_inscribed_rect_deg"] = {"horizontal": span(rect[0], rect[2], fx, cx), "vertical": span(rect[1], rect[3], fy, cy)}
    return out


def host_rectification(summary, alpha):
    """OpenCV stereoRectify from the calibration; returns transforms and per-eye maps."""
    w, h = summary["size"]
    L, R = summary["left"], summary["right"]
    T = np.array(summary["T_left_to_right_cm"])
    R1, R2, P1, P2, Q, roi1, roi2 = cv2.stereoRectify(np.array(L["K"]), np.array(L["D"]), np.array(R["K"]), np.array(R["D"]),
                                                      (w, h), np.array(summary["R_left_to_right"]), T,
                                                      flags=cv2.CALIB_ZERO_DISPARITY, alpha=alpha)
    maps = {"left": rect_maps(L["K"], L["D"], R1, P1, (w, h)), "right": rect_maps(R["K"], R["D"], R2, P2, (w, h))}
    info = {"alpha": alpha, "R1": R1.tolist(), "R2": R2.tolist(), "P1": P1.tolist(), "P2": P2.tolist(),
            "opencv_valid_roi_left": list(map(int, roi1)), "opencv_valid_roi_right": list(map(int, roi2)),
            "R1_vs_stored_rect_left_deg": rotation_angle_deg(R1, summary["stored_rect_R_left"]),
            "R2_vs_stored_rect_right_deg": rotation_angle_deg(R2, summary["stored_rect_R_right"])}
    for eye, P in (("left", P1), ("right", P2)):
        info[eye] = area_report(valid_mask(*maps[eye], (w, h)), P[:3, :3])
    return info, maps


# --- feature matching ---------------------------------------------------------------------------

def match_features(img_a, img_b, max_features=5000, ratio=0.75):
    sift = cv2.SIFT_create(nfeatures=max_features)
    ka, da = sift.detectAndCompute(img_a, None)
    kb, db = sift.detectAndCompute(img_b, None)
    if da is None or db is None or len(ka) < 10 or len(kb) < 10:
        return np.empty((0, 2)), np.empty((0, 2)), {"keypoints": [len(ka), len(kb)], "ratio_mutual": 0}
    bf = cv2.BFMatcher(cv2.NORM_L2)
    fwd = bf.knnMatch(da, db, k=2)
    back = {m.queryIdx: m.trainIdx for m in bf.match(db, da)}
    good = [m for m, n in (p for p in fwd if len(p) == 2) if m.distance < ratio * n.distance and back.get(m.trainIdx) == m.queryIdx]
    pa = np.float64([ka[m.queryIdx].pt for m in good]).reshape(-1, 2)
    pb = np.float64([kb[m.trainIdx].pt for m in good]).reshape(-1, 2)
    return pa, pb, {"keypoints": [len(ka), len(kb)], "ratio_mutual": len(good)}


def grid_coverage(pts, size, n=3):
    w, h = size
    cells = np.zeros((n, n), dtype=int)
    for x, y in pts:
        cells[min(n - 1, int(y * n / h)), min(n - 1, int(x * n / w))] += 1
    return cells


def vertical_disparity(left, right, fx, rectified, max_disp_fraction=0.5):
    """Residual |yL - yR| over reliable matches. Returns counts at each filter stage and statistics (or 'insufficient')."""
    h, w = left.shape[:2]
    pl, pr, info = match_features(left, right)
    out = {"rectified_input": rectified, "keypoints": info["keypoints"], "after_ratio_and_mutual": info["ratio_mutual"]}
    if len(pl) < 8:
        out.update({"status": "insufficient", "reason": "fewer than 8 candidate matches", "reliable": 0})
        return out
    _, inl = cv2.findFundamentalMat(pl, pr, cv2.USAC_MAGSAC, EPIPOLAR_THRESH_PX, 0.999, 10000)
    keep = inl.ravel().astype(bool) if inl is not None else np.zeros(len(pl), bool)
    out["after_epipolar_check"] = int(keep.sum())
    d = pl[:, 0] - pr[:, 0]
    keep &= (d >= -2.0) & (d <= max_disp_fraction * w)
    out["after_disparity_range"] = int(keep.sum())
    pl, pr = pl[keep], pr[keep]
    cells = grid_coverage(pl, (w, h))
    out["grid_3x3_counts"] = cells.tolist()
    covered = int((cells >= 3).sum())
    out["reliable"] = int(len(pl))
    dy = pl[:, 1] - pr[:, 1]
    if len(pl) < MIN_INLIERS or covered < MIN_GRID_CELLS:
        out.update({"status": "insufficient",
                    "reason": f"{len(pl)} reliable matches in {covered} grid cells (need >= {MIN_INLIERS} in >= {MIN_GRID_CELLS})"})
        if len(pl) >= MIN_INLIERS:
            out["covered_region_only_not_a_whole_image_score"] = {"abs_dy_px": _stats(dy), "grid_cells_covered": covered}
        return out
    r = np.hypot((pl[:, 0] - w / 2) / (w / 2), (pl[:, 1] - h / 2) / (h / 2)) / math.sqrt(2)
    out.update({"status": "ok", "grid_cells_covered": covered,
                "abs_dy_px": _stats(dy), "signed_dy_px_median": float(np.median(dy)),
                "abs_dy_arcmin": _stats(np.degrees(np.arctan(np.abs(dy) / fx)) * 60),
                "abs_dy_px_centre": _stats(dy[r < 0.5]), "abs_dy_px_periphery": _stats(dy[r >= 0.5]),
                "fraction_abs_dy_over_1px": float(np.mean(np.abs(dy) > 1.0)),
                "disparity_px_range": [float(np.percentile(d[keep], 5)), float(np.percentile(d[keep], 95))]})
    return out


def fit_rectified_camera(raw, rect, K, D, R):
    """Fit the camera matrix a rectified frame was produced with, from raw<->rectified matches of the same frame.

    rect_px = f * xn + c, where xn are raw points undistorted and rotated by R. The residual shows how well
    the device output agrees with the calibration model (distortion correction, rotation)."""
    pa, pb, info = match_features(raw, rect)
    if len(pa) < 30:
        return {"status": "insufficient", "matches": len(pa)}
    n = cv2.undistortPointsIter(pa.reshape(-1, 1, 2), np.asarray(K), np.asarray(D), np.asarray(R), None,
                                (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 200, 1e-9)).reshape(-1, 2)
    keep = np.ones(len(n), bool)
    for _ in range(5):
        ax = np.polyfit(n[keep, 0], pb[keep, 0], 1)
        ay = np.polyfit(n[keep, 1], pb[keep, 1], 1)
        res = np.hypot(np.polyval(ax, n[:, 0]) - pb[:, 0], np.polyval(ay, n[:, 1]) - pb[:, 1])
        mad = np.median(np.abs(res[keep] - np.median(res[keep]))) + 1e-9
        new = res < max(1.0, np.median(res[keep]) + 4 * 1.4826 * mad)
        if (new == keep).all():
            break
        keep = new
    if keep.sum() < 30:
        return {"status": "insufficient", "matches": int(keep.sum())}
    return {"status": "ok", "matches": int(len(pa)), "used": int(keep.sum()),
            "K": [[float(ax[0]), 0.0, float(ax[1])], [0.0, float(ay[0]), float(ay[1])], [0.0, 0.0, 1.0]],
            "residual_px": _stats(res[keep])}


# --- visual comparison -------------------------------------------------------------------------

def comparison_image(raw_l, raw_r, rect_l, rect_r, spacing=40):
    """Analysis aid: raw pair (top) and rectified pair (bottom) with thin neutral horizontal guide lines."""
    top, bottom = np.hstack([raw_l, raw_r]), np.hstack([rect_l, rect_r])
    img = cv2.cvtColor(np.vstack([top, bottom]), cv2.COLOR_GRAY2BGR)
    for y in range(spacing, img.shape[0], spacing):
        cv2.line(img, (0, y), (img.shape[1] - 1, y), (255, 255, 255), 1)
        cv2.line(img, (0, y + 1), (img.shape[1] - 1, y + 1), (0, 0, 0), 1)
    h, w = raw_l.shape[:2]
    for text, (x, y) in (("raw left", (10, 30)), ("raw right", (w + 10, 30)),
                         ("rectified left", (10, h + 30)), ("rectified right", (w + 10, h + 30))):
        cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 1, cv2.LINE_AA)
    return img


# --- offline mode ------------------------------------------------------------------------------

def offline(args):
    import depthai as dai
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = RESULTS_DIR / f"stage_e_offline_{stamp}_{args.label}"
    out_dir.mkdir(parents=True, exist_ok=False)
    first = cv2.imread(str(args.pair[0][0]), cv2.IMREAD_GRAYSCALE)
    h, w = first.shape
    summary = calibration_summary(dai, args.calibration, w, h)
    report = {"timestamp": dt.datetime.now().isoformat(timespec="seconds"), "mode": "offline host rectification",
              "note": "host (OpenCV) rectification of previously captured raw pairs; the device may use a different "
                      "rectified camera matrix and mesh", "calibration": summary, "alphas": {}}
    for alpha in args.alpha:
        info, maps = host_rectification(summary, alpha)
        entry = {"rectification": info, "pairs": []}
        for i, (lp, rp) in enumerate(args.pair):
            raw_l, raw_r = cv2.imread(str(lp), cv2.IMREAD_GRAYSCALE), cv2.imread(str(rp), cv2.IMREAD_GRAYSCALE)
            rect_l = cv2.remap(raw_l, *maps["left"], cv2.INTER_LINEAR, borderValue=0)
            rect_r = cv2.remap(raw_r, *maps["right"], cv2.INTER_LINEAR, borderValue=0)
            fx_rect = info["P1"][0][0]
            pair = {"left": str(lp), "right": str(rp),
                    "raw": vertical_disparity(raw_l, raw_r, summary["left"]["K"][0][0], rectified=False),
                    "rectified": vertical_disparity(rect_l, rect_r, fx_rect, rectified=True)}
            name = f"alpha{alpha:g}_pair{i}"
            cv2.imwrite(str(out_dir / f"{name}_comparison.png"), comparison_image(raw_l, raw_r, rect_l, rect_r))
            pair["comparison_image"] = f"{name}_comparison.png"
            entry["pairs"].append(pair)
        report["alphas"][f"{alpha:g}"] = entry
    (out_dir / "geometry_offline.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved {out_dir}")
    return report


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--pair", nargs=2, type=Path, action="append", required=True, metavar=("LEFT", "RIGHT"))
    p.add_argument("--alpha", type=float, action="append", default=None)
    p.add_argument("--label", default="offline")
    a = p.parse_args(argv)
    a.alpha = a.alpha or [0.0, 1.0]
    for path in [a.calibration] + [x for pr in a.pair for x in pr]:
        if not path.is_file():
            p.error(f"file not found: {path}")
    return a


if __name__ == "__main__":
    offline(parse_args())
    sys.exit(0)

"""Offline analysis of Stage E runs (E1-E5). Reads saved results only; writes a new analysis folder.

    .venv\\Scripts\\python.exe analyse_stage_e.py

For each run and saved group it:
  * re-matches rectified left/right features (same filters as stereo_geometry.vertical_disparity)
    and fits dy = a + b*x + c*y + d*disparity, to separate a constant vertical offset (a), a
    relative roll (b), a vertical scale difference (c) and a depth-dependent term (d)
  * maps signed dy over a 3 x 3 grid (centre against edges)
  * examines every |dy| > 3 px match: local neighbourhood consistency, patch correlation and
    whether nearby matches in the run's other groups agree (persistent = local geometry,
    isolated = likely mismatch)
  * measures black borders directly from the rectified images (zero pixels connected to the edge)
  * fits a pure homography raw -> rectified and compares its residual with the calibrated
    distortion-correction model (tells whether distortion was corrected)
Across runs of the same camera it compares rectified images feature-to-feature (E1 vs E5, E1 vs E3,
E2 vs E4) to measure the actual difference between transformations.
"""

import datetime as dt
import glob
import json
import math
from pathlib import Path

import cv2
import numpy as np

import stereo_geometry as sg

RESULTS = Path(__file__).resolve().parent / "results"
RUNS = {"E1": "E1_A_default", "E2": "E2_B_default", "E3": "E3_A_alpha0", "E4": "E4_B_alpha0", "E5": "E5_A_dc_auto"}


def run_dir(label):
    hits = sorted(RESULTS.glob(f"rectify_*_{label}"))
    if len(hits) != 1:
        raise SystemExit(f"expected one folder for {label}, found {len(hits)}")
    return hits[0]


def load_groups(d):
    out = {}
    for p in sorted((d / "images").glob("group*_raw_left.png")):
        stem = p.name[: -len("_raw_left.png")]
        out[stem] = {k: cv2.imread(str(d / "images" / f"{stem}_{k}.png"), cv2.IMREAD_GRAYSCALE)
                     for k in ("raw_left", "raw_right", "rect_left", "rect_right")}
    return out


def reliable_rect_matches(left, right):
    """Same filter chain as stereo_geometry.vertical_disparity, returning the points."""
    w = left.shape[1]
    pl, pr, _ = sg.match_features(left, right)
    if len(pl) < 8:
        return pl[:0], pr[:0]
    _, inl = cv2.findFundamentalMat(pl, pr, cv2.USAC_MAGSAC, sg.EPIPOLAR_THRESH_PX, 0.999, 10000)
    keep = inl.ravel().astype(bool)
    d = pl[:, 0] - pr[:, 0]
    keep &= (d >= -2.0) & (d <= 0.5 * w)
    return pl[keep], pr[keep]


def dy_model(pl, pr, size):
    w, h = size
    dy = pl[:, 1] - pr[:, 1]
    x, y, disp = (pl[:, 0] - w / 2) / (w / 2), (pl[:, 1] - h / 2) / (h / 2), pl[:, 0] - pr[:, 0]
    A = np.column_stack([np.ones_like(x), x, y, disp])
    coef, *_ = np.linalg.lstsq(A, dy, rcond=None)
    resid = dy - A @ coef
    return {"offset_px": float(coef[0]), "per_half_width_x_px": float(coef[1]), "per_half_height_y_px": float(coef[2]),
            "per_px_disparity": float(coef[3]), "residual_abs_median_px": float(np.median(np.abs(resid))),
            "residual_abs_p95_px": float(np.percentile(np.abs(resid), 95)), "n": int(len(dy))}


def grid_signed(pl, dy, size, n=3):
    w, h = size
    cells = [[[] for _ in range(n)] for _ in range(n)]
    for (x, y), v in zip(pl, dy):
        cells[min(n - 1, int(y * n / h))][min(n - 1, int(x * n / w))].append(v)
    return [[(round(float(np.median(c)), 2), len(c)) if c else (None, 0) for c in row] for row in cells]


def ncc(a, b):
    a, b = a.astype(float) - a.mean(), b.astype(float) - b.mean()
    den = math.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den > 0 else None


def patch(img, x, y, r=10):
    x, y = int(round(x)), int(round(y))
    if x - r < 0 or y - r < 0 or x + r + 1 > img.shape[1] or y + r + 1 > img.shape[0]:
        return None
    return img[y - r:y + r + 1, x - r:x + r + 1]


def outliers(pl, pr, left, right, others, thresh=3.0):
    """Examine matches with |dy| > thresh: neighbours, patch correlation, persistence in other groups."""
    dy = pl[:, 1] - pr[:, 1]
    res = []
    for i in np.flatnonzero(np.abs(dy) > thresh):
        dist = np.hypot(pl[:, 0] - pl[i, 0], pl[:, 1] - pl[i, 1])
        nb = np.argsort(dist)[1:11]
        pa, pb = patch(left, *pl[i]), patch(right, *pr[i])
        pb_aligned = patch(right, pr[i, 0], pl[i, 1])  # same row as the left point: what a correct rectification predicts
        persist = []
        for opl, opr in others:
            near = np.hypot(opl[:, 0] - pl[i, 0], opl[:, 1] - pl[i, 1]) < 6
            if near.any():
                persist.append(float(np.median(opl[near, 1] - opr[near, 1])))
        nb_med = float(np.median(dy[nb]))
        res.append({"left_xy": [round(float(v), 1) for v in pl[i]], "right_xy": [round(float(v), 1) for v in pr[i]],
                    "dy_px": round(float(dy[i]), 2), "disparity_px": round(float(pl[i, 0] - pr[i, 0]), 1),
                    "neighbour_median_dy_px": round(nb_med, 2),
                    "neighbour_distance_px": round(float(np.median(dist[nb])), 1),
                    "patch_ncc_as_matched": None if pa is None or pb is None else round(ncc(pa, pb), 3),
                    "patch_ncc_same_row": None if pa is None or pb_aligned is None else round(ncc(pa, pb_aligned), 3),
                    "other_groups_dy_near_same_point": [round(v, 2) for v in persist],
                    "verdict": ("persistent across groups: local geometry"
                                if len(persist) >= 2 and all(abs(v - dy[i]) < 1.5 for v in persist)
                                else "isolated: likely mismatch" if abs(dy[i] - nb_med) > 2.5
                                else "consistent with neighbours")})
    return res


def border_fraction(img):
    """Zero-valued pixels connected to the image edge (the fill colour is 0)."""
    mask = (img == 0).astype(np.uint8)
    n, labels = cv2.connectedComponents(mask, connectivity=4)
    edge = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))) - {0}
    border = np.isin(labels, list(edge)) & (mask == 1)
    rows, cols = np.flatnonzero(border.any(1)), np.flatnonzero(border.any(0))
    return {"fraction": float(border.mean()),
            "sides_px": {"top": int(border[0].sum()), "bottom": int(border[-1].sum()),
                         "left": int(border[:, 0].sum()), "right": int(border[:, -1].sum())},
            "rows_touched": int(rows.size), "cols_touched": int(cols.size)}


def model_check(raw, rect, K, D, R):
    """Residual of a pure homography raw->rect against the calibrated distortion-correction model."""
    pa, pb, _ = sg.match_features(raw, rect)
    Hm, inl = cv2.findHomography(pa, pb, cv2.LMEDS)
    proj = cv2.perspectiveTransform(pa.reshape(-1, 1, 2), Hm).reshape(-1, 2)
    res_h = np.hypot(*(proj - pb).T)
    fit = sg.fit_rectified_camera(raw, rect, K, D, R)
    r = np.hypot(pa[:, 0] - raw.shape[1] / 2, pa[:, 1] - raw.shape[0] / 2)
    outer = r > np.percentile(r, 75)
    return {"homography_residual_px": {"median": float(np.median(res_h)), "p95": float(np.percentile(res_h, 95)),
                                       "outer_quartile_median": float(np.median(res_h[outer]))},
            "distortion_model_residual_px": fit.get("residual_px"), "matches": int(len(pa))}


def distortion_magnitude(K, D, size):
    """How far the calibrated distortion moves pixels (px), at the image corners and edge midpoints."""
    w, h = size
    pts = np.array([[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1], [0, h / 2], [w - 1, h / 2], [w / 2, 0], [w / 2, h - 1]], float)
    und = cv2.undistortPointsIter(pts.reshape(-1, 1, 2), K, D, None, K,
                                  (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 200, 1e-9)).reshape(-1, 2)
    return {"corners_px": [round(float(v), 1) for v in np.hypot(*(und[:4] - pts[:4]).T)],
            "edge_midpoints_px": [round(float(v), 1) for v in np.hypot(*(und[4:] - pts[4:]).T)]}


def cross_run(a_img, b_img):
    """Feature mapping between two runs' rectified images of the same (static) scene: affine fit and residual."""
    pa, pb, _ = sg.match_features(a_img, b_img)
    M, inl = cv2.estimateAffine2D(pa, pb, method=cv2.LMEDS)
    inl = inl.ravel().astype(bool)
    pred = (M @ np.column_stack([pa, np.ones(len(pa))]).T).T
    res = np.hypot(*(pred[inl] - pb[inl]).T)
    disp = np.hypot(*(pb[inl] - pa[inl]).T)
    return {"matches": int(len(pa)), "inliers": int(inl.sum()), "affine": np.round(M, 5).tolist(),
            "scale_x": float(np.hypot(M[0, 0], M[1, 0])), "scale_y": float(np.hypot(M[0, 1], M[1, 1])),
            "residual_px_median": float(np.median(res)), "residual_px_p95": float(np.percentile(res, 95)),
            "displacement_px_median": float(np.median(disp)), "displacement_px_max": float(disp.max())}


def main():
    import depthai as dai
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RESULTS / f"stage_e_analysis_{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    analysis = {"timestamp": dt.datetime.now().isoformat(timespec="seconds"), "runs": {}, "cross_run": {}}
    imgs = {}
    for key, label in RUNS.items():
        d = run_dir(label)
        groups = load_groups(d)
        imgs[key] = groups
        cal = sg.calibration_summary(dai, d / "calibration_before_run.json", 1280, 800)
        R = {"left": cal["stored_rect_R_left"], "right": cal["stored_rect_R_right"]}
        matches = {s: reliable_rect_matches(g["rect_left"], g["rect_right"]) for s, g in groups.items()}
        entry = {"folder": d.name, "groups": {}}
        for stem, g in groups.items():
            pl, pr = matches[stem]
            others = [matches[o] for o in matches if o != stem]
            entry["groups"][stem] = {
                "dy_model": dy_model(pl, pr, (1280, 800)),
                "signed_dy_grid_3x3": grid_signed(pl, pl[:, 1] - pr[:, 1], (1280, 800)),
                "outliers_over_3px": outliers(pl, pr, g["rect_left"], g["rect_right"], others),
                "black_border": {"left": border_fraction(g["rect_left"]), "right": border_fraction(g["rect_right"])},
            }
        first = next(iter(groups.values()))
        entry["model_check_left"] = model_check(first["raw_left"], first["rect_left"], np.array(cal["left"]["K"]),
                                                np.array(cal["left"]["D"]), R["left"])
        entry["distortion_magnitude_left"] = distortion_magnitude(np.array(cal["left"]["K"]), np.array(cal["left"]["D"]), (1280, 800))
        analysis["runs"][key] = entry
        print(f"{key} analysed ({len(groups)} groups)")
    for a, b in (("E1", "E5"), ("E1", "E3"), ("E2", "E4")):
        ga, gb = next(iter(imgs[a].values())), next(iter(imgs[b].values()))
        analysis["cross_run"][f"{a}_vs_{b}"] = {"raw_left_same_scene": cross_run(ga["raw_left"], gb["raw_left"]),
                                                "rect_left": cross_run(ga["rect_left"], gb["rect_left"]),
                                                "rect_right": cross_run(ga["rect_right"], gb["rect_right"]),
                                                "rect_left_mean_abs_pixel_difference": float(np.mean(np.abs(
                                                    ga["rect_left"].astype(int) - gb["rect_left"].astype(int))))}
    (out / "analysis.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()

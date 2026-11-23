"""Offline epipolar-alignment analysis across Stage E scenes, with candidate software corrections.

Reads saved rectify_stereo.py run folders only (no camera access) and writes a new analysis folder.

    .venv\\Scripts\\python.exe analyse_epipolar.py --run E2_B_default:scene1 --run E6_B_s2_mixed:scene2 ^
        --run E7_B_s2_near:scene2 --fit-on E2_B_default --evaluate-on E6_B_s2_mixed,E7_B_s2_near

  --run LABEL[:SCENE]   a run folder label (or path) and the scene it belongs to; repeatable
  --fit-on / --evaluate-on   fit candidate corrections on some runs, evaluate on others (same camera)
  --crop x0,y0,x1,y1    inclusive pixel indices of a crop to verify on every saved group (both eyes)

Per run: a robust fit of dy = a + b*x + c*y + d*disparity (x, y normalised to -1..1, dy = yL - yR in px),
with 95% intervals from a block bootstrap over 5 x 5 image cells (matches within a cell are not
independent), converted to arcmin / degrees using the run's fitted rectified camera matrix; a 5 x 5 map
of signed dy with match counts and coverage flags (lower third, corners); dy by disparity bin.
Across scenes of one camera: are a (offset), b (roll) and c (vertical scale) consistent?
Corrections are only evaluated on saved images here: they are never applied to a camera stream.
"""

import argparse
import datetime as dt
import json
import math
from pathlib import Path

import cv2
import numpy as np

import analyse_stage_e as ase

RESULTS = Path(__file__).resolve().parent / "results"
W, H = 1280, 800
GRID = 5
MIN_CELL = 10                 # matches needed before a 5 x 5 cell counts as verified
TOL = {"offset_px": 0.25, "roll_deg": 0.02, "vscale_pct": 0.05}   # pre-specified consistency tolerances
CANDIDATES = {"C1_shift": (0,), "C2_shift_roll": (0, 1), "C3_shift_roll_vscale": (0, 1, 2)}


def resolve(spec):
    p = Path(spec)
    if p.is_dir():
        return p
    hits = sorted(RESULTS.glob(f"rectify_*_{spec}"))
    if len(hits) != 1:
        raise SystemExit(f"run {spec!r}: expected one folder, found {len(hits)}")
    return hits[0]


def camera_of(folder):
    for part in folder.name.split("_"):
        if len(part) == 18 and all(ch in "0123456789ABCDEF" for ch in part):
            return part
    raise SystemExit(f"no device id in {folder.name}")


def features(pl, pr):
    x, y = (pl[:, 0] - W / 2) / (W / 2), (pl[:, 1] - H / 2) / (H / 2)
    return np.column_stack([np.ones_like(x), x, y, pl[:, 0] - pr[:, 0]])


def robust_fit(A, dy, cols=(0, 1, 2, 3)):
    """Least squares with iterative trimming (3.5 x MAD) so isolated mismatches do not steer the fit."""
    cols = list(cols)
    keep = np.ones(len(dy), bool)
    for _ in range(10):
        coef, *_ = np.linalg.lstsq(A[keep][:, cols], dy[keep], rcond=None)
        r = dy - A[:, cols] @ coef
        mad = 1.4826 * np.median(np.abs(r[keep] - np.median(r[keep]))) + 1e-9
        new = np.abs(r - np.median(r[keep])) <= max(3.5 * mad, 0.5)
        if (new == keep).all():
            break
        keep = new
    full = np.zeros(4)
    full[cols] = coef
    return full, keep


def cells_of(pl):
    return (np.minimum(GRID - 1, (pl[:, 1] * GRID / H).astype(int)) * GRID +
            np.minimum(GRID - 1, (pl[:, 0] * GRID / W).astype(int)))


def block_bootstrap(A, dy, cell, n=300, seed=7):
    rng = np.random.default_rng(seed)
    ids = np.unique(cell)
    out = []
    for _ in range(n):
        pick = rng.choice(ids, size=len(ids), replace=True)
        idx = np.concatenate([np.flatnonzero(cell == c) for c in pick])
        out.append(robust_fit(A[idx], dy[idx])[0])
    lo, hi = np.percentile(np.array(out), [2.5, 97.5], axis=0)
    return lo, hi


def to_angles(coef, K):
    fx, fy = K[0][0], K[1][1]
    return {"offset_arcmin": math.degrees(math.atan(coef[0] / fy)) * 60,
            "roll_deg": math.degrees(math.atan(coef[1] / (W / 2) * fx / fy)),
            "vscale_pct": coef[2] / (H / 2) * 100}


def grid_map(pl, dy):
    cell = cells_of(pl)
    out = []
    for r in range(GRID):
        row = []
        for c in range(GRID):
            v = dy[cell == r * GRID + c]
            row.append({"n": int(v.size), "signed_median_px": round(float(np.median(v)), 2) if v.size else None,
                        "abs_p95_px": round(float(np.percentile(np.abs(v), 95)), 2) if v.size else None,
                        "verified": bool(v.size >= MIN_CELL)})
        out.append(row)
    return out


def coverage(grid, pl):
    lower = pl[:, 1] > 2 * H / 3
    corners = [grid[0][0], grid[0][-1], grid[-1][0], grid[-1][-1]]
    return {"cells_verified": sum(c["verified"] for row in grid for c in row), "cells_total": GRID * GRID,
            "lower_third_matches": int(lower.sum()),
            "lower_third_cells_verified": sum(c["verified"] for row in grid[GRID * 2 // 3:] for c in row),
            "corners_verified": [c["verified"] for c in corners],
            "verdict": "whole image covered" if all(c["verified"] for row in grid for c in row)
                       else "partial: unverified cells listed in grid"}


def disparity_bins(pl, pr, dy):
    d = pl[:, 0] - pr[:, 0]
    edges = np.percentile(d, [0, 33, 67, 100])
    out = []
    for lo, hi in zip(edges, edges[1:]):
        m = (d >= lo) & (d <= hi)
        out.append({"disparity_px": [round(float(lo), 1), round(float(hi), 1)], "n": int(m.sum()),
                    "signed_median_dy_px": round(float(np.median(dy[m])), 3) if m.any() else None})
    return out


def crop_check(groups, crop):
    x0, y0, x1, y1 = crop
    res = []
    for stem, g in groups.items():
        for eye in ("rect_left", "rect_right"):
            b = ase_border(g[eye])
            res.append({"group": stem, "eye": eye, "crop_shape_wh": [x1 - x0 + 1, y1 - y0 + 1],
                        "border_px_inside_crop": int(b[y0:y1 + 1, x0:x1 + 1].sum())})
    return {"crop_inclusive": list(crop), "numpy_slice": f"img[{y0}:{y1 + 1}, {x0}:{x1 + 1}]",
            "all_border_free": all(r["border_px_inside_crop"] == 0 for r in res), "per_image": res}


def ase_border(img):
    m = (img == 0).astype(np.uint8)
    n, lab = cv2.connectedComponents(m, connectivity=4)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    return np.isin(lab, list(edge)) & (m == 1)


def load_run(spec, scene):
    folder = resolve(spec)
    geo = json.loads((folder / "geometry.json").read_text(encoding="utf-8"))
    K = geo["groups"][0]["device_rectified_camera_left"]["K"]
    groups = ase.load_groups(folder)
    pls, prs = [], []
    for g in groups.values():
        pl, pr = ase.reliable_rect_matches(g["rect_left"], g["rect_right"])
        pls.append(pl)
        prs.append(pr)
    return {"label": spec, "scene": scene, "folder": folder, "camera": camera_of(folder), "K": K, "groups": groups,
            "pl": np.vstack(pls), "pr": np.vstack(prs), "per_group": list(zip(pls, prs))}


def analyse_run(run, crop=None):
    pl, pr = run["pl"], run["pr"]
    dy = pl[:, 1] - pr[:, 1]
    A = features(pl, pr)
    coef, keep = robust_fit(A, dy)
    lo, hi = block_bootstrap(A[keep], dy[keep], cells_of(pl)[keep])
    resid = dy - A @ coef
    grid = grid_map(pl, dy)
    per_group = [robust_fit(features(a, b), a[:, 1] - b[:, 1])[0].tolist() for a, b in run["per_group"] if len(a) >= 30]
    out = {"folder": run["folder"].name, "scene": run["scene"], "camera": run["camera"],
           "rectified_K_left": run["K"], "matches": int(len(dy)), "used_in_fit": int(keep.sum()),
           "abs_dy_px": {"median": float(np.median(np.abs(dy))), "p95": float(np.percentile(np.abs(dy), 95)),
                         "max": float(np.abs(dy).max())},
           "model_px": dict(zip(("offset", "x_term", "y_term", "per_px_disparity"), map(float, coef))),
           "model_ci95_px": {k: [float(lo[i]), float(hi[i])] for i, k in enumerate(("offset", "x_term", "y_term", "per_px_disparity"))},
           "model_angles": to_angles(coef, run["K"]),
           "model_angles_ci95": {k: sorted([to_angles(lo, run["K"])[k], to_angles(hi, run["K"])[k]]) for k in ("offset_arcmin", "roll_deg", "vscale_pct")},
           "per_group_offset_px_range": [min(p[0] for p in per_group), max(p[0] for p in per_group)] if per_group else None,
           "residual_after_model_px": {"median": float(np.median(np.abs(resid[keep]))), "p95": float(np.percentile(np.abs(resid[keep]), 95))},
           "grid_5x5": grid, "coverage": coverage(grid, pl), "disparity_bins": disparity_bins(pl, pr, dy)}
    if crop:
        out["crop_check"] = crop_check(run["groups"], crop)
    return out


def compare_scenes(results):
    """Per camera: are offset, roll and vertical scale consistent across scenes (pre-specified tolerances)?"""
    out = {}
    by_cam = {}
    for r in results:
        by_cam.setdefault(r["camera"], []).append(r)
    for cam, rs in by_cam.items():
        pairs = []
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                if a["scene"] == b["scene"]:
                    continue
                entry = {"runs": [a["folder"], b["folder"]], "scenes": [a["scene"], b["scene"]]}
                for key, tol_key, src in (("offset_px", "offset_px", None), ("roll_deg", "roll_deg", "model_angles"),
                                          ("vscale_pct", "vscale_pct", "model_angles")):
                    if src:
                        va, vb = a[src][key], b[src][key]
                        ha = abs(a["model_angles_ci95"][key][1] - a["model_angles_ci95"][key][0]) / 2
                        hb = abs(b["model_angles_ci95"][key][1] - b["model_angles_ci95"][key][0]) / 2
                    else:
                        va, vb = a["model_px"]["offset"], b["model_px"]["offset"]
                        ha = (a["model_ci95_px"]["offset"][1] - a["model_ci95_px"]["offset"][0]) / 2
                        hb = (b["model_ci95_px"]["offset"][1] - b["model_ci95_px"]["offset"][0]) / 2
                    allowed = max(TOL[tol_key], math.hypot(ha, hb))
                    entry[key] = {"a": va, "b": vb, "difference": vb - va, "allowed": allowed,
                                  "consistent": abs(vb - va) <= allowed}
                entry["all_consistent"] = all(entry[k]["consistent"] for k in ("offset_px", "roll_deg", "vscale_pct"))
                pairs.append(entry)
        out[cam] = pairs
    return out


def region_stats(pl, dy):
    lower = pl[:, 1] > 2 * H / 3
    corner = (((pl[:, 0] < W / GRID) | (pl[:, 0] > W * (GRID - 1) / GRID)) &
              ((pl[:, 1] < H / GRID) | (pl[:, 1] > H * (GRID - 1) / GRID)))
    upper_left = (pl[:, 0] < W / 2.5) & (pl[:, 1] < H / 3)

    def s(m):
        v = np.abs(dy[m])
        return None if v.size == 0 else {"n": int(v.size), "median": float(np.median(v)), "p95": float(np.percentile(v, 95))}
    return {"all": s(np.ones(len(dy), bool)), "lower_third": s(lower), "corners": s(corner), "upper_left": s(upper_left),
            "fraction_over_1px": float(np.mean(np.abs(dy) > 1.0))}


def correction_map(coef):
    """Right-eye remap that moves content down by f(x, y) = a + b*xn + c*yn (dy' = dy - f)."""
    xs, ys = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    f = coef[0] + coef[1] * (xs - W / 2) / (W / 2) + coef[2] * (ys - H / 2) / (H / 2)
    return xs, (ys - f).astype(np.float32)


def evaluate_corrections(fit_runs, eval_runs):
    pl = np.vstack([r["pl"] for r in fit_runs])
    pr = np.vstack([r["pr"] for r in fit_runs])
    A_fit, dy_fit = features(pl, pr), pl[:, 1] - pr[:, 1]
    out = {"fit_on": [r["folder"].name for r in fit_runs], "evaluate_on": [r["folder"].name for r in eval_runs],
           "note": "f(x, y) is applied to the right eye only in this evaluation; for display it could be split "
                   "half to each eye (+f/2 left, -f/2 right) to keep framing symmetric. Not applied to any stream.",
           "candidates": {}}
    for name, cols in CANDIDATES.items():
        coef, _ = robust_fit(A_fit, dy_fit, cols)
        entry = {"coefficients_px": dict(zip(("offset", "x_term", "y_term"), map(float, coef[:3])))}
        for r in eval_runs:
            dy = r["pl"][:, 1] - r["pr"][:, 1]
            after = dy - features(r["pl"], r["pr"])[:, :3] @ coef[:3]
            ev = {"before": region_stats(r["pl"], dy), "after": region_stats(r["pl"], after)}
            g = next(iter(r["groups"].values()))
            mx, my = correction_map(coef)
            right_corr = cv2.remap(g["rect_right"], mx, my, cv2.INTER_LINEAR, borderValue=0)
            ipl, ipr = ase.reliable_rect_matches(g["rect_left"], right_corr)
            ev["image_level_check_first_group"] = {"abs_dy_median_px": float(np.median(np.abs(ipl[:, 1] - ipr[:, 1]))) if len(ipl) else None,
                                                   "matches": int(len(ipl))}
            entry[r["folder"].name] = ev
        out["candidates"][name] = entry
    none = {r["folder"].name: region_stats(r["pl"], r["pl"][:, 1] - r["pr"][:, 1]) for r in eval_runs}
    out["candidates"]["C0_none"] = none
    return out


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", action="append", required=True, metavar="LABEL[:SCENE]")
    p.add_argument("--fit-on", default="")
    p.add_argument("--evaluate-on", default="")
    p.add_argument("--crop", default=None, help="x0,y0,x1,y1 inclusive; checked on runs of the camera given by --crop-camera")
    p.add_argument("--crop-camera", default="19443010B14C872F00")
    p.add_argument("--out", type=Path, default=None, help="output folder (default: results/epipolar_analysis_<stamp>)")
    a = p.parse_args(argv)
    if a.crop:
        a.crop = tuple(int(v) for v in a.crop.split(","))
        if len(a.crop) != 4 or not (0 <= a.crop[0] < a.crop[2] < W and 0 <= a.crop[1] < a.crop[3] < H):
            p.error("--crop must be x0,y0,x1,y1 inclusive inside 1280 x 800")
    return a


def main(argv=None):
    args = parse_args(argv)
    runs = []
    for spec in args.run:
        label, sep, scene = spec.rpartition(":")
        if not sep or len(label) == 1 or "\\" in scene or "/" in scene:   # no scene, or the colon belonged to a drive letter
            label, scene = spec, ""
        runs.append(load_run(label, scene or "unspecified"))
        print(f"loaded {label} ({len(runs[-1]['groups'])} groups, {len(runs[-1]['pl'])} matches)")
    results = [analyse_run(r, args.crop if r["camera"] == args.crop_camera else None) for r in runs]
    report = {"timestamp": dt.datetime.now().isoformat(timespec="seconds"), "tolerances": TOL, "min_matches_per_cell": MIN_CELL,
              "runs": results, "scene_comparison": compare_scenes(results)}
    by_label = {r["label"]: r for r in runs}
    if args.fit_on and args.evaluate_on:
        fit = [by_label[x] for x in args.fit_on.split(",")]
        ev = [by_label[x] for x in args.evaluate_on.split(",")]
        if len({r["camera"] for r in fit + ev}) != 1:
            raise SystemExit("--fit-on and --evaluate-on must be runs of the same camera")
        report["corrections"] = evaluate_corrections(fit, ev)
    out = args.out or RESULTS / f"epipolar_analysis_{dt.datetime.now():%Y%m%d_%H%M%S}"
    out.mkdir(parents=True, exist_ok=False)
    (out / "analysis.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    for r in results:
        m, a = r["model_px"], r["model_angles"]
        print(f"{r['folder'][-30:]:30s} [{r['scene']}] |dy| med {r['abs_dy_px']['median']:.2f} p95 {r['abs_dy_px']['p95']:.2f} | "
              f"offset {m['offset']:+.2f} px ({a['offset_arcmin']:+.1f}') CI {np.round(r['model_ci95_px']['offset'], 2).tolist()} | "
              f"roll {a['roll_deg']:+.3f} deg | vscale {a['vscale_pct']:+.3f}% | coverage {r['coverage']['cells_verified']}/25, "
              f"lower third cells {r['coverage']['lower_third_cells_verified']}, corners {r['coverage']['corners_verified']}"
              + (f" | crop border-free {r['crop_check']['all_border_free']}" if "crop_check" in r else ""))
    for cam, pairs in report["scene_comparison"].items():
        for e in pairs:
            print(f"compare {cam[-6:]} {e['scenes']}: offset diff {e['offset_px']['difference']:+.2f} (allowed {e['offset_px']['allowed']:.2f}) "
                  f"roll diff {e['roll_deg']['difference']:+.3f} (allowed {e['roll_deg']['allowed']:.3f}) -> all consistent {e['all_consistent']}")
    if "corrections" in report:
        for name, c in report["corrections"]["candidates"].items():
            for run_name, ev in c.items():
                if isinstance(ev, dict) and "after" in ev:
                    print(f"{name:22s} on {run_name[-28:]}: |dy| median {ev['before']['all']['median']:.2f} -> {ev['after']['all']['median']:.2f}, "
                          f"p95 {ev['before']['all']['p95']:.2f} -> {ev['after']['all']['p95']:.2f} | image-level {ev['image_level_check_first_group']['abs_dy_median_px']}")
    print(f"Saved {out}")
    return report


if __name__ == "__main__":
    main()

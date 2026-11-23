"""Physical field-of-view coverage check with printed ArUco markers (offline; reads saved run images).

1. Generate markers to print (no camera access):
       .venv\\Scripts\\python.exe coverage_check.py generate --ids 0-7 --marker-mm 140
2. Place them at the boundaries of the area the camera must show (e.g. corners of the construction
   area, robot base, block storage), capture with rectify_stereo.py in the approved configuration,
   then analyse the saved rectified images:
       .venv\\Scripts\\python.exe coverage_check.py analyse --run E10_B_coverage --expect-ids 0-7

For every expected marker and saved group: found in the left and right rectified eyes, centre in
pixels and degrees from the optical axis (fitted rectified camera matrix), and the margin to the
nearest edge of the displayed frame (the crop for Camera A, if given). Markers are a test aid only
and must be removed before any participant session.
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
DICTIONARY = cv2.aruco.DICT_4X4_50


def parse_ids(text):
    ids = set()
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        ids.update(range(int(lo), int(hi or lo) + 1))
    if not ids or min(ids) < 0 or max(ids) > 49:
        raise argparse.ArgumentTypeError("ids must be within 0-49")
    return sorted(ids)


def generate(args):
    d = cv2.aruco.getPredefinedDictionary(DICTIONARY)
    px = int(round(args.marker_mm / 25.4 * args.dpi))
    margin = px // 6                      # quiet zone of one marker cell (4x4 code + border = 6 cells)
    page_mm = (px + 2 * margin) / args.dpi * 25.4
    if page_mm > 190:                     # leaves >= 10 mm each side on A4 portrait (printer margins)
        raise SystemExit(f"page would be {page_mm:.0f} mm wide; use --marker-mm <= 140 for A4 portrait")
    out = RESULTS / f"coverage_markers_{dt.datetime.now():%Y%m%d_%H%M%S}_{args.marker_mm}mm"
    out.mkdir(parents=True, exist_ok=False)
    for i in args.ids:
        m = cv2.aruco.generateImageMarker(d, i, px)
        page = np.full((px + 2 * margin + 80, px + 2 * margin), 255, np.uint8)
        page[margin:margin + px, margin:margin + px] = m
        cv2.putText(page, f"ID {i}  |  {args.marker_mm} mm square  |  print at 100% ({args.dpi} dpi)",
                    (margin, px + margin + 50), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 0, 2, cv2.LINE_AA)
        cv2.imwrite(str(out / f"aruco4x4_id{i:02d}_{args.marker_mm}mm.png"), page)
    (out / "README.txt").write_text(
        f"ArUco DICT_4X4_50 markers {args.ids}, {args.marker_mm} mm black square at {args.dpi} dpi.\n"
        "Print at 100% scale, measure the printed square, mount flat. Test aid only: remove before participant sessions.\n",
        encoding="utf-8")
    print(f"Saved {len(args.ids)} markers to {out}")


def detect(img):
    det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(DICTIONARY), cv2.aruco.DetectorParameters())
    corners, ids, _ = det.detectMarkers(img)
    return {} if ids is None else {int(i): c.reshape(4, 2) for i, c in zip(ids.ravel(), corners)}


def marker_report(corners, K, bounds):
    x0, y0, x1, y1 = bounds
    fx, fy, cx, cy = K[0][0], K[1][1], K[0][2], K[1][2]
    c = corners.mean(axis=0)
    margin_px = float(min(corners[:, 0].min() - x0, x1 - corners[:, 0].max(), corners[:, 1].min() - y0, y1 - corners[:, 1].max()))

    def ang(u, f, c0):
        return math.degrees(math.atan((u - c0) / f))
    edge_deg = min(ang(corners[:, 0].min(), fx, cx) - ang(x0, fx, cx), ang(x1, fx, cx) - ang(corners[:, 0].max(), fx, cx),
                   ang(corners[:, 1].min(), fy, cy) - ang(y0, fy, cy), ang(y1, fy, cy) - ang(corners[:, 1].max(), fy, cy))
    return {"centre_px": [round(float(v), 1) for v in c],
            "centre_deg": [round(ang(c[0], fx, cx), 2), round(ang(c[1], fy, cy), 2)],
            "margin_to_displayed_edge_px": round(margin_px, 1), "margin_to_displayed_edge_deg": round(edge_deg, 2)}


def analyse(args):
    folder = ase.run_dir(args.run) if not Path(args.run).is_dir() else Path(args.run)
    geo = json.loads((folder / "geometry.json").read_text(encoding="utf-8"))
    K = geo["groups"][0]["device_rectified_camera_left"]["K"]
    bounds = args.crop or (0, 0, 1279, 799)
    groups = ase.load_groups(folder)
    per_group, summary = {}, {i: {"left": 0, "right": 0, "within_margin": 0} for i in args.expect_ids}
    for stem, g in groups.items():
        entry = {}
        for eye in ("rect_left", "rect_right"):
            found = detect(g[eye])
            entry[eye] = {}
            for i in args.expect_ids:
                if i in found:
                    rep = marker_report(found[i], K, bounds)
                    entry[eye][i] = rep
                    summary[i]["left" if eye == "rect_left" else "right"] += 1
                else:
                    entry[eye][i] = None
            entry[eye]["unexpected_ids"] = sorted(set(found) - set(args.expect_ids))
        for i in args.expect_ids:
            l, r = entry["rect_left"][i], entry["rect_right"][i]
            if l and r and min(l["margin_to_displayed_edge_deg"], r["margin_to_displayed_edge_deg"]) >= args.min_margin_deg:
                summary[i]["within_margin"] += 1
        per_group[stem] = entry
    n = len(groups)
    status = {i: ("covered with margin" if s["within_margin"] == n else
                  "visible but near the displayed edge" if s["left"] == n and s["right"] == n else
                  "missing or intermittent") for i, s in summary.items()}
    report = {"timestamp": dt.datetime.now().isoformat(timespec="seconds"), "run": folder.name, "groups": n,
              "rectified_K_left": K, "displayed_bounds_inclusive": list(bounds), "min_margin_deg": args.min_margin_deg,
              "expected_ids": args.expect_ids, "per_marker": {i: {**summary[i], "status": status[i]} for i in args.expect_ids},
              "all_covered_with_margin": all(v == "covered with margin" for v in status.values()), "per_group": per_group}
    out = args.out or RESULTS / f"coverage_{dt.datetime.now():%Y%m%d_%H%M%S}_{folder.name.split('_', 4)[-1]}"
    out.mkdir(parents=True, exist_ok=False)
    (out / "coverage.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    first = next(iter(per_group.values()))
    for i in args.expect_ids:
        l = first["rect_left"][i]
        print(f"marker {i}: {status[i]:38s} | left {summary[i]['left']}/{n} right {summary[i]['right']}/{n}"
              + (f" | centre {l['centre_deg']} deg, margin {l['margin_to_displayed_edge_deg']} deg" if l else ""))
    print(f"ALL COVERED WITH MARGIN: {report['all_covered_with_margin']}  ({out})")
    return report


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--ids", type=parse_ids, default=parse_ids("0-7"))
    g.add_argument("--marker-mm", type=int, default=140, help="black square size; 140 mm fits A4 portrait")
    g.add_argument("--dpi", type=int, default=150)
    a = sub.add_parser("analyse")
    a.add_argument("--run", required=True)
    a.add_argument("--expect-ids", type=parse_ids, required=True)
    a.add_argument("--min-margin-deg", type=float, default=2.0)
    a.add_argument("--crop", default=None, help="x0,y0,x1,y1 inclusive displayed area (Camera A)")
    a.add_argument("--out", type=Path, default=None, help="output folder (default: results/coverage_<stamp>_<label>)")
    args = p.parse_args(argv)
    if getattr(args, "crop", None):
        args.crop = tuple(int(v) for v in args.crop.split(","))
    return args


if __name__ == "__main__":
    a = parse_args()
    generate(a) if a.cmd == "generate" else analyse(a)

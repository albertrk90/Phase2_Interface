"""Stage E: raw and rectified stereo capture from one OAK PoE camera, with geometry analysis (DepthAI v3).

Local capture only. Uses the Stage B/C safeguards from capture_stereo.py: verified
device-ID selection, native-mode check, IR dot projector and flood light set to 0
(acknowledged before and after start), AutoCalibrationMode.OFF confirmed before the
pipeline starts (a StereoDepth pipeline is exactly what automatic calibration targets),
and calibration compared by content in-session and through a fresh read-only
connection after shutdown.

Pipeline: CAM_B / CAM_C OV9282 at native 1280 x 800 GRAY8 (no undistortion, no resize)
-> StereoDepth (rectification on, distortion correction set explicitly, border fill 0,
optional alpha). Four outputs go to the host: syncedLeft / syncedRight (the raw frames
StereoDepth rectified) and rectifiedLeft / rectifiedRight. A group is formed only when
all four carry the same sequence number, so raw and rectified images always come from
the same capture instant. Depth and disparity outputs are not used or sent.

After shutdown, saved groups are analysed on the host (stereo_geometry.py): residual
vertical disparity (raw and rectified), the rectified camera matrix the device used
(fitted from raw <-> rectified matches of the same frame), valid image area, black
borders and effective field of view. Guide-line comparison images are analysis aids,
never participant material.

--setup-preview: after every pre-start safeguard has passed and the pipeline is running,
a local window shows the live rectified left/right pair (scaled copy), with a toggleable
5 x 5 grid matching analyse_epipolar.py, a texture-point count per cell, optional crop
outline, camera identity, measured frame rate and instructions. It reads from the same
four-stream source the capture uses, so rectification, framing and pairing are unchanged.
Overlays exist only on the display copy; preview groups are never saved.
  Space   close the preview and run the normal capture (warm-up, groups, saving, checks)
  G       toggle grid, counts and crop outline
  Q / Esc / closing the window   cancel: no capture; RESULT CANCELLED (exit code 3)

    .venv\\Scripts\\python.exe rectify_stereo.py --expect 169.254.1.222=19443010B14C872F00 ^
        --baseline-user <user.json> --baseline-factory <factory.json> --label E1_A_default
"""

import argparse
import csv
import datetime as dt
import json
import logging
import os
import platform
import re
import socket
import sys
import time
import traceback
from pathlib import Path

import calibration_check as cc
import capture_stereo as cs
import discover_cameras as dc
import stereo_geometry as sg

log = logging.getLogger("rectify")

STREAMS = ("raw_left", "raw_right", "rect_left", "rect_right")
GRID = 5            # must match analyse_epipolar.GRID
CANCELLED = 3       # exit code when the setup preview is cancelled
CSV_FIELDS = ("group_index", "host_elapsed_s", "seq", "raw_left_ts_device_s", "raw_right_ts_device_s",
              "rect_left_ts_device_s", "rect_right_ts_device_s", "raw_lr_diff_ms", "rect_vs_raw_left_ms",
              "rect_vs_raw_right_ms", "raw_size", "rect_size", "latency_ms", "exposure_us", "iso", "saved")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--expect", required=True, metavar="IP=DEVICE_ID")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=800)
    p.add_argument("--fps", type=float, default=5.0)
    p.add_argument("--groups", type=int, default=45, help="raw+rectified groups to collect (1-600)")
    p.add_argument("--warmup-groups", type=int, default=30, help="groups before saving (auto-exposure settling; 6 s at 5 fps)")
    p.add_argument("--save-groups", type=int, default=5, help="groups saved and analysed (1-20)")
    p.add_argument("--alpha", type=float, default=None, help="StereoDepth alpha scaling 0..1; default: DepthAI default (unset)")
    p.add_argument("--distortion-correction", choices=("on", "off", "auto"), default="on",
                   help="on/off set it explicitly so both cameras use the same rule; auto leaves DepthAI's default "
                        "(mesh with distortion correction above 85 deg FOV, otherwise 3x3 homography)")
    p.add_argument("--max-seconds", type=float, default=60.0)
    p.add_argument("--frame-timeout-s", type=float, default=5.0)
    p.add_argument("--queue-size", type=int, default=8)
    p.add_argument("--label", default="")
    p.add_argument("--allow-non-isolated", action="store_true")
    p.add_argument("--baseline-user", type=Path)
    p.add_argument("--baseline-factory", type=Path)
    p.add_argument("--post-verify-wait-s", type=float, default=60.0)
    p.add_argument("--connect-timeout-ms", type=int, default=15000)
    p.add_argument("--setup-preview", action="store_true", help="live rectified preview before capture (Space start, Q/Esc cancel)")
    p.add_argument("--setup-max-minutes", type=float, default=20.0, help="preview time limit before it cancels (1-60)")
    p.add_argument("--preview-scale", type=float, default=0.5, help="display scale of the side-by-side preview (0.25-1)")
    p.add_argument("--preview-crop", default=None, help="x0,y0,x1,y1 inclusive crop outline shown in the preview (display only)")
    a = p.parse_args(argv)
    a.expect = dc.parse_expectation(p, a.expect)
    a.post_verify_poll_s = 2.0
    a.preview = False
    for path in (a.baseline_user, a.baseline_factory):
        if path is not None and not path.is_file():
            p.error(f"baseline file not found: {path}")
    checks = [
        (a.width == 1280 and a.height == 800, "Stage E uses the native 1280 x 800 mode only"),
        (1.0 <= a.fps <= 10.0, "--fps must be 1-10 (four streams per camera)"),
        (1 <= a.groups <= 600, "--groups must be 1-600"),
        (0 <= a.warmup_groups < a.groups, "--warmup-groups must be 0 to --groups minus 1"),
        (1 <= a.save_groups <= 20 and a.save_groups <= a.groups - a.warmup_groups, "--save-groups must be 1-20 and fit after warm-up"),
        (a.alpha is None or 0.0 <= a.alpha <= 1.0, "--alpha must be 0..1"),
        (1.0 <= a.max_seconds <= 600.0 and a.groups / a.fps <= a.max_seconds, "--max-seconds too short for --groups at --fps"),
        (0.5 <= a.frame_timeout_s <= 30.0, "--frame-timeout-s must be 0.5-30"),
        (1 <= a.queue_size <= 64, "--queue-size must be 1-64"),
        (5.0 <= a.post_verify_wait_s <= 180.0, "--post-verify-wait-s must be 5-180"),
        (re.fullmatch(r"[A-Za-z0-9_\-]{0,32}", a.label) is not None, "--label: up to 32 letters, digits, _ or -"),
        (1.0 <= a.setup_max_minutes <= 60.0, "--setup-max-minutes must be 1-60"),
        (0.25 <= a.preview_scale <= 1.0, "--preview-scale must be 0.25-1"),
    ]
    for ok, message in checks:
        if not ok:
            p.error(message)
    if a.preview_crop:
        try:
            a.preview_crop = tuple(int(v) for v in a.preview_crop.split(","))
        except ValueError:
            p.error("--preview-crop must be x0,y0,x1,y1")
        x0, y0, x1, y1 = a.preview_crop if len(a.preview_crop) == 4 else (0, 0, -1, -1)
        if not (0 <= x0 < x1 < a.width and 0 <= y0 < y1 < a.height):
            p.error("--preview-crop must be x0,y0,x1,y1 inclusive inside 1280 x 800")
    a.setup_max_s = a.setup_max_minutes * 60
    return a


def save_indices(args):
    first, last = args.warmup_groups, args.groups - 1
    if args.save_groups == 1:
        return {last}
    step = (last - first) / (args.save_groups - 1)
    return {round(first + i * step) for i in range(args.save_groups)}


def build_pipeline(dai, device, args, report):
    pipeline = dai.Pipeline(device)
    pipeline.setAutoCalibrationMode(dai.Pipeline.AutoCalibrationMode.OFF)
    mode = pipeline.getAutoCalibrationMode()
    report["auto_calibration_mode"] = str(mode)
    if mode != dai.Pipeline.AutoCalibrationMode.OFF:
        raise cs.SafetyAbort(f"AutoCalibrationMode is {mode}, refusing to start (it may flash calibration)")
    outs = {}
    for label, sock in ((cs.LEFT, dai.CameraBoardSocket.CAM_B), (cs.RIGHT, dai.CameraBoardSocket.CAM_C)):
        cam = pipeline.create(dai.node.Camera).build(sock, sensorResolution=(args.width, args.height), sensorFps=args.fps)
        outs[label] = cam.requestOutput((args.width, args.height), type=dai.ImgFrame.Type.GRAY8,
                                        fps=args.fps, enableUndistortion=False)
    stereo = pipeline.create(dai.node.StereoDepth)
    outs[cs.LEFT].link(stereo.left)
    outs[cs.RIGHT].link(stereo.right)
    stereo.setInputResolution(args.width, args.height)
    stereo.setRectification(True)
    if args.distortion_correction != "auto":
        stereo.enableDistortionCorrection(args.distortion_correction == "on")
    stereo.setRectificationUseSpecTranslation(False)
    stereo.setRectifyEdgeFillColor(0)
    if args.alpha is not None:
        stereo.setAlphaScaling(args.alpha)
    report["pipeline"] = {
        "cameras": "CAM_B (left) / CAM_C (right) Camera.requestOutput GRAY8 1280x800, enableUndistortion=False",
        "fps": args.fps,
        "stereo": {"rectification": True, "distortion_correction": args.distortion_correction,
                   "rectification_use_spec_translation": False, "edge_fill_color": 0,
                   "alpha_scaling": args.alpha if args.alpha is not None else "DepthAI default (unset)",
                   "outputs_used": ["syncedLeft", "syncedRight", "rectifiedLeft", "rectifiedRight"],
                   "depth_disparity": "not used, not sent"},
        "grouping": "host, equal sequence number across all four streams",
        "host_queue": {"maxSize": args.queue_size, "blocking": False},
    }
    sources = {"raw_left": stereo.syncedLeft, "raw_right": stereo.syncedRight,
               "rect_left": stereo.rectifiedLeft, "rect_right": stereo.rectifiedRight}
    return pipeline, {k: o.createOutputQueue(maxSize=args.queue_size, blocking=False) for k, o in sources.items()}


def group_source(queues, args, report, now):
    """Yields ({stream: frame}, meta) when all four streams have the same sequence number; returns a stop reason."""
    pending = {k: {} for k in STREAMS}
    gs = report["grouping"] = {"received": {k: 0 for k in STREAMS}, "unmatched": {k: 0 for k in STREAMS},
                               "seqs": {k: [] for k in STREAMS}}
    margin = max(4, args.queue_size)
    last_rx = time.monotonic()
    try:
        while True:
            got = False
            for k in STREAMS:
                msg = queues[k].tryGet()
                if msg is not None:
                    got, last_rx = True, time.monotonic()
                    pending[k][msg.getSequenceNum()] = (msg, cs.seconds(now()))
                    gs["received"][k] += 1
                    gs["seqs"][k].append(msg.getSequenceNum())
            common = set.intersection(*(set(pending[k]) for k in STREAMS))
            for seq in sorted(common):
                items = {k: pending[k].pop(seq) for k in STREAMS}
                yield {k: v[0] for k, v in items.items()}, {"rx_clock_s": max(v[1] for v in items.values())}
            newest = max((gs["seqs"][k][-1] for k in STREAMS if gs["seqs"][k]), default=None)
            if newest is not None:
                for k in STREAMS:
                    for seq in [s for s in pending[k] if s < newest - margin]:
                        pending[k].pop(seq)
                        gs["unmatched"][k] += 1
            if not got:
                if time.monotonic() - last_rx > args.frame_timeout_s:
                    report["errors"].append(f"no frame on any stream within {args.frame_timeout_s} s")
                    return "frame_timeout"
                time.sleep(0.002)
    finally:
        gs["pending_at_stop"] = {k: len(pending[k]) for k in STREAMS}


class CvUI:
    """Thin OpenCV window wrapper (replaced by a scripted fake in offline tests)."""
    window = "Stage E setup preview (rectified)"

    def show(self, img):
        cv2_module().imshow(self.window, img)

    def key(self, ms):
        return cv2_module().waitKey(ms) & 0xFF

    def closed(self):
        return cv2_module().getWindowProperty(self.window, cv2_module().WND_PROP_VISIBLE) < 1

    def close(self):
        try:
            cv2_module().destroyWindow(self.window)
            cv2_module().waitKey(1)
        except Exception:
            pass


def cv2_module():
    import cv2
    return cv2


def preview_image(frames, args, info, show_grid, fast):
    """Display copy only: scaled side-by-side rectified pair with optional grid, counts, crop and text."""
    import cv2
    import numpy as np
    left, right = frames["rect_left"].getFrame(), frames["rect_right"].getFrame()
    s = args.preview_scale
    view = cv2.cvtColor(cv2.resize(np.hstack([left, right]), None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)
    w, h = int(round(args.width * s)), int(round(args.height * s))
    if show_grid:
        small = cv2.resize(left, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        pts = np.array([k.pt for k in fast.detect(small, None)]).reshape(-1, 2) * 2
        for eye in (0, 1):
            ox = eye * w
            for k in range(1, GRID):
                cv2.line(view, (ox + k * w // GRID, 0), (ox + k * w // GRID, h - 1), (255, 255, 255), 1)
                cv2.line(view, (ox, k * h // GRID), (ox + w - 1, k * h // GRID), (255, 255, 255), 1)
            if args.preview_crop:
                x0, y0, x1, y1 = args.preview_crop
                cv2.rectangle(view, (ox + int(x0 * s), int(y0 * s)), (ox + int(x1 * s), int(y1 * s)), (255, 255, 255), 1)
        for r in range(GRID):
            for c in range(GRID):
                n = int(((pts[:, 0] // (args.width / GRID) == c) & (pts[:, 1] // (args.height / GRID) == r)).sum()) if len(pts) else 0
                org = (c * w // GRID + 4, r * h // GRID + 16)
                cv2.putText(view, str(n), org, cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(view, str(n), org, cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    lines = [f"{info['device_id']} @ {info['ip']}  {args.label or ''}  |  {info['fps']}  |  seq {info['seq']}",
             "SPACE start capture   G grid/counts   Q or Esc cancel"]
    bar = np.zeros((44, view.shape[1], 3), np.uint8)
    for i, t in enumerate(lines):
        cv2.putText(bar, t, (8, 17 + 20 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return np.vstack([bar, view])


def setup_preview(source, args, report, ui=None):
    """Live preview from the capture's own source. Returns 'start', or a stop reason."""
    import cv2
    ui = ui or CvUI()
    fast = cv2.FastFeatureDetector_create(threshold=20)
    info = {"device_id": args.expect[1], "ip": args.expect[0], "fps": "measuring fps", "seq": "-"}
    sp = report["setup_preview"] = {"groups_shown": 0, "outcome": None, "grid_toggles": 0}
    t0, ts, show_grid = time.monotonic(), [], True
    log.info("Setup preview: position targets, then press SPACE to capture or Q/Esc to cancel.")
    try:
        while True:
            if time.monotonic() - t0 > args.setup_max_s:
                sp["outcome"] = "setup_timeout"
                return "setup_timeout"
            try:
                frames, _ = next(source)
            except StopIteration as stop:
                sp["outcome"] = stop.value or "source_ended"
                return sp["outcome"]
            sp["groups_shown"] += 1
            ts.append(cs.seconds(frames["rect_left"].getTimestampDevice()))
            ts = ts[-11:]
            if len(ts) > 1 and ts[-1] > ts[0]:
                info["fps"] = f"{(len(ts) - 1) / (ts[-1] - ts[0]):.1f} fps"
            info["seq"] = frames["rect_left"].getSequenceNum()
            ui.show(preview_image(frames, args, info, show_grid, fast))
            key = ui.key(1)
            if key == ord(" "):
                sp["outcome"] = "start"
                return "start"
            if key in (ord("q"), ord("Q"), 27):
                sp["outcome"] = "setup_cancelled"
                return "setup_cancelled"
            if key in (ord("g"), ord("G")):
                show_grid = not show_grid
                sp["grid_toggles"] += 1
            if ui.closed():
                sp["outcome"] = "setup_window_closed"
                return "setup_window_closed"
    finally:
        sp["seconds"] = round(time.monotonic() - t0, 1)
        ui.close()


def acquire(source, args, report, rows, saved):
    import numpy as np
    to_save = save_indices(args)
    t0 = time.monotonic()
    try:
        while len(rows) < args.groups:
            if time.monotonic() - t0 > args.max_seconds:
                return "max_seconds_reached"
            try:
                frames, meta = next(source)
            except StopIteration as stop:
                return stop.value or "source_ended"
            n = len(rows)
            ts = {k: cs.seconds(f.getTimestampDevice()) for k, f in frames.items()}
            raw_size = (frames["raw_left"].getWidth(), frames["raw_left"].getHeight())
            rect_size = (frames["rect_left"].getWidth(), frames["rect_left"].getHeight())
            row = {"group_index": n, "host_elapsed_s": round(time.monotonic() - t0, 4),
                   "seq": frames["raw_left"].getSequenceNum(),
                   **{f"{k}_ts_device_s": ts[k] for k in STREAMS},
                   "raw_lr_diff_ms": (ts["raw_left"] - ts["raw_right"]) * 1000,
                   "rect_vs_raw_left_ms": (ts["rect_left"] - ts["raw_left"]) * 1000,
                   "rect_vs_raw_right_ms": (ts["rect_right"] - ts["raw_right"]) * 1000,
                   "raw_size": f"{raw_size[0]}x{raw_size[1]}", "rect_size": f"{rect_size[0]}x{rect_size[1]}",
                   "latency_ms": (meta["rx_clock_s"] - cs.seconds(frames["raw_left"].getTimestamp())) * 1000,
                   "exposure_us": round(cs.seconds(frames["raw_left"].getExposureTime()) * 1e6),
                   "iso": frames["raw_left"].getSensitivity(), "saved": False}
            if raw_size != (args.width, args.height) or (frames["raw_right"].getWidth(), frames["raw_right"].getHeight()) != raw_size:
                report["errors"].append(f"group {n}: raw size {raw_size}, expected {args.width}x{args.height}")
                rows.append(row)
                return "unexpected_frame_size"
            if n in to_save:
                saved.append((n, row["seq"], {k: np.array(frames[k].getFrame(), copy=True) for k in STREAMS}))
                row["saved"] = True
            rows.append(row)
        return "target_groups_reached"
    finally:
        source.close()


def summarise(rows, args, report):
    gs = report.get("grouping")
    if gs and "seqs" in gs:
        seqs = gs.pop("seqs")
        gs["per_stream_sequence"] = {k: cs.sequence_gaps(seqs[k]) for k in STREAMS}
    if not rows:
        return
    seq = [r["seq"] for r in rows]
    gaps = [{"after_group": rows[i - 1]["group_index"], "missing_frames": seq[i] - seq[i - 1] - 1}
            for i in range(1, len(rows)) if seq[i] - seq[i - 1] != 1]
    span = rows[-1]["raw_left_ts_device_s"] - rows[0]["raw_left_ts_device_s"]
    report["measurements"] = {
        "groups": len(rows),
        "raw_sizes": sorted({r["raw_size"] for r in rows}), "rect_sizes": sorted({r["rect_size"] for r in rows}),
        "fps_device_timestamps": (len(rows) - 1) / span if span > 0 else None,
        "abs_raw_lr_diff_ms": cs.stats([abs(r["raw_lr_diff_ms"]) for r in rows]),
        "abs_rect_vs_raw_ms": cs.stats([abs(r["rect_vs_raw_left_ms"]) for r in rows] + [abs(r["rect_vs_raw_right_ms"]) for r in rows]),
        "latency_ms": cs.stats([r["latency_ms"] for r in rows]),
        "exposure_us": cs.stats([r["exposure_us"] for r in rows]),
    }
    expected = seq[-1] - seq[0] + 1
    report["continuity"] = {"consecutive": not gaps, "expected_frames": expected,
                            "missing_frames": sum(g["missing_frames"] for g in gaps), "gaps": gaps}


def write_images(saved, out_dir, report):
    import cv2
    img_dir = out_dir / "images"
    img_dir.mkdir(exist_ok=True)
    report["saved_images"] = []
    for n, seq, frames in saved:
        for k in STREAMS:
            path = img_dir / f"group{n:03d}_seq{seq}_{k}.png"
            if not cv2.imwrite(str(path), frames[k]):
                report["errors"].append(f"failed to write {path.name}")
            report["saved_images"].append(str(path.relative_to(out_dir)))


def analyse(saved, out_dir, calib_path, args, report, calib_dai):
    """Host geometry analysis of the saved groups (after the camera is closed)."""
    import cv2
    import numpy as np
    w, h = args.width, args.height
    summary = sg.calibration_summary(calib_dai, calib_path, w, h)
    geo = {"calibration": summary, "groups": []}
    Rs = {"left": summary["stored_rect_R_left"], "right": summary["stored_rect_R_right"]}
    for n, seq, f in saved:
        g = {"group_index": n, "seq": seq,
             "raw": sg.vertical_disparity(f["raw_left"], f["raw_right"], summary["left"]["K"][0][0], rectified=False)}
        for eye in ("left", "right"):
            cal = summary[eye]
            fit = sg.fit_rectified_camera(f[f"raw_{eye}"], f[f"rect_{eye}"], cal["K"], cal["D"], Rs[eye])
            g[f"device_rectified_camera_{eye}"] = fit
            if fit["status"] == "ok":
                mapx, mapy = sg.rect_maps(cal["K"], cal["D"], Rs[eye], fit["K"], (w, h))
                mask = sg.valid_mask(mapx, mapy, (w, h))
                area = sg.area_report(mask, fit["K"])
                img = f[f"rect_{eye}"]
                area["observed_zero_pixels_in_predicted_border"] = float((img[~mask] == 0).mean()) if (~mask).any() else None
                area["observed_zero_pixels_in_predicted_valid"] = float((img[mask] == 0).mean())
                g[f"area_{eye}"] = area
        fx = (g["device_rectified_camera_left"].get("K") or summary["left"]["K"])[0][0]
        g["rectified"] = sg.vertical_disparity(f["rect_left"], f["rect_right"], fx, rectified=True)
        name = f"group{n:03d}_seq{seq}_comparison.png"
        cv2.imwrite(str(out_dir / "images" / name), sg.comparison_image(f["raw_left"], f["raw_right"], f["rect_left"], f["rect_right"]))
        g["comparison_image"] = f"images/{name}"
        geo["groups"].append(g)
    ok = [g["rectified"] for g in geo["groups"] if g["rectified"]["status"] == "ok"]
    raw_ok = [g["raw"] for g in geo["groups"] if g["raw"]["status"] == "ok"]
    geo["summary"] = {
        "groups_analysed": len(geo["groups"]), "rectified_groups_scored": len(ok), "raw_groups_scored": len(raw_ok),
        "rectified_abs_dy_px_median_of_groups": float(np.median([m["abs_dy_px"]["median"] for m in ok])) if ok else None,
        "rectified_abs_dy_px_p95_max_over_groups": max((m["abs_dy_px"]["p95"] for m in ok), default=None),
        "rectified_abs_dy_px_max_over_groups": max((m["abs_dy_px"]["max"] for m in ok), default=None),
        "raw_abs_dy_px_median_of_groups": float(np.median([m["abs_dy_px"]["median"] for m in raw_ok])) if raw_ok else None,
        "note": "scores only where enough well-spread reliable matches exist; static-scene result",
    }
    (out_dir / "geometry.json").write_text(json.dumps(geo, indent=2), encoding="utf-8")
    report["geometry_summary"] = geo["summary"]
    return geo


def run(dai, args, out_dir, report, calib_dai=None, ui=None):
    """Returns exit code. Always stops the pipeline and closes every device it opened."""
    rows, saved, device, pipeline, started, before = [], [], None, None, False, None
    report["errors"], report["stop_reason"] = [], None
    try:
        device = cs.connect_verified(dai, args, report)
        report["ir_drivers"] = dc.safe_call(device, "getIrDrivers")
        cs.check_sensor_modes(dai, device, args, report)
        before = cc.read_user_and_factory(device)
        report["calibration_before"] = {"user_sha256": before["user_sha256"], "factory_sha256": before["factory_sha256"],
                                        "user_equals_factory": before["user"] == before["factory"]}
        (out_dir / "calibration_before_run.json").write_text(json.dumps(before["user"], sort_keys=True), encoding="utf-8")
        (out_dir / "calibration_factory_before_run.json").write_text(json.dumps(before["factory"], sort_keys=True), encoding="utf-8")
        report["ir_off_before_start"] = cs.set_ir_off(device)
        if report["ir_off_before_start"] != {"setIrLaserDotProjectorIntensity": True, "setIrFloodLightIntensity": True}:
            raise cs.SafetyAbort(f"device did not acknowledge IR off: {report['ir_off_before_start']}")
        pipeline, queues = build_pipeline(dai, device, args, report)
        pipeline.start()
        started = True
        report["ir_off_after_start"] = cs.set_ir_off(device)
        if report["ir_off_after_start"] != report["ir_off_before_start"]:
            raise cs.SafetyAbort(f"device did not acknowledge IR off after start: {report['ir_off_after_start']}")
        source = group_source(queues, args, report, dai.Clock.now)
        outcome = setup_preview(source, args, report, ui) if args.setup_preview else "start"
        if outcome != "start":
            source.close()
            report["stop_reason"] = outcome
            log.warning("Setup preview ended without capture: %s", outcome)
        else:
            log.info("Capturing raw + rectified at %.1f fps: %d groups (warm-up %d, save %d), distortion correction %s, alpha %s",
                     args.fps, args.groups, args.warmup_groups, args.save_groups, args.distortion_correction, args.alpha)
            report["stop_reason"] = acquire(source, args, report, rows, saved)
    except KeyboardInterrupt:
        report["stop_reason"] = "interrupted"
        log.warning("Interrupted; shutting down.")
    except cs.SafetyAbort as exc:
        report["stop_reason"] = "safety_abort"
        report["errors"].append(f"SafetyAbort: {exc}")
        log.error("Refused: %s", exc)
    except Exception as exc:
        report["stop_reason"] = report["stop_reason"] or "error"
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["traceback"] = traceback.format_exc()
        log.error("Error: %s", report["errors"][-1])
    finally:
        checks = []
        if device is not None and before is not None:
            if cs.is_closed(device):
                report["errors"].append("device disconnected before the in-session calibration re-read")
                report["calibration_in_session"] = {"equal": None, "error": "device already closed or disconnected"}
            else:
                try:
                    report["calibration_in_session"] = cs.compare_calibrations(
                        "in-session", cc.read_user_and_factory(device), before, report)
                except Exception as exc:
                    report["calibration_in_session"] = {"equal": None, "error": f"{type(exc).__name__}: {exc}"}
                    report["errors"].append(f"in-session calibration re-read failed: {type(exc).__name__}: {exc}")
            checks.append(report["calibration_in_session"]["equal"])
        if pipeline is not None and started:
            try:
                pipeline.stop()
                report["pipeline_stopped"] = True
            except Exception as exc:
                report["pipeline_stopped"] = False
                report["errors"].append(f"pipeline.stop failed: {type(exc).__name__}: {exc}")
            report["device_closed_by_pipeline_stop"] = cs.is_closed(device) if device is not None else None
        if device is not None:
            try:
                if not cs.is_closed(device):
                    device.close()
                report["device_closed"] = cs.is_closed(device)
            except Exception as exc:
                report["device_closed"] = False
                report["errors"].append(f"device.close failed: {type(exc).__name__}: {exc}")
        summarise(rows, args, report)
        with open(out_dir / "groups.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        try:
            write_images(saved, out_dir, report)
        except Exception as exc:
            report["errors"].append(f"image writing failed: {type(exc).__name__}: {exc}")
        if started and before is not None:
            try:
                checks.append(cs.post_run_verification(dai, args, before, report)["equal"])
            except Exception as exc:
                checks.append(None)
                report["errors"].append(f"post-run calibration verification crashed: {type(exc).__name__}: {exc}")
        report["calibration_unchanged"] = None if not checks or None in checks else all(checks)
        if saved and before is not None:
            try:
                analyse(saved, out_dir, out_dir / "calibration_before_run.json", args, report, calib_dai or dai)
            except Exception as exc:
                report["geometry_error"] = f"{type(exc).__name__}: {exc}"
                report["geometry_traceback"] = traceback.format_exc()

    passed = (report["stop_reason"] == "target_groups_reached" and not report["errors"]
              and report.get("pipeline_stopped") and report.get("device_closed")
              and report.get("calibration_unchanged") is True)
    if report["stop_reason"] == "interrupted":
        return 130
    if report["stop_reason"] in ("setup_cancelled", "setup_window_closed", "setup_timeout"):
        # No capture by choice; still FAIL if shutdown or calibration checks went wrong.
        clean = (not report["errors"] and report.get("pipeline_stopped") and report.get("device_closed")
                 and report.get("calibration_unchanged") is True)
        return CANCELLED if clean else 1
    return 0 if passed else 1


def main(argv=None):
    args = parse_args(argv)
    os.environ.setdefault("DEPTHAI_PROTOCOL", "tcpip")
    os.environ.setdefault("DEPTHAI_CONNECT_TIMEOUT", str(args.connect_timeout_ms))
    os.environ.setdefault("DEPTHAI_AUTOCALIBRATION", "OFF")  # belt and braces; the pipeline setter is what is verified
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = dc.RESULTS_DIR / "_".join(filter(None, ("rectify", stamp, args.expect[1], args.label)))
    out_dir.mkdir(parents=True, exist_ok=False)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(out_dir / "rectify.log", encoding="utf-8")])
    report = {"timestamp": dt.datetime.now().isoformat(timespec="seconds"), "hostname": socket.gethostname(),
              "python": sys.version.split()[0], "platform": platform.platform(),
              "args": {k: (list(v) if isinstance(v, tuple) else str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}}
    dumps_before = dc.crash_dumps()
    exit_code = 1
    try:
        import depthai as dai
        report["depthai_version"] = getattr(dai, "__version__", "unknown")
        log.info("DepthAI %s; output folder %s", report["depthai_version"], out_dir)
        exit_code = run(dai, args, out_dir, report)
    finally:
        report["new_crash_dumps"] = sorted(dc.crash_dumps() - dumps_before)
        if report["new_crash_dumps"]:
            log.warning("DepthAI saved new crash dump(s): %s", report["new_crash_dumps"])
            exit_code = exit_code or 1
        report["result"] = {0: "PASS", 130: "INTERRUPTED", CANCELLED: "CANCELLED"}.get(exit_code, "FAIL")
        (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        m, c, post = report.get("measurements", {}), report.get("continuity", {}), report.get("calibration_post_run", {})
        log.info("Stop: %s | groups %s | raw %s rect %s | fps %s | |rect-raw| ts ms %s",
                 report.get("stop_reason"), m.get("groups"), m.get("raw_sizes"), m.get("rect_sizes"),
                 m.get("fps_device_timestamps"), m.get("abs_rect_vs_raw_ms"))
        log.info("Grouping: %s | CONTINUITY: %s", report.get("grouping"),
                 None if not c else ("no frames missing" if c["consecutive"] else f"{c['missing_frames']} missing in {len(c['gaps'])} gap(s)"))
        log.info("Calibration: in-session equal %s | post-run (%s) equal %s, baselines %s | unchanged: %s",
                 report.get("calibration_in_session", {}).get("equal"), post.get("status"), post.get("equal"),
                 [(x["compared"], x["equal"]) for x in post.get("baselines", [])], report.get("calibration_unchanged"))
        log.info("Device closed: %s (by pipeline.stop: %s) | post-run device closed: %s | errors: %s",
                 report.get("device_closed"), report.get("device_closed_by_pipeline_stop"), post.get("device_closed"),
                 report.get("errors") or "none")
        if "setup_preview" in report:
            log.info("Setup preview: %s", report["setup_preview"])
        log.info("GEOMETRY: %s", report.get("geometry_summary") or report.get("geometry_error") or "not analysed")
        log.info("RESULT: %s  (%s)", report["result"], out_dir)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

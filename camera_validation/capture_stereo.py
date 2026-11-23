"""Stages C/D: synchronised left/right mono capture from one OAK PoE camera (DepthAI v3).

Local capture only. Selects the camera with the Stage B verified method
(broadcast pre-check, then device-ID and IP check after connecting), streams
CAM_B (left) and CAM_C (right) OV9282 frames and records, per pair, sequence
numbers, device and host timestamps, left/right timing, capture-to-receipt
latency, host queue occupancy and host processing time.

Pairing (--pairing):
  device-sync  DepthAI Sync node on the camera (default, the Stage C method).
  host-seq     Stage D diagnostic: raw left and right queues, paired on the host
               by sequence number and checked against the device timestamps
               (within half a frame period). It shows losses on one sensor
               only, and frames that never found a partner, which the Sync node
               hides by discarding the partner.

Safety:
  * IR dot projector and flood light are set to 0 before and after pipeline start;
    the run is refused if the device does not acknowledge.
  * DepthAI >= 3.6 runs automatic stereo calibration at pipeline start by default
    and may flash the result as user calibration. This tool sets
    AutoCalibrationMode.OFF, refuses to start unless the pipeline reports OFF,
    and compares the device calibration (user and factory, by content) before
    the run, after capture while still connected, and after shutdown through a
    fresh read-only connection. DepthAI 3.11.0's Pipeline.stop() closes the
    device, so the post-shutdown check has to reconnect.
  * No depth, rectification, undistortion, resizing or cropping: the requested
    output size must equal a native sensor mode.
  * Nothing is served on the network; no RemoteConnection or recording features.
    --network-stats only reads Windows counters (netstat, Get-NetAdapterStatistics).

Overhead: PNGs are written after streaming, from in-memory copies. The live
preview (--preview) runs in the capture loop; its cost appears in loop_busy_ms.

Sync threshold: by default half the frame period (25 ms at 20 fps). Adjacent
frames from one sensor are a full period apart, so a pair matched within half a
period cannot be frame n paired with n+1. The actual left/right differences are
recorded per pair; the threshold is only an upper bound for pairing.

RESULT (PASS/FAIL) is functional: target pairs, no errors, clean shutdown,
calibration unchanged. CONTINUITY is reported separately: whether every sensor
frame in the run reached the host as part of a pair.

    .venv\\Scripts\\python.exe capture_stereo.py --expect 169.254.1.222=19443010B14C872F00 --preview
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
import subprocess
import sys
import time
import traceback
from pathlib import Path

import calibration_check as cc
import discover_cameras as dc

log = logging.getLogger("capture")

LEFT, RIGHT = "left", "right"
CSV_FIELDS = (
    "pair_index", "host_elapsed_s", "left_seq", "right_seq",
    "left_ts_device_s", "right_ts_device_s", "lr_diff_ms", "left_ts_host_s", "right_ts_host_s",
    "rx_clock_s", "left_rx_clock_s", "right_rx_clock_s",
    "latency_ms", "wait_ms", "loop_busy_ms", "left_queue_size", "right_queue_size",
    "left_width", "left_height", "right_width", "right_height", "left_type", "right_type",
    "left_exposure_us", "right_exposure_us", "left_iso", "right_iso", "saved",
)


class SafetyAbort(RuntimeError):
    """A pre-start check failed; nothing has been streamed."""


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--expect", required=True, metavar="IP=DEVICE_ID", help="the one camera to capture from")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--fps", type=float, default=20.0)
    parser.add_argument("--pairs", type=int, default=200, help="synchronised pairs to collect (1-5000)")
    parser.add_argument("--max-seconds", type=float, default=60.0, help="hard limit on streaming time (1-600)")
    parser.add_argument("--frame-timeout-s", type=float, default=5.0, help="stop if no pair arrives within this (0.5-30)")
    parser.add_argument("--save-pairs", type=int, default=5, help="representative pairs saved as PNG (0-20)")
    parser.add_argument("--warmup-pairs", type=int, default=40,
                        help="pairs skipped before saving images and steady-state statistics "
                             "(auto-exposure settled by pair 26 on 4 Nov)")
    parser.add_argument("--sync-threshold-ms", type=float, default=None, help="default: half the frame period")
    parser.add_argument("--pairing", choices=("device-sync", "host-seq"), default="device-sync")
    parser.add_argument("--queue-size", type=int, default=8, help="host output queue size, non-blocking (1-64)")
    parser.add_argument("--network-stats", action="store_true",
                        help="record Windows TCP and adapter counters before and after (read-only)")
    parser.add_argument("--adapter", default="Ethernet 4", help="adapter name for --network-stats")
    parser.add_argument("--label", default="", help="short run label added to the output folder name")
    parser.add_argument("--preview", action="store_true", help="show a local side-by-side window (q or Esc stops)")
    parser.add_argument("--allow-non-isolated", action="store_true",
                        help="permit the broadcast pre-check while non-link-local IPv4 addresses are active")
    parser.add_argument("--baseline-user", type=Path, help="saved user calibration JSON for the post-run comparison")
    parser.add_argument("--baseline-factory", type=Path, help="saved factory calibration JSON for the post-run comparison")
    parser.add_argument("--post-verify-wait-s", type=float, default=60.0,
                        help="how long to wait for the camera to return to bootloader state before re-reading (5-180)")
    parser.add_argument("--connect-timeout-ms", type=int, default=15000)
    args = parser.parse_args(argv)
    args.expect = dc.parse_expectation(parser, args.expect)
    args.post_verify_poll_s = 2.0
    for p in (args.baseline_user, args.baseline_factory):
        if p is not None and not p.is_file():
            parser.error(f"baseline file not found: {p}")
    limits = [
        (256 <= args.width <= 4096 and 200 <= args.height <= 4096, "--width/--height out of range"),
        (1.0 <= args.fps <= 60.0, "--fps must be 1-60 for this conservative tool"),
        (1 <= args.pairs <= 5000, "--pairs must be 1-5000"),
        (1.0 <= args.max_seconds <= 600.0, "--max-seconds must be 1-600"),
        (0.5 <= args.frame_timeout_s <= 30.0, "--frame-timeout-s must be 0.5-30"),
        (0 <= args.save_pairs <= 20, "--save-pairs must be 0-20"),
        (0 <= args.warmup_pairs < args.pairs, "--warmup-pairs must be 0 to --pairs minus 1"),
        (5.0 <= args.post_verify_wait_s <= 180.0, "--post-verify-wait-s must be 5-180"),
        (1 <= args.queue_size <= 64, "--queue-size must be 1-64"),
        (re.fullmatch(r"[A-Za-z0-9 _\-]{1,64}", args.adapter) is not None, "--adapter: letters, digits, space, _ or - only"),
        (re.fullmatch(r"[A-Za-z0-9_\-]{0,32}", args.label) is not None, "--label: up to 32 letters, digits, _ or -"),
        (args.pairs / args.fps <= args.max_seconds, "--pairs / --fps exceeds --max-seconds"),
    ]
    for ok, message in limits:
        if not ok:
            parser.error(message)
    half_period_ms = 500.0 / args.fps
    if args.sync_threshold_ms is None:
        args.sync_threshold_ms = half_period_ms
    elif not 0 < args.sync_threshold_ms <= half_period_ms:
        parser.error(f"--sync-threshold-ms must be > 0 and <= half the frame period ({half_period_ms:.1f} ms)")
    return args


def save_indices(args):
    """Evenly spaced pair indices after warm-up."""
    if args.save_pairs == 0:
        return set()
    first, last = args.warmup_pairs, args.pairs - 1
    if args.save_pairs == 1:
        return {last}
    step = (last - first) / (args.save_pairs - 1)
    return {round(first + i * step) for i in range(args.save_pairs)}


def seconds(td):
    return td.total_seconds() if td is not None else None


def stats(values):
    import numpy as np
    values = [v for v in values if v not in (None, "")]
    if not values:
        return None
    a = np.asarray(values, dtype=float)
    return {"n": int(a.size), "mean": float(a.mean()), "median": float(np.median(a)),
            "p95": float(np.percentile(a, 95)), "max": float(a.max()), "min": float(a.min())}


def sequence_gaps(seqs):
    gaps = backwards = 0
    for prev, cur in zip(seqs, seqs[1:]):
        if cur <= prev:
            backwards += 1
        else:
            gaps += cur - prev - 1
    return {"missing_between_pairs": gaps, "non_increasing_steps": backwards}


def set_ir_off(device):
    out = {}
    for name in ("setIrLaserDotProjectorIntensity", "setIrFloodLightIntensity"):
        try:
            out[name] = bool(getattr(device, name)(0.0))
        except Exception as exc:
            out[name] = f"error: {type(exc).__name__}: {exc}"
    return out


def is_closed(device):
    try:
        return bool(device.isClosed())
    except Exception:
        return True


def network_snapshot(adapter):
    """Read-only Windows counters: TCP (netstat -s -n -p tcp) and the camera adapter's statistics.

    -n matters: without it netstat resolves the addresses of active connections and can hang.
    The TCP counters are the laptop's own: "Segments Retransmitted" counts segments the laptop
    re-sent, so it cannot show retransmissions by the camera on the camera-to-laptop video stream.
    """
    snap = {"monotonic_s": time.monotonic()}
    try:
        out = subprocess.run(["netstat", "-s", "-n", "-p", "tcp"], capture_output=True, text=True, timeout=15).stdout
        for line in out.splitlines():
            key, sep, value = line.partition("=")
            if sep and value.strip().isdigit():
                snap["tcp_" + "_".join(key.strip().lower().split())] = int(value.strip())
    except Exception as exc:
        snap["tcp_error"] = f"{type(exc).__name__}: {exc}"
    command = (f"Get-NetAdapterStatistics -Name '{adapter}' | Select-Object ReceivedBytes,ReceivedUnicastPackets,"
               "ReceivedDiscardedPackets,ReceivedPacketErrors,SentBytes,OutboundDiscardedPackets,OutboundPacketErrors"
               " | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                             capture_output=True, text=True, timeout=20).stdout
        snap.update({"adapter_" + k: v for k, v in json.loads(out).items()})
    except Exception as exc:
        snap["adapter_error"] = f"{type(exc).__name__}: {exc}"
    return snap


def network_delta(before, after, stream_start_s):
    delta = {k: after[k] - before[k] for k in after
             if k in before and isinstance(after[k], int) and isinstance(before[k], int) and k != "monotonic_s"}
    span = after["monotonic_s"] - stream_start_s
    if "adapter_ReceivedBytes" in delta and span > 0:
        delta["adapter_receive_mbit_per_s_since_pipeline_start"] = delta["adapter_ReceivedBytes"] * 8 / span / 1e6
    delta["note"] = ("tcp_* are system-wide laptop counters; tcp_segments_retransmitted counts the laptop's own "
                     "retransmissions, not the camera's on the video stream")
    return delta


def compare_calibrations(label, current, before, report):
    """Content comparison of user and factory calibration with the start-of-run read."""
    result = {"user": cc.comparison(f"{label} user", current["user"], "before-run user", before["user"]),
              "factory": cc.comparison(f"{label} factory", current["factory"], "before-run factory", before["factory"]),
              "user_sha256": current["user_sha256"], "factory_sha256": current["factory_sha256"]}
    result["equal"] = result["user"]["equal"] and result["factory"]["equal"]
    return result


def post_run_verification(dai, args, before, report):
    """Fresh read-only connection after shutdown; compares with the start of the run and optional baselines."""
    log.info("Post-run calibration check: waiting for the camera to return to bootloader state ...")
    rec = cc.reconnect_and_read(dai, args.expect, args.allow_non_isolated,
                                wait_s=args.post_verify_wait_s, poll_s=args.post_verify_poll_s)
    entry = {k: v for k, v in rec.items() if k not in ("user", "factory")}
    if rec["status"] == "read_ok":
        entry["vs_before_run"] = compare_calibrations("post-run", rec, before, report)
        entry["baselines"] = []
        for kind, path in (("user", args.baseline_user), ("factory", args.baseline_factory)):
            if path is not None:
                base = cc.load_baseline(path)
                c = cc.comparison(f"post-run {kind}", rec[kind], f"baseline {path.name}", base["data"])
                c["baseline_sha256"] = base["sha256"]
                entry["baselines"].append(c)
        entry["equal"] = entry["vs_before_run"]["equal"] and all(c["equal"] for c in entry["baselines"])
    else:
        entry["equal"] = None
        report["errors"].append(f"post-run calibration verification failed ({rec['status']}): {rec['errors']}")
    if rec.get("device_closed") is False:
        report["errors"].append("post-run verification device did not close cleanly")
    report["calibration_post_run"] = entry
    return entry


def check_sensor_modes(dai, device, args, report):
    """Refuse unless CAM_B and CAM_C are OV9282 with a native MONO mode of the requested size and fps."""
    features = {str(f.socket): f for f in device.getConnectedCameraFeatures()}
    report["sensors"] = {}
    for label, socket_ in ((LEFT, dai.CameraBoardSocket.CAM_B), (RIGHT, dai.CameraBoardSocket.CAM_C)):
        f = features.get(str(socket_))
        if f is None:
            raise SafetyAbort(f"{socket_} not present on device")
        modes = [{"width": c.width, "height": c.height, "minFps": c.minFps, "maxFps": c.maxFps, "type": str(c.type)}
                 for c in f.configs]
        report["sensors"][label] = {"socket": str(socket_), "sensor": f.sensorName,
                                    "native": [f.width, f.height], "modes": modes}
        if f.sensorName != "OV9282":
            raise SafetyAbort(f"{socket_} is {f.sensorName}, expected OV9282")
        match = [m for m in modes if (m["width"], m["height"]) == (args.width, args.height)
                 and m["type"].endswith("MONO") and m["minFps"] <= args.fps <= m["maxFps"]]
        if not match:
            raise SafetyAbort(f"{socket_}: no native MONO mode {args.width}x{args.height} at {args.fps} fps; "
                              f"available: {modes}")


def connect_verified(dai, args, report):
    """Stage B selection: broadcast pre-check, connect with the discovered DeviceInfo, verify ID and IP."""
    ip, device_id = args.expect
    selection = {"requested_ip": ip, "expected_device_id": device_id, "errors": []}
    report["selection"] = selection
    non_isolated = [a for a in dc.host_ipv4_addresses() if not dc.is_isolated_address(a)]
    if non_isolated and not args.allow_non_isolated:
        raise SafetyAbort(f"pre-check refused: non-link-local addresses active {non_isolated}")
    found = list(dai.Device.getAllAvailableDevices())
    report["broadcast_results"] = [dc.to_jsonable(i) for i in found]
    selected = dc.preflight(dai, [selection], found)
    if selected is None:
        raise SafetyAbort("pre-check failed, nothing booted: " + "; ".join(selection["errors"]))
    t0 = time.monotonic()
    device = dai.Device(selected[0])
    selection["connect_seconds"] = round(time.monotonic() - t0, 2)
    selection["actual_device_id"] = device.getDeviceId()
    selection["actual_ip"] = getattr(device.getDeviceInfo(), "name", None)
    if (selection["actual_device_id"], selection["actual_ip"]) != (device_id, ip):
        selection["errors"].append(f"connected to {selection['actual_device_id']} at {selection['actual_ip']}")
        try:
            device.close()
        finally:
            raise SafetyAbort("identity mismatch after connecting; device closed")
    log.info("Verified %s at %s in %.2f s", device_id, ip, selection["connect_seconds"])
    return device


def build_pipeline(dai, device, args, report):
    """Returns (pipeline, queues): {"sync": q} for device-sync, {"left": q, "right": q} for host-seq."""
    pipeline = dai.Pipeline(device)
    pipeline.setAutoCalibrationMode(dai.Pipeline.AutoCalibrationMode.OFF)
    mode = pipeline.getAutoCalibrationMode()
    report["auto_calibration_mode"] = str(mode)
    if mode != dai.Pipeline.AutoCalibrationMode.OFF:
        raise SafetyAbort(f"AutoCalibrationMode is {mode}, refusing to start (it may flash calibration)")
    outputs, pools = {}, {}
    for label, socket_ in ((LEFT, dai.CameraBoardSocket.CAM_B), (RIGHT, dai.CameraBoardSocket.CAM_C)):
        cam = pipeline.create(dai.node.Camera).build(socket_, sensorResolution=(args.width, args.height),
                                                     sensorFps=args.fps)
        outputs[label] = cam.requestOutput((args.width, args.height), type=dai.ImgFrame.Type.GRAY8,
                                           fps=args.fps, enableUndistortion=False)
        pools[label] = {name: dc.safe_call(cam, name) for name in
                        ("getOutputsNumFramesPool", "getRawNumFramesPool", "getIspNumFramesPool")}
    report["pipeline"] = {
        "left": "CAM_B Camera.requestOutput GRAY8, enableUndistortion=False",
        "right": "CAM_C Camera.requestOutput GRAY8, enableUndistortion=False",
        "size": [args.width, args.height], "fps": args.fps, "pairing": args.pairing,
        "camera_frame_pools": pools,
        "host_queue": {"maxSize": args.queue_size, "blocking": False, "when_full": "oldest message discarded"},
    }
    if args.pairing == "device-sync":
        sync = pipeline.create(dai.node.Sync)
        sync.setSyncThreshold(dt.timedelta(milliseconds=args.sync_threshold_ms))
        sync.setTimestampSource(dai.node.Sync.TimestampSource.DEVICE)
        outputs[LEFT].link(sync.inputs[LEFT])
        outputs[RIGHT].link(sync.inputs[RIGHT])
        report["pipeline"]["sync"] = {
            "threshold_ms": args.sync_threshold_ms, "timestamp_source": "DEVICE",
            "threshold_basis": "half the frame period",
            "inputs": {k: {"maxSize": dc.safe_call(sync.inputs[k], "getMaxSize"),
                           "blocking": dc.safe_call(sync.inputs[k], "getBlocking")} for k in (LEFT, RIGHT)}}
        return pipeline, {"sync": sync.out.createOutputQueue(maxSize=args.queue_size, blocking=False)}
    report["pipeline"]["host_pairing"] = {"match": "equal sequence number and |L-R device timestamp| <= half period"}
    return pipeline, {k: outputs[k].createOutputQueue(maxSize=args.queue_size, blocking=False) for k in (LEFT, RIGHT)}


def device_sync_source(queues, args, report, now):
    """Yields (left, right, meta) from the camera-side Sync node; returns a stop reason."""
    queue = queues["sync"]
    timeout = dt.timedelta(seconds=args.frame_timeout_s)
    while True:
        t0 = time.monotonic()
        group = queue.get(timeout)
        wait_ms = (time.monotonic() - t0) * 1000
        if group is None:
            report["errors"].append(f"no synchronised pair within {args.frame_timeout_s} s")
            return "frame_timeout"
        meta = {"rx_clock_s": seconds(now()), "left_rx_clock_s": "", "right_rx_clock_s": "", "wait_ms": wait_ms,
                "left_queue_size": queue.getSize(), "right_queue_size": ""}
        left, right = group[LEFT], group[RIGHT]
        if left is None or right is None:
            report["errors"].append(f"incomplete group {group.getMessageNames()}")
            continue
        yield left, right, meta


def host_seq_source(queues, args, report, now):
    """Yields (left, right, meta) paired on the host by sequence number; returns a stop reason."""
    half_period_s = 0.5 / args.fps
    # A frame is declared unpaired only once the other sensor is this many sequence numbers ahead, so that
    # left and right streams arriving out of step after a delivery stall are not miscounted as losses.
    margin = max(4, args.queue_size)
    pending = {LEFT: {}, RIGHT: {}}
    hp = report["host_pairing"] = {"received": {LEFT: 0, RIGHT: 0}, "unpaired": {LEFT: 0, RIGHT: 0},
                                   "timestamp_mismatch": 0, "seqs": {LEFT: [], RIGHT: []}}
    last_rx = t_wait = time.monotonic()
    try:
        while True:
            got = False
            for side in (LEFT, RIGHT):
                msg = queues[side].tryGet()
                if msg is not None:
                    got, last_rx = True, time.monotonic()
                    seq = msg.getSequenceNum()
                    pending[side][seq] = (msg, seconds(now()), queues[side].getSize())
                    hp["received"][side] += 1
                    hp["seqs"][side].append(seq)
            for seq in sorted(set(pending[LEFT]) & set(pending[RIGHT])):
                (left, l_rx, l_q), (right, r_rx, r_q) = pending[LEFT].pop(seq), pending[RIGHT].pop(seq)
                if abs(seconds(left.getTimestampDevice()) - seconds(right.getTimestampDevice())) > half_period_s:
                    hp["timestamp_mismatch"] += 1
                    continue
                meta = {"rx_clock_s": max(l_rx, r_rx), "left_rx_clock_s": l_rx, "right_rx_clock_s": r_rx,
                        "wait_ms": (time.monotonic() - t_wait) * 1000, "left_queue_size": l_q, "right_queue_size": r_q}
                yield left, right, meta
                t_wait = time.monotonic()
            for side, other in ((LEFT, RIGHT), (RIGHT, LEFT)):
                if hp["seqs"][other]:
                    newest = hp["seqs"][other][-1]
                    for seq in [s for s in pending[side] if s < newest - margin]:
                        pending[side].pop(seq)
                        hp["unpaired"][side] += 1
            if not got:
                if time.monotonic() - last_rx > args.frame_timeout_s:
                    report["errors"].append(f"no frame on either queue within {args.frame_timeout_s} s")
                    return "frame_timeout"
                time.sleep(0.001)
    finally:
        # Recorded when the source is closed, so it reflects frames still unpaired at the end of the run.
        hp["pending"] = {LEFT: len(pending[LEFT]), RIGHT: len(pending[RIGHT])}


def frame_row(left, right):
    l_ts, r_ts = seconds(left.getTimestampDevice()), seconds(right.getTimestampDevice())
    return {
        "left_seq": left.getSequenceNum(), "right_seq": right.getSequenceNum(),
        "left_ts_device_s": l_ts, "right_ts_device_s": r_ts,
        "lr_diff_ms": (l_ts - r_ts) * 1000.0,
        "left_ts_host_s": seconds(left.getTimestamp()), "right_ts_host_s": seconds(right.getTimestamp()),
        "left_width": left.getWidth(), "left_height": left.getHeight(),
        "right_width": right.getWidth(), "right_height": right.getHeight(),
        "left_type": str(left.getType()), "right_type": str(right.getType()),
        "left_exposure_us": round(seconds(left.getExposureTime()) * 1e6), "right_exposure_us": round(seconds(right.getExposureTime()) * 1e6),
        "left_iso": left.getSensitivity(), "right_iso": right.getSensitivity(),
    }


def acquire(source, args, report, rows, pending_images):
    """Consume pairs from a source generator; returns the stop reason. Images are only copied here."""
    import cv2
    import numpy as np
    to_save = save_indices(args)
    t_start = time.monotonic()
    report["acquisition_cpu"] = {"process_s_start": time.process_time()}
    window = "stereo preview (q/Esc to stop)"
    try:
        while len(rows) < args.pairs:
            if time.monotonic() - t_start > args.max_seconds:
                return "max_seconds_reached"
            try:
                left, right, meta = next(source)
            except StopIteration as stop:
                return stop.value or "source_ended"
            t_got = time.monotonic()
            n = len(rows)
            row = {"pair_index": n, "host_elapsed_s": round(t_got - t_start, 4), **frame_row(left, right),
                   **meta, "loop_busy_ms": "", "saved": False}
            row["latency_ms"] = (row["rx_clock_s"] - row["left_ts_host_s"]) * 1000.0
            if (row["left_width"], row["left_height"], row["right_width"], row["right_height"]) != \
                    (args.width, args.height, args.width, args.height):
                report["errors"].append(f"pair {n}: size {row['left_width']}x{row['left_height']} / "
                                        f"{row['right_width']}x{row['right_height']}, expected {args.width}x{args.height}")
                rows.append(row)
                return "unexpected_frame_size"
            if n in to_save:
                pending_images.append((n, row["left_seq"], row["right_seq"],
                                       np.array(left.getFrame(), copy=True), np.array(right.getFrame(), copy=True)))
                row["saved"] = True
            stop = None
            if args.preview:
                view = cv2.resize(np.hstack([left.getFrame(), right.getFrame()]), None, fx=0.5, fy=0.5,
                                  interpolation=cv2.INTER_AREA)
                view = cv2.cvtColor(view, cv2.COLOR_GRAY2BGR)
                cv2.putText(view, f"pair {n}  L{row['left_seq']} R{row['right_seq']}  dL-R {row['lr_diff_ms']:+.3f} ms",
                            (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
                cv2.imshow(window, view)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27) or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    stop = "stopped_by_user"
            row["loop_busy_ms"] = (time.monotonic() - t_got) * 1000
            rows.append(row)
            if stop:
                return stop
        return "target_pairs_reached"
    finally:
        source.close()
        cpu = report["acquisition_cpu"]
        cpu["process_s"] = time.process_time() - cpu.pop("process_s_start")
        cpu["wall_s"] = time.monotonic() - t_start
        cpu["percent_of_one_core"] = 100 * cpu["process_s"] / cpu["wall_s"] if cpu["wall_s"] > 0 else None


def write_images(pending_images, out_dir, report):
    import cv2
    import numpy as np
    images_dir = out_dir / "images"
    images_dir.mkdir(exist_ok=True)
    report["saved_images"] = []
    for n, l_seq, r_seq, l_img, r_img in pending_images:
        stem = f"pair{n:04d}_L{l_seq}_R{r_seq}"
        for suffix, img in (("left", l_img), ("right", r_img), ("sidebyside", np.hstack([l_img, r_img]))):
            path = images_dir / f"{stem}_{suffix}.png"
            if not cv2.imwrite(str(path), img):
                report["errors"].append(f"failed to write {path.name}")
            report["saved_images"].append(str(path.relative_to(out_dir)))


def analyse_gap(rows, i, args):
    """Context of a sequence gap before rows[i]: delivery delay, host queue occupancy, latency change."""
    period_ms = 1000.0 / args.fps
    window = rows[max(0, i - 20):i]
    arrivals = [(b["host_elapsed_s"] - a["host_elapsed_s"]) * 1000 for a, b in zip(window, window[1:])]
    queue_max = max((r["left_queue_size"] for r in window if r["left_queue_size"] != ""), default=None)
    latency_before = max((r["latency_ms"] for r in window), default=None)
    out = {"after_pair": rows[i - 1]["pair_index"], "missing_frames": rows[i]["left_seq"] - rows[i - 1]["left_seq"] - 1,
           "interval_ms": round((rows[i]["left_ts_device_s"] - rows[i - 1]["left_ts_device_s"]) * 1000, 3),
           "max_host_interarrival_ms_before": round(max(arrivals), 1) if arrivals else None,
           "max_latency_ms_before": round(latency_before, 1) if latency_before is not None else None,
           "latency_ms_after": round(rows[i]["latency_ms"], 1),
           "max_host_queue_size_before": queue_max}
    if queue_max is not None and queue_max >= args.queue_size - 1:
        out["consistent_with"] = "host queue full before the gap: host-side overflow (oldest frames discarded)"
    elif latency_before is not None and latency_before > 2 * period_ms:
        out["consistent_with"] = ("frames delayed before reaching the host queue, then lost upstream "
                                  "(camera-side loss during a delivery stall)")
    else:
        out["consistent_with"] = "no preceding delay seen: loss upstream without backlog (sensor or Sync)"
    return out


def summarise(rows, args, report):
    hp = report.get("host_pairing")
    per_sensor = None
    if hp and "seqs" in hp:
        seqs = hp.pop("seqs")
        hp["per_sensor_sequence"] = {side: sequence_gaps(seqs[side]) for side in (LEFT, RIGHT)}
        per_sensor = {side: hp["per_sensor_sequence"][side]["missing_between_pairs"] for side in (LEFT, RIGHT)}
    if not rows:
        return
    diffs = [abs(r["lr_diff_ms"]) for r in rows]
    l_ts = [r["left_ts_device_s"] for r in rows]
    span = l_ts[-1] - l_ts[0]
    gap_idx = [i for i in range(1, len(rows)) if rows[i]["left_seq"] - rows[i - 1]["left_seq"] != 1]
    gaps = [analyse_gap(rows, i, args) for i in gap_idx]
    intervals = [(b - a) * 1000 for a, b in zip(l_ts, l_ts[1:])]
    arrivals = [(b["host_elapsed_s"] - a["host_elapsed_s"]) * 1000 for a, b in zip(rows, rows[1:])]
    host_span = rows[-1]["host_elapsed_s"] - rows[0]["host_elapsed_s"]
    steady = rows[args.warmup_pairs:] if len(rows) > args.warmup_pairs else rows
    expected = rows[-1]["left_seq"] - rows[0]["left_seq"] + 1
    missing = sum(g["missing_frames"] for g in gaps)
    period_ms = 1000.0 / args.fps
    report["measurements"] = {
        "pairs": len(rows),
        "actual_size": sorted({(r["left_width"], r["left_height"], r["right_width"], r["right_height"]) for r in rows}),
        "actual_types": sorted({(r["left_type"], r["right_type"]) for r in rows}),
        "fps_device_timestamps": (len(rows) - 1) / span if span > 0 else None,
        "fps_host_arrival": (len(rows) - 1) / host_span if host_span > 0 else None,
        "abs_lr_diff_ms": stats(diffs),
        "pairs_with_equal_sequence_numbers": sum(r["left_seq"] == r["right_seq"] for r in rows),
        "left_sequence": sequence_gaps([r["left_seq"] for r in rows]),
        "right_sequence": sequence_gaps([r["right_seq"] for r in rows]),
        "frame_gaps": gaps,
        "frame_interval_ms": stats(intervals),
        "host_interarrival_ms": stats(arrivals),
        "host_stalls_over_2_periods": [{"before_pair": i + 1, "ms": round(a, 1)}
                                       for i, a in enumerate(arrivals) if a > 2 * period_ms],
        "latency_ms_all": stats([r["latency_ms"] for r in rows]),
        "latency_ms_steady_state": stats([r["latency_ms"] for r in steady]),
        "wait_ms": stats([r["wait_ms"] for r in rows]),
        "loop_busy_ms": stats([r["loop_busy_ms"] for r in rows]),
        "left_queue_size": stats([r["left_queue_size"] for r in rows]),
        "right_queue_size": stats([r["right_queue_size"] for r in rows]),
        # Sampled just after get(): queue_size - 1 remaining means the queue was full before the read.
        "pairs_seeing_queue_full": sum(1 for r in rows if r["left_queue_size"] not in ("", None)
                                       and r["left_queue_size"] >= args.queue_size - 1),
        "exposure_us_left": stats([r["left_exposure_us"] for r in rows]),
        "iso_left": stats([r["left_iso"] for r in rows]),
        "note": "missing frames are sensor frames that never reached the host in a delivered pair. "
                "consistent_with is an interpretation of timing evidence, not a measurement of where the loss happened. "
                "latency_ms = host receipt (dai.Clock) minus host-synchronised capture timestamp.",
    }
    report["continuity"] = {"consecutive": not gaps, "expected_frames_per_sensor": expected,
                            "missing_frames": missing, "gaps": len(gaps),
                            "missing_per_1000_expected": round(1000 * missing / expected, 3) if expected else None}
    if per_sensor is not None:
        report["continuity"]["per_sensor_missing"] = per_sensor
    if gaps:
        log.warning("Frame gaps: %s", gaps)


def run_capture(dai, args, out_dir, report):
    """Returns exit code. Always stops the pipeline and closes every device it opened.

    Shutdown order (DepthAI 3.11.0 Pipeline.stop() closes the device):
      1. network counters after streaming (if requested), then calibration re-read while still connected
      2. stop the pipeline, then close the device if stop() has not
      3. write pairs.csv, measurements and the deferred PNGs
      4. if the pipeline ran: fresh read-only connection to re-read calibration (post-run check)
    """
    import cv2
    rows, pending_images, device, pipeline, started, before = [], [], None, None, False, None
    stream_start = None
    report["errors"] = []
    report["stop_reason"] = None
    try:
        device = connect_verified(dai, args, report)
        report["ir_drivers"] = dc.safe_call(device, "getIrDrivers")
        check_sensor_modes(dai, device, args, report)
        before = cc.read_user_and_factory(device)
        report["calibration_before"] = {"user_sha256": before["user_sha256"], "factory_sha256": before["factory_sha256"],
                                        "user_equals_factory": before["user"] == before["factory"]}
        (out_dir / "calibration_before_run.json").write_text(json.dumps(before["user"], sort_keys=True), encoding="utf-8")
        (out_dir / "calibration_factory_before_run.json").write_text(json.dumps(before["factory"], sort_keys=True),
                                                                     encoding="utf-8")
        report["ir_off_before_start"] = set_ir_off(device)
        if report["ir_off_before_start"] != {"setIrLaserDotProjectorIntensity": True, "setIrFloodLightIntensity": True}:
            raise SafetyAbort(f"device did not acknowledge IR off: {report['ir_off_before_start']}")
        pipeline, queues = build_pipeline(dai, device, args, report)
        if args.network_stats:
            report["network_before"] = network_snapshot(args.adapter)
        pipeline.start()
        started, stream_start = True, time.monotonic()
        report["ir_off_after_start"] = set_ir_off(device)
        if report["ir_off_after_start"] != report["ir_off_before_start"]:
            raise SafetyAbort(f"device did not acknowledge IR off after start: {report['ir_off_after_start']}")
        log.info("Streaming (%s): target %d pairs, %dx%d at %.1f fps, sync threshold %.1f ms, host queue %d",
                 args.pairing, args.pairs, args.width, args.height, args.fps, args.sync_threshold_ms, args.queue_size)
        source = (device_sync_source if args.pairing == "device-sync" else host_seq_source)(
            queues, args, report, dai.Clock.now)
        report["stop_reason"] = acquire(source, args, report, rows, pending_images)
    except KeyboardInterrupt:
        report["stop_reason"] = "interrupted"
        log.warning("Interrupted; shutting down.")
    except SafetyAbort as exc:
        report["stop_reason"] = "safety_abort"
        report["errors"].append(f"SafetyAbort: {exc}")
        log.error("Refused: %s", exc)
    except Exception as exc:
        report["stop_reason"] = report["stop_reason"] or "error"
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["traceback"] = traceback.format_exc()
        log.error("Error: %s", report["errors"][-1])
    finally:
        if "network_before" in report and started:
            try:
                report["network_after"] = network_snapshot(args.adapter)
                report["network_delta"] = network_delta(report["network_before"], report["network_after"], stream_start)
            except Exception as exc:
                report["network_delta"] = {"error": f"{type(exc).__name__}: {exc}"}
        checks = []
        if device is not None and before is not None:
            if is_closed(device):
                report["errors"].append("device disconnected before the in-session calibration re-read")
                report["calibration_in_session"] = {"equal": None, "error": "device already closed or disconnected"}
            else:
                try:
                    current = cc.read_user_and_factory(device)
                    report["calibration_in_session"] = compare_calibrations("in-session", current, before, report)
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
            report["device_closed_by_pipeline_stop"] = is_closed(device) if device is not None else None
        if device is not None:
            try:
                if not is_closed(device):
                    device.close()
                report["device_closed"] = is_closed(device)
            except Exception as exc:
                report["device_closed"] = False
                report["errors"].append(f"device.close failed: {type(exc).__name__}: {exc}")
        if args.preview:
            cv2.destroyAllWindows()
        summarise(rows, args, report)
        with open(out_dir / "pairs.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        try:
            write_images(pending_images, out_dir, report)
        except Exception as exc:
            report["errors"].append(f"image writing failed: {type(exc).__name__}: {exc}")
        if started and before is not None:
            try:
                checks.append(post_run_verification(dai, args, before, report)["equal"])
            except Exception as exc:
                checks.append(None)
                report["errors"].append(f"post-run calibration verification crashed: {type(exc).__name__}: {exc}")
        # True only if every check ran and matched; None if any could not be completed.
        report["calibration_unchanged"] = None if not checks or None in checks else all(checks)

    passed = (report["stop_reason"] == "target_pairs_reached" and not report["errors"]
              and report.get("pipeline_stopped") and report.get("device_closed")
              and report.get("calibration_unchanged") is True)
    if report["stop_reason"] == "interrupted":
        return 130
    return 0 if passed else 1


def main(argv=None):
    args = parse_args(argv)
    os.environ.setdefault("DEPTHAI_PROTOCOL", "tcpip")
    os.environ.setdefault("DEPTHAI_CONNECT_TIMEOUT", str(args.connect_timeout_ms))
    os.environ.setdefault("DEPTHAI_AUTOCALIBRATION", "OFF")  # belt and braces; the pipeline setter is what is verified

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = dc.RESULTS_DIR / ("_".join(filter(None, ("stereo", stamp, args.expect[1], args.label))))
    out_dir.mkdir(parents=True, exist_ok=False)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(out_dir / "capture.log", encoding="utf-8")])
    report = {"timestamp": dt.datetime.now().isoformat(timespec="seconds"), "hostname": socket.gethostname(),
              "python": sys.version.split()[0], "platform": platform.platform(),
              "args": {k: (list(v) if isinstance(v, tuple) else str(v) if isinstance(v, Path) else v)
                       for k, v in vars(args).items()}}
    dumps_before = dc.crash_dumps()
    exit_code = 1
    try:
        import depthai as dai
        report["depthai_version"] = getattr(dai, "__version__", "unknown")
        log.info("DepthAI %s; output folder %s", report["depthai_version"], out_dir)
        exit_code = run_capture(dai, args, out_dir, report)
    finally:
        report["new_crash_dumps"] = sorted(dc.crash_dumps() - dumps_before)
        if report["new_crash_dumps"]:
            log.warning("DepthAI saved new crash dump(s): %s", report["new_crash_dumps"])
            exit_code = exit_code or 1
        report["result"] = {0: "PASS", 130: "INTERRUPTED"}.get(exit_code, "FAIL")
        (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        m = report.get("measurements", {})
        log.info("Stop reason: %s | pairs: %s | size: %s | fps (device): %s | |L-R| ms: %s",
                 report.get("stop_reason"), m.get("pairs"), m.get("actual_size"),
                 m.get("fps_device_timestamps"), m.get("abs_lr_diff_ms"))
        log.info("Latency ms (steady): %s | host stalls > 2 periods: %s | max host queue: %s | loop busy ms: %s",
                 m.get("latency_ms_steady_state"), m.get("host_stalls_over_2_periods"),
                 (m.get("left_queue_size") or {}).get("max"), m.get("loop_busy_ms"))
        if "host_pairing" in report:
            log.info("Host pairing: %s", report["host_pairing"])
        if "network_delta" in report:
            log.info("Network delta: %s", report["network_delta"])
        post = report.get("calibration_post_run", {})
        log.info("Calibration: in-session equal %s | post-run (%s) equal %s, baselines %s | unchanged: %s",
                 report.get("calibration_in_session", {}).get("equal"), post.get("status"), post.get("equal"),
                 [(c["compared"], c["equal"]) for c in post.get("baselines", [])], report.get("calibration_unchanged"))
        log.info("Device closed: %s (by pipeline.stop: %s) | post-run device closed: %s | errors: %s",
                 report.get("device_closed"), report.get("device_closed_by_pipeline_stop"),
                 post.get("device_closed"), report.get("errors") or "none")
        c = report.get("continuity")
        if c:
            log.info("CONTINUITY: %s", "no frames missing" if c["consecutive"] else
                     f"{c['missing_frames']} of {c['expected_frames_per_sensor']} frames missing in {c['gaps']} gap(s)")
        log.info("RESULT: %s  (%s)", report["result"], out_dir)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

"""Camera A gateway (Task 06): OAK-D Pro PoE AF rectified stereo -> on-device H.264
-> FrameMeta SEI + end-of-frame SEI -> localhost RTSP (MediaMTX) or MPEG-TS files.

PREPARED OFFLINE. NOT RUN ON HARDWARE. Without --live it only validates the
arguments, checks the pinned safeguard sources and prints the plan; it imports
DepthAI but never searches for, connects to or configures a device.

SAFEGUARDS (the validated camera_validation code, imported read-only; its three
source files are SHA-256 pinned and the gateway refuses to start if they change;
no bytecode is written into camera_validation):
  * Camera A only: --expect must name device 19443010B14C872F00 at a link-local
    address; capture_stereo.connect_verified (broadcast pre-check, bootloader
    state, ID and IP verified after connecting; refuses on non-link-local host
    addresses unless --allow-non-isolated, which is not to be used);
  * capture_stereo.check_sensor_modes: CAM_B / CAM_C are OV9282 with a native
    1280 x 800 MONO mode at --fps;
  * calibration read (read-only) before start and compared with the baseline
    files BEFORE start (refuses on any difference), re-read in session, and
    verified again after shutdown by a fresh connection (post_run_verification);
  * IR dot projector and flood light set to 0 and acknowledged before AND after
    pipeline start (capture_stereo.set_ir_off), else refuse;
  * Pipeline.setAutoCalibrationMode(OFF) confirmed with the getter before start,
    else refuse (a 1280 x 800 StereoDepth pipeline is what auto-calibration targets);
  * nothing is ever written to the device: no calibration, firmware, bootloader,
    IP or device settings (no such call exists in this file);
  * pipeline stopped and device closed in every exit path.

PIPELINE (rectification exactly as the approved Stage E E1 configuration):
  CAM_B/CAM_C Camera.requestOutput GRAY8 1280 x 800 @ --fps, enableUndistortion
  False -> StereoDepth (rectification on, distortion correction ON, alpha unset,
  edge fill 0, no spec translation) -> rectifiedLeft / rectifiedRight -> two
  VideoEncoder nodes (H.264 Baseline, CBR --bitrate-kbps, keyframe every --keyint,
  0 B-frames; GRAY8 input is converted to NV12 by DepthAI) -> host queues
  (non-blocking, --device-queue). Depth and disparity are not used or sent.

HOST (capture and network independent):
  main thread   drains both encoder queues, logs captured.csv, checks the pair
                (equal seq, device-time skew), feeds the per-eye GopQueue
                (bounded, GOP-aware latest-frame policy; gateway_core);
  sender x 2    one per eye: connect first, start at a recovery point, age guard,
                package (SEI + frame end), mux, reconnect with backoff
                (gateway_output). A blocked or failed write never stops capture.

Outputs: camera_gateway/results/gw_<stamp>_A_<label>/ events.jsonl, captured.csv,
sent.csv, report.json (safeguards, pipeline, counters, hardware checks),
calibration copies, and in --sink file mode camA_<eye>_seg<k>.ts.

NETWORK SCOPE (12 Nov 2026, researcher-approved opt-in; default unchanged):
  --network-scope isolated (DEFAULT) = the validated path above, unchanged: refuses while any non-link-local
      host address exists (Wi-Fi must be off) and selects the camera by broadcast pre-check.
  --network-scope ethernet_scoped = for the now-permitted concurrent Wi-Fi + Ethernet: network_scope.py must
      pass BEFORE anything is contacted (the camera route uses one wired, link-local-only interface, no other
      link-local route, no overlap, ARP = recorded Camera A MAC); NO broadcast discovery (it would also go out
      on the Wi-Fi network): unicast DeviceInfo(ip), then the same ID / IP / bootloader verification, calibration
      checks, IR off, AutoCalibration OFF; re-checked every --scope-check-interval-s during streaming, and any
      change stops the stream (stop reason network_scope_changed, a failed run); the post-run calibration
      read uses the same unicast, verified connection. Cannot be combined with --allow-non-isolated.

Plan only:   camera_gateway\\.venv\\Scripts\\python.exe -I camera_gateway\\camera_gateway_a.py --expect 169.254.1.222=19443010B14C872F00 --baseline-user <u.json> --baseline-factory <f.json>
Live (approval, isolated Ethernet, MediaMTX for --sink rtsp): add --live  [and --network-scope ethernet_scoped with Wi-Fi on]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import pathlib
import re
import statistics
import sys
import threading
import time
import traceback

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
CV = ROOT / "camera_validation"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gateway_core as gc  # noqa: E402
import gateway_output as go  # noqa: E402
import network_scope as ns  # noqa: E402
from gateway_core import pc  # noqa: E402

CAMERA_A_ID = "19443010B14C872F00"
EXTENDED_MAX_S = 600.0      # hard maximum of the opt-in --extended-test mode (13 Nov 2026); the default limit stays 120 s
# Camera A flash bootloader as recorded by the validated discovery (discover_20261104_143828.json).
# Read back (read-only) on every connection; a different value means the persistent device state
# is not the validated one, and the gateway refuses.
EXPECTED_BOOTLOADER = "0.0.26"
READ_ONLY_DEVICE_GETTERS = ("getBootloaderVersion", "getProductName", "getDeviceName", "getPlatformAsString",
                            "getChipTemperature")
RESULTS = HERE / "results"
SAFETY_SOURCES = {          # camera_validation sources as validated (4 Nov 2026); refuse if changed
    "discover_cameras.py": "5de6f1193bde0a7694c272bd02f4afb952962228dcb99ede5c46501014ee169f",
    "calibration_check.py": "69ad1f31192d324fce4343142e3c83f51583aff1e6f7ca23d964fa10b5dd9df8",
    "capture_stereo.py": "a66716afeffa55198089c2cfef3014f21cbd2b6452490bc348c1ee5b3a439ca2",
}
CAPTURED_FIELDS = ("eye", "seq", "t_dev_ns", "t_host_mono_ns", "t_received_mono_ns", "host_receipt_minus_capture_ms",
                   "frame_type", "recovery_point", "idr", "sps", "aud", "bytes", "queued", "nal_types", "width", "height")


class SafetySourceChanged(RuntimeError):
    pass


def load_safety_modules(cv_dir=CV, pins=SAFETY_SOURCES):
    """Import the validated safeguard modules read-only after checking their SHA-256."""
    for name, digest in pins.items():
        actual = hashlib.sha256((pathlib.Path(cv_dir) / name).read_bytes()).hexdigest()
        if actual != digest:
            raise SafetySourceChanged("{} changed since validation (sha256 {} != pinned {}); refusing".format(name, actual, digest))
    if str(cv_dir) not in sys.path:
        sys.path.append(str(cv_dir))
    import calibration_check as cc
    import capture_stereo as cs
    import discover_cameras as dc
    return cs, cc, dc


def parse_args(argv, dc):
    p = argparse.ArgumentParser(description="Camera A -> on-device H.264 -> localhost RTSP gateway (Task 06)")
    p.add_argument("--expect", required=True, metavar="IP=DEVICE_ID")
    p.add_argument("--baseline-user", type=pathlib.Path, required=True)
    p.add_argument("--baseline-factory", type=pathlib.Path, required=True)
    p.add_argument("--seconds", type=float, default=60.0)
    p.add_argument("--fps", type=float, default=20.0)
    p.add_argument("--bitrate-kbps", type=int, default=8000)
    p.add_argument("--keyint", type=int, default=20, help="keyframe (IDR) every N frames; bounds the resync time")
    p.add_argument("--queue-frames", type=int, default=10, help="host GopQueue per eye")
    p.add_argument("--device-queue", type=int, default=8, help="DepthAI host output queue per eye (non-blocking)")
    p.add_argument("--max-send-age-ms", type=float, default=150.0)
    p.add_argument("--frame-end", choices=pc.FRAME_END_MODES, default="sei")
    p.add_argument("--stale-policy", choices=gc.STALE_POLICIES, default="resync",
                   help="resync (validated default) | catchup (proposed 6 Nov, opt-in, under review)")
    p.add_argument("--hard-max-age-ms", type=float, default=500.0, help="catchup only: never send a frame older than this")
    p.add_argument("--sink", choices=("rtsp", "file"), default="rtsp")
    p.add_argument("--server", default="rtsp://127.0.0.1:8554")
    p.add_argument("--label", default="preview")
    p.add_argument("--frame-timeout-s", type=float, default=3.0)
    p.add_argument("--post-verify-wait-s", type=float, default=60.0)
    p.add_argument("--post-verify-poll-s", type=float, default=2.0)
    p.add_argument("--allow-non-isolated", action="store_true", help="NOT to be used (kept for parity with camera_validation)")
    p.add_argument("--dump-raw", action="store_true",
                   help="also save each eye's UNMODIFIED encoder output (camA_<eye>_raw.h264, Annex-B as received)")
    p.add_argument("--stop-file", type=pathlib.Path,
                   help="end the stream cleanly (stop reason stop_file) as soon as this file exists; the normal "
                        "shutdown and calibration verification still run (used by the Stage 2 runner)")
    p.add_argument("--live", action="store_true", help="actually connect to the camera (needs approval)")
    p.add_argument("--extended-test", action="store_true",
                   help="13 Nov 2026, researcher-approved opt-in: allows --seconds up to a hard 600 for the extended live S4.1 "
                        "walkthrough; without it the validated 5-120 s preview limit applies unchanged")
    p.add_argument("--network-scope", choices=("isolated", "ethernet_scoped"), default="isolated",
                   help="isolated (validated default: Wi-Fi off) | ethernet_scoped (concurrent Wi-Fi; see the header)")
    p.add_argument("--camera-mac", default=ns.CAMERA_A_MAC, help="ethernet_scoped: the recorded Camera A MAC (ARP check)")
    p.add_argument("--scope-check-interval-s", type=float, default=5.0, help="ethernet_scoped: re-check period while streaming")
    a = p.parse_args(argv)
    a.expect = dc.parse_expectation(p, a.expect)
    a.width, a.height = gc.WIDTH, gc.HEIGHT
    checks = [
        (a.expect[1] == CAMERA_A_ID, "this gateway is Camera A only (device {})".format(CAMERA_A_ID)),
        (5.0 <= a.seconds <= (EXTENDED_MAX_S if a.extended_test else 120.0),
         "--seconds must be 5-{} ({})".format(int(EXTENDED_MAX_S), "extended test, hard maximum") if a.extended_test else "--seconds must be 5-120 (preview scale)"),
        (10.0 <= a.fps <= 30.0, "--fps must be 10-30"),
        (1000 <= a.bitrate_kbps <= 20000, "--bitrate-kbps must be 1000-20000"),
        (5 <= a.keyint <= 60, "--keyint must be 5-60"),
        (2 <= a.queue_frames <= 40, "--queue-frames must be 2-40"),
        (1 <= a.device_queue <= 64, "--device-queue must be 1-64"),
        (0 <= a.max_send_age_ms <= 1000, "--max-send-age-ms must be 0-1000"),
        (0.5 <= a.frame_timeout_s <= 30, "--frame-timeout-s must be 0.5-30"),
        (5.0 <= a.post_verify_wait_s <= 180.0, "--post-verify-wait-s must be 5-180"),
        (re.fullmatch(r"[A-Za-z0-9_\-]{1,32}", a.label) is not None, "--label: 1-32 letters, digits, _ or -"),
        (a.baseline_user.is_file() and a.baseline_factory.is_file(), "baseline files must exist"),
        (not (a.network_scope == "ethernet_scoped" and a.allow_non_isolated), "--network-scope ethernet_scoped cannot be combined with --allow-non-isolated"),
        (re.fullmatch(r"([0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}", a.camera_mac) is not None, "--camera-mac must be a MAC address"),
        (1.0 <= a.scope_check_interval_s <= 30.0, "--scope-check-interval-s must be 1-30"),
    ]
    for ok, msg in checks:
        if not ok:
            p.error(msg)
    if a.sink == "rtsp":
        try:
            pc.check_local_url(a.server)
        except ValueError as exc:
            p.error(str(exc))
    return a


def plan(a) -> dict:
    mpix = 2 * a.width * a.height * a.fps / 1e6
    return {"camera": "A", "device": {"ip": a.expect[0], "id": a.expect[1]}, "seconds": a.seconds,
            "rectification": "StereoDepth: rectification on, distortion correction ON, alpha unset, edge fill 0, no spec translation",
            "encoder": {"profile": "H264_BASELINE", "rate_control": "CBR", "bitrate_kbps_per_eye": a.bitrate_kbps,
                        "keyframe_every": a.keyint, "b_frames": 0, "fps": a.fps, "input": "GRAY8 1280x800 (DepthAI converts to NV12)",
                        "encoder_load_mpix_per_s": round(mpix, 2), "documented_limit_mpix_per_s": 248},
            "sink": a.sink, "server": a.server if a.sink == "rtsp" else None,
            "network_scope": getattr(a, "network_scope", "isolated"),
            "duration_limit_s": EXTENDED_MAX_S if getattr(a, "extended_test", False) else 120.0,
            "extended_test": bool(getattr(a, "extended_test", False)),

            "device_selection": "broadcast pre-check (validated)" if getattr(a, "network_scope", "isolated") == "isolated"
                                else "unicast DeviceInfo(ip) after the ethernet-scoped check; no broadcast discovery",
            "paths": ["camA_left", "camA_right"], "frame_end": a.frame_end, "config_id": gc.CONFIG_ID,
            "host_queue_frames": a.queue_frames, "device_queue": a.device_queue, "max_send_age_ms": a.max_send_age_ms,
            "stale_policy": a.stale_policy, "hard_max_age_ms": a.hard_max_age_ms if a.stale_policy == "catchup" else None,
            "safeguards": ["Camera A identity verified", "OV9282 1280x800 MONO mode", "calibration == baselines before start",
                           "IR off acknowledged before and after start", "AutoCalibrationMode OFF confirmed",
                           "in-session and post-run calibration verification", "no device writes"]}


def build_pipeline(dai, device, args, report, cs):
    pipeline = dai.Pipeline(device)
    pipeline.setAutoCalibrationMode(dai.Pipeline.AutoCalibrationMode.OFF)
    mode = pipeline.getAutoCalibrationMode()
    report["auto_calibration_mode"] = str(mode)
    if mode != dai.Pipeline.AutoCalibrationMode.OFF:
        raise cs.SafetyAbort("AutoCalibrationMode is {}, refusing to start (it may flash calibration)".format(mode))
    outs = {}
    for eye, sock in (("left", dai.CameraBoardSocket.CAM_B), ("right", dai.CameraBoardSocket.CAM_C)):
        cam = pipeline.create(dai.node.Camera).build(sock, sensorResolution=(args.width, args.height), sensorFps=args.fps)
        outs[eye] = cam.requestOutput((args.width, args.height), type=dai.ImgFrame.Type.GRAY8, fps=args.fps,
                                      enableUndistortion=False)
    stereo = pipeline.create(dai.node.StereoDepth)
    outs["left"].link(stereo.left)
    outs["right"].link(stereo.right)
    stereo.setInputResolution(args.width, args.height)
    stereo.setRectification(True)
    stereo.enableDistortionCorrection(True)
    stereo.setRectificationUseSpecTranslation(False)
    stereo.setRectifyEdgeFillColor(0)
    queues, enc_report = {}, {}
    for eye, src in (("left", stereo.rectifiedLeft), ("right", stereo.rectifiedRight)):
        enc = pipeline.create(dai.node.VideoEncoder).build(src, frameRate=args.fps,
                                                          profile=dai.VideoEncoderProperties.Profile.H264_BASELINE,
                                                          keyframeFrequency=args.keyint)
        enc.setRateControlMode(dai.VideoEncoderProperties.RateControlMode.CBR)
        enc.setBitrateKbps(args.bitrate_kbps)
        enc.setNumBFrames(0)
        enc_report[eye] = {g: str(getattr(enc, g)()) for g in ("getProfile", "getRateControlMode", "getBitrateKbps",
                                                                "getKeyframeFrequency", "getNumBFrames", "getFrameRate")}
        queues[eye] = enc.out.createOutputQueue(maxSize=args.device_queue, blocking=False)
    report["pipeline"] = {
        "cameras": "CAM_B (left) / CAM_C (right) Camera.requestOutput GRAY8 1280x800, enableUndistortion=False",
        "fps": args.fps,
        "stereo": {"rectification": True, "distortion_correction": "on", "rectification_use_spec_translation": False,
                   "edge_fill_color": 0, "alpha_scaling": "DepthAI default (unset)",
                   "outputs_used": ["rectifiedLeft", "rectifiedRight"], "depth_disparity": "not used, not sent"},
        "encoders": enc_report, "host_queue": {"maxSize": args.device_queue, "blocking": False}}
    return pipeline, queues


class AuStats:
    def __init__(self):
        self.c = {"frames": 0, "recovery_points": 0, "idr": 0, "sps": 0, "aud": 0, "no_slice": 0, "frame_meta_present": 0}
        self.frame_types, self.sizes, self.first_nal_types = {}, set(), None
        self.recovery_gaps, self._since = [], None
        self.profile_idc = None

    def add(self, f: gc.CameraFrame):
        i = f.info
        self.c["frames"] += 1
        self.c["recovery_points"] += int(i.recovery_point)
        self.c["idr"] += int(i.has_idr)
        self.c["sps"] += int(i.has_sps)
        self.c["aud"] += int(i.has_aud)
        self.c["no_slice"] += int(i.vcl_count == 0)
        self.c["frame_meta_present"] += int(i.has_frame_meta)
        self.frame_types[str(f.frame_type)] = self.frame_types.get(str(f.frame_type), 0) + 1
        self.sizes.add((f.width, f.height))
        if self.first_nal_types is None:
            self.first_nal_types = i.nal_types
        if i.has_sps and self.profile_idc is None:
            self.profile_idc = pc.sps_profile_idc(f.au)
        if i.recovery_point:
            if self._since is not None:
                self.recovery_gaps.append(self._since)
            self._since = 1
        elif self._since is not None:
            self._since += 1

    def summary(self):
        return dict(self.c, frame_types=self.frame_types, sizes=sorted(self.sizes), first_au_nal_types=self.first_nal_types,
                    sps_profile_idc=self.profile_idc,
                    recovery_interval_frames=statistics.median(self.recovery_gaps) if self.recovery_gaps else None)


def hardware_checks(report, args):
    """Informational verdicts for the first physical test (NOT_TESTED when there is no data)."""
    au, pm = report.get("au_stats", {}), report.get("pairing", {})
    out = {}

    def v(ok, tested):
        return "NOT_TESTED" if not tested else ("PASS" if ok else "FAIL")
    for eye in gc.EYES:
        s = au.get(eye) or {}
        n = s.get("frames", 0)
        out[eye] = {
            "h264_baseline_profile_66": v(s.get("sps_profile_idc") == 66, s.get("sps_profile_idc") is not None),
            "size_1280x800": v(s.get("sizes") == [(args.width, args.height)] or s.get("sizes") == [[args.width, args.height]], n > 0),
            "no_b_frames": v(s.get("frame_types", {}).get("B", 0) == 0, n > 0),
            "recovery_interval_equals_keyint": v(s.get("recovery_interval_frames") == args.keyint, s.get("recovery_interval_frames") is not None),
            "every_au_has_a_slice": v(s.get("no_slice", 0) == 0, n > 0),
            "no_foreign_frame_meta": v(s.get("frame_meta_present", 0) == 0, n > 0),
        }
    out["stereo_pairs_equal_seq_and_skew_le_1ms"] = v(pm.get("pairs", 0) > 0 and pm.get("skew_violations", 1) == 0,
                                                      pm.get("pairs", 0) > 0)
    rate = report.get("capture_rate_fps")
    out["capture_rate_within_5pct"] = v(rate is not None and abs(rate - args.fps) <= 0.05 * args.fps, rate is not None)
    return out


def stream(dai, queues, args, out_dir, report, log, now=pc.mono_ns, make_output=None, stop_flag=None):
    """Capture loop (this thread) plus one sender per eye. Returns the stop reason."""
    host, session, trial = pc.host_id(), "camgw", args.label
    gq = {e: gc.GopQueue(e, args.queue_frames, on_event=log.emit) for e in gc.EYES}
    params, monitor, stats = go.ParamStore(), gc.PairMonitor(), {e: AuStats() for e in gc.EYES}
    sent_fh, sent_w = go.sent_writer(out_dir / "sent.csv")
    lock = threading.Lock()
    if make_output is None:
        def make_output(eye, seg):
            if args.sink == "rtsp":
                return go.PreEncodedOutput("{}/cam{}_{}".format(args.server.rstrip("/"), gc.CAMERA, eye), "rtsp", int(args.fps))
            return go.PreEncodedOutput(str(out_dir / "cam{}_{}_seg{}.ts".format(gc.CAMERA, eye, seg)), "file", int(args.fps))
    senders = {e: go.EyeSender(e, gq[e], params, make_output, log, sent_w, lock, host, session, trial, args.frame_end,
                               args.max_send_age_ms, stale_policy=getattr(args, "stale_policy", "resync"),
                               hard_max_age_ms=getattr(args, "hard_max_age_ms", 500.0)) for e in gc.EYES}
    for s in senders.values():
        s.start()
    cap_fh = open(out_dir / "captured.csv", "w", newline="", encoding="utf-8")
    cap_w = csv.DictWriter(cap_fh, fieldnames=CAPTURED_FIELDS)
    cap_w.writeheader()
    raw = {e: open(out_dir / "cam{}_{}_raw.h264".format(gc.CAMERA, e), "wb") for e in gc.EYES} if getattr(args, "dump_raw", False) else None
    t_start = now()
    last_rx, first_rx, n_rx = t_start, None, 0
    stop_file = getattr(args, "stop_file", None)
    next_stop_check = t_start
    reason = "seconds_reached"
    try:
        while True:
            t = now()
            if (t - t_start) / 1e9 >= args.seconds:
                break
            if stop_flag is not None and stop_flag.is_set():
                reason = "stopped"
                break
            if stop_file is not None and t >= next_stop_check:
                next_stop_check = t + 100_000_000
                if pathlib.Path(stop_file).exists():
                    reason = "stop_file"
                    log.emit("stop_file_seen", {"path": str(stop_file)})
                    break
            got = False
            for eye in gc.EYES:
                msg = queues[eye].tryGet()
                if msg is None:
                    continue
                got, last_rx = True, now()
                f = gc.frame_from_encoded(eye, msg, last_rx)
                first_rx = first_rx or last_rx
                n_rx += 1
                stats[eye].add(f)
                params.offer(f)
                monitor.add(f)
                queued = gq[eye].put(f)
                if raw is not None:
                    raw[eye].write(f.au)
                cap_w.writerow({"eye": eye, "seq": f.seq, "t_dev_ns": f.t_dev_ns, "t_host_mono_ns": f.t_host_mono_ns,
                                "t_received_mono_ns": f.t_received_mono_ns,
                                "host_receipt_minus_capture_ms": round((f.t_received_mono_ns - f.t_host_mono_ns) / 1e6, 2),
                                "frame_type": f.frame_type, "recovery_point": int(f.recovery_point), "idr": int(f.info.has_idr),
                                "sps": int(f.info.has_sps), "aud": int(f.info.has_aud), "bytes": len(f.au), "queued": int(queued),
                                "nal_types": " ".join(str(t) for t in f.info.nal_types), "width": f.width, "height": f.height})
            if not got:
                if (now() - last_rx) / 1e9 > args.frame_timeout_s:
                    report["errors"].append("no encoded frame on either eye within {} s".format(args.frame_timeout_s))
                    reason = "frame_timeout"
                    break
                time.sleep(0.001)
    finally:
        for q in gq.values():
            q.close()
        for s in senders.values():
            s.stop()
        joined = {}
        for e, s in senders.items():
            s.join(5.0)
            joined[e] = not s.is_alive()
        cap_fh.close()
        sent_fh.close()
        if raw is not None:
            for fh in raw.values():
                fh.close()
        span = (last_rx - first_rx) / 1e9 if first_rx and last_rx > first_rx else None
        report["capture_rate_fps"] = round(n_rx / 2 / span, 3) if span else None
        report["au_stats"] = {e: stats[e].summary() for e in gc.EYES}
        report["pairing"] = monitor.summary()
        report["gop_queues"] = {e: dict(gq[e].c) for e in gc.EYES}
        report["senders"] = {e: dict(senders[e].c, segments=senders[e].segment, joined=joined[e]) for e in gc.EYES}
    return reason


def connect_unicast_verified(dai, args, report, cs):
    """ethernet_scoped selection: unicast DeviceInfo(ip) (no broadcast), then the validated identity check."""
    ip, device_id = args.expect
    sel = {"requested_ip": ip, "expected_device_id": device_id, "errors": [],
           "method": "unicast DeviceInfo(ip) after the ethernet-scoped network check; no broadcast discovery"}
    report["selection"] = sel
    t0 = time.monotonic()
    device = dai.Device(dai.DeviceInfo(ip))
    sel["connect_seconds"] = round(time.monotonic() - t0, 2)
    sel["actual_device_id"] = device.getDeviceId()
    sel["actual_ip"] = getattr(device.getDeviceInfo(), "name", None)
    if (sel["actual_device_id"], sel["actual_ip"]) != (device_id, ip):
        sel["errors"].append("connected to {} at {}".format(sel["actual_device_id"], sel["actual_ip"]))
        try:
            device.close()
        finally:
            raise cs.SafetyAbort("identity mismatch after connecting; device closed")
    return device


def reconnect_unicast_and_read(dai, expect, cc, wait_s=60.0, poll_s=2.0):
    """ethernet_scoped post-run read: as calibration_check.reconnect_and_read, but unicast (the camera is back in its
    bootloader when a connection succeeds again); verified identity; read-only; always closes."""
    ip, device_id = expect
    rec = {"requested_ip": ip, "expected_device_id": device_id, "status": "not_attempted", "errors": [],
           "connect_attempts": 0, "method": "unicast DeviceInfo(ip); no broadcast discovery"}
    t0, device = time.monotonic(), None
    try:
        while True:
            rec["connect_attempts"] += 1
            try:
                t1 = time.monotonic()
                device = dai.Device(dai.DeviceInfo(ip))
                rec["connect_seconds"] = round(time.monotonic() - t1, 2)
                break
            except Exception as exc:        # noqa: BLE001  (still rebooting: retry until wait_s)
                rec["last_connect_error"] = "{}: {}".format(type(exc).__name__, exc)
                if time.monotonic() - t0 >= wait_s:
                    rec["status"] = "camera_not_back"
                    rec["errors"].append("no unicast connection within {} s: {}".format(round(time.monotonic() - t0, 1), rec["last_connect_error"]))
                    return rec
                time.sleep(poll_s)
        rec["waited_s"] = round(time.monotonic() - t0, 2)
        rec["actual_device_id"] = device.getDeviceId()
        rec["actual_ip"] = getattr(device.getDeviceInfo(), "name", None)
        if (rec["actual_device_id"], rec["actual_ip"]) != (device_id, ip):
            rec["status"] = "identity_mismatch"
            rec["errors"].append("connected to {} at {}".format(rec["actual_device_id"], rec["actual_ip"]))
            return rec
        rec.update(cc.read_user_and_factory(device))
        rec["status"] = "read_ok"
    except Exception as exc:                # noqa: BLE001
        rec["status"] = rec["status"] if rec["status"] == "identity_mismatch" else "error"
        rec["errors"].append("{}: {}".format(type(exc).__name__, exc))
    finally:
        if device is not None:
            try:
                device.close()
                rec["device_closed"] = bool(device.isClosed())
            except Exception as exc:        # noqa: BLE001
                rec["device_closed"] = False
                rec["errors"].append("device.close failed: {}: {}".format(type(exc).__name__, exc))
    return rec


def post_run_verification_scoped(dai, args, before, report, cs, cc):
    """capture_stereo.post_run_verification with the unicast reconnect (same comparisons, same report keys)."""
    rec = reconnect_unicast_and_read(dai, args.expect, cc, wait_s=args.post_verify_wait_s, poll_s=args.post_verify_poll_s)
    entry = {k: v for k, v in rec.items() if k not in ("user", "factory")}
    if rec["status"] == "read_ok":
        entry["vs_before_run"] = cs.compare_calibrations("post-run", rec, before, report)
        entry["baselines"] = []
        for kind, path in (("user", args.baseline_user), ("factory", args.baseline_factory)):
            base = cc.load_baseline(path)
            c = cc.comparison("post-run {}".format(kind), rec[kind], "baseline {}".format(path.name), base["data"])
            c["baseline_sha256"] = base["sha256"]
            entry["baselines"].append(c)
        entry["equal"] = entry["vs_before_run"]["equal"] and all(c["equal"] for c in entry["baselines"])
    else:
        entry["equal"] = None
        report["errors"].append("post-run calibration verification failed ({}): {}".format(rec["status"], rec["errors"]))
    if rec.get("device_closed") is False:
        report["errors"].append("post-run verification device did not close cleanly")
    report["calibration_post_run"] = entry
    return entry


class ScopeMonitor(threading.Thread):
    """ethernet_scoped: re-runs the network check while streaming; any failure sets the stop flag."""

    def __init__(self, check, interval_s, stop_flag, log):
        super().__init__(daemon=True)
        self.check, self.interval_s, self.stop_flag, self.log = check, interval_s, stop_flag, log
        self.done, self.checks, self.failure = threading.Event(), 0, None

    def run(self):
        while not self.done.wait(self.interval_s):
            try:
                res = self.check()
            except Exception as exc:            # noqa: BLE001
                res = {"ok": False, "problems": ["check failed: {}: {}".format(type(exc).__name__, exc)]}
            self.checks += 1
            if not res.get("ok"):
                self.failure = res.get("problems")
                self.log.emit("network_scope_changed", {"problems": self.failure})
                self.stop_flag.set()
                return

    def summary(self):
        return {"checks_while_streaming": self.checks, "interval_s": self.interval_s, "failure": self.failure}


def run(dai, args, out_dir, report, cs, cc, dc, make_output=None, scope_check=None):
    """Returns an exit code. Always stops the pipeline and closes every device it opened."""
    device, pipeline, started, before = None, None, False, None
    report["errors"], report["stop_reason"] = [], None
    log = pc.EventLog(out_dir / "events.jsonl", "gateway_A", "camgw", args.label)
    log.emit("run_start", {"plan": plan(args), "argv": sys.argv[1:]})
    scoped = getattr(args, "network_scope", "isolated") == "ethernet_scoped"
    if scoped and scope_check is None:
        def scope_check():
            return ns.check_now(args.expect[0], args.camera_mac)
    monitor = None
    try:
        if scoped:
            pre = scope_check()
            report["network_scope"] = {"mode": "ethernet_scoped", "pre_check": pre}
            log.emit("network_scope_pre_check", pre)
            if not pre.get("ok"):
                raise cs.SafetyAbort("ethernet-scoped network pre-check refused, nothing contacted: {}".format(pre.get("problems")))
            device = connect_unicast_verified(dai, args, report, cs)
        else:
            device = cs.connect_verified(dai, args, report)
        report["device_read_only"] = {g: dc.safe_call(device, g) for g in READ_ONLY_DEVICE_GETTERS}
        if report["device_read_only"]["getBootloaderVersion"] != EXPECTED_BOOTLOADER:
            raise cs.SafetyAbort("bootloader {} is not the validated {}; refusing".format(
                report["device_read_only"]["getBootloaderVersion"], EXPECTED_BOOTLOADER))
        report["ir_drivers"] = dc.safe_call(device, "getIrDrivers")
        cs.check_sensor_modes(dai, device, args, report)
        before = cc.read_user_and_factory(device)
        report["calibration_before"] = {"user_sha256": before["user_sha256"], "factory_sha256": before["factory_sha256"]}
        (out_dir / "calibration_before_run.json").write_text(json.dumps(before["user"], sort_keys=True), encoding="utf-8")
        (out_dir / "calibration_factory_before_run.json").write_text(json.dumps(before["factory"], sort_keys=True), encoding="utf-8")
        pre = []
        for kind, path in (("user", args.baseline_user), ("factory", args.baseline_factory)):
            base = cc.load_baseline(path)
            c = cc.comparison("before-start {}".format(kind), before[kind], "baseline {}".format(path.name), base["data"])
            c["baseline_sha256"] = base["sha256"]
            pre.append(c)
        report["calibration_vs_baselines_before_start"] = pre
        if not all(c["equal"] for c in pre):
            raise cs.SafetyAbort("calibration differs from the baselines before start; refusing")
        report["ir_off_before_start"] = cs.set_ir_off(device)
        if report["ir_off_before_start"] != {"setIrLaserDotProjectorIntensity": True, "setIrFloodLightIntensity": True}:
            raise cs.SafetyAbort("device did not acknowledge IR off: {}".format(report["ir_off_before_start"]))
        pipeline, queues = build_pipeline(dai, device, args, report, cs)
        pipeline.start()
        started = True
        report["ir_off_after_start"] = cs.set_ir_off(device)
        if report["ir_off_after_start"] != report["ir_off_before_start"]:
            raise cs.SafetyAbort("device did not acknowledge IR off after start: {}".format(report["ir_off_after_start"]))
        log.emit("pipeline_started", {"pipeline": report["pipeline"]})
        stop_flag = None
        if scoped:
            stop_flag = threading.Event()
            monitor = ScopeMonitor(scope_check, args.scope_check_interval_s, stop_flag, log)
            monitor.start()
        report["stop_reason"] = stream(dai, queues, args, out_dir, report, log, make_output=make_output, stop_flag=stop_flag)
        if monitor is not None and monitor.failure is not None:
            report["stop_reason"] = "network_scope_changed"
            report["errors"].append("network scope changed while streaming: {}".format(monitor.failure))
    except KeyboardInterrupt:
        report["stop_reason"] = "interrupted"
    except cs.SafetyAbort as exc:
        report["stop_reason"] = "safety_abort"
        report["errors"].append("SafetyAbort: {}".format(exc))
    except Exception as exc:                    # noqa: BLE001
        report["stop_reason"] = report["stop_reason"] or "error"
        report["errors"].append("{}: {}".format(type(exc).__name__, exc))
        report["traceback"] = traceback.format_exc()
    finally:
        if monitor is not None:
            monitor.done.set()
            monitor.join(10.0)
            report.setdefault("network_scope", {})["monitor"] = monitor.summary()
        checks = []
        if device is not None and before is not None:
            if cs.is_closed(device):
                report["errors"].append("device disconnected before the in-session calibration re-read")
                report["calibration_in_session"] = {"equal": None}
            else:
                try:
                    report["calibration_in_session"] = cs.compare_calibrations("in-session", cc.read_user_and_factory(device), before, report)
                except Exception as exc:        # noqa: BLE001
                    report["calibration_in_session"] = {"equal": None, "error": "{}: {}".format(type(exc).__name__, exc)}
                    report["errors"].append("in-session calibration re-read failed: {}".format(exc))
            checks.append(report["calibration_in_session"]["equal"])
        if pipeline is not None and started:
            try:
                pipeline.stop()
                report["pipeline_stopped"] = True
            except Exception as exc:            # noqa: BLE001
                report["pipeline_stopped"] = False
                report["errors"].append("pipeline.stop failed: {}".format(exc))
        if device is not None:
            try:
                if not cs.is_closed(device):
                    device.close()
                report["device_closed"] = cs.is_closed(device)
            except Exception as exc:            # noqa: BLE001
                report["device_closed"] = False
                report["errors"].append("device.close failed: {}".format(exc))
        if started and before is not None:
            try:
                checks.append((post_run_verification_scoped(dai, args, before, report, cs, cc) if scoped
                               else cs.post_run_verification(dai, args, before, report))["equal"])

            except Exception as exc:            # noqa: BLE001
                checks.append(None)
                report["errors"].append("post-run calibration verification crashed: {}".format(exc))
        report["calibration_unchanged"] = None if not checks or None in checks else all(checks)
        report["hardware_checks"] = hardware_checks(report, args)
        log.emit("run_end", {"stop_reason": report["stop_reason"], "errors": report["errors"],
                             "calibration_unchanged": report["calibration_unchanged"]})
        log.close()
    ok = (report["stop_reason"] in ("seconds_reached", "stop_file") and not report["errors"] and report.get("pipeline_stopped")
          and report.get("device_closed") and report.get("calibration_unchanged") is True)
    return 130 if report["stop_reason"] == "interrupted" else (0 if ok else 1)


def main(argv=None, dai=None):
    cs, cc, dc = load_safety_modules()
    args = parse_args(argv, dc)
    print(json.dumps({"plan": plan(args), "live": args.live}, indent=1))
    if not args.live:
        print("PLAN ONLY: no device searched, contacted or configured (add --live, with approval, to run).")
        return 0
    if dai is None:
        import depthai as dai
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = RESULTS / "gw_{}_A_{}".format(stamp, args.label)
    out_dir.mkdir(parents=True, exist_ok=False)
    report = {"tool": "camera_gateway_a.py", "depthai": getattr(dai, "__version__", None), "pyav": go.av.__version__,
              "started": dt.datetime.now().isoformat(), "plan": plan(args),
              "safety_sources_sha256": SAFETY_SOURCES, "host": pc.host_id()}
    code = run(dai, args, out_dir, report, cs, cc, dc)
    report["exit_code"] = code
    (out_dir / "report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print("RESULT: {} (stop {}, calibration unchanged {}, errors {}) -> {}".format(
        "PASS" if code == 0 else "FAIL", report["stop_reason"], report.get("calibration_unchanged"), len(report["errors"]), out_dir))
    return code


if __name__ == "__main__":
    sys.exit(main())

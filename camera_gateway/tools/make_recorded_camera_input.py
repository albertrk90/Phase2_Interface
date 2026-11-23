"""Offline Unity replay input from REAL Camera A imagery, through the actual gateway code.

The five rectified Camera A pairs of the approved Stage E E1 run (read-only) are
cycled at 20 fps for --seconds, encoded per eye by the libx264 stand-in
(tools/standin_encoder.py; NOT the OAK encoder) and fed as stand-in EncodedFrames
through camera_gateway_a.stream() -- the same capture loop, GopQueue, EyeSender,
packaging (FrameMeta SEI with FLAG_SYNTHETIC clear, end-of-frame SEI) and
template muxer the live gateway uses -- into MPEG-TS files instead of RTSP.

Faults reproduced offline (both eyes):
  * device gap: seqs --gap-at .. +2 are never delivered by the "device" -> the
    gateway resyncs and resumes at the next IDR;
  * link loss: the first segment's writer fails after --break-after writes ->
    link_down, backoff, reconnect as segment 2 starting at a recovery point.

Writes, in Unity's file-replay layout (unity/Phase2Client/test_results/inputs/<name>/):
  camA_<eye>_seg<k>.ts, schedule.json (release_ms = the gateway's real send time),
  ref_<eye>_<seq>.y = the decoded luma the receiver must display bit-exactly (not the
  camera source: the stand-in encoder's own loss is reported separately in the manifest),
  plus the gateway's own captured.csv / sent.csv / events.jsonl / report.json.

Run: camera_gateway\\.venv\\Scripts\\python.exe -I camera_gateway\\tools\\make_recorded_camera_input.py [--name camera_E1_A]
"""
import argparse
import csv
import json
import pathlib
import sys
import threading
import time
import types

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
GW = HERE.parent
sys.path[:0] = [str(GW), str(HERE)]

import av  # noqa: E402
import numpy as np  # noqa: E402

import camera_gateway_a as cga  # noqa: E402
import gateway_core as gc  # noqa: E402
import gateway_output as go  # noqa: E402
import standin_encoder as se  # noqa: E402
from gateway_core import pc  # noqa: E402

UNITY_INPUTS = GW.parent / "unity" / "Phase2Client" / "test_results" / "inputs"
MS = 1_000_000


class Q:
    def __init__(self):
        self.d, self.lock = [], threading.Lock()

    def push(self, m):
        with self.lock:
            self.d.append(m)

    def tryGet(self):
        with self.lock:
            return self.d.pop(0) if self.d else None


class BreakingOutput(go.PreEncodedOutput):
    """File output whose FIRST segment fails after n writes (simulated link loss)."""

    def __init__(self, path, seg, n):
        super().__init__(str(path), "file", 20)
        self.seg, self.n = seg, n

    def write(self, au, seq, keyframe):
        if self.seg == 1 and self.writes >= self.n:
            raise BrokenPipeError("simulated link loss (offline input)")
        return super().write(au, seq, keyframe)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="camera_E1_A")
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--gap-at", type=int, default=125)
    ap.add_argument("--break-after", type=int, default=200)
    ap.add_argument("--bitrate-kbps", type=int, default=8000)
    ap.add_argument("--keyint", type=int, default=20)
    a = ap.parse_args(argv)
    out = UNITY_INPUTS / a.name
    if out.exists():
        raise SystemExit("refusing to overwrite existing input folder {}".format(out))
    out.mkdir(parents=True)
    fps = 20
    n = int(a.seconds * fps)
    pairs = se.load_e1_pairs()
    src = {"left": [pairs[k % 5][1] for k in range(n)], "right": [pairs[k % 5][2] for k in range(n)]}
    aus = {e: se.encode_sequence(src[e], keyint=a.keyint, bitrate_kbps=a.bitrate_kbps) for e in gc.EYES}
    gap = set(range(a.gap_at, a.gap_at + 3))

    queues = {e: Q() for e in gc.EYES}
    args = types.SimpleNamespace(seconds=a.seconds + 1.5, fps=float(fps), queue_frames=10, max_send_age_ms=150.0,
                                 frame_end="sei", sink="file", server=None, label=a.name, frame_timeout_s=1.0,
                                 width=gc.WIDTH, height=gc.HEIGHT, keyint=a.keyint)

    def feed():
        t0 = pc.mono_ns()
        for k in range(n):
            target = t0 + k * 50 * MS
            while pc.mono_ns() < target:
                time.sleep(0.0005)
            cap = pc.mono_ns() - 25 * MS            # stand-in capture time: 25 ms before host receipt
            if k in gap:
                continue
            for e in gc.EYES:
                au = aus[e][k]
                queues[e].push(se.FakeEncodedFrame(k, 5_000_000_000 + k * 50 * MS, cap, au, gc.inspect_au(au).first_slice_type))

    def make_output(eye, seg):
        return BreakingOutput(out / "camA_{}_seg{}.ts".format(eye, seg), seg, a.break_after)

    report = {"errors": [], "tool": "make_recorded_camera_input.py"}
    log = pc.EventLog(out / "gateway_events.jsonl", "gateway_A_offline", "camgw", a.name)
    th = threading.Thread(target=feed, daemon=True)
    th.start()
    reason = cga.stream(None, queues, args, out, report, log, make_output=make_output)
    log.close()
    report["stop_reason"] = reason
    report["hardware_checks_on_standin"] = cga.hardware_checks(report, args)
    (out / "gateway_report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    for nm in ("captured.csv", "sent.csv"):
        (out / nm).rename(out / ("gateway_" + nm))

    # schedule (Unity file replay): release = the gateway's real send time, relative to the first send
    rows = list(csv.DictReader(open(out / "gateway_sent.csv", encoding="utf-8")))
    t0 = min(int(r["t_sent_mono_ns"]) for r in rows)
    eyes = {e: [] for e in gc.EYES}
    for r in rows:
        eyes[r["eye"]].append({"seq": int(r["seq"]), "segment": int(r["segment"]),
                               "release_ms": round((int(r["t_sent_mono_ns"]) - t0) / 1e6, 3),
                               "t_dev_ns": int(r["t_dev_ns"]), "t_host_mono_ns": int(r["t_host_mono_ns"]),
                               "t_utc_ns": int(r["t_utc_ns"]), "flags": int(r["flags"])})
    segments = max(int(r["segment"]) for r in rows)
    # reference = what a receiver must display: decode each segment and take the raw Y plane by SEI seq
    ref_seqs, quality = [], []
    for e in gc.EYES:
        for k in range(1, segments + 1):
            with av.open(str(out / "camA_{}_seg{}.ts".format(e, k))) as c:
                for pkt in c.demux(video=0):
                    data = bytes(pkt)
                    if not data or not any(t in pc.VCL_TYPES for t, _, _ in pc.split_nals(data)):
                        continue
                    m, _err = pc.extract_meta(data)
                    for fr in pkt.decode():
                        y = se.y_plane(fr)
                        if m is not None and m.seq % 25 == 0:
                            (out / "ref_{}_{:04d}.y".format(e, m.seq)).write_bytes(y)
                            if e == "left":
                                ref_seqs.append(m.seq)
                            x = np.frombuffer(y, np.uint8).astype(float) - np.frombuffer(src[e][m.seq], np.uint8)
                            quality.append(10 * np.log10(255 ** 2 / max(np.mean(x * x), 1e-9)))
    manifest = {
        "generator": "camera_gateway/tools/make_recorded_camera_input.py", "created_utc": pc.iso_utc(pc.utc_ns()),
        "source": "camera", "imagery": "real rectified Camera A pairs, Stage E E1 (approved configuration), cycled",
        "imagery_dir": str(se.E1_IMAGES), "encoder": "libx264 stand-in (NOT the OAK encoder), H.264 Baseline, CBR {} kbps, keyint {}, 0 B".format(a.bitrate_kbps, a.keyint),
        "camera": "A", "width": gc.WIDTH, "height": gc.HEIGHT, "fps": fps, "frame_end": "sei", "session": "camgw",
        "trial": a.name, "host": pc.host_id(), "config_id": gc.CONFIG_ID, "segments": segments,
        "faults": {"device_gap": sorted(gap), "link_break_after_writes": a.break_after},
        "standin_quality_vs_source_psnr_db": {"min": round(min(quality), 2), "median": round(float(np.median(quality)), 2)},
        "ref_seqs": sorted(set(ref_seqs)), "eyes": eyes,
        "gateway": {k: report.get(k) for k in ("stop_reason", "gop_queues", "senders", "pairing", "hardware_checks_on_standin")}}
    (out / "schedule.json").write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"out": str(out), "segments": segments, "frames_left": len(eyes["left"]),
                      "frames_right": len(eyes["right"]), "ref_seqs": len(set(ref_seqs)),
                      "gop_queues": report["gop_queues"], "senders": report["senders"],
                      "standin_psnr": manifest["standin_quality_vs_source_psnr_db"]}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

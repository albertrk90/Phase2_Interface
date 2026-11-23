"""Offline tests for streaming_poc (no network, no server, no camera).

Run: streaming_poc\\.venv\\Scripts\\python.exe -I test_streaming_poc.py
"""
import json
import os
import pathlib
import random
import shutil
import sys
import tempfile
import time
from fractions import Fraction

POC = pathlib.Path(r"C:\Users\a1920234\Documents\Phase2_Interface\streaming_poc")
sys.path.insert(0, str(POC))

import av  # noqa: E402
import poc_common as pc  # noqa: E402
import synthetic_stereo as ss  # noqa: E402
import receive_reference as rr  # noqa: E402
import analyse_poc as ap  # noqa: E402

RESULTS = []
TMP = pathlib.Path(tempfile.mkdtemp(prefix="poc_test_",
                                    dir=os.environ.get("POC_TMP") or None))


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + str(detail)) if detail and not cond else ""))


def meta(seq, eye="left", cam="A", flags=pc.FLAG_SYNTHETIC, t=None):
    t = t or pc.utc_ns()
    return pc.FrameMeta(cam, eye, seq, 123456789, pc.mono_ns(), t, "host-x", "sess", "trial-1", 7, flags)


# 1. emulation prevention
rng = random.Random(4)
ok = True
for _ in range(500):
    raw = bytes(rng.choice([0, 0, 0, 1, 2, 3, rng.randrange(256)]) for _ in range(rng.randrange(1, 200)))
    e = pc.add_emulation_prevention(raw)
    if pc.remove_emulation_prevention(e) != raw:
        ok = False
    for i in range(len(e) - 2):
        if e[i] == 0 and e[i + 1] == 0 and e[i + 2] <= 2:
            ok = False
check("emulation prevention round-trip and no 00 00 0x (x<=2) in EBSP", ok)

# 2. SEI round trip, CRC, foreign UUID
m = meta(0xFFFFFFFF + 5, "right", "B", pc.FLAG_SYNTHETIC | pc.FLAG_BURST)
nal = pc.build_sei_nal(m)
got, err = pc.extract_meta(nal)
check("SEI round-trip (64-bit seq, right/B, flags, strings)", got == m and err is None, (got, err))
check("SEI NAL has no start-code emulation inside", nal[4:].find(b"\x00\x00\x01") < 0)
bad = bytearray(nal)
bad[-10] ^= 0x01
got, err = pc.extract_meta(bytes(bad))
check("corrupted SEI -> CRC error, no meta", got is None and err is not None, err)
foreign = nal.replace(pc.SEI_UUID, bytes(16))
check("foreign-UUID SEI ignored", pc.extract_meta(foreign) == (None, None))

# 3. insertion before first VCL, 3- and 4-byte start codes
sps = b"\x00\x00\x00\x01\x67\x42\xc0\x1f\xaa"
pps = b"\x00\x00\x01\x68\xce\x3c\x80"
x264sei = b"\x00\x00\x01\x06\x05\x02\xaa\xbb\x80"
idr = b"\x00\x00\x01\x65\x88\x84\x00\x10"
au = sps + pps + x264sei + idr
out = pc.insert_sei_before_vcl(au, nal)
types = pc.nal_types(out)
check("SEI inserted after SPS/PPS/encoder-SEI, before IDR", types == [7, 8, 6, 6, 5], types)
check("meta found in composed AU", pc.extract_meta(out)[0] == m)
check("profile_idc read from SPS", pc.sps_profile_idc(au) == 66)
avcc = b"".join(len(n).to_bytes(4, "big") + n for n in (b"\x67\x42\x00", b"\x65\x88"))
check("length-prefixed fallback split", pc.nal_types(avcc) == [7, 5])

# 4. barcode on raw frames
ok = True
for seq in (0, 1, 2, 255, 1000, 65535, 2**32 - 1, 123456789):
    for eye in (0, 1):
        for cam in (0, 1):
            if ss.read_barcode(ss.make_luma(seq, eye, cam)) != (seq & 0xFFFFFFFF, eye, cam):
                ok = False
check("barcode encode/decode, all eyes/cameras", ok)
check("all-black strip rejected", ss.read_barcode(bytes(ss.WIDTH * ss.HEIGHT)) is None)
lum = ss.make_luma(5, 0, 0)
lum_r = ss.make_luma(5, 1, 0)
check("eye marker: left block at left edge only",
      lum[400 * ss.WIDTH + 10] == 255 and lum[400 * ss.WIDTH + ss.WIDTH - 10] != 255
      and lum_r[400 * ss.WIDTH + ss.WIDTH - 10] == 255 and lum_r[400 * ss.WIDTH + 10] != 255)
t0 = time.perf_counter()
for s in range(40):
    ss.make_luma(s, s & 1, 0)
gen_ms = (time.perf_counter() - t0) / 40 * 1000
check("frame generation fast enough for 4 eyes x 20 fps (< 5 ms/frame)", gen_ms < 5, "{:.2f} ms".format(gen_ms))


# 5/6. encode (libx264 baseline) -> SEI -> decode, and via an MPEG-TS file
class FakeArgs:
    fps = 20
    encoder = "libx264"
    preset = "veryfast"
    bitrate_kbps = 8000.0
    keyint = 20
    frame_end = "none"
    open_timeout = io_timeout = 3.0


def encode_to_ts(path, n=60, eye="left", cam="A"):
    import publish_synthetic as ps
    out = av.open(str(path), mode="w", format="mpegts")
    eo = ps.EyeOutput.__new__(ps.EyeOutput)
    eo.url, eo.args, eo.out, eo.pts0, eo.profile_idc, eo._chroma = "rtsp://127.0.0.1:8554/x", FakeArgs, out, None, None, None
    eo.writes = 0
    st = out.add_stream("libx264", rate=20)
    st.width, st.height, st.pix_fmt = ss.WIDTH, ss.HEIGHT, "yuv420p"
    st.bit_rate = 8_000_000
    st.codec_context.time_base = Fraction(1, 20)
    st.codec_context.options = {"profile": "baseline", "preset": "veryfast", "tune": "zerolatency",
                                "x264-params": "keyint=20:min-keyint=20:scenecut=0:bframes=0:repeat-headers=1"}
    eo.stream = st
    sent = []
    for s in range(n):
        mm = meta(s, eye, cam)
        eo.mux(eo.encode(ss.make_luma(s, pc.EYES[eye], pc.CAMERAS[cam]), mm))
        sent.append(mm)
    for pkt in st.encode(None):
        out.mux(pkt)
    out.close()
    return sent, eo.profile_idc


ts = TMP / "left.ts"
sent, prof = encode_to_ts(ts)
check("encoder output is Baseline profile (profile_idc 66)", prof == 66, prof)
inp = av.open(str(ts))
vs = inp.streams.video[0]
vs.codec_context.thread_count = 1
metas, codes, ptypes, ok_pairs, nosei = [], [], [], 0, 0
for packet in inp.demux(vs):
    if packet.size == 0:
        continue
    mm, err = pc.extract_meta(bytes(packet))
    if mm is None:
        nosei += 1
    for f in packet.decode():
        y = f.planes[0]
        code = ss.read_barcode(memoryview(y), y.line_size)
        ptypes.append(str(f.pict_type))
        codes.append(code)
        if mm is not None and code == (mm.seq, 0, 0):
            ok_pairs += 1
        if mm is not None:
            metas.append(mm)
inp.close()
check("all 60 frames carry intact SEI after TS mux/demux", len(metas) == 60 and nosei == 0, (len(metas), nosei))
check("SEI equals what was sent", [x.seq for x in metas] == list(range(60)) and metas[3].t_utc_ns == sent[3].t_utc_ns)
check("barcode after lossy encode == SEI for every frame", ok_pairs == 60, ok_pairs)
check("no B-frames decoded", not any("B" in p for p in ptypes), set(ptypes))
check("decoder output 1:1 with packets (no frame delay)", len(codes) == 60, len(codes))

# 7. Presenter logic with an injected clock
events = []


class L:
    def emit(self, t, p, t_utc=None, t_mono=None):
        events.append((t, p, t_mono))


rows = []
P = rr.Presenter("A", 20, 125, L(), rows.append)
base = 10**12
T = lambda ms: base + int(ms * 1e6)  # noqa: E731


def arrive(eye, seq, at_ms, cap_ms=None, flags=pc.FLAG_SYNTHETIC, barcode=None, cam="A"):
    cap = T(seq * 50 if cap_ms is None else cap_ms)
    mm = pc.FrameMeta(cam, eye, seq, 0, cap, cap, "h", "", "", 1, flags)
    P.on_frame(eye, {"meta": mm, "t_arrival_mono": T(at_ms), "t_arrival_utc": T(at_ms),
                     "t_decoded_mono": T(at_ms), "barcode": barcode or (seq, pc.EYES[eye], pc.CAMERAS[cam])})


# normal: seq 0..9 at 50 ms, 20 ms latency, display every 1000/60 ms
disp = []
tick_ms = 0.0
for s in range(10):
    arrive("left", s, s * 50 + 20)
    arrive("right", s, s * 50 + 22)
    while tick_ms < (s + 1) * 50:
        r = P.tick(T(tick_ms), T(tick_ms))
        if r:
            disp.append(r["seq"])
        tick_ms += 1000 / 60
check("normal: each seq displayed once, in order", disp == list(range(10)), disp)
# only left arrives for seq 10 -> must not display unmatched
arrive("left", 10, 520)
r = P.tick(T(530), T(530))
check("unmatched eye never displayed", r is None)
# stall: nothing until 1250 ms, then burst 10..24 (both eyes) arrive at once
t = 540.0
while t < 1250:
    P.tick(T(t), T(t))
    t += 1000 / 60
for s in range(10, 25):
    if s != 10:
        arrive("left", s, 1250)
    arrive("right", s, 1251)
r = P.tick(T(1252), T(1252))
check("after burst, newest pair shown first (latest-frame-wins)", r and r["seq"] == 24, r and r["seq"])
check("burst backlog counted as superseded, not shown", r and r["skipped_superseded"] == 14, r)
fs = [e for e in events if e[0] == "freeze_start"]
fe = [e for e in events if e[0] == "freeze_end"]
check("freeze detected once and ended once", len(fs) == 1 and len(fe) == 1, (len(fs), len(fe)))
last9 = next(x for x in rows if x["seq"] == 9)["t_display_mono_ns"]
expect_ms = (T(1252) - last9) / 1e6
check("freeze duration = time from last new pair to resume",
      fe and abs(fe[0][1]["duration_ms"] - expect_ms) < 0.2, (fe and fe[0][1], expect_ms))
# late arrival of an old seq is discarded
arrive("left", 23, 1260)
check("late (older) frame discarded", P.c["late_discarded"] >= 1)
# gap: seq 25..27 never sent, 28 arrives
arrive("left", 28, 1420)
arrive("right", 28, 1421)
r = P.tick(T(1430), T(1430))
check("missing seqs counted exactly", r and r["skipped_missing"] == 3, r)
# integrity: wrong barcode
arrive("left", 29, 1470, barcode=(999, 0, 0))
arrive("right", 29, 1471)
r = P.tick(T(1480), T(1480))
check("barcode/SEI mismatch flagged as integrity error", r and r["barcode_ok"] == 0 and P.c["integrity_errors"] == 1)
# wrong eye on right path
arrive("left", 30, 1520)
P.on_frame("right", {"meta": pc.FrameMeta("A", "left", 30, 0, T(1500), T(1500), "h", "", "", 1, 1),
                     "t_arrival_mono": T(1521), "t_arrival_utc": T(1521), "t_decoded_mono": T(1521),
                     "barcode": (30, 0, 0)})
r = P.tick(T(1530), T(1530))
check("eye mapping error flagged", r and r["eye_ok"] == 0 and P.c["eye_mismatch"] == 1)

# 8. URL guard
bad_urls = ["rtsp://192.168.1.99:8554/x", "rtsp://127.0.0.1:8080/x", "rtsp://localhost:8081/x",
            "http://127.0.0.1:8554/x", "rtsp://10.0.0.1/x", "rtsp://169.254.1.222:8554/x"]
refused = 0
for u in bad_urls:
    try:
        pc.check_local_url(u)
    except ValueError:
        refused += 1
check("non-loopback hosts, COROL ports and non-RTSP refused", refused == len(bad_urls), refused)
check("loopback RTSP allowed", pc.check_local_url("rtsp://127.0.0.1:8554/camA_left"))

# 9. EventLog format
lp = TMP / "ev.jsonl"
lg = pc.EventLog(lp, "unit", "s1", "t1")
lg.emit("hello", {"x": 1})
lg.close()
rec = pc.read_events(lp)[0]
need = {"event_id", "session", "trial", "source", "type", "t_utc", "t_utc_ns", "t_mono_ns", "host", "payload"}
check("event record has all addendum section 9 fields", need <= set(rec), set(rec) ^ need)

# 10. MediaMTX config: localhost-only, listeners off
cfg = (POC / "config" / "mediamtx_localhost.yml").read_text(encoding="utf-8")
lines = [l.split("#")[0].rstrip() for l in cfg.splitlines()]
kv = {l.split(":", 1)[0].strip(): l.split(":", 1)[1].strip() for l in lines if ":" in l and not l.startswith(" ")}
off = all(kv.get(k) == "false" for k in ("rtmp", "hls", "webrtc", "srt", "moq", "api", "metrics", "pprof", "playback"))
check("config: every listener except RTSP disabled", off, {k: kv.get(k) for k in ("rtmp", "hls", "webrtc", "srt", "moq")})
check("config: RTSP on 127.0.0.1:8554, TCP only", kv.get("rtspAddress") == "127.0.0.1:8554" and kv.get("rtspTransports") == "[tcp]")
addr_ok = all(v.startswith("127.0.0.1:") for k, v in kv.items() if k.endswith("Address"))
check("config: every *Address bound to 127.0.0.1", addr_ok)
check("config: no all_others path; no 8080/8081", "all_others" not in "\n".join(lines) and ":8080" not in cfg and ":8081" not in cfg)
check("config: publish/read restricted to loopback IPs", 'ips: ["127.0.0.1", "::1"]' in cfg and "ips: []" not in cfg)

# 11. analyse_poc on synthetic logs
pub = TMP / "pub"
rx = TMP / "rx"
pub.mkdir()
rx.mkdir()
pl = pc.EventLog(pub / "events.jsonl", "publisher_A")
pl.emit("run_start", {})
pl.emit("link_up", {}, t_utc=T(0))
pl.emit("stall_start", {"index": 0, "at_s": 1, "dur_ms": 700, "mode": "burst"}, t_utc=T(1000))
pl.emit("stall_end", {"index": 0, "mode": "burst", "seq_first": 20, "seq_last": 33, "count": 14}, t_utc=T(1700))
pl.emit("stall_start", {"index": 1, "at_s": 3, "dur_ms": 300, "mode": "drop"}, t_utc=T(3000))
pl.emit("stall_end", {"index": 1, "mode": "drop", "seq_first": 60, "seq_last": 65, "count": 6}, t_utc=T(3300))
pl.close()
(pub / "report.json").write_text(json.dumps({"counts": {"unsent_link_down": 0}, "baseline": True}))
rl = pc.EventLog(rx / "events.jsonl", "receiver_A")
rl.emit("freeze_start", {}, t_utc=T(1130))
rl.emit("freeze_start", {}, t_utc=T(3140))
rl.close()
with open(rx / "frames.csv", "w", newline="") as fh:
    import csv
    w = csv.DictWriter(fh, fieldnames=rr.FRAME_FIELDS)
    w.writeheader()
    seqs = [s for s in range(0, 120) if not (20 <= s <= 32) and not (60 <= s <= 65)]
    prev = None
    for s in seqs:
        disp_ms = s * 50 + 30 if s != 33 else 1702
        age = 30.0 if s != 33 else 30.0
        w.writerow({"t_display_utc_ns": T(disp_ms), "t_display_mono_ns": T(disp_ms), "seq": s,
                    "age_utc_ms_left": age, "age_utc_ms_right": age, "age_mono_ms": age,
                    "arrival_skew_ms": 1, "interval_ms": 50,
                    "skipped_superseded": 13 if s == 33 else 0, "skipped_incomplete": 0,
                    "skipped_missing": 6 if s == 66 else 0, "burst": 1 if s == 33 else 0,
                    "barcode_ok": 1, "eye_ok": 1})
(rx / "summary.json").write_text(json.dumps({
    "seconds": 700, "presenter": {"counts": {"displayed": len(seqs), "integrity_errors": 0, "missing": 6,
                                             "burst_displayed": 1}},
    "readers": {"left": {"decode_errors": 0, "sei_errors": 0, "no_sei": 0, "packets": 100},
                "right": {"decode_errors": 0, "sei_errors": 0, "no_sei": 0, "packets": 100}}}))
rep = ap.analyse(pub, rx)
c = rep["criteria"]
check("analyse: pairing/duration/age/metadata PASS", all(c[k]["verdict"] == "PASS" for k in
      ("G1.1_pairing", "G1.2_duration_decoder", "G1.3_frame_age", "G1.7_metadata")), {k: v["verdict"] for k, v in c.items()})
check("analyse: stale-frame recovery PASS (0 frames)", c["G1.4_stale_frames"]["verdict"] == "PASS", c["G1.4_stale_frames"])
check("analyse: logging exact (6 missing == 6 dropped)", c["G1.5_logging"]["verdict"] == "PASS", c["G1.5_logging"])
check("analyse: no restart -> G1.6 NOT_TESTED, overall INCOMPLETE",
      c["G1.6_reconnect"]["verdict"] == "NOT_TESTED" and rep["overall"] == "INCOMPLETE")

print()
n_fail = sum(1 for _, ok in RESULTS if not ok)
print("{} checks, {} failed".format(len(RESULTS), n_fail))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if n_fail else 0)

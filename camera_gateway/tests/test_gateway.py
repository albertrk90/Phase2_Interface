"""Offline tests for the Camera A gateway (Task 06). No camera, no MediaMTX, no network.

Inputs: the five real rectified Camera A pairs of the approved Stage E E1 run
(read-only), encoded by the libx264 stand-in (tools/standin_encoder.py) with the
settings requested from the OAK encoder. A fake DepthAI module drives the full
safety sequence of camera_gateway_a.run() and refuses any device write.

Covered: access-unit inspection and the recovery-point rule; SEI / frame-end
packaging and its refusals; muxing with the camera's own parameter sets and no
encoder; decoding of the packaged stream and metadata survival through MPEG-TS;
the GOP-aware latest-frame queue (start, device gaps, reversals, overflow,
alignment, a threaded stress run that must only ever deliver decodable chains);
the pair monitor; the per-eye sender (connect failures, link loss and reconnect
to a new segment starting at a recovery point, age guard); the capture loop to
files; and the safety sequence with every refusal path.

Run: camera_gateway\\.venv\\Scripts\\python.exe -I camera_gateway\\tests\\test_gateway.py
"""
import datetime as dt
import hashlib
import io
import json
import pathlib
import random
import shutil
import sys
import tempfile
import threading
import time
import types

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
GW = HERE.parent
sys.path.insert(0, str(GW))
sys.path.insert(0, str(GW / "tools"))
sys.path.insert(0, str(HERE))

import av  # noqa: E402
import numpy as np  # noqa: E402

import camera_gateway_a as cga  # noqa: E402
import gateway_core as gc  # noqa: E402
import gateway_output as go  # noqa: E402
import standin_encoder as se  # noqa: E402
from gateway_core import pc  # noqa: E402

RESULTS = []
MS = 1_000_000


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + str(detail)[:400]) if detail and not cond else ""))


def psnr(a, b):
    x, y = np.frombuffer(a, np.uint8).astype(np.float64), np.frombuffer(b, np.uint8).astype(np.float64)
    mse = float(np.mean((x - y) ** 2))
    return 99.0 if mse == 0 else 10 * np.log10(255 * 255 / mse)


# ------------------------------------------------------------------ real imagery and stand-in AUs
PAIRS = se.load_e1_pairs()
check("five real rectified Camera A pairs loaded from the E1 run (1280 x 800 GRAY8)",
      len(PAIRS) == 5 and all(len(l) == len(r) == 1280 * 800 for _, l, r in PAIRS), [p[0] for p in PAIRS])
N = 45
LEFT = [PAIRS[i % 5][1] for i in range(N)]
RIGHT = [PAIRS[i % 5][2] for i in range(N)]
AU_L = se.encode_sequence(LEFT, keyint=20)
AU_R = se.encode_sequence(RIGHT, keyint=20)
AU_AUD = se.encode_sequence(LEFT[:3], keyint=20, aud=True, slices=2)

# ------------------------------------------------------------------ access-unit inspection
i0, i1 = gc.inspect_au(AU_L[0]), gc.inspect_au(AU_L[1])
check("IDR AU: SPS, PPS, IDR, first slice I -> recovery point", i0.has_sps and i0.has_pps and i0.has_idr
      and i0.first_slice_type == "I" and i0.recovery_point, i0)
check("P AU: first slice P, not a recovery point", i1.first_slice_type == "P" and not i1.recovery_point, i1)
check("recovery points exactly every 20 frames (0, 20, 40)",
      [k for k, a in enumerate(AU_L) if gc.inspect_au(a).recovery_point] == [0, 20, 40])
ia = gc.inspect_au(AU_AUD[0])
check("AUD + 2 slices variant: AUD seen, 2 VCL NALs", ia.has_aud and ia.vcl_count == 2 and ia.recovery_point, ia)
check("single-slice stand-in (threads=1): one VCL NAL per AU", all(gc.inspect_au(a).vcl_count == 1 for a in AU_L), gc.inspect_au(AU_L[0]))
# non-IDR I with SPS/PPS (IDR NAL type rewritten to 1): recovery by the SPS+PPS+I rule; without SPS: not
nals = pc.split_nals(AU_L[0])
au_b = bytearray(AU_L[0])
for t, s, e in nals:
    if t == 5:
        au_b[s] = (au_b[s] & 0xE0) | 1
nonidr = bytes(au_b)
inn = gc.inspect_au(nonidr)
check("non-IDR I-slice AU with SPS+PPS -> recovery point (I rule)", not inn.has_idr and inn.first_slice_type == "I"
      and inn.recovery_point, inn)
no_ps = b"".join(b"\x00\x00\x00\x01" + nonidr[s:e] for t, s, e in pc.split_nals(nonidr) if t not in (7, 8))
check("non-IDR I-slice AU WITHOUT SPS/PPS -> not a recovery point", not gc.inspect_au(no_ps).recovery_point)
check("parameter_sets() returns SPS then PPS", [t for t, _, _ in pc.split_nals(gc.parameter_sets(AU_L[0]))] == [7, 8])
check("SPS profile_idc 66 (Baseline)", pc.sps_profile_idc(AU_L[0]) == 66)

# ------------------------------------------------------------------ packaging
T0 = 10_000 * MS


def cf(eye, seq, au, t_host=None, t_recv=None):
    th = T0 + seq * 50 * MS if t_host is None else t_host
    return gc.CameraFrame(eye, seq, 7_000 * MS + seq * 50 * MS, th, au, th + 5 * MS if t_recv is None else t_recv,
                          gc.inspect_au(au).first_slice_type)


f0 = cf("left", 0, AU_L[0])
meta = gc.make_meta(f0, "HOSTX", "camgw", "t", 1_000)
pk = gc.package(f0, meta)
def expect_layout(au, pk_):
    src = [t for t, _, _ in pc.split_nals(au)]
    first = next(i for i, t in enumerate(src) if t in pc.VCL_TYPES)
    return src[:first] + [6] + src[first:] + [6] == [t for t, _, _ in pc.split_nals(pk_)]


types_ = [t for t, _, _ in pc.split_nals(pk)]
check("packaged IDR: encoder NALs kept, FrameMeta SEI right before the slice, eof SEI after it",
      expect_layout(AU_L[0], pk) and types_[-2:] == [5, 6], types_)
pp1 = gc.package(cf("left", 1, AU_L[1]), gc.make_meta(cf("left", 1, AU_L[1]), "H", "s", "t", 0))
check("packaged P (CBR: encoder SEI, slice, filler NAL 12): FrameMeta before the slice, eof after the filler",
      expect_layout(AU_L[1], pp1) and [t for t, _, _ in pc.split_nals(pp1)][-1] == 6, [t for t, _, _ in pc.split_nals(pp1)])
m2, err = pc.extract_meta(pk)
check("FrameMeta round trip: camera A, eye, seq, device/host/UTC times, config, flags 0",
      err is None and m2 == meta and m2.camera == "A" and m2.t_utc_ns == m2.t_host_mono_ns + 1_000
      and m2.config_id == gc.CONFIG_ID and m2.flags == 0, (m2, err))
check("end-of-frame SEI carries the frame's seq", pc.frame_end_markers(pk)["eof_seq"] == [0])
pa = gc.package(cf("left", 0, AU_AUD[0]), gc.make_meta(cf("left", 0, AU_AUD[0]), "H", "s", "t", 0))
ta = [t for t, _, _ in pc.split_nals(pa)]
check("AUD + 2 slices: SEI after AUD/SPS/PPS(/encoder SEI), once before the first slice; eof after the last slice",
      expect_layout(AU_AUD[0], pa) and ta[0] == 9 and ta[-3:] == [5, 5, 6] and ta.count(5) == 2, ta)
for name, fn in (("already packaged AU", lambda: gc.package(cf("left", 0, pk), meta)),
                 ("AU without a slice", lambda: gc.package(cf("left", 0, gc.parameter_sets(AU_L[0])), meta)),
                 ("metadata of another seq", lambda: gc.package(cf("left", 1, AU_L[1]), meta)),
                 ("metadata of the other eye", lambda: gc.package(cf("right", 0, AU_R[0]), meta)),
                 ("synthetic flag set", lambda: gc.package(f0, pc.FrameMeta(**dict(meta.to_dict(), flags=pc.FLAG_SYNTHETIC))))):
    try:
        fn()
        ok = False
    except gc.PackagingError:
        ok = True
    check("package refuses: {} (designed to fail)".format(name), ok)

# EncodedFrame adapter
fe = se.FakeEncodedFrame(123, 7_000_123_000, 9_000_456_000, AU_L[0], "I")
fr = gc.frame_from_encoded("left", fe, 42)
check("EncodedFrame adapter: seq, timedelta->ns, data, frame type, size",
      (fr.seq, fr.t_dev_ns, fr.t_host_mono_ns, fr.au == AU_L[0], fr.frame_type, fr.width, fr.height, fr.t_received_mono_ns)
      == (123, 7_000_123_000, 9_000_456_000, True, "I", 1280, 800, 42), fr)
check("td_ns exact for days/seconds/us", gc.td_ns(dt.timedelta(days=1, seconds=2, microseconds=3)) == 86_402_000_003_000)


# ------------------------------------------------------------------ muxing + decoding (file)
def write_file(path, frames_):
    o = go.PreEncodedOutput(str(path), "file", 20)
    o.connect(frames_[0].au)
    ok_noenc = not o.stream.codec_context.is_open
    ex = bytes(o.stream.codec_context.extradata)
    for f in frames_:
        o.write(gc.package(f, gc.make_meta(f, "H", "camgw", "t", 0)), f.seq, f.recovery_point)
    o.close()
    return ok_noenc, ex


NON_VCL = []
DEC_ERR = []


def read_ts(path):
    """Demux like the receivers (FFmpeg's H.264 parser). The end-of-frame SEI makes the parser
    close each access unit; it then belongs to the next packet, so the final one arrives as a
    standalone non-VCL packet (counted, not decoded), exactly as the receivers' non_vcl_packets."""
    seqs, eofs, lumas = [], [], []
    with av.open(str(path)) as c:
        for pkt in c.demux(video=0):
            data = bytes(pkt)
            if not data:
                continue
            m, e = pc.extract_meta(data)
            if m:
                seqs.append((m.seq, m.eye, m.flags))
            eofs += pc.frame_end_markers(data)["eof_seq"]
            if not any(t in pc.VCL_TYPES for t, _, _ in pc.split_nals(data)):
                NON_VCL.append(len(data))
                continue
            try:
                for fr_ in pkt.decode():
                    lumas.append(se.y_plane(fr_))
            except av.error.InvalidDataError:
                DEC_ERR.append(len(data))
    return seqs, eofs, lumas


def decode_raw(aus):
    c = av.CodecContext.create("h264", "r")
    out = []
    for a in aus:
        for fr_ in c.decode(av.Packet(a)):
            out.append(se.y_plane(fr_))
    for fr_ in c.decode(None):
        out.append(se.y_plane(fr_))
    return out


tmp = pathlib.Path(tempfile.mkdtemp(prefix="gwtest_"))
try:
    frames_l = [cf("left", k, AU_L[k]) for k in range(N)]
    noenc, ex = write_file(tmp / "l.ts", frames_l)
    check("muxer: no encoder opened on the pre-encoded stream", noenc)
    pl = lambda b: [b[s_:e_] for t_, s_, e_ in pc.split_nals(b)]
    check("container extradata = the camera's own SPS/PPS (NAL payloads identical)",
          pl(ex) == pl(gc.parameter_sets(AU_L[0])) and len(pl(ex)) == 2, (len(ex),))
    seqs, eofs, lumas = read_ts(tmp / "l.ts")
    check("MPEG-TS: every packet keeps its FrameMeta (seq 0..44, left, flags 0) and its end-of-frame SEI",
          seqs == [(k, "left", 0) for k in range(N)] and eofs == list(range(N)), (seqs[:3], eofs[:3]))
    check("all 45 frames decode; only the trailing end-of-frame SEI is a non-VCL packet", len(lumas) == N and NON_VCL == [35], (len(lumas), NON_VCL))
    raw = decode_raw(AU_L)
    check("packaged + muxed stream decodes BIT-IDENTICALLY to the unpackaged camera AUs (packaging never alters a picture)",
          lumas == raw and len(raw) == N)
    ps = [psnr(lumas[k], LEFT[k]) for k in range(len(lumas))]
    print("     info: stand-in encoder quality vs the real source luma: PSNR min {:.1f} / median {:.1f} dB "
          "(libx264 stand-in at 8 Mbit/s CBR; NOT the OAK encoder's quality)".format(min(ps), float(np.median(ps))))
    # a stream that starts at a P-frame would not decode: the queue must prevent it (shown here)
    bad = tmp / "p_start.ts"
    o = go.PreEncodedOutput(str(bad), "file", 20)
    o.connect(AU_L[0])
    for f in frames_l[1:10]:
        o.write(gc.package(f, gc.make_meta(f, "H", "s", "t", 0)), f.seq, False)
    o.close()
    DEC_ERR.clear()
    _s, _e, lp = read_ts(bad)
    check("control: a stream started at a P-frame does not decode cleanly (why GopQueue exists)", len(lp) < 9 or DEC_ERR, (len(lp), DEC_ERR))
    try:
        go.PreEncodedOutput("rtsp://192.168.1.10:8554/camA_left", "rtsp", 20)
        ok = False
    except ValueError:
        ok = True
    check("RTSP target must be loopback (192.168.1.10 refused)", ok)
    try:
        go.PreEncodedOutput("rtsp://127.0.0.1:8080/camA_left", "rtsp", 20)
        ok = False
    except ValueError:
        ok = True
    check("RTSP port 8080 (COROL) refused", ok)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ------------------------------------------------------------------ GopQueue
ev = []
q = gc.GopQueue("left", 5, on_event=lambda k, p: ev.append((k, p)))
fl = [cf("left", k, AU_L[k]) for k in range(N)]
check("starts waiting: P-frames before the first IDR are dropped", not q.put(fl[1]) and q.c["dropped_waiting"] == 1)
q2 = gc.GopQueue("left", 5)
r = [q2.put(f) for f in fl[0:4]]
check("IDR then P-frames queued in order", r == [True] * 4 and [q2.get(0).seq for _ in range(4)] == [0, 1, 2, 3])
q3 = gc.GopQueue("left", 50, on_event=lambda k, p: ev.append((k, p)))
for f in fl[0:5]:
    q3.put(f)
q3.put(fl[7])                                   # device gap of 2
check("device gap: queued frames discarded, P after the gap dropped, gap counted",
      len(q3) == 0 and q3.c["device_gaps"] == 1 and q3.c["device_gap_frames"] == 2 and q3.waiting)
for f in fl[8:20]:
    q3.put(f)
check("... frames dropped until the next IDR (seq 20) resumes", len(q3) == 0 and q3.put(fl[20]) and len(q3) == 1)
q3.put(fl[19])
check("sequence reversal -> resync", q3.c["seq_reversals"] == 1 and len(q3) == 0 and q3.waiting)
q4 = gc.GopQueue("left", 5)
for f in fl[0:12]:
    q4.put(f)
check("bounded: never more than maxlen; overflow resyncs to the next IDR", q4.c["max_depth"] <= 5 and q4.c["overflows"] >= 1
      and len(q4) == 0 and q4.waiting, q4.c)
q5 = gc.GopQueue("left", 10)
for f in fl[0:4]:
    q5.put(f)
q5.align("connect")
check("align on connect keeps a queued IDR at the head", len(q5) == 4 and q5.get(0).seq == 0)
q5.align("connect")
check("align with a P-frame head discards to empty and waits", len(q5) == 0 and q5.waiting)
check("get() on an empty queue times out with None", gc.GopQueue("left", 3).get(0.01) is None)

# threaded stress: random gaps and consumer stalls; consumer must only see decodable chains
random.seed(6)
seqs_all = []
k = 0
while len(seqs_all) < 600:
    if random.random() < 0.03:
        k += random.randint(1, 4)               # device gap
    seqs_all.append(k)
    k += 1
qs = gc.GopQueue("left", 6)
got = []


def consumer():
    while True:
        f = qs.get(0.05)
        if f is None:
            if qs.closed:
                return
            continue
        got.append(f)
        if random.random() < 0.02:
            qs.request_resync("stale")
        if random.random() < 0.05:
            time.sleep(0.004)


th = threading.Thread(target=consumer)
th.start()
for s in seqs_all:
    qs.put(gc.CameraFrame("left", s, 0, 0, AU_L[0] if s % 20 == 0 else AU_L[1], 0))
    time.sleep(0.0005)
qs.close()
th.join(5)
chains_ok, prev = True, None
for f in got:
    if prev is None or f.seq != prev + 1:
        chains_ok &= f.recovery_point           # every discontinuity in the delivered stream is at a recovery point
    prev = f.seq
check("threaded stress (600 frames, random gaps, consumer stalls and resyncs): every chain starts at a recovery point",
      chains_ok and len(got) > 50 and qs.c["max_depth"] <= 6, (len(got), qs.c))

# ------------------------------------------------------------------ PairMonitor
pm = gc.PairMonitor(1.0, keep=4)
for s in range(5):
    pm.add(gc.CameraFrame("left", s, 1000 + s, 0, AU_L[1], 0))
    pm.add(gc.CameraFrame("right", s, 1000 + s + (int(1.5 * MS) if s == 3 else 30_000), 0, AU_R[1], 0))
smy = pm.summary()
check("pair monitor: 5 pairs, one skew 1.5 ms > 1 ms flagged", smy["pairs"] == 5 and smy["skew_violations"] == 1, smy)
for s in range(10, 20):
    pm.add(gc.CameraFrame("left", s, 0, 0, AU_L[1], 0))
check("pair monitor: unpaired frames bounded (keep 4)", pm.summary()["pending"] <= 4 and pm.summary()["unpaired_dropped"] >= 6)


# ------------------------------------------------------------------ EyeSender with fake outputs
class FakeOut:
    def __init__(self, seg, fail_connect=False, fail_after=None, sink=None):
        self.seg, self.fail_connect, self.fail_after, self.sink = seg, fail_connect, fail_after, sink
        self.n = 0

    def connect(self, au, ps):
        if self.fail_connect:
            raise ConnectionRefusedError("server down")

    def write(self, au, seq, key):
        if self.fail_after is not None and self.n >= self.fail_after:
            raise BrokenPipeError("link lost")
        self.n += 1
        self.sink.append((self.seg, seq, key, au))
        return len(au)

    def close(self):
        pass


class Log:
    def __init__(self):
        self.ev = []

    def emit(self, k, p=None):
        self.ev.append((k, p or {}))


def run_sender(plan_outputs, frames_, pace_s=0.002, max_age_ms=150.0, stale_seqs=()):
    log, sink = Log(), []
    gq = gc.GopQueue("left", 8, on_event=log.emit)
    params = go.ParamStore()
    import csv as _csv
    buf = io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=go.SENT_FIELDS)
    w.writeheader()
    made = []

    def make_output(eye, seg):
        o = FakeOut(seg, sink=sink, **plan_outputs(seg))
        made.append(o)
        return o
    s = go.EyeSender("left", gq, params, make_output, log, w, threading.Lock(), "H", "camgw", "t",
                     max_send_age_ms=max_age_ms, reconnect_max_s=0.02, sleep=lambda d: time.sleep(0.001))
    s.start()
    for f in frames_:
        now = pc.mono_ns()
        f.t_host_mono_ns = now - (400 * MS if f.seq in stale_seqs else 5 * MS)
        params.offer(f)
        gq.put(f)
        time.sleep(pace_s)
    time.sleep(0.05)
    s.stop()
    gq.close()
    s.join(2)
    return s, log, sink, buf.getvalue()


frames60 = [gc.CameraFrame("left", k, 0, 0, AU_L[k % 40] if k % 20 else AU_L[0], 0) for k in range(80)]
s, log, sink, sent_csv = run_sender(lambda seg: {"fail_connect": seg <= 2}, frames60)
kinds = [k for k, _ in log.ev]
check("sender: two connect failures logged with backoff, then connected (segment 3)",
      kinds.count("link_connect_failed") == 2 and s.c["connects"] == 1 and all(x[0] == 3 for x in sink), s.c)
check("sender: the first frame written on a connection is a recovery point", sink and sink[0][2] is True, sink[:1])
check("sender: every written AU carries FrameMeta + end-of-frame SEI",
      all(pc.extract_meta(a)[0] is not None and pc.frame_end_markers(a)["eof_seq"] == [q_] for _sg, q_, _k, a in sink))
check("sender: sent.csv rows written", sent_csv.count("\n") == s.c["sent"] + 1, (s.c["sent"],))

s, log, sink, _ = run_sender(lambda seg: {"fail_after": 15 if seg == 1 else None}, frames60)
segs = sorted({x[0] for x in sink})
first2 = next(x for x in sink if x[0] == 2)
check("sender: link lost after 15 writes -> link_down, reconnect as segment 2", segs == [1, 2] and s.c["link_downs"] == 1
      and "link_down" in [k for k, _ in log.ev], (segs, s.c))
check("sender: segment 2 starts at a recovery point", first2[2] is True, first2[:3])
per = {}
mono_ok = True
for sg, q_, _k, _a in sink:
    mono_ok &= per.get(sg, -1) < q_
    per[sg] = q_
check("sender: seq strictly increasing within each segment", mono_ok)
s, log, sink, _ = run_sender(lambda seg: {}, frames60, stale_seqs=set(range(25, 28)))
sent_seqs = [x[1] for x in sink]
check("sender: frames older than 150 ms are not sent, their GOP is dropped, sending resumes at the next IDR (40)",
      not set(range(25, 40)) & set(sent_seqs) and 40 in sent_seqs and s.c["skipped_stale"] >= 1, (s.c, sent_seqs[20:30]))


# ------------------------------------------------------------------ fake DepthAI for run()
import fake_dai  # noqa: E402


def make_fake_dai(calls, **kw):
    return fake_dai.make_fake_dai(calls, AU_L, AU_R, **kw)


FakeDai = fake_dai.FakeDai


cs, cc, dc = cga.load_safety_modules()
work = pathlib.Path(tempfile.mkdtemp(prefix="gwrun_"))


def gw_args(calls_dir, user, factory, extra=()):
    (calls_dir / "u.json").write_text(json.dumps(user), encoding="utf-8")
    (calls_dir / "f.json").write_text(json.dumps(factory), encoding="utf-8")
    a = cga.parse_args(["--expect", "169.254.1.222=19443010B14C872F00", "--baseline-user", str(calls_dir / "u.json"),
                        "--baseline-factory", str(calls_dir / "f.json"), "--seconds", "5", "--sink", "file",
                        "--post-verify-wait-s", "5", "--frame-timeout-s", "1.0", *extra], dc)
    a.allow_non_isolated = True                 # the test laptop is on Wi-Fi; the live run must not use this
    return a


def do_run(name, extra=(), **kw):
    d = work / name
    d.mkdir()
    calls = []
    fake, user, factory = make_fake_dai(calls, **{k: v for k, v in kw.items() if k not in ("baseline_user",)})
    a = gw_args(d, kw.get("baseline_user", user), factory, extra)
    rep = {}
    code = cga.run(fake, a, d, rep, cs, cc, dc)
    return code, rep, calls, d


try:
    code, rep, calls, d = do_run("ok", autocal_sticks=False)
    check("run(): happy path exit 0, stop at --seconds, calibration unchanged, pipeline stopped, device closed",
          code == 0 and rep["stop_reason"] == "seconds_reached" and rep["calibration_unchanged"] is True
          and rep["pipeline_stopped"] and rep["device_closed"], (code, rep.get("stop_reason"), rep.get("errors")))
    order = [c for c in calls if c in ("device_open", "read_user_calibration", "ir_dot_0.0", "autocal_set_OFF", "autocal_get_OFF",
                                        "pipeline_start", "pipeline_stop", "device_close")]
    exp = ["device_open", "read_user_calibration", "ir_dot_0.0", "autocal_set_OFF", "autocal_get_OFF", "pipeline_start",
           "ir_dot_0.0", "read_user_calibration", "pipeline_stop", "device_close", "device_open", "read_user_calibration", "device_close"]
    check("run(): safety order = verify+connect, calibration read, IR off, AutoCal OFF confirmed, start, IR off, "
          "in-session re-read, stop, close, fresh post-run read", order == exp, order)
    check("run(): no forbidden device call (no calibration/firmware/IP/device writes)", not [c for c in calls if c.startswith("FORBIDDEN")])
    check("run(): rectification as approved (distortion ON, no spec translation, edge fill 0, no alpha)",
          "stereo_enableDistortionCorrection(True,)" in calls and "stereo_setRectificationUseSpecTranslation(False,)" in calls
          and "stereo_setRectifyEdgeFillColor(0,)" in calls and not [c for c in calls if "Alpha" in c])
    check("run(): two H.264 Baseline encoders on rectifiedLeft/Right, keyframe 20, CBR, non-blocking queues",
          "encoder_build_rectifiedLeft_20.0_H264_BASELINE_20" in calls and "encoder_build_rectifiedRight_20.0_H264_BASELINE_20" in calls
          and "queue_enc_rectifiedLeft_8_False" in calls and calls.count("enc_rc_CBR") == 2)
    hc = rep["hardware_checks"]
    check("run(): stand-in stream passes the hardware checks (profile 66, 1280x800, no B, IDR every 20, pairs)",
          all(v == "PASS" for e in gc.EYES for v in hc[e].values()) and hc["stereo_pairs_equal_seq_and_skew_le_1ms"] == "PASS", hc)
    segl = sorted(d.glob("camA_left_seg*.ts"))
    seqs_l, eofs_l, lum_l = read_ts(segl[0]) if segl else ([], [], [])
    check("run(): file sink camA_left_seg1.ts decodes, starts at a recovery point, metadata intact",
          segl and lum_l and seqs_l[0][0] % 20 == 0 and all(x[1] == "left" and x[2] == 0 for x in seqs_l), (segl, seqs_l[:2]))
    check("run(): captured.csv, sent.csv, events.jsonl written",
          all((d / n).exists() for n in ("captured.csv", "sent.csv", "events.jsonl")))
    check("run(): read-only device record incl. bootloader 0.0.26", rep["device_read_only"]["getBootloaderVersion"] == "0.0.26",
          rep.get("device_read_only"))
    import csv as _c2
    caprows = list(_c2.DictReader(open(d / "captured.csv", encoding="utf-8")))
    check("run(): captured.csv has per-AU NAL types and size", bool(caprows) and caprows[0]["nal_types"].split()[:2] == ["7", "8"]
          and caprows[0]["width"] == "1280", caprows[:1])

    code, rep, calls, d = do_run("raw", autocal_sticks=False, extra=("--dump-raw",))
    rl = d / "camA_left_raw.h264"
    nraw = 0
    if rl.exists():
        with av.open(str(rl), format="h264") as c_:
            for p_ in c_.demux(video=0):
                try:
                    nraw += len(p_.decode())
                except av.error.InvalidDataError:
                    pass
    caps = sum(1 for r_ in _c2.DictReader(open(d / "captured.csv", encoding="utf-8")) if r_["eye"] == "left")
    check("--dump-raw: unmodified encoder output per eye decodes, one frame per captured AU, no FrameMeta inside",
          code == 0 and rl.exists() and nraw == caps and pc.extract_meta(rl.read_bytes())[0] is None, (code, nraw, caps))
    stopf = work / "STOP_ME"
    threading.Timer(1.5, lambda: stopf.write_text("stop", encoding="utf-8")).start()
    t_s = time.monotonic()
    code, rep, calls, d = do_run("stopfile", autocal_sticks=False, extra=("--stop-file", str(stopf)))
    check("--stop-file: stream ends early (stop_file), clean shutdown and calibration verification still run, exit 0",
          code == 0 and rep["stop_reason"] == "stop_file" and rep["calibration_unchanged"] is True and rep["pipeline_stopped"]
          and rep["device_closed"] and time.monotonic() - t_s < 15, (code, rep.get("stop_reason"), rep.get("errors")))
    code, rep, calls, d = do_run("autocal", autocal_sticks=True)
    check("refuse: AutoCalibrationMode stays ON_START -> safety_abort, pipeline never started (designed to fail)",
          code == 1 and rep["stop_reason"] == "safety_abort" and "pipeline_start" not in calls and "device_close" in calls, rep.get("errors"))
    code, rep, calls, d = do_run("ir", autocal_sticks=False, ir_ack=False)
    check("refuse: IR off not acknowledged -> safety_abort before the pipeline is built",
          code == 1 and rep["stop_reason"] == "safety_abort" and "autocal_set_OFF" not in calls, rep.get("errors"))
    code, rep, calls, d = do_run("calib", autocal_sticks=False,
                                 baseline_user={"cameraData": [[0, {"intrinsicMatrix": [[2, 0, 0]]}]], "batchName": "A"})
    check("refuse: calibration differs from the baseline before start -> safety_abort, IR/pipeline untouched",
          code == 1 and rep["stop_reason"] == "safety_abort" and "pipeline_start" not in calls
          and not any(c.startswith("ir_") for c in calls), rep.get("errors"))
    code, rep, calls, d = do_run("ident", autocal_sticks=False, device_id="194430108183F12E00")
    check("refuse: device answers with another ID -> safety_abort, nothing configured",
          code == 1 and rep["stop_reason"] == "safety_abort" and "pipeline_start" not in calls, rep.get("errors"))
    code, rep, calls, d = do_run("bootloader", autocal_sticks=False, bootloader="0.0.29")
    check("refuse: bootloader not the validated 0.0.26 -> safety_abort before calibration read / IR / pipeline (designed to fail)",
          code == 1 and rep["stop_reason"] == "safety_abort" and "pipeline_start" not in calls
          and "read_user_calibration" not in calls, rep.get("errors"))
    code, rep, calls, d = do_run("sensor", autocal_sticks=False, sensor="IMX378")
    check("refuse: wrong sensor -> safety_abort", code == 1 and rep["stop_reason"] == "safety_abort", rep.get("errors"))
    code, rep, calls, d = do_run("timeout", autocal_sticks=False, frames=0)
    check("no frames from the device -> frame_timeout, still stopped, closed and verified", code == 1
          and rep["stop_reason"] == "frame_timeout" and rep["pipeline_stopped"] and rep["calibration_unchanged"] is True, rep.get("errors"))

    # pinned sources
    cvcopy = work / "cv"
    cvcopy.mkdir()
    for n in cga.SAFETY_SOURCES:
        shutil.copy(cga.CV / n, cvcopy / n)
    (cvcopy / "capture_stereo.py").write_text((cvcopy / "capture_stereo.py").read_text(encoding="utf-8") + "\n# edit\n", encoding="utf-8")
    try:
        cga.load_safety_modules(cvcopy)
        ok = False
    except cga.SafetySourceChanged:
        ok = True
    check("refuse: a changed safeguard source (hash pin) (designed to fail)", ok)
    check("the pinned hashes match the current camera_validation sources",
          all(hashlib.sha256((cga.CV / n).read_bytes()).hexdigest() == h for n, h in cga.SAFETY_SOURCES.items()))
    for argv, what in ((["--expect", "169.254.1.223=194430108183F12E00"], "Camera B"),
                       (["--expect", "169.254.1.222=19443010B14C872F00", "--seconds", "600"], "600 s"),
                       (["--expect", "169.254.1.222=19443010B14C872F00", "--server", "rtsp://10.0.0.5:8554"], "non-loopback server"),
                       # extended-test mode (13 Nov 2026): opt-in, hard maximum 600 s; the default 120 s limit is unchanged
                       (["--expect", "169.254.1.222=19443010B14C872F00", "--seconds", "121"], "121 s without --extended-test"),
                       (["--expect", "169.254.1.222=19443010B14C872F00", "--seconds", "601", "--extended-test"], "601 s with --extended-test (hard maximum 600)"),
                       (["--expect", "169.254.1.222=19443010B14C872F00", "--seconds", "1e9", "--extended-test"], "1e9 s with --extended-test"),
                       (["--expect", "169.254.1.223=194430108183F12E00", "--seconds", "300", "--extended-test"], "Camera B with --extended-test"),
                       (["--expect", "169.254.1.222=19443010B14C872F00", "--seconds", "600", "--extended-test", "--server", "rtsp://10.0.0.5:8554"],
                        "non-loopback server with --extended-test")):
        try:
            cga.parse_args(argv + ["--baseline-user", str(work / "ok" / "u.json"), "--baseline-factory", str(work / "ok" / "f.json")], dc)
            ok = False
        except SystemExit:
            ok = True
        check("argument refused: {}".format(what), ok)
    bl = ["--baseline-user", str(work / "ok" / "u.json"), "--baseline-factory", str(work / "ok" / "f.json")]
    a120 = cga.parse_args(["--expect", "169.254.1.222=19443010B14C872F00", "--seconds", "120"] + bl, dc)
    a600 = cga.parse_args(["--expect", "169.254.1.222=19443010B14C872F00", "--seconds", "600", "--extended-test"] + bl, dc)
    check("accepted: 120 s default mode (extended_test False); 600 s only with --extended-test",
          a120.seconds == 120.0 and a120.extended_test is False and a600.seconds == 600.0 and a600.extended_test is True
          and cga.EXTENDED_MAX_S == 600.0)
    check("extended mode keeps every other safeguard default (keyint 20, resync, 150 ms age guard, loopback server, Camera A)",
          a600.keyint == a120.keyint == 20 and a600.max_send_age_ms == a120.max_send_age_ms == 150
          and a600.stale_policy == a120.stale_policy == "resync" and a600.server == a120.server
          and a600.expect == a120.expect and a600.fps == a120.fps and a600.bitrate_kbps == a120.bitrate_kbps)
finally:
    shutil.rmtree(work, ignore_errors=True)

print()
n_fail = sum(1 for _, ok in RESULTS if not ok)
print("{} checks, {} failed".format(len(RESULTS), n_fail))
sys.exit(1 if n_fail else 0)

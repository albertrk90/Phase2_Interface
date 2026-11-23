"""Offline regression test for G1 failure P2 (stale in-hand frame at reconnect).

G1 mechanism: PyAV's RTSP output connects inside the container header write,
which PyAV performs during the first mux. The old sender took a pair, encoded
it, then made that first write; the write blocked while the server was down
and, when the server came back, sent the held pair ~1.65 s old.

Emulation (no network, no server): the real publish_synthetic.main() writes
FLV to in-memory sinks. FLV, like RTSP, is a global-header muxer whose header
is written at start_encoding(), so a sink's first write is its "connection".
During the outage, writes on an established connection block 0.4 s and fail
(link down); a NEW connection's first write blocks until the server is back
and then succeeds (the G1 reconnect pattern).

  * control run: connect() disabled (old lazy behaviour) -> the first frame
    sent after recovery must be stale; this proves the test detects the defect;
  * fixed run: the first frame after recovery is fresh, and P2 (scored by
    smoke_check.publisher_outage, the acceptance-criterion code itself) PASSes;
  * age guard: a pair older than --max-send-age-ms is discarded before
    encoding and counted; the stream still decodes.

Run: .venv\\Scripts\\python.exe -I tests\\test_publisher_reconnect.py
"""
import csv
import io
import json
import pathlib
import shutil
import sys
import tempfile
import threading
import time

POC = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))

import av  # noqa: E402
import poc_common as pc  # noqa: E402
import publish_synthetic as ps  # noqa: E402
import smoke_check as sc  # noqa: E402

RESULTS = []
OUTAGE = (2.0, 4.5)                 # s after start: "server down"


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + str(detail)) if detail and not cond else ""))


class Ctl:
    def __init__(self):
        self.t0 = self.utc0 = None
        self.conn = 0
        self.connects = []          # (conn, eye, attempt_start_s, done_s)
        self.lock = threading.Lock()

    def rel(self):
        return time.monotonic() - self.t0

    def down(self):
        return OUTAGE[0] <= self.rel() < OUTAGE[1]


class Sink(io.RawIOBase):
    def __init__(self, ctl, eye, conn):
        self.ctl, self.eye, self.conn = ctl, eye, conn
        self.buf = bytearray()
        self.connected = False

    def writable(self):
        return True

    def write(self, b):
        if not self.connected:
            start = self.ctl.rel()
            while self.ctl.down():              # connection attempt: blocks until the server is back
                time.sleep(0.005)
            self.connected = True
            with self.ctl.lock:
                self.ctl.connects.append((self.conn, self.eye, start, self.ctl.rel()))
        elif self.ctl.down():
            time.sleep(0.4)
            raise BrokenPipeError("simulated server outage")
        self.buf += bytes(b)
        return len(b)


def run(tmp, label, extra=()):
    ctl = Ctl()
    sinks = []

    def factory(eye):
        def opener():
            with ctl.lock:
                ctl.conn += 1
                c = ctl.conn
            s = Sink(ctl, eye, c)
            sinks.append(s)
            return av.open(s, mode="w", format="flv", options={"flush_packets": "1"}, buffer_size=4096)
        return opener

    argv = ["--camera", "B", "--seconds", "8", "--fps", "20", "--frame-end", "sei", "--queue-pairs", "2",
            "--reconnect-max-s", "0.5", "--label", label, "--out", str(tmp)] + list(extra)
    ctl.t0, ctl.utc0 = time.monotonic(), time.time_ns()
    out_dir = ps.main(argv, opener_factory=factory)
    rep = json.loads((out_dir / "report.json").read_text())
    sent = list(csv.DictReader(open(out_dir / "sent.csv", encoding="utf-8")))
    ev = pc.read_events(out_dir / "events.jsonl")
    restart = {"stop_issued_utc_ns": ctl.utc0 + int(OUTAGE[0] * 1e9),
               "start_issued_utc_ns": ctl.utc0 + int(OUTAGE[1] * 1e9)}
    C = {}
    sc.publisher_outage(C, {}, out_dir, rep, sent, ev, restart)
    return ctl, sinks, rep, sent, ev, C


tmp = pathlib.Path(tempfile.mkdtemp(prefix="pub_rc_"))

# ---------------------------------------------------------------------------
# 1. control: old lazy-connect behaviour reproduces the G1 defect
# ---------------------------------------------------------------------------
real_connect = ps.EyeOutput.connect
ps.EyeOutput.connect = lambda self: None
try:
    _ctl, _s, _rep, _sent, _ev, C0 = run(tmp, "control")
finally:
    ps.EyeOutput.connect = real_connect
p2c = C0["P2_bounded_queue_no_stale_backlog"]
check("control (lazy connect): stale in-hand frame sent after recovery -> P2 FAIL (test detects the defect)",
      p2c["verdict"] == "FAIL" and (p2c["first_frame_sent_after_recovery_age_ms"] or 0) > 500, p2c)

# ---------------------------------------------------------------------------
# 2. fixed publisher
# ---------------------------------------------------------------------------
ctl, sinks, rep, sent, ev, C = run(tmp, "fixed")
c = rep["counts"]
p2 = C["P2_bounded_queue_no_stale_backlog"]
p1 = C["P1_generation_continues_during_outage"]
check("fixed: P2 PASS (smoke_check criterion code)", p2["verdict"] == "PASS", p2)
check("fixed: first frame after recovery <= (queue+1) periods + 50 ms (200 ms)",
      p2["first_frame_sent_after_recovery_age_ms"] is not None and p2["first_frame_sent_after_recovery_age_ms"] <= 200,
      p2["first_frame_sent_after_recovery_age_ms"])
check("fixed: P1 PASS (generation continued during the outage)", p1["verdict"] == "PASS", p1)
check("fixed: queue depth never above 2 pairs", rep["queue_max_depth"] <= 2, rep["queue_max_depth"])

t0 = int(sent[0]["t_host_mono_ns"]) - int(sent[0]["t_dev_ns"])
rel = lambda ns: (ns - t0) / 1e9  # noqa: E731
left = [s for s in sent if s["eye"] == "left"]
post = [s for s in left if rel(int(s["t_sent_mono_ns"])) >= OUTAGE[1]]
pre_out = [s for s in post if rel(int(s["t_host_mono_ns"])) < OUTAGE[1] - 0.2]
check("fixed: no frame captured > 200 ms before recovery is sent after it", not pre_out,
      [(s["seq"], round(rel(int(s["t_host_mono_ns"])), 3)) for s in pre_out])
ages = [(int(s["t_sent_mono_ns"]) - int(s["t_host_mono_ns"])) / 1e6 for s in sent if not int(s["flags"]) & pc.FLAG_BURST]
check("fixed: every frame sent at most 200 ms after capture (whole run)", max(ages) <= 200, max(ages))

blocked = [x for x in ctl.connects if x[2] >= OUTAGE[0]]
check("fixed: the reconnection blocked during the outage and completed only when the server returned",
      blocked and all(x[3] >= OUTAGE[1] for x in blocked) and any(x[3] - x[2] > 0.5 for x in blocked), blocked)

types = [e["type"] for e in ev]
conn_ev = [e for e in ev if e["type"] == "link_connected"]
ups = [e for e in ev if e["type"] == "link_up"]
check("fixed: link_connected logged for the initial connection and the reconnection", len(conn_ev) == 2, len(conn_ev))
check("fixed: each link_up follows a link_connected; exactly one link_down",
      len(ups) == 2 and all(any(ce["t_mono_ns"] <= u["t_mono_ns"] for ce in conn_ev) for u in ups)
      and types.count("link_down") == 1, (len(ups), types.count("link_down")))
rc = conn_ev[1]
check("fixed: reconnection's link_connected reports the blocked connect time (> 0.5 s)",
      rc["payload"]["connect_s"] > 0.5, rc["payload"])
check("fixed: link_up after recovery carries a frame captured after the connection completed",
      ups[1]["payload"]["first_seq"] * 50e6 + t0 >= rc["t_mono_ns"] - 150e6, (ups[1]["payload"], rc["t_mono_ns"]))

total = (c["sent"] + c["burst_sent"] + c["dropped_stall"] + c["dropped_drop"] + c["unsent_link_down"]
         + c["queue_discarded_link_up"] + c["skipped_stale"])
check("fixed: accounting incl. skipped_stale: generated = sent + burst + dropped + unsent + skipped",
      total == rep["generated"], (total, rep["generated"], c))

# the media written after the reconnection decodes from its first frame (IDR), with intact SEI
dec_ok, first_key, seen = True, None, []
for s in sinks:
    if s.eye != "left" or not s.buf or s.conn == min(x.conn for x in sinks):
        continue
    try:
        inp = av.open(io.BytesIO(bytes(s.buf)), format="flv")
        vs = inp.streams.video[0]
        for i, p in enumerate(inp.demux(vs)):
            if not p.size:
                continue
            if first_key is None:
                first_key = p.is_keyframe
            for f in p.decode():
                seen.append(f.pts)
        inp.close()
    except Exception as e:                       # noqa: BLE001
        dec_ok = False
        print("   decode error:", e)
check("fixed: post-reconnection media decodes, starting with a keyframe", dec_ok and first_key and len(seen) >= 10,
      (dec_ok, first_key, len(seen)))

# ---------------------------------------------------------------------------
# 3. age guard (Sender alone, in-memory MPEG-TS, no outage)
# ---------------------------------------------------------------------------
class NullSink(io.RawIOBase):
    def writable(self):
        return True

    def write(self, b):
        return len(b)


args = ps.build_args(["--camera", "A", "--fps", "20", "--frame-end", "sei", "--label", "guard", "--out", str(tmp)])
check("guard: default max send age = (queue_pairs + 1) periods = 150 ms", abs(args.max_send_age_ms - 150) < 1e-9,
      args.max_send_age_ms)
check("guard: --max-send-age-ms 0 disables it",
      ps.build_args(["--camera", "A", "--max-send-age-ms", "0"]).max_send_age_ms == 0)
gdir = tmp / "guard"
gdir.mkdir()
log = pc.EventLog(gdir / "events.jsonl", "publisher_A", "poc", "guard")
fh = open(gdir / "sent.csv", "w", newline="", encoding="utf-8")
w = csv.DictWriter(fh, fieldnames=ps.SENT_FIELDS)
w.writeheader()
outs = {eye: ps.EyeOutput("rtsp://127.0.0.1:8554/camA_" + eye, args,
                          lambda: av.open(NullSink(), mode="w", format="mpegts", buffer_size=4096))
        for eye in ("left", "right")}
q = ps.LatestQueue(2)
now = pc.mono_ns()
lum = {eye: ps.ss.make_luma(0, pc.EYES[eye], 0) for eye in ("left", "right")}
q.put(ps.FramePair(0, now - 400_000_000, pc.utc_ns(), lum))       # 400 ms old when taken
q.put(ps.FramePair(1, now, pc.utc_ns(), lum))                     # fresh
snd = ps.Sender(args, outs, q, log, w, now - 1_000_000_000, "host", 0)
snd.start()
time.sleep(1.0)
q.close()
snd.join(5)
fh.close()
log.close()
gs = list(csv.DictReader(open(gdir / "sent.csv", encoding="utf-8")))
gev = pc.read_events(gdir / "events.jsonl")
sk = [e for e in gev if e["type"] == "stale_skipped"]
check("guard: the 400 ms-old pair is discarded before encoding and counted",
      snd.c["skipped_stale"] == 1 and len(sk) == 1 and sk[0]["payload"]["seq"] == 0 and sk[0]["payload"]["age_ms"] > 150,
      (snd.c, sk))
check("guard: the fresh pair is sent (both eyes), the stale one never is",
      sorted({int(r["seq"]) for r in gs}) == [1] and len(gs) == 2, [(r["eye"], r["seq"]) for r in gs])
check("guard: sender finished", not snd.is_alive())

shutil.rmtree(tmp, ignore_errors=True)
print()
n_fail = sum(1 for _, ok in RESULTS if not ok)
print("{} checks, {} failed".format(len(RESULTS), n_fail))
sys.exit(1 if n_fail else 0)

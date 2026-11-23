"""Offline tests for the non-blocking publisher (no network, no server).

The real publish_synthetic.main() runs with an opener that writes MPEG-TS to
an in-memory sink instead of RTSP. A controller makes the sink behave like a
lost server for a window: every write blocks 0.4 s and then fails, for both
the established connection and every reconnection attempt.

Run: .venv\\Scripts\\python.exe -I tests\\test_publisher_nonblocking.py
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

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + str(detail)) if detail and not cond else ""))


# ---------------------------------------------------------------------------
# 1. LatestQueue
# ---------------------------------------------------------------------------
q = ps.LatestQueue(2)
dropped = [q.put(i) for i in range(10)]
check("queue: never holds more than its bound", len(q) == 2 and q.max_depth == 2)
check("queue: keeps the newest, discards the oldest (counted)",
      q.get(0) == 8 and q.get(0) == 9 and q.discarded == 8 and dropped[2] == 0 and dropped[9] == 7)
check("queue: get on empty returns None after timeout", q.get(0.01) is None)
q.close()
check("queue: closed + empty returns None immediately", q.get(5) is None)
try:
    ps.LatestQueue(0)
    check("queue: bound < 1 refused", False)
except ValueError:
    check("queue: bound < 1 refused", True)


# ---------------------------------------------------------------------------
# 2. Publisher through a simulated outage (real main(), in-memory sink)
# ---------------------------------------------------------------------------
class Ctl:
    def __init__(self, outage):
        self.t0 = None
        self.outage = outage
        self.conn = 0
        self.writes = []            # (t_mono_ns, eye, conn, nbytes)
        self.lock = threading.Lock()

    def down(self):
        t = time.monotonic() - self.t0
        return self.outage[0] <= t < self.outage[1]


class Sink(io.RawIOBase):
    def __init__(self, ctl, eye, conn):
        self.ctl, self.eye, self.conn = ctl, eye, conn
        self.buf = bytearray()

    def writable(self):
        return True

    def write(self, b):
        if self.ctl.down():
            time.sleep(0.4)
            raise BrokenPipeError("simulated server outage")
        with self.ctl.lock:
            self.ctl.writes.append((time.monotonic_ns(), self.eye, self.conn, len(b)))
        self.buf += bytes(b)
        return len(b)


SINKS = []


def factory(ctl):
    def for_eye(eye):
        def opener():
            with ctl.lock:
                ctl.conn += 1
                c = ctl.conn
            s = Sink(ctl, eye, c)
            SINKS.append(s)
            return av.open(s, mode="w", format="mpegts", options={"flush_packets": "1"}, buffer_size=4096)
        return opener
    return for_eye


tmp = pathlib.Path(tempfile.mkdtemp(prefix="pub_nb_"))
ctl = Ctl(outage=(3.0, 4.0))
argv = ["--camera", "A", "--seconds", "6", "--fps", "20", "--frame-end", "sei", "--queue-pairs", "2",
        "--stall", "1.0:300:burst", "--reconnect-max-s", "0.5", "--label", "nbtest", "--out", str(tmp)]
ctl.t0 = time.monotonic()
out_dir = ps.main(argv, opener_factory=factory(ctl))
rep = json.loads((out_dir / "report.json").read_text())
gen = list(csv.DictReader(open(out_dir / "generated.csv", encoding="utf-8")))
sent = [r for r in csv.DictReader(open(out_dir / "sent.csv", encoding="utf-8")) if r["eye"] == "left"]
ev = pc.read_events(out_dir / "events.jsonl")
c = rep["counts"]
t0 = int(gen[0]["t_mono_ns"]) - int(float(gen[0]["late_ms"]) * 1e6)
rel = lambda ns: (ns - t0) / 1e9  # noqa: E731

# generation continues on schedule through the outage
tm = [int(g["t_mono_ns"]) for g in gen]
gaps = [(b - a) / 1e6 for a, b in zip(tm, tm[1:])]
during = [(b - a) / 1e6 for a, b in zip(tm, tm[1:]) if 3.0 <= rel(a) < 4.2]
check("generation: every frame generated (120/120)", rep["generated"] == 120 and len(gen) == 120)
check("generation: no gap > 2 frame periods anywhere, incl. the outage",
      max(gaps) <= 100.0, "max gap {:.1f} ms".format(max(gaps)))
check("generation: frames kept being generated during the outage", len(during) >= 18, len(during))
check("generation: no frame late by more than one period", c["late_frames"] == 0, rep["max_late_ms"])

# bounded queue
check("queue: depth never above 2 pairs", rep["queue_max_depth"] <= 2, rep["queue_max_depth"])
check("queue: outage frames discarded by the latest-frame policy, counted as link-down",
      c["unsent_link_down"] >= 10 and c["queue_discarded_link_up"] == 0, c)

# link_up semantics
ups = [e for e in ev if e["type"] == "link_up"]
downs = [e for e in ev if e["type"] == "link_down"]
fails = [e for e in ev if e["type"] == "link_connect_failed"]
check("link: exactly two link_up events (initial + after recovery)", len(ups) == 2, [rel(e["t_mono_ns"]) for e in ups])
check("link: no link_up during the outage", not any(3.0 <= rel(e["t_mono_ns"]) < 4.0 for e in ups))
check("link: one link_down at the outage start, failed reconnects logged as link_connect_failed",
      len(downs) == 1 and 3.0 <= rel(downs[0]["t_mono_ns"]) < 3.6 and len(fails) >= 1, (len(downs), len(fails)))


def first_write_after(t_ns):
    w = [x for x in ctl.writes if x[0] >= t_ns - 2_000_000_000]
    return w


ok = True
for e in ups:
    # a successful sink write must precede (or coincide with) each link_up
    prior = [w for w in ctl.writes if w[0] <= e["t_mono_ns"] and w[0] >= e["t_mono_ns"] - 1_000_000_000]
    if not prior:
        ok = False
check("link: every link_up preceded by a successful write on that connection", ok)

# after recovery: only fresh frames, no backlog
up2 = ups[1]
post = [s for s in sent if int(s["t_sent_mono_ns"]) >= up2["t_mono_ns"] - 1_000_000_000 and rel(int(s["t_host_mono_ns"])) >= 3.9]
first = post[0] if post else None
age_ms = (int(first["t_sent_mono_ns"]) - int(first["t_host_mono_ns"])) / 1e6 if first else None
check("recovery: first frame sent after the outage is at most ~3 periods old (bounded backlog)",
      first is not None and age_ms <= 170, age_ms)
seqs = [int(s["seq"]) for s in sent]
check("sent: sequence strictly increasing over the whole run", all(b > a for a, b in zip(seqs, seqs[1:])))

# burst stall keeps its original meaning (6 frames held, then sent together)
st_end = next(e for e in ev if e["type"] == "stall_end")
burst = [s for s in sent if int(s["flags"]) & pc.FLAG_BURST]
check("burst stall: 6 frames held and sent late, flagged BURST (not limited by the queue)",
      st_end["payload"]["count"] == 6 and len(burst) == 6 and c["burst_sent"] == 6, (st_end["payload"], len(burst)))
bt = [int(s["t_sent_mono_ns"]) for s in burst]
check("burst stall: held frames released together at the stall end (< 200 ms spread)",
      (max(bt) - min(bt)) / 1e6 < 200, (max(bt) - min(bt)) / 1e6)

# accounting
total = c["sent"] + c["burst_sent"] + c["dropped_stall"] + c["dropped_drop"] + c["unsent_link_down"] + c["queue_discarded_link_up"]
check("accounting: generated = sent + burst + dropped + unsent", total == rep["generated"], (total, rep["generated"], c))

# media on the sinks decodes, with intact SEI, per connection
decoded_ok = True
seen = []
for s in SINKS:
    if s.eye != "left" or not s.buf:
        continue
    try:
        inp = av.open(io.BytesIO(bytes(s.buf)), format="mpegts")
        for p in inp.demux(inp.streams.video[0]):
            if p.size:
                m, err = pc.extract_meta(bytes(p))
                if err:
                    decoded_ok = False
                if m:
                    seen.append(m.seq)
        inp.close()
    except Exception:
        decoded_ok = False
check("sinks: written media demuxes with intact SEI; seqs match sent.csv (left)",
      decoded_ok and sorted(set(seen)) == sorted(set(seqs)), (len(set(seen)), len(set(seqs))))

shutil.rmtree(tmp, ignore_errors=True)
print()
n_fail = sum(1 for _, ok in RESULTS if not ok)
print("{} checks, {} failed".format(len(RESULTS), n_fail))
sys.exit(1 if n_fail else 0)

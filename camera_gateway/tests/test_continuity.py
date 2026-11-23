"""Offline regression tests for the continuity investigation (6 Nov 2026). No camera, no network.

* gateway_core.on_stale: the default "resync" policy is exactly the validated behaviour; the opt-in
  "catchup" policy jumps to a queued keyframe, otherwise sends late within the hard limit, and
  never breaks decodability;
* EyeSender with each policy keeps every transmitted chain decodable;
* the continuity simulator reproduces the six Stage 2 freezes (calibration), and the properties the
  recommendation relies on: keyint 10 shortens freezes without changing what is displayed
  (every displayed pair fresh and < 120 ms old, no stale display, L/R intact, decodable);
  sending late frames (400 ms limit or catchup) shortens freezes further but displays older pairs
  (the documented trade-off);
* the live defaults are unchanged (keyint 20, resync, 150 ms) and keyint 10 is a valid opt-in.
Run: camera_gateway\\.venv\\Scripts\\python.exe -I camera_gateway\\tests\\test_continuity.py
"""
import pathlib
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
GW = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(GW), str(GW / "tools")]

import camera_gateway_a as cga  # noqa: E402
import continuity_sim as cs  # noqa: E402
import gateway_core as gc  # noqa: E402
import gateway_output as go  # noqa: E402

RESULTS = []
MS = 1_000_000


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + str(detail)[:300]) if detail and not cond else ""))


def frames(n, keyint=20):
    return [cs.frame("right", k, keyint) for k in range(n)]


# ------------------------------------------------------------------ on_stale
ev = []
q = gc.GopQueue("right", 10, on_event=lambda k, p: ev.append((k, p)))
fs = frames(30)
for f in fs[0:6]:
    q.put(f)
head = q.get(0)
r = gc.on_stale(q, head, 240 * MS, "resync")
check("resync (default): frame dropped, queue cleared, waiting for the next IDR, event 'stale'",
      r is False and len(q) == 0 and q.waiting and ev[-1][0] == "gop_resync" and ev[-1][1]["reason"] == "stale", ev[-1:])
q = gc.GopQueue("right", 10)
for f in fs[15:23]:                       # 15..19 P, 20 IDR, 21, 22
    q.put(f) if f.seq != 15 else None
q2 = gc.GopQueue("right", 10)
q2.waiting = False
for f in fs[16:23]:
    q2.put(f)
r = gc.on_stale(q2, fs[15], 240 * MS, "catchup")
check("catchup: a newer IDR is queued -> jump to it (frame dropped, head is the IDR 20)", r is False and q2.get(0).seq == 20)
q3 = gc.GopQueue("right", 10)
q3.waiting = False
for f in fs[3:7]:
    q3.put(f)
before = len(q3)
r = gc.on_stale(q3, fs[2], 240 * MS, "catchup")
check("catchup: no IDR queued, age <= hard limit -> send late (chain kept, queue untouched)", r is True and len(q3) == before)
r = gc.on_stale(q3, fs[2], 600 * MS, "catchup", hard_age_ns=500 * MS)
check("catchup: older than the hard limit -> resync (designed to fail the send)", r is False and len(q3) == 0 and q3.waiting)
try:
    gc.on_stale(q3, fs[2], 1, "bogus")
    ok = False
except ValueError:
    ok = True
check("unknown policy refused", ok)
check("jump_to_recovery with no queued IDR changes nothing", gc.GopQueue("right", 5).jump_to_recovery("x") is False)


# ------------------------------------------------------------------ EyeSender decodability with each policy
class Out:
    def __init__(self, sink):
        self.sink = sink

    def connect(self, au, ps):
        pass

    def write(self, au, seq, key):
        self.sink.append((seq, key))
        if seq == 25:
            time.sleep(0.3)                  # a 300 ms blocked write, as in Stage 2
        return len(au)

    def close(self):
        pass


class Log:
    def emit(self, k, p=None):
        pass


def sender_run(policy, keyint=20):
    import csv
    import io
    sink = []
    gq = gc.GopQueue("right", 10)
    params = go.ParamStore()
    w = csv.DictWriter(io.StringIO(), fieldnames=go.SENT_FIELDS)
    s = go.EyeSender("right", gq, params, lambda e, sg: Out(sink), Log(), w, threading.Lock(), "H", "s", "t",
                     max_send_age_ms=150, reconnect_max_s=0.02, sleep=lambda d: time.sleep(0.001), stale_policy=policy)
    s.start()
    for k in range(80):
        f = cs.frame("right", k, keyint)
        f.t_host_mono_ns = time.monotonic_ns() - 70 * MS
        params.offer(f)
        gq.put(f)
        time.sleep(0.05)
    time.sleep(0.1)
    s.stop()
    gq.close()
    s.join(2)
    ok, prev = True, None
    for seq, key in sink:
        if prev is not None and seq != prev + 1:
            ok &= key
        prev = seq
    return s, sink, ok


for pol in ("resync", "catchup"):
    s, sink, ok = sender_run(pol)
    check("EyeSender ({}): a 300 ms blocked write never breaks decodability (every gap restarts at an IDR)".format(pol),
          ok and sink and sink[0][1], (s.c, sink[20:40]))
    if pol == "resync":
        check("EyeSender (resync): the stall costs frames up to the next IDR (drop-to-IDR)", s.c["skipped_stale"] >= 1
              and 30 not in [q for q, _ in sink], s.c)
    else:
        check("EyeSender (catchup): late frames sent instead (sent_late > 0) and far fewer frames lost",
              s.c["sent_late"] >= 1 and len(sink) > 70, (s.c, len(sink)))

# ------------------------------------------------------------------ simulator
base = cs.simulate(stalls_right=cs.STAGE2_STALLS, **cs.CONFIGS[0][1])
check("calibration: simulated baseline reproduces each Stage 2 freeze within 50 ms",
      len(base["freezes_ms"]) == 6 and all(abs(a - b) <= 50 for a, b in zip(base["freezes_ms"], cs.STAGE2_OBSERVED_FREEZES_MS)),
      (base["freezes_ms"], cs.STAGE2_OBSERVED_FREEZES_MS))
sw = cs.sweep_stalls(315)
n = 100 + 61 * 20 + 80
A = cs.simulate(stalls_right=sw, n=n, **cs.CONFIGS[0][1])
B = cs.simulate(stalls_right=sw, n=n, **cs.CONFIGS[1][1])
C = cs.simulate(stalls_right=sw, n=n, **cs.CONFIGS[2][1])
D = cs.simulate(stalls_right=sw, n=n, **cs.CONFIGS[3][1])
check("keyint 10: shorter total and worst freeze than keyint 20 (same 20 stalls)",
      sum(B["freezes_ms"]) < 0.8 * sum(A["freezes_ms"]) and max(B["freezes_ms"]) < max(A["freezes_ms"]), (sum(A["freezes_ms"]), sum(B["freezes_ms"])))
for name, r in (("A keyint 20", A), ("B keyint 10", B)):
    check("{}: no stale display, every displayed pair < 120 ms old, display increasing, 0 integrity errors, decodable".format(name),
          not r["stale_display_violations"] and r["max_displayed_abs_age_ms"] < 120 and r["display_increasing"]
          and r["integrity_errors"] == 0 and all(r["decodable_streams"].values()), r["max_displayed_abs_age_ms"])
check("trade-off documented: sending late (400 ms limit / catchup) shortens freezes further but displays older pairs (> 120 ms)",
      sum(C["freezes_ms"]) < sum(B["freezes_ms"]) and C["max_displayed_abs_age_ms"] > 120 and D["max_displayed_abs_age_ms"] > 120,
      (C["max_displayed_abs_age_ms"], D["max_displayed_abs_age_ms"]))
check("all simulated configurations keep both eye streams decodable",
      all(all(r["decodable_streams"].values()) for r in (A, B, C, D)))

# ------------------------------------------------------------------ live defaults unchanged
cs_, cc, dc = cga.load_safety_modules()
R = GW.parent / "camera_validation" / "results"
base_args = ["--expect", "169.254.1.222=19443010B14C872F00", "--baseline-user", str(R / "calibration_user_19443010B14C872F00_20261103_182445.json"),
             "--baseline-factory", str(R / "calibration_factory_19443010B14C872F00_20261103_182445.json")]
a = cga.parse_args(base_args, dc)
check("validated live defaults unchanged: keyint 20, stale policy resync, 150 ms send-age guard",
      a.keyint == 20 and a.stale_policy == "resync" and a.max_send_age_ms == 150.0)
a10 = cga.parse_args(base_args + ["--keyint", "10"], dc)
check("keyint 10 is a valid opt-in (gateway plan shows keyframe_every 10, fps and bitrate unchanged)",
      cga.plan(a10)["encoder"]["keyframe_every"] == 10 and a10.fps == 20.0 and a10.bitrate_kbps == 8000)
ps = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(GW / "tools" / "run_stage2.ps1"), "-PlanOnly",
                     "-Keyint", "10"], capture_output=True, text=True, timeout=180)
check("Stage 2 runner -Keyint 10 (plan only): the gateway command carries --keyint 10", "--keyint 10" in ps.stdout, ps.stdout[-400:] + ps.stderr[-300:])
ps0 = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(GW / "tools" / "run_stage2.ps1"), "-PlanOnly"],
                     capture_output=True, text=True, timeout=180)
check("Stage 2 runner default (plan only): keyint 20, unchanged", "--keyint 20" in ps0.stdout, ps0.stdout[-400:])

print()
n_fail = sum(1 for _, ok in RESULTS if not ok)
print("{} checks, {} failed".format(len(RESULTS), n_fail))
sys.exit(1 if n_fail else 0)

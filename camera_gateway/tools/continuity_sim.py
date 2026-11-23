"""Offline continuity simulator (Task 06 follow-up, 6 Nov 2026). No camera, no network.

Discrete-event model of one stereo stream, built from REAL components and MEASURED parameters:
  * gateway: the real gateway_core.GopQueue (maxlen 10) and gateway_core.on_stale policy;
  * frames: real H.264 access units from the libx264 stand-in at the chosen keyframe interval
    (recovery points decided by gateway_core.inspect_au exactly as live);
  * timing (Stage 2 medians): capture every 50 ms; capture -> host receipt 73.8 ms; write 2 ms;
    gateway send -> Unity arrival 1.3 ms; decode 1.6 ms; Unity display tick 60.1 Hz;
  * transport stall (Stage 2 measurement): from the moment frame k0 is written, the connection
    delivers nothing for D ms; writes still return while about 100 kB is buffered (two P-frames),
    then block until the stall ends; everything written during it arrives at the stall end;
  * receiver: the validated Python presenter (streaming_poc/receive_reference.Presenter, imported
    read-only) with the exact freshness policy of the Stage 2 Unity run, camera semantics.
Outputs per run: display freezes, frames not sent per eye, pairs displayed, stale-display
violations (a "fresh" label with absolute age > 150 ms or excess > 100 ms, or a non-increasing
display), integrity errors, and whether every gap in each transmitted eye stream restarts at a
recovery point (decodability). This is a MODEL: it reproduces the six Stage 2 events but cannot
prove behaviour of the real encoder or network.
"""
import pathlib
import sys

sys.dont_write_bytecode = True
GW = pathlib.Path(__file__).resolve().parents[1]
ROOT = GW.parent
sys.path[:0] = [str(GW), str(GW / "tools"), str(ROOT / "streaming_poc")]

import gateway_core as gc  # noqa: E402
import receive_reference as rr  # noqa: E402
import standin_encoder as se  # noqa: E402
from gateway_core import pc  # noqa: E402

MS = 1_000_000
PERIOD = 50 * MS
CAP_TO_HOST = int(73.8 * MS)
WRITE = 2 * MS
SEND_TO_ARRIVAL = int(1.3 * MS)
DECODE = int(1.6 * MS)
TICK = int(1e9 / 60.096)
BUFFER_BYTES = 100_000
OFF = 1_700_000_000 * 10**9
STAGE2_POLICY = {"enabled": True, "max_excess_ms": 100, "window_s": 10, "warmup_pairs": 20, "rebaseline_s": 2, "max_age_ms": 0,
                 "fresh_age_ms": 150, "clock_uncertainty_ms": None, "same_host_uncertainty_ms": 1, "local_host": "SIMHOST"}
# Stage 2 right-eye events: (first delayed frame = stall onset, connection stall ms), from gw_20261106_125623_A_stage2
STAGE2_STALLS = [(261, 321), (314, 314), (696, 310), (760, 316), (961, 322), (1326, 318)]
STAGE2_OBSERVED_FREEZES_MS = [1015.4, 1364.5, 1281.3, 1064.8, 998.1, 765.3]
_AUS = {}


def aus(keyint):
    if keyint not in _AUS:
        pairs = se.load_e1_pairs()
        a = se.encode_sequence([pairs[k % 5][1] for k in range(2 * keyint)], keyint=keyint)
        _AUS[keyint] = [(x, gc.inspect_au(x)) for x in a]
    return _AUS[keyint]


def frame(eye, seq, keyint):
    au, info = aus(keyint)[seq % (2 * keyint)]
    t_cap = seq * PERIOD
    return gc.CameraFrame(eye, seq, t_cap, t_cap, au, t_cap + CAP_TO_HOST, info.first_slice_type, info=info)


def send_eye(eye, n, keyint, policy, max_age_ms, hard_age_ms, stalls):
    """[(seq, t_written, t_delivered)] for one eye, plus the queue counters."""
    q = gc.GopQueue(eye, 10)
    stall_at = {s: d for s, d in stalls}
    out, k, t = [], 0, 0
    stall_end, buffered = None, 0
    while True:
        while k < n and k * PERIOD + CAP_TO_HOST <= t:
            q.put(frame(eye, k, keyint))
            k += 1
        f = q.get(0)
        if f is None:
            if k >= n:
                break
            t = k * PERIOD + CAP_TO_HOST
            continue
        age = t - f.t_host_mono_ns
        if age > max_age_ms * MS and not gc.on_stale(q, f, age, policy, int(hard_age_ms * MS)):
            continue
        if f.seq in stall_at and (stall_end is None or t >= stall_end):
            stall_end, buffered = t + int(stall_at[f.seq] * MS), 0
        size = len(f.au) if not f.recovery_point else 209_000          # OAK-sized IDR (Stage 1/2 median)
        size = max(size, 40_000)
        if stall_end is not None and t < stall_end:
            buffered += size
            if buffered <= BUFFER_BYTES:
                t_ret, t_del = t + WRITE, stall_end + WRITE
            else:
                t_ret = t_del = stall_end + WRITE
        else:
            t_ret = t_del = t + WRITE
        out.append((f.seq, t_ret, t_del, f.recovery_point))
        t = t_ret
    return out, dict(q.c)


class _Log:
    def __init__(self):
        self.ev = []

    def emit(self, t, p, t_utc=None, t_mono=None):
        self.ev.append((t, p))


def simulate(keyint=20, policy="resync", max_age_ms=150.0, hard_age_ms=500.0, n=1400, stalls_right=(), stalls_left=()):
    sent = {"left": send_eye("left", n, keyint, policy, max_age_ms, hard_age_ms, stalls_left),
            "right": send_eye("right", n, keyint, policy, max_age_ms, hard_age_ms, stalls_right)}
    arrivals = sorted(((td + SEND_TO_ARRIVAL, eye, q) for eye, (rows, _c) in sent.items() for q, _tr, td, _k in rows))
    log, rows = _Log(), []
    P = rr.Presenter("A", 20, 125.0, log, rows.append, policy=rr.FreshnessPolicy(**STAGE2_POLICY))
    i, t = 0, arrivals[0][0]
    t_end = arrivals[-1][0] + 500 * MS
    while t <= t_end:
        while i < len(arrivals) and arrivals[i][0] <= t:
            ta, eye, q = arrivals[i]
            m = pc.FrameMeta("A", eye, q, q * PERIOD, q * PERIOD, q * PERIOD + OFF, "SIMHOST", "sim", "sim", gc.CONFIG_ID, 0)
            P.on_frame(eye, {"meta": m, "t_arrival_mono": ta, "t_arrival_utc": ta + OFF, "t_decoded_mono": ta + DECODE,
                             "barcode": (q, pc.EYES[eye], 0)})
            i += 1
        P.tick(t, t + OFF)
        t += TICK
    shown = [int(r["seq"]) for r in rows]
    fz = [p["duration_ms"] for typ, p in log.ev if typ == "freeze_end"]
    viol = [r["seq"] for r in rows if (r["freshness"] == "fresh" and r["abs_age_ms"] not in ("", None) and float(r["abs_age_ms"]) > 150)
            or (r["excess_ms"] not in ("", None) and float(r["excess_ms"]) > 100)]
    decodable = {}
    for eye, (rs, _c) in sent.items():
        seqs = [(q, key) for q, _tr, _td, key in rs]
        decodable[eye] = all(key for (pq, _), (q, key) in zip([(-1, True)] + seqs[:-1], seqs) if q != pq + 1)
    counts = P.summary()["counts"]
    return {"config": {"keyint": keyint, "policy": policy, "max_age_ms": max_age_ms, "hard_age_ms": hard_age_ms},
            "freezes_ms": [round(x, 1) for x in fz], "displayed": len(shown),
            "not_sent": {e: n - len(rs) for e, (rs, _c) in sent.items()},
            "stale_display_violations": viol, "display_increasing": all(b > a for a, b in zip(shown, shown[1:])),
            "integrity_errors": counts["integrity_errors"], "rejected_excess_delay": counts["rejected_excess_delay"],
            "max_displayed_abs_age_ms": max((float(r["abs_age_ms"]) for r in rows if r["abs_age_ms"] not in ("", None)), default=None),
            "decodable_streams": decodable}


CONFIGS = [("A baseline (validated): keyint 20, resync, 150 ms", dict(keyint=20, policy="resync", max_age_ms=150)),
           ("B keyint 10, resync, 150 ms", dict(keyint=10, policy="resync", max_age_ms=150)),
           ("C keyint 20, resync, 400 ms age limit", dict(keyint=20, policy="resync", max_age_ms=400)),
           ("D keyint 20, catchup (150 ms guard, 500 ms hard)", dict(keyint=20, policy="catchup", max_age_ms=150)),
           ("E keyint 10, catchup (150 ms guard, 500 ms hard)", dict(keyint=10, policy="catchup", max_age_ms=150))]


def sweep_stalls(d_ms, n_events=20):
    """One stall per GOP phase (onset seq 100 + 61 j covers every residue mod 20 and mod 10)."""
    return [(100 + 61 * j, d_ms) for j in range(n_events)]


def main():
    import json
    import statistics
    out = {"model": __doc__.strip().splitlines()[0], "calibration_stage2": {}, "sweeps": {}}
    base = simulate(stalls_right=STAGE2_STALLS, **CONFIGS[0][1])
    out["calibration_stage2"] = {"observed_freezes_ms": STAGE2_OBSERVED_FREEZES_MS, "simulated_freezes_ms": base["freezes_ms"],
                                 "simulated_not_sent_right": base["not_sent"]["right"]}
    print("CALIBRATION vs Stage 2 (baseline): observed", STAGE2_OBSERVED_FREEZES_MS, "simulated", base["freezes_ms"])
    for d in (315, 600):
        res = {}
        for name, cfg in CONFIGS:
            r = simulate(stalls_right=sweep_stalls(d), n=100 + 61 * 20 + 80, **cfg)
            fz = r["freezes_ms"]
            res[name] = dict(r, freeze_median_ms=round(statistics.median(fz), 1) if fz else 0.0, freeze_max_ms=max(fz, default=0.0),
                             freeze_total_s=round(sum(fz) / 1000, 2), freezes=len(fz))
            print("D={} ms | {:50s} freezes {:2d} median {:6.1f} max {:6.1f} total {:5.2f} s | not sent R {:3d} | violations {} | "
                  "decodable {} | max age {}".format(d, name, len(fz), res[name]["freeze_median_ms"], res[name]["freeze_max_ms"],
                                                     res[name]["freeze_total_s"], r["not_sent"]["right"], len(r["stale_display_violations"]),
                                                     all(r["decodable_streams"].values()), r["max_displayed_abs_age_ms"]))
        out["sweeps"]["stall_{}ms".format(d)] = res
    dest = GW / "results" / "continuity_sim_20261106.json"
    dest.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print("->", dest)


if __name__ == "__main__":
    main()

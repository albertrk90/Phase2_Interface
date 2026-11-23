"""O1 diagnosis: correlate gateway->MediaMTX holds with system-wide TCP retransmission-counter steps.

Inputs: a gateway folder (sent.csv, captured.csv, events.jsonl), the runner folder (unity_rx_*_A_* with
arrivals.csv) and the sampler CSV (tcp_counters.csv, same host monotonic clock).

Holds: for every mid-stream gateway stale resync, the blocked write is the write that returned just before
it; held frames are the frames before it whose write returned normally but which reached Unity > 30 ms
later. hold onset = hand-over of the first held frame (or the blocked write's start if none), release =
first arrival of held data in Unity (or the blocked write's return when no reader is connected).

Counter: IPv4 RetransSegs (system-wide, all connections; loopback included, see loopback_check.json).
A step "near" a release is one whose sample interval overlaps [release - W, release + W].
Background: step rate over streaming time outside every [onset - 0.5 s, release + 0.5 s].
Correlation in an aggregate counter supports but does not prove that a camera connection retransmitted.
Usage: analyse_tcp_holds.py <gateway_dir> <runner_dir> <tcp_counters.csv> [--window-ms 20]
"""
import argparse, bisect, csv, json, pathlib, statistics

ap = argparse.ArgumentParser()
ap.add_argument("gw"); ap.add_argument("run"); ap.add_argument("tcp")
ap.add_argument("--window-ms", type=float, default=20.0)
a = ap.parse_args()
gw, run = pathlib.Path(a.gw), pathlib.Path(a.run); MS = 1e6; W = a.window_ms * MS
rows = lambda p: list(csv.DictReader(open(p, encoding="utf-8-sig")))
ev = [json.loads(l) for l in (gw / "events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
g0 = next(e for e in ev if e["type"] == "run_start")["t_mono_ns"]
link = min(e["t_mono_ns"] for e in ev if e["type"] == "link_up")
stop = next((e["t_mono_ns"] for e in ev if e["type"] in ("stop_file_seen", "duration_reached")), None)
cap = {(r["eye"], int(r["seq"])): int(r["t_received_mono_ns"]) for r in rows(gw / "captured.csv")}
sent = {"left": [], "right": []}
for r in rows(gw / "sent.csv"):
    sent[r["eye"]].append((int(r["t_sent_mono_ns"]), int(r["seq"]), int(r["bytes"])))
for e in sent: sent[e].sort()
arr = {"left": {}, "right": {}}; rx_win = []
for d in sorted(run.glob("unity_rx_*_A_*")):
    for r in rows(d / "arrivals.csv"):
        arr[r["eye"]][int(r["seq"])] = int(r["t_arrival_mono_ns"])
    rev = [json.loads(l) for l in (d / "events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rx_win.append((rev[0]["t_mono_ns"], [x for x in rev if x["type"] == "run_end"][-1]["t_mono_ns"]))

holds = []
for e in ev:
    if e["type"] != "gop_resync" or e["payload"]["seq"] == 0:
        continue
    eye = e["payload"]["eye"]; s = sent[eye]; ts = [x[0] for x in s]
    i = bisect.bisect_left(ts, e["t_mono_ns"]) - 1
    blk, prev = s[i], s[i - 1]
    ws = max(prev[0], cap[(eye, blk[1])])
    measurable = blk[1] in arr[eye]
    held = []; j = i - 1
    while measurable and j > 0 and i - j <= 8:
        t_a = arr[eye].get(s[j][1])
        if t_a is not None and t_a - s[j][0] > 30 * MS:
            held.append(j); j -= 1
        else:
            break
    onset = s[held[-1]][0] if held else ws
    rel_frames = s[held[-1]:i + 1] if held else [blk]
    arrs = [arr[eye][x[1]] for x in rel_frames if x[1] in arr[eye]]
    release = min(arrs) if arrs else blk[0]
    holds.append({"t_s": round((e["t_mono_ns"] - g0) / 1e9, 3), "eye": eye, "reader": measurable, "onset": onset, "release": release,
                  "hold_ms": round((release - onset) / MS, 1), "held_frames": len(held) if measurable else None,
                  "age_ms": e["payload"]["age_ms"]})

# counter steps
smp = [(int(r["t_mono_ns"]), int(r["v4_retrans"]), int(r["v4_out"])) for r in rows(a.tcp)]
steps = [(smp[k - 1][0], smp[k][0], smp[k][1] - smp[k - 1][1]) for k in range(1, len(smp)) if smp[k][1] != smp[k - 1][1]]
def steps_in(t_lo, t_hi):      # steps whose sample interval overlaps [t_lo, t_hi]
    return [s for s in steps if s[1] >= t_lo and s[0] <= t_hi]
for h in holds:
    near = steps_in(h["release"] - W, h["release"] + W)
    h["steps_near_release"] = [(round((s[1] - h["release"]) / MS, 1), s[2]) for s in near]
    near_on = steps_in(h["onset"] - W, h["onset"] + W)
    h["steps_near_onset"] = [(round((s[1] - h["onset"]) / MS, 1), s[2]) for s in near_on]
    h["steps_during_hold"] = [(round((s[1] - h["onset"]) / MS, 1), s[2]) for s in steps_in(h["onset"] + W, h["release"] - W)]
    h["onset_s"] = round((h["onset"] - g0) / 1e9, 3); h["release_s"] = round((h["release"] - g0) / 1e9, 3)

# background over streaming time, excluding hold neighbourhoods
excl = [(h["onset"] - 500 * MS, h["release"] + 500 * MS) for h in holds]
def excluded(t): return any(lo <= t <= hi for lo, hi in excl)
s_lo, s_hi = link, (stop or smp[-1][0])
bg_steps = [s for s in steps if s_lo <= s[1] <= s_hi and not excluded(s[1])]
excl_ms = sum(min(hi, s_hi) - max(lo, s_lo) for lo, hi in excl if hi > s_lo and lo < s_hi) / MS
bg_time_s = ((s_hi - s_lo) / MS - excl_ms) / 1e3
bg_rate = len(bg_steps) / bg_time_s if bg_time_s > 0 else None
p_window = None if bg_rate is None else 1 - pow(2.718281828, -bg_rate * (2 * W / 1e9 + 0.010))  # +1 sample interval
meas = [h for h in holds if h["reader"]]
hit = [h for h in holds if h["steps_near_release"]]
pre_steps = [s for s in steps if s[1] < link]; post_steps = [s for s in steps if stop and s[1] > stop]
out = {
    "window_ms": a.window_ms,
    "holds": len(holds), "holds_with_reader": len(meas),
    "hold_ms_with_reader": None if not meas else {"min": min(h["hold_ms"] for h in meas), "median": statistics.median(h["hold_ms"] for h in meas), "max": max(h["hold_ms"] for h in meas)},
    "holds_with_a_step_near_release": len(hit),
    "holds_with_a_step_near_onset": sum(bool(h["steps_near_onset"]) for h in holds),
    "holds_with_steps_inside_hold": sum(bool(h["steps_during_hold"]) for h in holds),
    "step_size_near_release": [s for h in holds for s in h["steps_near_release"]],
    "background": {"streaming_s_outside_holds": round(bg_time_s, 1), "steps": len(bg_steps), "rate_per_s": None if bg_rate is None else round(bg_rate, 4),
                   "segments": sum(s[2] for s in bg_steps), "chance_of_a_step_in_one_window": None if p_window is None else round(p_window, 4),
                   "expected_chance_hits": None if p_window is None else round(p_window * len(holds), 2)},
    "steps_before_streaming": {"n": len(pre_steps), "segments": sum(s[2] for s in pre_steps)},
    "steps_after_stop": {"n": len(post_steps), "segments": sum(s[2] for s in post_steps)},
    "steps_during_streaming_total": {"n": len([s for s in steps if s_lo <= s[1] <= s_hi]), "segments": sum(s[2] for s in steps if s_lo <= s[1] <= s_hi)},
    "per_hold": [{k: v for k, v in h.items() if k not in ("onset", "release")} for h in holds],
}
print(json.dumps(out, indent=1))

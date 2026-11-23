"""Offline tests for the S7 investigation: frame-boundary release and the
receiver freshness safeguard. No network, no server, no camera.

Run: .venv\\Scripts\\python.exe -I tests\\test_freshness.py
"""
import csv
import json
import pathlib
import sys

POC = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))
sys.path.insert(0, str(POC / "tests"))

import av  # noqa: E402,F401
import poc_common as pc  # noqa: E402
import receive_reference as rr  # noqa: E402
import trace_frame_release as tr  # noqa: E402

RESULTS = []
PREV_PUB = POC / "results" / "pub_20261105_113222_A_smoke"
PREV_RX = POC / "results" / "rx_20261105_113217_A_smoke"


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + str(detail)) if detail and not cond else ""))


# ---------------------------------------------------------------------------
# 1. Where the holdback is (offline trace)
# ---------------------------------------------------------------------------
aus = tr.encoded_aus(12)
res = tr.summarise(aus)
check("packetiser: every frame's RTP packets leave in its own mux call (all modes)",
      all(res[m]["packetiser_all_frames_complete_in_own_mux"] for m in res), {m: res[m]["packetiser_rtp_packets_per_frame"] for m in res})
check("parser baseline: each frame held until the next frame's first NAL (11/11)",
      res["none"]["parser_held_one_frame"] == 11 and res["none"]["parser_released_in_same_frame"] == 0, res["none"])
check("parser + trailing AUD: every frame released within its own input (12/12)",
      res["aud"]["parser_released_in_same_frame"] == 12, res["aud"]["parser_examples"])
check("parser + trailing EOF SEI: every frame released within its own input (12/12)",
      res["sei"]["parser_released_in_same_frame"] == 12, res["sei"]["parser_examples"])
check("decoder: one frame per parsed packet, same seq, no delay (all modes)",
      all(res[m]["decoder_one_frame_per_packet_same_seq"] and not res[m]["decoder_errors_on_vcl_packets"] for m in res))
check("only leftover after the final frame is a slice-less marker packet",
      res["none"]["non_vcl_leftover_packets"] == [] and res["aud"]["non_vcl_leftover_packets"] == [[9]]
      and res["sei"]["non_vcl_leftover_packets"] == [[6]], {m: res[m]["non_vcl_leftover_packets"] for m in res})

# metadata still belongs to the right frame after the parser moves the marker
parser = av.CodecContext.create("h264", "r")
ok = True
seen = []
for s, au in enumerate(aus):
    for ch in tr.nal_chunks(pc.append_frame_end(au, "sei", s)):
        for p in parser.parse(ch):
            m, _ = pc.extract_meta(bytes(p))
            marks = pc.frame_end_markers(bytes(p))
            seen.append((m.seq if m else None, marks["eof_seq"]))
for i, (seq, eof) in enumerate(seen):
    if seq != i or (i > 0 and eof != [i - 1]) or (i == 0 and eof):
        ok = False
check("with EOF SEI, parsed packet n carries meta n (and the EOF of n-1)", ok, seen[:4])
check("EOF SEI never mistaken for frame metadata",
      pc.extract_meta(pc.build_eof_sei_nal(7)) == (None, None) and pc.frame_end_markers(pc.build_eof_sei_nal(7))["eof_seq"] == [7])

# ---------------------------------------------------------------------------
# 2. Freshness safeguard (Presenter with an injected clock)
# ---------------------------------------------------------------------------
BASE_M = 10**12           # receiver monotonic origin
UTC0 = 1_700_000_000 * 10**9


class Log:
    def __init__(self):
        self.ev = []

    def emit(self, t, p, t_utc=None, t_mono=None):
        self.ev.append((t, p))

    def types(self, t):
        return [p for x, p in self.ev if x == t]


def make(policy_kw=None, host="remote-host"):
    log = Log()
    rows = []
    pol = rr.FreshnessPolicy(local_host="this-host", **(policy_kw or {}))
    P = rr.Presenter("A", 20, 125, log, rows.append, policy=pol)
    return P, log, rows, host


def run(P, host, arrivals, until_ms, offset_ms=0.0, latency_utc_skew=0.0):
    """arrivals: list of (seq, cap_ms, arr_ms[, flags]) for both eyes (right +1 ms).
    Sender UTC = true time + offset_ms (sender clock error). Returns displayed rows."""
    shown = []
    ev = sorted([(a[2], "L", a) for a in arrivals] + [(a[2] + 1, "R", a) for a in arrivals])
    t = 0.0
    i = 0
    while t <= until_ms:
        while i < len(ev) and ev[i][0] <= t:
            at, eye, a = ev[i]
            seq, cap = a[0], a[1]
            flags = a[3] if len(a) > 3 else pc.FLAG_SYNTHETIC
            cap_utc = UTC0 + int((cap + offset_ms) * 1e6)
            m = pc.FrameMeta("A", "left" if eye == "L" else "right", seq, 0, BASE_M + int(cap * 1e6),
                             cap_utc, host, "", "", 1, flags)
            P.on_frame(m.eye, {"meta": m, "t_arrival_mono": BASE_M + int(at * 1e6),
                               "t_arrival_utc": UTC0 + int(at * 1e6),
                               "t_decoded_mono": BASE_M + int(at * 1e6),
                               "barcode": (seq, pc.EYES[m.eye], 0)})
            i += 1
        r = P.tick(BASE_M + int(t * 1e6), UTC0 + int(t * 1e6))
        if r:
            shown.append(r)
        t += 1000 / 60
    return shown


def stall_scenario(hold_prestall=True, n=60, stall_at=20, stall_frames=14, lat=12.0, enc=11.0):
    """20 fps; a 700 ms burst stall: frames stall_at..stall_at+13 captured on
    time, all sent when the stall ends, one encode (enc ms) apart; the
    publisher then catches up. With hold_prestall the frame before the stall
    is released only when the next frame is sent (the observed parser holdback)."""
    arr = []
    end = (stall_at + stall_frames) * 50.0
    t_send = None
    for s in range(n):
        cap = s * 50.0
        if s < stall_at:
            send = cap + 10
        elif s < stall_at + stall_frames:
            send = end + (s - stall_at) * enc
        else:
            send = max(cap + 10, end + (s - stall_at) * enc)
        arr.append([s, cap, send + lat, pc.FLAG_BURST if stall_at <= s < stall_at + stall_frames else 1])
    if hold_prestall:
        for k in range(len(arr) - 1):          # every frame released by the next send
            arr[k][2] = arr[k + 1][2] - lat + 0.2 + lat
    return [tuple(a) for a in arr]


# 2a normal flow, untrusted clock: unverified during warm-up, then fresh
P, log, rows, host = make()
normal = [(s, s * 50.0, s * 50.0 + 15) for s in range(60)]
shown = run(P, host, normal, 3000)
labels = [r["freshness"] for r in shown]
check("normal flow: every seq shown once, in order", [r["seq"] for r in shown] == list(range(60)))
check("untrusted clock: 'unverified' during warm-up, then only 'fresh_relative' (never absolute 'fresh')",
      labels[:19] == ["unverified"] * 19 and set(labels[20:]) == {"fresh_relative"}, labels[:22])
check("untrusted clock: absolute age reported as unknown, no bounds",
      all(r["abs_status"] == "unknown" and r["abs_age_lo_ms"] == "" and r["clock_source"] == "untrusted" for r in shown))
check("normal flow: nothing rejected", P.c["rejected_excess_delay"] == 0 and not log.types("pair_rejected"))

# 2b same-host sender: trusted monotonic clock verifies freshness immediately
P, log, rows, host = make(host="this-host")
shown = run(P, host, normal, 3000)
check("same-host sender: verified fresh from the first pair via trusted clock",
      all(r["freshness"] == "fresh" and r["clock_trusted"] == 1 for r in shown))
check("same-host sender: absolute bounds = age -/+ 1 ms, source same_host_monotonic",
      all(r["clock_source"] == "same_host_monotonic" and r["abs_uncertainty_ms"] == 1.0
          and abs(float(r["abs_age_hi_ms"]) - float(r["abs_age_lo_ms"]) - 2.0) < 1e-6 for r in shown))

# 2c REGRESSION: the 700 ms stall with the parser holdback (as recorded) -- safeguard ON
P, log, rows, host = make()
scen = stall_scenario(hold_prestall=True)
shown = run(P, host, scen, 4000)
seqs = [r["seq"] for r in shown]
stall_end_ms = 34 * 50.0
after = [r for r in shown if (r["t_display_mono_ns"] - BASE_M) / 1e6 >= stall_end_ms]
check("regression (holdback + 700 ms stall): pre-stall frame 19 is not shown after the stall",
      19 not in [r["seq"] for r in after], [r["seq"] for r in after[:3]])
check("regression: no burst-held frame (20-33) displayed", not any(20 <= s <= 33 for s in seqs), seqs)
check("regression: first display after stall has excess <= threshold",
      after and float(after[0]["excess_ms"]) <= 100, after and after[0])
check("regression: displayed sequence strictly increasing, no duplicates",
      all(b > a for a, b in zip(seqs, seqs[1:])))
rej = log.types("pair_rejected")
check("regression: rejections logged with reasons", rej and all(r["reasons"] for r in rej)
      and {"excess_delay"} >= {x for r in rej for x in r["reasons"]}, rej[:2])
check("regression: every displayed pair within threshold",
      all(r["excess_ms"] == "" or float(r["excess_ms"]) <= 100 for r in shown))

# 2d the same without the safeguard reproduces the failure
P, log, rows, host = make({"enabled": False})
shown_off = run(P, host, stall_scenario(hold_prestall=True), 4000)
after_off = [r for r in shown_off if (r["t_display_mono_ns"] - BASE_M) / 1e6 >= stall_end_ms]
check("control (safeguard off): stale pre-stall/burst frames ARE shown (the S7 failure)",
      after_off and (after_off[0]["seq"] == 19 or any(r["burst"] for r in after_off[:10])),
      [r["seq"] for r in after_off[:5]])

# 2e no holdback (parser fix) + stall: frame 19 shown before the stall; burst rejected
P, log, rows, host = make()
shown = run(P, host, stall_scenario(hold_prestall=False), 4000)
pre = [r for r in shown if (r["t_display_mono_ns"] - BASE_M) / 1e6 < 20 * 50.0 + 60]
check("parser fix: frame 19 displayed before the stall, not after",
      19 in [r["seq"] for r in pre] and 19 not in [r["seq"] for r in shown if (r["t_display_mono_ns"] - BASE_M) / 1e6 >= stall_end_ms])
check("parser fix + safeguard: no burst frame displayed", not any(r["burst"] for r in shown))

# 2f clock offset independence (sender clock 5 s ahead / 3 s behind, untrusted)
outs = []
for off in (0.0, 5000.0, -3000.0):
    P, log, rows, host = make()
    s = run(P, host, stall_scenario(hold_prestall=True), 4000, offset_ms=off)
    outs.append(([r["seq"] for r in s], [p["seq"] for p in log.types("pair_rejected")]))
check("clock offset +5 s / -3 s: identical displays and rejections", outs[0] == outs[1] == outs[2],
      [len(o[0]) for o in outs])

# 2g initial join into a backlog: decreasing delays never rejected, never 'fresh' early
P, log, rows, host = make()
# receiver joins while a 1 s backlog drains: seq 0-19 (captured 0-950 ms) arrive
# 1000-1095 ms; live frames from seq 20 (captured 1000 ms) arrive 15 ms after capture
backlog = [(s, s * 50.0, 1000 + s * 5.0) for s in range(20)] + [(s, s * 50.0, s * 50.0 + 15) for s in range(20, 70)]
shown = run(P, host, backlog, 3600)
first = shown[0]
check("join into backlog: first shown pair is 'unverified', not 'fresh'", first["freshness"] == "unverified", first)
check("join into backlog: no pair labelled fresh before warm-up completes",
      all(r["freshness"] != "fresh" for r in shown if P.pairs_since_reset < 20) and
      all(r["freshness"] != "fresh" for r in shown[:5]))
check("join into backlog: live frames not falsely rejected",
      all(s in [r["seq"] for r in shown] for s in range(25, 70)), [r["seq"] for r in shown][:10])

# 2h reconnect resets the reference
P, log, rows, host = make()
run(P, host, normal[:30], 1600)
P.on_link_reset("left")
more = [(s, s * 50.0, s * 50.0 + 15) for s in range(30, 60)]
t0 = 1600.0


def run_from(P, host, arrivals, t_start, t_end):
    out = []
    ev = sorted([(a[2], "L", a) for a in arrivals] + [(a[2] + 1, "R", a) for a in arrivals])
    i, t = 0, t_start
    while t <= t_end:
        while i < len(ev) and ev[i][0] <= t:
            at, eye, a = ev[i]
            m = pc.FrameMeta("A", "left" if eye == "L" else "right", a[0], 0, BASE_M + int(a[1] * 1e6),
                             UTC0 + int(a[1] * 1e6), host, "", "", 1, 1)
            P.on_frame(m.eye, {"meta": m, "t_arrival_mono": BASE_M + int(at * 1e6), "t_arrival_utc": UTC0 + int(at * 1e6),
                               "t_decoded_mono": BASE_M + int(at * 1e6), "barcode": (a[0], pc.EYES[m.eye], 0)})
            i += 1
        r = P.tick(BASE_M + int(t * 1e6), UTC0 + int(t * 1e6))
        if r:
            out.append(r)
        t += 1000 / 60
    return out


s2 = run_from(P, host, more, t0, 3200)
check("reconnect: reset logged and warm-up restarts ('unverified' again)",
      log.types("freshness_reset") and s2 and s2[0]["freshness"] == "unverified")

# 2i persistent delay increase (+300 ms): rejected, then re-baselined, display resumes
P, log, rows, host = make()
step = [(s, s * 50.0, s * 50.0 + 15) for s in range(40)] + [(s, s * 50.0, s * 50.0 + 315) for s in range(40, 140)]
shown = run(P, host, step, 7500)
rb = log.types("delay_rebaseline")
late_shown = [r for r in shown if r["seq"] >= 40]
check("delay step +300 ms: re-baseline logged after ~2 s", len(rb) == 1, rb)
check("delay step: display resumes after re-baseline (no permanent freeze)",
      late_shown and late_shown[-1]["seq"] >= 135, late_shown[-1:] if late_shown else None)

post_rb = [r for r in late_shown if r["seq"] >= 90]
check("delay step, untrusted clock: after re-baseline labelled 'relative_adapted', never fresh",
      post_rb and all(r["freshness"] == "relative_adapted" for r in post_rb),
      sorted({r["freshness"] for r in post_rb}))
check("delay step: baseline shift recorded (~300 ms)",
      post_rb and all(abs(float(r["baseline_shift_ms"]) - 300) < 5 for r in post_rb), post_rb[:1])

# 2i' the same persistent delay with a trusted (same-host) clock: 'late', never fresh
P, log, rows, host = make(host="this-host")
shown = run(P, host, step, 7500)
post_rb = [r for r in shown if r["seq"] >= 90]
check("delay step, trusted clock: after re-baseline labelled 'late' (absolute age over limit)",
      post_rb and all(r["freshness"] == "late" and r["abs_status"] == "over" for r in post_rb),
      sorted({r["freshness"] for r in post_rb}))
check("delay step, trusted clock: re-baseline event logged",
      len(log.types("delay_rebaseline")) == 1 and P.c["rebaselines"] == 1)

# 2l configured cross-host clock uncertainty: bounds and 'uncertain' status
P, log, rows, host = make({"clock_uncertainty_ms": 20.0})
mixed = [(s, s * 50.0, s * 50.0 + (40 if s < 30 else 140)) for s in range(60)]
shown = run(P, host, mixed, 3200)
low = [r for r in shown if r["seq"] < 30]
high = [r for r in shown if r["seq"] >= 33 and r["freshness"] != ""]
check("configured uncertainty 20 ms: age ~40 ms -> 'within', labelled fresh, bounds +/-20",
      low and all(r["abs_status"] == "within" and r["freshness"] == "fresh"
                  and r["clock_source"] == "utc_configured_uncertainty" for r in low))
check("configured uncertainty: age ~140 ms straddles 150 -> 'uncertain', never 'fresh'",
      not any(r["freshness"] == "fresh" and r["abs_status"] != "within" for r in shown)
      and any(r["abs_status"] == "uncertain" for r in shown), sorted({(r["abs_status"], r["freshness"]) for r in shown}))

# 2m server restart: reset on reconnect; re-delivered old frames never replayed
P, log, rows, host = make(host="this-host")
pre = [(s, s * 50.0, s * 50.0 + 15) for s in range(0, 40)]
shown_pre = run(P, host, pre, 2050)
P.on_link_reset("left")
P.on_link_reset("right")
# after reconnect: a stale tail of pre-restart frames (35-39) arrives again, then live frames from 100
again = [(s, s * 50.0, 5000 + s) for s in range(35, 40)] + [(s, s * 50.0, s * 50.0 + 15) for s in range(100, 140)]
shown_post = run_from(P, host, again, 2050, 7200)
seqs_all = [r["seq"] for r in shown_pre + shown_post]
check("restart: no pre-restart frame displayed after the reconnect",
      shown_post and min(r["seq"] for r in shown_post) >= 100, [r["seq"] for r in shown_post[:3]])
check("restart: re-delivered old frames discarded as late",
      P.c["late_discarded"] >= 5, P.c["late_discarded"])
check("restart: reference reset (pairs_since_reset restarts) and two reset events",
      shown_post[0]["pairs_since_reset"] <= 3 and len(log.types("freshness_reset")) == 2, shown_post[0])
check("restart: displayed sequence strictly increasing across the restart",
      all(b > a for a, b in zip(seqs_all, seqs_all[1:])))

# 2j missing frames are counted, not treated as stale
P, log, rows, host = make()
gap = [(s, s * 50.0, s * 50.0 + 15) for s in range(40) if not 20 <= s <= 24]
shown = run(P, host, gap, 2200)
check("missing seqs counted as missing, no rejection", P.c["missing"] == 5 and P.c["rejected_excess_delay"] == 0)

# 2k absolute limit with trusted clock
P, log, rows, host = make({"max_age_ms": 80.0}, host="this-host")
slow = [(s, s * 50.0, s * 50.0 + 120) for s in range(30)]
shown = run(P, host, slow, 2000)
check("absolute limit (trusted clock): pairs older than max_age rejected, reason logged",
      not shown and P.c["rejected_absolute_age"] > 0
      and all("absolute_age" in p["reasons"] for p in log.types("pair_rejected")))

# ---------------------------------------------------------------------------
# 3. Replay of the recorded failing run (20261105_113138) as a regression
# ---------------------------------------------------------------------------
if PREV_RX.exists():
    arr = [r for r in csv.DictReader(open(PREV_RX / "arrivals.csv", encoding="utf-8")) if r["sei"] == "ok"]
    pev = pc.read_events(PREV_PUB / "events.jsonl")
    stall_end = next(e for e in pev if e["type"] == "stall_end")
    off = sorted(int(a["t_arrival_utc_ns"]) - int(a["t_arrival_mono_ns"]) for a in arr)[len(arr) // 2]

    def replay(enabled):
        log = Log()
        pol = rr.FreshnessPolicy(enabled=enabled, local_host=arr[0]["host"])
        P = rr.Presenter("A", 20, 125, log, None, policy=pol)
        ev = sorted(arr, key=lambda a: int(a["t_arrival_mono_ns"]))
        t = int(ev[0]["t_arrival_mono_ns"])
        end = int(ev[-1]["t_arrival_mono_ns"]) + 200_000_000
        i, shown = 0, []
        while t <= end:
            while i < len(ev) and int(ev[i]["t_arrival_mono_ns"]) <= t:
                a = ev[i]
                m = pc.FrameMeta(a["camera"], a["meta_eye"], int(a["seq"]), int(a["t_dev_ns"]),
                                 int(a["t_host_mono_ns"]), int(a["t_utc_ns"]), a["host"], a["session"],
                                 a["trial"], int(a["config_id"]), int(a["flags"]))
                P.on_frame(a["eye"], {"meta": m, "t_arrival_mono": int(a["t_arrival_mono_ns"]),
                                      "t_arrival_utc": int(a["t_arrival_utc_ns"]),
                                      "t_decoded_mono": int(a["t_decoded_mono_ns"]),
                                      "barcode": (int(a["barcode_seq"]), int(a["barcode_eye"]), int(a["barcode_camera"]))})
                i += 1
            r = P.tick(t, t + off)
            if r:
                shown.append(r)
            t += int(1e9 / 60)
        aft = [r for r in shown if r["t_display_utc_ns"] >= stall_end["t_utc_ns"]]
        return shown, aft, P, log

    shown, aft, P, log = replay(False)
    check("replay of recorded run, safeguard OFF: reproduces S7 failure (seq 599 shown after stall)",
          aft and aft[0]["seq"] == 599, aft[:1])
    shown, aft, P, log = replay(True)
    sq = [r["seq"] for r in shown]
    check("replay, safeguard ON: 599 and burst 600-613 not shown after the stall",
          not any(599 <= r["seq"] <= 613 for r in aft), [r["seq"] for r in aft[:3]])
    check("replay, safeguard ON: first display after stall within threshold, monotonic display",
          aft and float(aft[0]["excess_ms"]) <= 100 and all(b > a for a, b in zip(sq, sq[1:])))
    check("replay, safeguard ON: normal frames not rejected outside the stall (< 1 %)",
          P.c["rejected_excess_delay"] <= 0.01 * len(shown) + 3, P.c)
else:
    check("replay of recorded run (results folder present)", False, "missing " + str(PREV_RX))

print()
n_fail = sum(1 for _, ok in RESULTS if not ok)
print("{} checks, {} failed".format(len(RESULTS), n_fail))
sys.exit(1 if n_fail else 0)

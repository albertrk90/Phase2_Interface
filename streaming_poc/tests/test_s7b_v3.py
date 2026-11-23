"""Offline tests for S7b v3 (smoke_check.s7b_v3_check; approved 6 Nov 2026, post-hoc
after the T4 v1 FAIL) and for v1 / v2 and every other smoke criterion staying
unchanged.

  * synthetic cases (one stall: seq 40-53, t = 2.0-2.7 s; pre-stall frame 39):
    - no per-stall recovery rule: the T4 burst pattern PASSes in v3 although v2
      FAILs it on "recovery not at the first frame";
    - pre-stall frame transport-held only if send->receipt > 50 ms (either eye):
      the T4 drop-stall pattern (2.5 ms, arrived 1 ms after the stall start,
      displayed) PASSes in v3 and still FAILs in v2; 50.0 ms is not held; 50.1 ms
      is held and FAILs without a rejection (designed to fail); one slow eye is
      enough; a held pre-stall frame that is rejected PASSes; not sent / not
      received are reported and never held;
    - unchanged v2 rules, designed to fail: rejection only outside the window,
      rejection of an unrelated frame, 3 held frames shown, a displayed pair
      over the threshold, a "fresh" label without verification, a non-increasing
      display order; safeguard off and no stalls -> NOT_TESTED;
    - the three measurements (transport delay, freshness, inappropriate display)
      are reported separately.
  * recorded evidence (read-only; nothing written): the G1 rerun (camera A) and
    the T4 Python reference reproduce EVERY recorded smoke criterion exactly
    (S7b v1 FAIL / PASS and v2 FAIL as recorded); S7b v3 is absent unless asked
    for and adding it changes no other key; evidence files unchanged.

Run: .venv\\Scripts\\python.exe -I tests\\test_s7b_v3.py
"""
import hashlib
import json
import pathlib
import sys

POC = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))

import smoke_check as sc  # noqa: E402

RESULTS = []
S = 10**9
MS = 10**6


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + str(detail)) if detail and not cond else ""))


STALL = {"start_ns": 2 * S, "end_ns": int(2.7 * S), "seq_first": 40, "seq_last": 53}


def build(mode="burst", held_arrive=True, rej=((2.5, 41, ()),), shown=(), pre_s2r=(2.5, 2.5), pre_arrival_s=2.001,
          pre_sent=True, pre_received=True, show_pre=False, over=(), fresh_bad=(), order_ok=True, enabled=True,
          extra_frames=()):
    """Returns the s7b_v3_check arguments. Monotonic and UTC clocks are equal here."""
    stall = dict(STALL, mode=mode)
    sent, send, ok_arr = [], {}, []
    for e, s2r in zip(("left", "right"), pre_s2r):           # pre-stall frame 39
        arr_ns = int(pre_arrival_s * S)
        snd = arr_ns - int(s2r * MS)
        if pre_sent:
            sent.append({"eye": e, "seq": "39", "t_host_mono_ns": str(snd - 13 * MS), "t_sent_mono_ns": str(snd)})
            send[(e, 39)] = snd
            if pre_received:
                ok_arr.append({"eye": e, "seq": "39", "t_arrival_utc_ns": str(arr_ns), "t_arrival_mono_ns": str(arr_ns)})
    if held_arrive:
        for q in range(40, 54):
            for e in ("left", "right"):
                t = int(2.75 * S) + q * MS
                ok_arr.append({"eye": e, "seq": str(q), "t_arrival_utc_ns": str(t), "t_arrival_mono_ns": str(t)})
    frames = []
    if show_pre:
        frames.append({"seq": "39", "t_display_utc_ns": str(int(pre_arrival_s * S) + 7 * MS), "excess_ms": "74", "abs_age_ms": "88"})
    frames += [{"seq": str(q), "t_display_utc_ns": str(int(2.8 * S) + q * MS), "excess_ms": "5", "abs_age_ms": "30"}
               for q in list(shown)]
    frames += [{"seq": str(q), "t_display_utc_ns": str(int(2.9 * S) + q * MS), "excess_ms": "5", "abs_age_ms": "30"}
               for q in (55, 56)]
    frames += list(extra_frames)
    frames.sort(key=lambda f: int(f["t_display_utc_ns"]))
    rejects = [{"t_utc_ns": int(t * S), "payload": {"seq": q, "obsolete_older": list(ob)}} for t, q, ob in rej]
    dseq = [int(f["seq"]) for f in frames]
    disp_order = order_ok and all(b > a for a, b in zip(dseq, dseq[1:]))
    return ([stall], frames, ok_arr, send, sent, rejects, {"enabled": enabled}, list(over), list(fresh_bad),
            disp_order, dseq, 100.0)


def v3(**kw):
    return sc.s7b_v3_check(*build(**kw))


def v2_same(recover, **kw):
    stalls, frames, ok_arr, send, sent, rejects, pol, over, fresh_bad, disp_order, dseq, thr = build(**kw)
    s7 = [{"first_display_after": {"seq": 55}, "frames_to_recover_age": recover}]
    return sc.s7b_v2(stalls, s7, frames, ok_arr, rejects, pol, over, fresh_bad, disp_order, dseq, thr)


# --- change 1: no duplicate recovery rule ---------------------------------------------
r = v3()
check("burst stall, held arrived, rejection in window -> PASS", r["verdict"] == "PASS", r)
check("v3 result: version 3, post-hoc label, recovery deferred to M1.4/G1.4",
      r["version"] == 3 and "post-hoc" in r["post_hoc"].lower() and "M1.4" in r["recovery"], r)
check("v3 has no frames_to_recover input or field", "frames_to_recover_age" not in json.dumps(r))
check("same input with recovery at frame 2: v2 FAILs (the T4 burst pattern) ...",
      v2_same(2)["verdict"] == "FAIL")
check("... and v3 PASSes (recovery is no longer duplicated)", v3()["verdict"] == "PASS")

# --- change 2: pre-stall frame held only if transport-held ----------------------------
t4drop = dict(mode="drop", held_arrive=False, rej=(), pre_s2r=(2.5, 2.5), pre_arrival_s=2.001, show_pre=True)
r = v3(**t4drop)
st = r["stalls"][0]
check("T4 drop pattern (pre-stall 2.5 ms send->receipt, arrived 1 ms after the start, displayed) -> PASS",
      r["verdict"] == "PASS", r)
check("  pre-stall frame not transport-held, not in the held set, rejection not applicable",
      st["transport_delay"]["transport_held"] is False and st["transport_delay"]["pre_stall_in_held_set"] is False
      and st["inappropriate_display"]["rejection_requirement"].startswith("not applicable")
      and st["inappropriate_display"]["held_shown_after_stall_start"] == [], st)
check("  the same input still FAILs under v2 (v2 unchanged)", v2_same(0, **t4drop)["verdict"] == "FAIL")
r = v3(**dict(t4drop, pre_s2r=(50.0, 50.0)))
check("boundary: send->receipt exactly 50.0 ms -> not held -> PASS",
      r["verdict"] == "PASS" and r["stalls"][0]["transport_delay"]["transport_held"] is False, r["stalls"][0])
r = v3(**dict(t4drop, pre_s2r=(50.1, 50.1)))
check("boundary: 50.1 ms -> held; arrived after the start, shown, never rejected -> FAIL (designed to fail)",
      r["verdict"] == "FAIL" and r["stalls"][0]["transport_delay"]["transport_held"] is True
      and r["stalls"][0]["inappropriate_display"]["held_shown_after_stall_start"] == [39], r["stalls"][0])
r = v3(**dict(t4drop, pre_s2r=(60.0, 3.0)))
check("one eye over 50 ms is enough to be held -> FAIL without a rejection (designed to fail)",
      r["verdict"] == "FAIL" and r["stalls"][0]["transport_delay"]["transport_held"] is True, r["stalls"][0])
r = v3(**dict(t4drop, pre_s2r=(60.0, 60.0), show_pre=False, rej=((2.1, 39, ()),)))
check("held pre-stall frame rejected in the window and not shown -> PASS", r["verdict"] == "PASS", r["stalls"][0])
r = v3(**dict(t4drop, pre_s2r=(60.0, 60.0), show_pre=True, rej=((2.1, 39, ()),)))
check("held pre-stall frame shown once (<= 2) with a rejection on a held frame -> PASS (limit unchanged)",
      r["verdict"] == "PASS", r["stalls"][0])
r = v3(**dict(t4drop, pre_sent=False, show_pre=False))
td = r["stalls"][0]["transport_delay"]
check("pre-stall frame never sent: reported (sent False), not held -> PASS",
      r["verdict"] == "PASS" and td["transport_held"] is False and not any(e["sent"] for e in td["eyes"]), td)
r = v3(**dict(t4drop, pre_received=False, show_pre=False))
td = r["stalls"][0]["transport_delay"]
check("pre-stall frame sent but never received: send->receipt None, not held -> PASS",
      r["verdict"] == "PASS" and td["transport_held"] is False and all(e["send_to_receipt_ms"] is None for e in td["eyes"]), td)
check("capture->send (publisher side) reported separately from send->receipt",
      v3(**t4drop)["stalls"][0]["transport_delay"]["eyes"][0]["capture_to_send_ms"] == 13.0)

# --- unchanged v2 rules (designed to fail) -------------------------------------------
check("held frames arrived, only rejection 2.1 s after the stall end -> FAIL", v3(rej=((4.8, 41, ()),))["verdict"] == "FAIL")
check("rejection in window but of an unrelated frame -> FAIL", v3(rej=((2.5, 200, ()),))["verdict"] == "FAIL")
check("held frame rejected as obsolete backlog of a later rejection -> PASS",
      v3(rej=((2.9, 60, (44, 45)),))["verdict"] == "PASS")
check("3 held frames shown -> FAIL", v3(shown=(50, 51, 52))["verdict"] == "FAIL")
check("2 held frames shown -> PASS (limit <= 2)", v3(shown=(52, 53))["verdict"] == "PASS")
check("a displayed pair over the excess threshold -> FAIL", v3(over=[{"excess_ms": "150"}])["verdict"] == "FAIL")
check("a 'fresh' label without verification -> FAIL", v3(fresh_bad=[{"seq": "55"}])["verdict"] == "FAIL")
check("display order not strictly increasing -> FAIL", v3(order_ok=False)["verdict"] == "FAIL")
check("freshness safeguard off -> NOT_TESTED", v3(enabled=False)["verdict"] == "NOT_TESTED")
a = list(build())
a[0] = []
check("no stalls -> NOT_TESTED", sc.s7b_v3_check(*a)["verdict"] == "NOT_TESTED")

# --- separate measurements ------------------------------------------------------------
late = {"seq": "54", "t_display_utc_ns": str(int(2.85 * S)), "excess_ms": "120", "abs_age_ms": "140", "abs_status": "above"}
r = v3(extra_frames=[late], over=[late])
st = r["stalls"][0]
check("three separate blocks per stall: transport_delay, freshness, inappropriate_display",
      {"transport_delay", "freshness", "inappropriate_display"} <= set(st), list(st))
check("freshness block counts the late display (over threshold 1, abs not within 1, max excess 120)",
      st["freshness"]["over_threshold"] == 1 and st["freshness"]["abs_status_not_within"] == 1
      and st["freshness"]["max_excess_ms"] == 120.0, st["freshness"])
check("... it is not an inappropriate display of a held frame, and the global freshness rule FAILs the run",
      st["inappropriate_display"]["held_shown_after_stall_start"] == [] and r["verdict"] == "FAIL")

# --- recorded evidence: every smoke criterion reproduced; nothing written ------------
RES = POC / "results"
CASES = [("G1 rerun A", RES / "smoke_20261105_151122", RES / "pub_20261105_151130_A_g1r_A", RES / "rx_20261105_151132_A_g1r_A",
          {"S7b_stale_frame_rejection": "FAIL"}),
         ("T4 Python A", RES / "smoke_20261105_173500", RES / "pub_20261105_173508_A_m1t4_A", RES / "rx_20261105_173510_A_m1t4_A",
          {"S7b_stale_frame_rejection": "PASS", "S7b_v2_stale_frame_rejection": "FAIL"})]
for name, ev, pub, rx, expect in CASES:
    if not ev.exists():
        continue
    dirs = (ev, pub, rx)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for d in dirs for p in d.rglob("*") if p.is_file()}
    recorded = json.loads((ev / "smoke_report.json").read_text(encoding="utf-8-sig"))
    rec = recorded["streams"]["A:" + rx.name]["criteria"]
    restart = json.loads((ev / "restart.json").read_text(encoding="utf-8-sig"))
    C, _M = sc.stream_analysis(pub, rx, sc.mediamtx_text(ev), restart)
    Cj = json.loads(json.dumps(C))
    # keys added to smoke_check after a report was recorded (S7b v2: 5 Nov, after the G1 rerun)
    later = set(Cj) - set(rec)
    check("{}: every recorded smoke criterion reproduced exactly (default call)".format(name),
          all(Cj.get(k) == rec[k] for k in rec) and later <= {"S7b_v2_stale_frame_rejection"},
          ([k for k in rec if Cj.get(k) != rec[k]], later))
    check("{}: recorded S7b verdicts {}".format(name, expect), all(rec[k]["verdict"] == C[k]["verdict"] == v for k, v in expect.items()),
          {k: (rec[k]["verdict"], C[k]["verdict"]) for k in expect})
    check("{}: no S7b v3 key unless requested".format(name), "S7b_v3_stale_frame_rejection" not in C)
    C3, _M3 = sc.stream_analysis(pub, rx, sc.mediamtx_text(ev), restart, s7b_v3=True)
    check("{}: with s7b_v3=True every other key is unchanged".format(name),
          json.loads(json.dumps({k: v for k, v in C3.items() if k != "S7b_v3_stale_frame_rejection"})) == Cj)
    v3r = C3["S7b_v3_stale_frame_rejection"]
    if name.startswith("T4"):
        d = v3r["stalls"][2]
        check("T4 Python: v3 drop stall -> pre-stall 3599 not transport-held (fixture, not a recorded verdict)",
              d["held_seq"] == [3600, 3613] and d["transport_delay"]["transport_held"] is False and d["stall_ok"], d)
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for d in dirs for p in d.rglob("*") if p.is_file()}
    check("{}: evidence unchanged (no file written or modified)".format(name), before == after)

print()
n_fail = sum(1 for _, ok in RESULTS if not ok)
print("{} checks, {} failed".format(len(RESULTS), n_fail))
sys.exit(1 if n_fail else 0)

"""LANTERN host check (SIMULATION ONLY; 25-26 Nov 2026): the trial host's Lunar Lantern mode, errors and interventions, then RegoLight.

Live, on spare loopback ports with their own state dirs: Mohsi's server (simulator routes only) + the trial host. A DEVELOPMENT
identity (P950, condition A, active early + middle, SAGAT early) selects the schedule's development_lantern entry: +20 mm along the
row at P05 and at P10.
  L1  trial_baseline (lunar_lantern, P950)  -> lantern layout, config lantern_trial_v2, errors at P05 / P10
  L2  place_p01..place_p04                   -> nominal: released 10 mm short, settled into the pocket (<= 1 mm), arm back in travel
  L3  place_p05 (error +20 mm), pause_at_hover -> rests at first contact (~+20 mm along the row, perched); the robot waits at the hover
  L4  recover_slot_p05                       -> Facilitator A's hand move into the recovery stand, the robot's pick there, hold on line +20
  L5  nudge_along_rail_plus_10mm             -> refused before motion (along the row only); nothing moved
  L6  nudge_across_minus_10mm x2             -> line +20 -> 0; each achieved about -10 mm along the row
  L7  place_release                          -> down the centred line: the plate seats in its pocket (<= 1 mm); the arm waits at the
                                                hover up the plate axis (26 Nov: the participant re-decides on the re-placed plate)
  L8  place_p06..place_p09                   -> nominal
  L9  place_p10 + hold request               -> held before the descent on line +20 (plate attached)
  L10 nudge_across_plus_10mm, retry_p10      -> Retry discards the adjustment: the plate rests at the scheduled +20 mm again
  L11 place_p11                              -> P10's plate is settled into its pocket first (trial rule), then P11 nominal
  L12 recover_p11 (in-place recovery)        -> refused before motion on the lantern
  L13 trial_home                             -> upright at HOME (4030 mm)
  L14 trial_baseline (RegoLight, P01 / C / 1), place_p01 -> the RegoLight trial still works
Nothing here is physical.

    "..\\Phase 2_COROL\\lab_digital_twin\\.venv\\Scripts\\python.exe" -I twin_link\\twin_lantern_check.py [--twin-port 8094] [--host-port 8099]
"""
import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import twin_home_check as hc  # noqa: E402  (get / post / wait_url, paths)
import twin_schedule_check as sc  # noqa: E402  (study identities from the Unity protocol)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--twin-port", type=int, default=8094)
    ap.add_argument("--host-port", type=int, default=8099)
    a = ap.parse_args()
    TW, HO = "http://127.0.0.1:{}".format(a.twin_port), "http://127.0.0.1:{}".format(a.host_port)
    run = HERE / "runs" / ("lantern_check_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    run.mkdir(parents=True)
    stamp = datetime.datetime.now().strftime("%H%M%S")
    procs, results = [], []

    def check(name, ok, detail=""):
        results.append({"check": name, "pass": bool(ok), "detail": detail})
        print("{} {}  {}".format("PASS" if ok else "FAIL", name, detail), flush=True)

    def step(n, name, params=None):
        rid = "LLCHECK-{}-{}".format(stamp, n)
        hc.post(HO + "/api/requests", {"request_id": rid, "step": name, "params": params or {}})
        t0 = time.time()
        while time.time() - t0 < 400:
            r = hc.get(HO + "/api/requests/" + rid)
            if r.get("state") in ("COMPLETED", "FAILED", "UNKNOWN_OUTCOME", "REJECTED", "REFUSED"):
                return r
            time.sleep(0.2)
        return {"state": "TIMEOUT"}

    proto = json.loads(sc.PROTOCOL.read_text(encoding="utf-8"))
    ids = sc.identities(proto)

    def ident(pid, cid, t):
        return next(dict(i) for i in ids if i["participant_id"] == pid and i["condition"] == cid and i["trial_id"].endswith("T{}".format(t)))

    try:
        procs.append(subprocess.Popen([str(hc.DTPY), "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(a.twin_port)],
                                      cwd=str(hc.DT), env=dict(os.environ, PHASE2_STATE_DIR=str(run / "twin_state")),
                                      stdout=open(run / "twin_server.txt", "w"), stderr=subprocess.STDOUT))
        if not hc.wait_url(TW + "/api/sim/state", 90):
            check("L0_twin_up", False)
            return 1
        hc.post(TW + "/api/sim/remote", {"enabled": True})
        hc.post(TW + "/api/sim/tcp", {"robot": "ur20", "offset": [0, 0, 0.1946, 0, 0, 0]})
        procs.append(subprocess.Popen([str(hc.DTPY), "Albert/phase2/trial_host.py", "--port", str(a.host_port), "--twin", TW,
                                       "--state-dir", str(run / "host_state"), "--run-dir", str(run / "host")],
                                      cwd=str(hc.DT), env=dict(os.environ, DIGITAL_TWIN_URL=TW), stdout=open(run / "host_stdout.txt", "w"),
                                      stderr=subprocess.STDOUT))
        if not (hc.wait_url(HO + "/api/status", 90) and hc.get(HO + "/api/status").get("ready")):
            check("L0_host_ready", False)
            return 1
        def robot():
            st = hc.get(TW + "/api/sim/state")["robots"]["ur20"]
            return st["q_deg"], st["track_mm"]

        def obj(r):
            return (r.get("result") or {}).get("object") or {}

        def rvn(r):
            return obj(r).get("realised_vs_nominal") or {}

        def brick_state(name):
            return (hc.get(TW + "/api/phase2/objects?all=1")["objects"].get(name) or {}).get("state")

        dev = {"participant_id": "P950", "condition": "A", "architecture": "lunar_lantern", "interface": "2d", "trial_id": "B1-T1",
               "allocation": {"active": ["early", "middle"], "inactive": ["late"], "sagat": "early"},
               "schedule_version": proto["participant_schedule"]["schedule_version"]}
        r = step("L1", "trial_baseline", dev)
        res = r.get("result") or {}
        ts = res.get("trial_schedule") or {}
        check("L1_lantern_baseline_with_errors", r.get("state") == "COMPLETED" and res.get("architecture") == "lunar_lantern"
              and res.get("config_version") == "lantern_trial_v2_2026-11-26" and ts.get("errors_at") == ["P05", "P10"],
              json.dumps({"state": r.get("state"), "reason": r.get("reason"), "config": res.get("config_version"), "entry": ts.get("entry"),
                          "errors_at": ts.get("errors_at")})[:400])

        def nominal(lo, hi, tag):
            oks = []
            for k in range(lo, hi + 1):
                r = step("{}-{}".format(tag, k), "place_p{:02d}".format(k))
                e = rvn(r)
                oks.append(r.get("state") == "COMPLETED" and obj(r).get("state") == "released" and e.get("translation_mm", 99) <= 1.0)
                print("   place_p{:02d}: {} {} {} mm".format(k, r.get("state"), obj(r).get("pocket"), e.get("translation_mm")), r.get("reason") or "")
            return oks
        oks = nominal(1, 4, "L2")
        ev = [json.loads(l) for l in (run / "twin_state" / "object_events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        gaps = [e for e in ev if e.get("event") == "settle" and e.get("by") == "settle_after_release"]
        check("L2_nominal_lantern_placements", all(oks) and len(gaps) == 4 and all(abs(e.get("moved_mm", 0) - 10.0) <= 0.5 for e in gaps),
              "{} ok; settles {}".format(sum(oks), [round(e.get("moved_mm", 0), 2) for e in gaps]))
        r = step("L3", "place_p05", {"pause_at_hover": True})           # 26 Nov 2026: a decision point: the robot waits at the hover
        e = rvn(r)
        check("L3_error_rests_at_first_contact", r.get("state") == "COMPLETED" and abs(e.get("along_row_mm", 0) - 20) <= 1.0 and e.get("up_axis_mm", 0) > 5
              and (r.get("result") or {}).get("paused_at_hover") is True
              and obj(r).get("realised_vs_planned_rest_mm") is not None and obj(r)["realised_vs_planned_rest_mm"] <= 1.0, json.dumps({"state": r.get("state"), "reason": r.get("reason"), "realised": e})[:400])
        r = step("L4", "recover_slot_p05")
        res = r.get("result") or {}
        brick = res.get("brick")
        check("L4_recovery_via_the_stand", r.get("state") == "COMPLETED" and res.get("recovery") == "recovery_stand" and brick_state(brick) == "attached",
              json.dumps({"state": r.get("state"), "reason": r.get("reason"), "hand_move": res.get("hand_move"), "brick": brick})[:400])
        q0 = robot()
        r = step("L5", "nudge_along_rail_plus_10mm")
        check("L5_along_rail_refused", str(r.get("reason", "")).startswith("refused_before_motion") and robot() == q0, str(r.get("reason"))[:200])
        ach = []
        for k in (1, 2):
            r = step("L6-{}".format(k), "nudge_across_minus_10mm")
            ach.append(((r.get("result") or {}).get("achieved_by_held_brick") or {}).get("along_row_mm"))
            print("   nudge across -10: {} line {} achieved {}".format(r.get("state"), (r.get("result") or {}).get("line_along_row_mm"), ach[-1]), r.get("reason") or "")
        check("L6_two_nudges_along_the_row", all(a_ is not None and abs(a_ + 10) <= 0.5 for a_ in ach), json.dumps(ach))
        r = step("L7", "place_release")
        e = rvn(r)
        check("L7_place_release_seats_the_plate", r.get("state") == "COMPLETED" and e.get("translation_mm", 99) <= 1.0
              and (r.get("result") or {}).get("paused_at_hover") is True,
              json.dumps({"state": r.get("state"), "reason": r.get("reason"), "paused": (r.get("result") or {}).get("paused_at_hover"), "realised": e})[:400])
        oks = nominal(6, 9, "L8")
        check("L8_nominal_after_the_intervention", all(oks), "{} ok".format(sum(oks)))
        rid = "LLCHECK-{}-L9".format(stamp)
        hc.post(HO + "/api/requests", {"request_id": rid, "step": "place_p10", "params": {}})
        h = hc.post(HO + "/api/hold", {"request_id": rid, "placement_id": "LL-P10", "client_cmd_id": "check"})
        t0 = time.time()
        while time.time() - t0 < 400:
            r = hc.get(HO + "/api/requests/" + rid)
            if r.get("state") in ("COMPLETED", "FAILED", "UNKNOWN_OUTCOME", "REJECTED", "REFUSED"):
                break
            time.sleep(0.2)
        res = r.get("result") or {}
        check("L9_hold_before_the_descent", r.get("state") == "COMPLETED" and res.get("held_before_place") is True and brick_state(res.get("brick")) == "attached",
              json.dumps({"hold_reply": h, "state": r.get("state"), "held": res.get("held_before_place"), "reason": r.get("reason")})[:400])
        r1 = step("L10a", "nudge_across_plus_10mm")
        r = step("L10b", "retry_p10")
        e = rvn(r)
        check("L10_retry_repeats_the_scheduled_error", r1.get("state") == "COMPLETED" and r.get("state") == "COMPLETED"
              and (r.get("result") or {}).get("adjustments") == "discarded"
              and (r.get("result") or {}).get("paused_at_hover") is True and abs(e.get("along_row_mm", 0) - 20) <= 1.0 and e.get("up_axis_mm", 0) > 5,
              json.dumps({"nudge": r1.get("state"), "state": r.get("state"), "reason": r.get("reason"), "realised": e})[:400])
        r = step("L11", "place_p11")
        settled = (r.get("result") or {}).get("settled_before") or []
        check("L11_earlier_plate_settled_then_next_placement", r.get("state") == "COMPLETED" and [x.get("placement_id") for x in settled] == ["P10"]
              and rvn(r).get("translation_mm", 99) <= 1.0, json.dumps({"state": r.get("state"), "settled": settled, "reason": r.get("reason")})[:400])
        q0 = robot()
        r = step("L12", "recover_p11")
        check("L12_in_place_recovery_refused", str(r.get("reason", "")).startswith("refused_before_motion") and robot() == q0, str(r.get("reason"))[:200])
        r = step("L13", "trial_home")
        s = hc.get(TW + "/api/sim/state")["robots"]["ur20"]
        home = abs(s["track_mm"] - hc.HOME_MM) <= 1.0 and max(abs(x - y) for x, y in zip(s["q_deg"], hc.UPRIGHT)) <= 0.1
        check("L13_home_from_the_lantern", r.get("state") == "COMPLETED" and home, json.dumps({"state": r.get("state"), "rail": s["track_mm"], "reason": r.get("reason")}))
        r = step("L14a", "trial_baseline", ident("P01", "C", 1))
        res = r.get("result") or {}
        r2 = step("L14b", "place_p01")
        check("L14_back_to_regolight", r.get("state") == "COMPLETED" and str(res.get("manifest_version", "")).startswith("regolight")
              and r2.get("state") == "COMPLETED" and obj(r2).get("state") == "released",
              json.dumps({"state": r.get("state"), "reason": r.get("reason"), "place": r2.get("state"), "place_reason": r2.get("reason")})[:300])
    finally:
        for p in procs[::-1]:
            try:
                p.terminate()
                p.wait(15)
            except Exception:  # noqa: BLE001
                p.kill()
        n = sum(r["pass"] for r in results)
        (run / "lantern_check.json").write_text(json.dumps({"results": results}, indent=1), encoding="utf-8")
        print("{}: {}/{} checks; evidence {}".format("PASS" if n == len(results) else "FAIL", n, len(results), run))
    return 0 if results and all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

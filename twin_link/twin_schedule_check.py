"""Participant-schedule check on the DIGITAL TWIN REPO (SIMULATION ONLY), 25 Nov 2026.

Unity's protocol carries each study participant's CDP allocations (participant_schedule, exported from the twin's variation schedule
v2). This check confirms the interface's copy and the twin agree, and that the trial host selects entries by the block CONDITION:
  C0  offline: every one of the 288 study trials (24 participants x 4 conditions x 3), identity built from the Unity protocol exactly as
      the player builds it, is accepted by the twin's own lookup with the right entry
  Live (Mohsi's server + the trial host on spare loopback ports, own state dirs):
  S1  P01, Lunar Lantern 2D block (condition A) T1 -> baseline COMPLETED, entry P01/A/T1, errors at the schedule's placements
  S2  P01, RegoLight 2D block (condition C) T1    -> entry P01/C/T1 (a different entry from S1)
  S3  P01 C T1 with another trial's allocation    -> refused before motion
  S4  P31 (not scheduled, not a development id)   -> refused
  S5  P01 without a condition                     -> refused
  S6  a different schedule_version                -> refused
  S7  development id P950                         -> DEV entry (27 Nov 2026: P915 is now a pilot mirror)
  S8  pilot P901 mirroring P01, condition C T1    -> P01's entry P01/C/T1 (27 Nov 2026, pilot mirrors)
  S9  pilot P901 without naming the mirror        -> refused

    "..\\Phase 2_COROL\\lab_digital_twin\\.venv\\Scripts\\python.exe" -I twin_link\\twin_schedule_check.py [--twin-port 8092] [--host-port 8098]
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
from twin_hold_check import DT, DTPY, get, post, wait_url  # noqa: E402

PROTOCOL = HERE.parent / "unity" / "Phase2Client" / "Assets" / "Phase2" / "Experiment" / "Protocols" / "phase2_s41_corol_regolight_nominal_taught.json"
sys.path.insert(0, str(DT / "Albert" / "phase2"))
import variation_schedule as vs  # noqa: E402


def identities(proto):
    """The baseline identity of every study trial, as S4CorolRehearsal builds it (block order from the participant's sequence)."""
    ps = proto["participant_schedule"]
    seqs = proto["sequences"]
    conds = {c["id"]: c for c in proto["conditions"]}
    subs = (proto.get("development_substitutions") or {}).get("architectures") or {}
    out = []
    for pid, info in ps["participants"].items():
        for b, cid in enumerate(seqs[info["sequence"]], 1):
            c = conds[cid]
            for t, al in enumerate(info["conditions"][cid], 1):
                out.append({"participant_id": pid, "architecture": subs.get(c["architecture"], c["architecture"]), "interface": c["interface"],
                            "trial_id": "B{}-T{}".format(b, t), "block": b, "condition": cid, "allocation": al,
                            "schedule_version": ps["schedule_version"]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--twin-port", type=int, default=8092)
    ap.add_argument("--host-port", type=int, default=8098)
    a = ap.parse_args()
    TW, HO = "http://127.0.0.1:{}".format(a.twin_port), "http://127.0.0.1:{}".format(a.host_port)
    run = HERE / "runs" / ("schedule_check_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    run.mkdir(parents=True)
    procs, results = [], []
    stamp = datetime.datetime.now().strftime("%H%M%S")

    def check(name, ok, detail=""):
        results.append({"check": name, "pass": bool(ok), "detail": detail})
        print("{} {}  {}".format("PASS" if ok else "FAIL", name, detail), flush=True)

    proto = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    sched = vs.load(vs.OUT_V2)
    ids = identities(proto)
    bad = []
    for i in ids:
        key, e, prob = vs.lookup(sched, i)
        want = "{}/{}/T{}".format(i["participant_id"], i["condition"], i["trial_id"][-1])
        if prob or key != want:
            bad.append((want, key, prob))
    check("C0_all_study_trials_match_the_twin", len(ids) == 288 and not bad, "{} trials, {} mismatches {}".format(len(ids), len(bad), bad[:3]))

    def baseline(n, params):
        rid = "SCHEDCHECK-{}-{}".format(stamp, n)
        post(HO + "/api/requests", {"request_id": rid, "step": "trial_baseline", "params": params})
        t0 = time.time()
        while time.time() - t0 < 240:
            r = get(HO + "/api/requests/" + rid)
            if r.get("state") in ("COMPLETED", "FAILED", "UNKNOWN_OUTCOME", "REJECTED"):
                return r
            time.sleep(0.2)
        return {"state": "TIMEOUT"}

    def ident(pid, cid, t):
        return next(dict(i) for i in ids if i["participant_id"] == pid and i["condition"] == cid and i["trial_id"].endswith("T{}".format(t)))

    def ts(r):
        return (r.get("result") or {}).get("trial_schedule") or {}

    try:
        procs.append(subprocess.Popen([str(DTPY), "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(a.twin_port)],
                                      cwd=str(DT), env=dict(os.environ, PHASE2_STATE_DIR=str(run / "twin_state")),
                                      stdout=open(run / "twin_server.txt", "w"), stderr=subprocess.STDOUT))
        if not wait_url(TW + "/api/sim/state", 90):
            check("S0_twin_up", False); return 1
        post(TW + "/api/sim/remote", {"enabled": True})
        procs.append(subprocess.Popen([str(DTPY), "Albert/phase2/trial_host.py", "--port", str(a.host_port), "--twin", TW,
                                       "--state-dir", str(run / "host_state"), "--run-dir", str(run / "host")],
                                      cwd=str(DT), env=dict(os.environ, DIGITAL_TWIN_URL=TW), stdout=open(run / "host_stdout.txt", "w"), stderr=subprocess.STDOUT))
        if not (wait_url(HO + "/api/status", 90) and get(HO + "/api/status").get("ready")):
            check("S0_host_ready", False); return 1

        r = baseline("S1", ident("P01", "A", 1))
        want = sorted(sched["trials"]["P01/A/T1"]["variations"])
        check("S1_lunar_lantern_block_entry", r.get("state") == "COMPLETED" and ts(r).get("entry") == "P01/A/T1" and ts(r).get("errors_at") == want
              and ts(r).get("schedule_version") == sched["schedule_version"], json.dumps({"state": r.get("state"), "reason": r.get("reason"), "schedule": ts(r)})[:400])

        r = baseline("S2", ident("P01", "C", 1))
        check("S2_regolight_block_entry", r.get("state") == "COMPLETED" and ts(r).get("entry") == "P01/C/T1"
              and ts(r).get("errors_at") == sorted(sched["trials"]["P01/C/T1"]["variations"]), json.dumps({"state": r.get("state"), "reason": r.get("reason"), "schedule": ts(r)})[:400])

        p = ident("P01", "C", 1)
        other = next(i["allocation"] for i in ids if i["participant_id"] == "P01" and i["condition"] == "C" and i["allocation"] != p["allocation"])
        p["allocation"] = other
        r = baseline("S3", p)
        check("S3_wrong_allocation_refused", r.get("state") in ("REJECTED", "FAILED") and "not the schedule" in str(r.get("reason")), "{} {}".format(r.get("state"), str(r.get("reason"))[:200]))

        p = ident("P01", "C", 1); p["participant_id"] = "P31"
        r = baseline("S4", p)
        check("S4_unscheduled_id_refused", r.get("state") in ("REJECTED", "FAILED") and "neither" in str(r.get("reason")), "{} {}".format(r.get("state"), str(r.get("reason"))[:200]))

        p = ident("P01", "C", 1); p.pop("condition")
        r = baseline("S5", p)
        check("S5_no_condition_refused", r.get("state") in ("REJECTED", "FAILED") and "condition" in str(r.get("reason")), "{} {}".format(r.get("state"), str(r.get("reason"))[:200]))

        p = ident("P01", "C", 1); p["schedule_version"] = "variation_schedule_v1_old"
        r = baseline("S6", p)
        check("S6_schedule_version_pinned", r.get("state") in ("REJECTED", "FAILED") and "expects schedule" in str(r.get("reason")), "{} {}".format(r.get("state"), str(r.get("reason"))[:200]))

        r = baseline("S7", {"participant_id": "P950", "architecture": "regolight", "interface": "2d", "trial_id": "B1-T1", "block": 1, "condition": "C",
                            "allocation": {"active": ["early", "late"], "inactive": ["middle"], "sagat": "late"}})
        check("S7_dev_id_dev_entry", r.get("state") == "COMPLETED" and ts(r).get("entry") == "DEV/early-late/late", json.dumps({"state": r.get("state"), "reason": r.get("reason"), "schedule": ts(r)})[:300])

        p = ident("P01", "C", 1); p["participant_id"] = "P901"; p["mirrors"] = "P01"
        r = baseline("S8", p)
        check("S8_pilot_mirror_runs_the_study_entry", r.get("state") == "COMPLETED" and ts(r).get("entry") == "P01/C/T1"
              and ts(r).get("errors_at") == sorted(sched["trials"]["P01/C/T1"]["variations"]), json.dumps({"state": r.get("state"), "reason": r.get("reason"), "schedule": ts(r)})[:400])

        p = ident("P01", "C", 1); p["participant_id"] = "P901"
        r = baseline("S9", p)
        check("S9_pilot_without_mirror_refused", r.get("state") in ("REJECTED", "FAILED") and "mirrors" in str(r.get("reason")), "{} {}".format(r.get("state"), str(r.get("reason"))[:200]))
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(10)
            except Exception:  # noqa: BLE001
                p.kill()
        n = sum(r["pass"] for r in results)
        (run / "schedule_check.json").write_text(json.dumps({"passed": n, "total": len(results), "results": results}, indent=1), encoding="utf-8")
        print("{}/{} PASS; {}".format(n, len(results), run))
    return 0 if results and all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

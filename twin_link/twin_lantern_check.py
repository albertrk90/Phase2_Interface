"""LANTERN host check (SIMULATION ONLY; 25 Nov 2026): the trial host's Lunar Lantern mode, then back to RegoLight.

Live, on spare loopback ports with their own state dirs: Mohsi's server (simulator routes only) + the trial host. With the study
identity P01 / condition A / trial 1 (Lunar Lantern, from the Unity protocol's participant schedule):
  L1 trial_baseline (architecture lunar_lantern)  -> the lantern layout + config, lantern start pose, errors 0 (scheduled ones not applied)
  L2 place_p01..place_p03                          -> each plate released 10 mm short (+-0.5 mm: movel tolerance), settled into its pocket (<= 1 mm), arm back in travel
  L3 recover_p01 on the lantern                    -> refused before motion (interventions not yet on the lantern); nothing moved
  L4 trial_home                                    -> upright at HOME (4030 mm)
  L5 trial_baseline (RegoLight, P01 / C / 1)       -> back to the RegoLight trial (its own layout), from the lantern side
  L6 place_p01 on RegoLight                        -> the RegoLight placement still works (released 10 mm short, settled)
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
        idA = ident("P01", "A", 1)
        r = step("L1", "trial_baseline", idA)
        res = r.get("result") or {}
        ts = res.get("trial_schedule") or {}
        check("L1_lantern_baseline", r.get("state") == "COMPLETED" and res.get("architecture") == "lunar_lantern"
              and str(res.get("manifest_version", "")).startswith("lantern_assembly") and res.get("config_version") == "lantern_trial_nominal_v1_2026-11-25"
              and ts.get("errors_at") == [] and ts.get("entry") == "P01/A/T1",
              json.dumps({"state": r.get("state"), "reason": r.get("reason"), "manifest": res.get("manifest_version"), "config": res.get("config_version"),
                          "entry": ts.get("entry"), "ignored": ts.get("ignored_scheduled_errors"), "preinstalled": len(res.get("preinstalled") or [])})[:400])
        oks = []
        for k in (1, 2, 3):
            r = step("L2-{}".format(k), "place_p{:02d}".format(k))
            o = (r.get("result") or {}).get("object") or {}
            oks.append(r.get("state") == "COMPLETED" and o.get("state") == "released" and o.get("realised_vs_nominal_mm") is not None and o["realised_vs_nominal_mm"] <= 1.0)
            print("   place_p{:02d}: {} {} {}".format(k, r.get("state"), o.get("pocket"), o.get("realised_vs_nominal_mm")), r.get("reason") or "")
        ev = [json.loads(l) for l in (run / "twin_state" / "object_events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        gaps = [e for e in ev if e.get("event") == "settle" and e.get("by") == "settle_after_release"]
        check("L2_three_lantern_placements", all(oks) and len(gaps) == 3 and all(abs(e.get("moved_mm", 0) - 10.0) <= 0.5 for e in gaps),
              "{} ok; settles {}".format(sum(oks), [round(e.get("moved_mm", 0), 2) for e in gaps]))
        s0 = hc.get(TW + "/api/sim/state")["robots"]["ur20"]
        r = step("L3", "recover_p01")
        s1 = hc.get(TW + "/api/sim/state")["robots"]["ur20"]
        check("L3_intervention_refused_on_the_lantern", str(r.get("reason", "")).startswith("refused_before_motion") and s0["q_deg"] == s1["q_deg"] and s0["track_mm"] == s1["track_mm"],
              "{}: {}".format(r.get("state"), str(r.get("reason"))[:160]))
        r = step("L4", "trial_home")
        s = hc.get(TW + "/api/sim/state")["robots"]["ur20"]
        home = abs(s["track_mm"] - hc.HOME_MM) <= 1.0 and max(abs(x - y) for x, y in zip(s["q_deg"], hc.UPRIGHT)) <= 0.1
        check("L4_home_from_the_lantern", r.get("state") == "COMPLETED" and home, json.dumps({"state": r.get("state"), "rail": s["track_mm"], "reason": r.get("reason")}))
        r = step("L5", "trial_baseline", ident("P01", "C", 1))
        res = r.get("result") or {}
        check("L5_back_to_regolight", r.get("state") == "COMPLETED" and str(res.get("manifest_version", "")).startswith("regolight"),
              json.dumps({"state": r.get("state"), "reason": r.get("reason"), "manifest": res.get("manifest_version")})[:300])
        r = step("L6", "place_p01")
        o = (r.get("result") or {}).get("object") or {}
        check("L6_regolight_placement_still_works", r.get("state") == "COMPLETED" and o.get("state") == "released",
              json.dumps({"state": r.get("state"), "reason": r.get("reason")})[:300])
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

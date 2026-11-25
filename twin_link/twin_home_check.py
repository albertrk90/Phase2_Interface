"""HOME check (SIMULATION ONLY; 25 Nov 2026): every trial starts and ends at HOME, the arm upright at the middle screen.

Live, on spare loopback ports with their own state dirs: Mohsi's server (simulator routes only) + the trial host. Steps:
  H1 trial_baseline from wherever the simulator is                 -> travel pose at the first pick station
  H2 place_p01                                                     -> the arm ends in the sequence (hover over the seat)
  H3 trial_home                                                    -> upright at HOME (rail 4030 mm), the brick stays released
  H4 trial_baseline from HOME                                      -> leaves HOME upright, rail upright to the station, then travel
  H5 trial_home twice                                              -> the second one moves nothing (already home)
  (trial_home refuses before motion while a brick is held; not exercised here)
Nothing here is physical; no robot, rail or gripper endpoint is called.

    "..\\Phase 2_COROL\\lab_digital_twin\\.venv\\Scripts\\python.exe" -I twin_link\\twin_home_check.py [--twin-port 8094] [--host-port 8099]
"""
import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
DT = HERE.parent.parent / "Phase 2_COROL" / "lab_digital_twin" / "digital_twin"
DTPY = DT.parent / ".venv" / "Scripts" / "python.exe"
HOME_MM, UPRIGHT = 4030.0, [90.0, -90.0, 0.0, -180.0, -90.0, 0.0]


def get(u):
    with urllib.request.urlopen(u, timeout=10) as r:
        return json.loads(r.read())


def post(u, b):
    rq = urllib.request.Request(u, json.dumps(b).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(rq, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def wait_url(u, s):
    t0 = time.time()
    while time.time() - t0 < s:
        try:
            get(u)
            return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--twin-port", type=int, default=8094)
    ap.add_argument("--host-port", type=int, default=8099)
    a = ap.parse_args()
    TW, HO = "http://127.0.0.1:{}".format(a.twin_port), "http://127.0.0.1:{}".format(a.host_port)
    run = HERE / "runs" / ("home_check_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    run.mkdir(parents=True)
    stamp = datetime.datetime.now().strftime("%H%M%S")
    procs, results = [], []

    def check(name, ok, detail=""):
        results.append({"check": name, "pass": bool(ok), "detail": detail})
        print("{} {}  {}".format("PASS" if ok else "FAIL", name, detail), flush=True)

    def step(n, name, params=None):
        rid = "HOMECHECK-{}-{}".format(stamp, n)
        post(HO + "/api/requests", {"request_id": rid, "step": name, "params": params or {}})
        t0 = time.time()
        while time.time() - t0 < 300:
            r = get(HO + "/api/requests/" + rid)
            if r.get("state") in ("COMPLETED", "FAILED", "UNKNOWN_OUTCOME", "REJECTED", "REFUSED"):
                return r
            time.sleep(0.2)
        return {"state": "TIMEOUT"}

    def robot():
        u = get(TW + "/api/sim/state")["robots"]["ur20"]
        return u["track_mm"], u["q_deg"]

    def upright_at_home():
        rail, q = robot()
        return abs(rail - HOME_MM) <= 1.0 and max(abs(x - y) for x, y in zip(q, UPRIGHT)) <= 0.1, (round(rail, 1), [round(x, 2) for x in q])

    try:
        procs.append(subprocess.Popen([str(DTPY), "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(a.twin_port)],
                                      cwd=str(DT), env=dict(os.environ, PHASE2_STATE_DIR=str(run / "twin_state")),
                                      stdout=open(run / "twin_server.txt", "w"), stderr=subprocess.STDOUT))
        if not wait_url(TW + "/api/sim/state", 90):
            check("H0_twin_up", False)
            return 1
        post(TW + "/api/sim/remote", {"enabled": True})
        procs.append(subprocess.Popen([str(DTPY), "Albert/phase2/trial_host.py", "--port", str(a.host_port), "--twin", TW,
                                       "--state-dir", str(run / "host_state"), "--run-dir", str(run / "host")],
                                      cwd=str(DT), env=dict(os.environ, DIGITAL_TWIN_URL=TW), stdout=open(run / "host_stdout.txt", "w"),
                                      stderr=subprocess.STDOUT))
        if not (wait_url(HO + "/api/status", 90) and get(HO + "/api/status").get("ready")):
            check("H0_host_ready", False)
            return 1
        steps = [s["name"] if isinstance(s, dict) else s for s in (get(HO + "/api/status").get("steps") or [])]
        check("H0_host_offers_trial_home", "trial_home" in steps, "{} steps".format(len(steps)))

        r1 = step("H1", "trial_baseline")
        sp = (r1.get("result") or {}).get("start_pose") or {}
        check("H1_baseline_from_wherever", r1.get("state") == "COMPLETED", json.dumps({"state": r1.get("state"), "reason": r1.get("reason"), "came_from": sp.get("came_from")})[:300])
        r2 = step("H2", "place_p01")
        check("H2_place_p01", r2.get("state") == "COMPLETED", str(r2.get("reason"))[:200])
        r3 = step("H3", "trial_home")
        ok, where = upright_at_home()
        objs = get(TW + "/api/phase2/objects?all=1")["objects"]
        check("H3_trial_home_upright_at_home", r3.get("state") == "COMPLETED" and ok and not any(o["state"] == "attached" for o in objs.values()),
              json.dumps({"state": r3.get("state"), "reason": r3.get("reason"), "robot": where}))
        r4 = step("H4", "trial_baseline")
        sp = (r4.get("result") or {}).get("start_pose") or {}
        cf = sp.get("came_from") or {}
        subs = [e.get("substep") for e in (r4.get("events") or []) if isinstance(e, dict)]
        check("H4_baseline_leaves_home_upright", r4.get("state") == "COMPLETED" and cf.get("upright") and abs((cf.get("rail_mm") or 0) - HOME_MM) <= 1.0,
              json.dumps({"state": r4.get("state"), "came_from": cf, "start_rail_mm": sp.get("rail_mm")}))
        r5 = step("H5a", "trial_home")
        r6 = step("H5b", "trial_home")
        ok, where = upright_at_home()
        moved = ((r6.get("result") or {}).get("moved") or {}).get("rail_mm")
        check("H5_trial_home_repeat_is_a_no_op", r5.get("state") == "COMPLETED" and r6.get("state") == "COMPLETED" and ok and moved == 0.0,
              json.dumps({"second_moved_rail_mm": moved, "robot": where}))
    finally:
        for p in procs[::-1]:
            try:
                p.terminate()
                p.wait(15)
            except Exception:  # noqa: BLE001
                p.kill()
        n = sum(r["pass"] for r in results)
        (run / "home_check.json").write_text(json.dumps({"results": results}, indent=1), encoding="utf-8")
        print("{}: {}/{} checks; evidence {}".format("PASS" if n == len(results) else "FAIL", n, len(results), run))
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

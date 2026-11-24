"""Hold-before-place check on the DIGITAL TWIN REPO (SIMULATION ONLY), 24 Nov 2026.

A participant's Intervene during a (non-CDP) placement stops the robot at the hover above the receiving pose, before the descent,
holding the brick at the hold height (trial_host.py POST /api/hold). Starts Mohsi's server and the trial host on spare loopback
ports (own brick-state dir), then:
  H1  baseline
  H2  place_p01 + hold request early  -> held_before_place, brick attached (not released)
  H3  one 10 mm nudge (across +) of the held brick
  H4  place_release                  -> released; realised across offset about +10 mm
  H5  place_p02, no hold             -> normal placement
  H6  place_p03 + hold requested only during the final descent -> too late: normal placement (released)
  H7  hold request with no placement running -> refused (moves nothing)

    "..\\Phase 2_COROL\\lab_digital_twin\\.venv\\Scripts\\python.exe" -I twin_link\\twin_hold_check.py [--twin-port 8091] [--host-port 8097]
"""
import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
DT = pathlib.Path(r"C:\Users\a1920234\Documents\Phase 2_COROL\lab_digital_twin\digital_twin")
DTPY = DT.parent / ".venv" / "Scripts" / "python.exe"


def get(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def wait_url(url, s):
    t0 = time.time()
    while time.time() - t0 < s:
        try:
            get(url, 1); return True
        except Exception:  # noqa: BLE001
            time.sleep(0.3)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--twin-port", type=int, default=8091)
    ap.add_argument("--host-port", type=int, default=8097)
    a = ap.parse_args()
    TW, HO = "http://127.0.0.1:{}".format(a.twin_port), "http://127.0.0.1:{}".format(a.host_port)
    run = HERE / "runs" / ("hold_check_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    run.mkdir(parents=True)
    procs, results = [], []
    stamp = datetime.datetime.now().strftime("%H%M%S")

    def check(name, ok, detail=""):
        results.append({"check": name, "pass": bool(ok), "detail": detail})
        print("{} {}  {}".format("PASS" if ok else "FAIL", name, detail), flush=True)

    def submit(step):
        rid = "HOLDCHECK-{}-{}".format(stamp, step)
        rec = post(HO + "/api/requests", {"request_id": rid, "step": step})
        return rid, rec

    def wait_final(rid, s=240, on_progress=None):
        t0 = time.time()
        while time.time() - t0 < s:
            r = get(HO + "/api/requests/" + rid)
            if on_progress:
                on_progress(r)
            if r.get("state") in ("COMPLETED", "FAILED", "UNKNOWN_OUTCOME", "REJECTED"):
                return r
            time.sleep(0.1)
        return {"state": "TIMEOUT"}

    def brick_state(name):
        return get(TW + "/api/phase2/objects").get("objects", {}).get(name, {}).get("state")

    try:
        procs.append(subprocess.Popen([str(DTPY), "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(a.twin_port)],
                                      cwd=str(DT), env=dict(os.environ, PHASE2_STATE_DIR=str(run / "twin_state")),
                                      stdout=open(run / "twin_server.txt", "w"), stderr=subprocess.STDOUT))
        if not wait_url(TW + "/api/sim/state", 90):
            check("H0_twin_up", False); return 1
        post(TW + "/api/sim/remote", {"enabled": True})
        procs.append(subprocess.Popen([str(DTPY), "Albert/phase2/trial_host.py", "--port", str(a.host_port), "--twin", TW,
                                       "--state-dir", str(run / "host_state"), "--run-dir", str(run / "host")],
                                      cwd=str(DT), env=dict(os.environ, DIGITAL_TWIN_URL=TW), stdout=open(run / "host_stdout.txt", "w"), stderr=subprocess.STDOUT))
        if not (wait_url(HO + "/api/status", 90) and get(HO + "/api/status").get("ready")):
            check("H0_host_ready", False); return 1

        rid, _ = submit("trial_baseline")
        r = wait_final(rid)
        check("H1_baseline", r.get("state") == "COMPLETED", r.get("state"))

        rid, _ = submit("place_p01")
        h = post(HO + "/api/hold", {"request_id": rid, "placement_id": "RG-P01", "client_cmd_id": "check"})
        r = wait_final(rid)
        res = r.get("result") or {}
        brick = res.get("brick")
        check("H2_hold_before_descent", r.get("state") == "COMPLETED" and res.get("held_before_place") is True
              and (res.get("object") or {}).get("state") == "attached" and brick_state(brick) == "attached",
              json.dumps({"hold_reply": h, "state": r.get("state"), "held": res.get("held_before_place"), "brick": brick,
                          "twin_brick_state": brick_state(brick), "hold": res.get("hold"), "reason": r.get("reason")})[:400])

        rid, _ = submit("nudge_across_plus_10mm")
        r = wait_final(rid)
        check("H3_nudge_held_brick", r.get("state") == "COMPLETED", json.dumps({"state": r.get("state"), "reason": r.get("reason"),
                                                                              "achieved": (r.get("result") or {}).get("achieved_by_held_brick")})[:300])

        rid, _ = submit("place_release")
        r = wait_final(rid)
        o = (r.get("result") or {}).get("object") or {}
        rvn = o.get("realised_vs_nominal") or {}
        check("H4_place_release", r.get("state") == "COMPLETED" and brick_state(brick) == "released" and abs(float(rvn.get("across_mm", 0)) - 10.0) < 2.0,
              json.dumps({"state": r.get("state"), "reason": r.get("reason"), "twin_brick_state": brick_state(brick), "realised_vs_nominal": rvn})[:300])

        rid, _ = submit("place_p02")
        r = wait_final(rid)
        res = r.get("result") or {}
        check("H5_next_placement_normal", r.get("state") == "COMPLETED" and not res.get("held_before_place") and (res.get("object") or {}).get("state") == "released",
              json.dumps({"state": r.get("state"), "reason": r.get("reason")})[:200])

        rid, _ = submit("place_p03")
        sent = {"hold": None}

        def late(rec):
            if sent["hold"] is None and "place: movel down" in str(rec.get("current_substep") or ""):
                sent["hold"] = post(HO + "/api/hold", {"request_id": rid, "placement_id": "RG-P03", "client_cmd_id": "late"})
        r = wait_final(rid, on_progress=late)
        res = r.get("result") or {}
        check("H6_late_hold_places_normally", sent["hold"] is not None and r.get("state") == "COMPLETED" and not res.get("held_before_place")
              and (res.get("object") or {}).get("state") == "released", json.dumps({"hold_reply": sent["hold"], "state": r.get("state")})[:300])

        h = post(HO + "/api/hold", {"request_id": rid, "placement_id": "RG-P03"})
        check("H7_hold_without_running_placement_refused", h.get("accepted") is False, json.dumps(h)[:200])
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(10)
            except Exception:  # noqa: BLE001
                p.kill()
        (run / "hold_check.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    n = sum(r["pass"] for r in results)
    print("{}: {}/{} checks; evidence {}".format("PASS" if n == len(results) else "FAIL", n, len(results), run))
    return 0 if n == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

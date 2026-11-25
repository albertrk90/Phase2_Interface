"""End-to-end check: the REAL S4 participant interface running one RegoLight trial against the DIGITAL TWIN REPO (SIMULATION ONLY).

Starts, from lab_digital_twin (branch albert-phase2-alpha), on spare loopback ports so nothing else is disturbed:
  * Mohsi's server (digital_twin/server.py, unmodified apart from the one Phase 2 line) via uvicorn on 127.0.0.1
  * the Phase 2 trial host (Albert/phase2/trial_host.py): placements and interventions, request ledger
  * the renderers of the two views (digital_twin/phase2/vcam_render.py: wrist + site)
then the S4 player with the nominal protocol and the scripted participant (-s4CorolTrialScript): 16 placements, formal CDPs at 5
and 10 (SAGAT RG-2 at 10), inactive 14, unscheduled Inspect at 3, a hold merged into CDP 5, an unscheduled Intervene with
recovery, a nudge and Retry at 7, and at CDP 10 Intervene -> recovery -> individual nudges -> controlled place-and-release.
20 Nov 2026 (v5): the development participant gets the variation schedule's DEV entry for this allocation: a position error at
P05 (left in place by Allow; settled to nominal when P06 starts) and at P10 (corrected with 10 mm nudges).
NOTE: the twin server keeps its simulator state in digital_twin/models/sim_state.json: do not run another twin-repo server meanwhile.

    "..\\Phase 2_COROL\\lab_digital_twin\\.venv\\Scripts\\python.exe" -I twin_link\\twin_trial_e2e.py [--twin-port 8091] [--host-port 8097]
(from Phase2_Interface; standard library only, any Python 3 works)
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
ROOT = HERE.parent
DT = pathlib.Path(r"C:\Users\a1920234\Documents\Phase 2_COROL\lab_digital_twin\digital_twin")
DTPY = DT.parent / ".venv" / "Scripts" / "python.exe"
UNITY = ROOT / "unity" / "Phase2Client"
PLAYER = UNITY / "Builds" / "S4" / "SiteWindowSession.exe"
PROTOCOL = UNITY / "Assets" / "Phase2" / "Experiment" / "Protocols" / "phase2_s41_corol_regolight_nominal_taught_quickcheck.json"   # one trial (the manual protocol has 4 x 3)
PHYSICAL = ("/api/execute", "/api/jog", "/api/gripper", "/api/sync/live", "/api/robots/release", "/api/dashboard", "/api/robot/tcp", "/api/stop")


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


def jsonl(p):
    p = pathlib.Path(p)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--twin-port", type=int, default=8091)
    ap.add_argument("--host-port", type=int, default=8097)
    ap.add_argument("--player-seconds", type=float, default=2400)
    ap.add_argument("--relay-port", type=int, default=8198)
    a = ap.parse_args(argv)
    TW, HO = "http://127.0.0.1:{}".format(a.twin_port), "http://127.0.0.1:{}".format(a.host_port)
    for u in (TW, HO):
        try:
            urllib.request.urlopen(u + "/", timeout=1); sys.exit("something already answers at {}".format(u))
        except urllib.error.HTTPError:
            sys.exit("something already answers at {}".format(u))
        except OSError:
            pass
    run = HERE / "runs" / ("twin_trial_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    run.mkdir(parents=True)
    checks, procs, rep = [], [], {"run_dir": str(run)}

    def check(name, ok, detail=""):
        checks.append({"name": name, "pass": bool(ok), "detail": detail})
        print("{} {}  {}".format("PASS" if ok else "FAIL", name, detail), flush=True)

    try:
        srv_log = run / "twin_server.txt"
        # its own brick states (PHASE2_STATE_DIR): a check never inherits a session's objects (the simulator's own state file is shared)
        procs.append(subprocess.Popen([str(DTPY), "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(a.twin_port)],
                                      cwd=str(DT), env=dict(os.environ, PHASE2_STATE_DIR=str(run / "twin_state")),
                                      stdout=open(srv_log, "w"), stderr=subprocess.STDOUT))
        ok = wait_url(TW + "/api/sim/state", 90)
        check("E1_twin_repo_server_up_with_phase2_addons", ok and get(TW + "/api/phase2/objects").get("seq") is not None and "cameras" in get(TW + "/api/phase2/vcam"))
        post(TW + "/api/sim/remote", {"enabled": True})
        env = dict(os.environ, DIGITAL_TWIN_URL=TW)
        procs.append(subprocess.Popen([str(DTPY), "Albert/phase2/trial_host.py", "--port", str(a.host_port), "--twin", TW,
                                       "--state-dir", str(run / "host_state"), "--run-dir", str(run / "host")],
                                      cwd=str(DT), env=env, stdout=open(run / "host_stdout.txt", "w"), stderr=subprocess.STDOUT))
        check("E2_trial_host_up_ready", wait_url(HO + "/api/status", 90) and get(HO + "/api/status").get("ready"), json.dumps({k: get(HO + "/api/status").get(k) for k in ("ready", "twin")})[:300])
        procs.append(subprocess.Popen([str(DTPY), "phase2/vcam_render.py", "--cams", "wrist", "--site", "--twin", TW, "--seconds", str(int(a.player_seconds + 300))],
                                      cwd=str(DT), env=env, stdout=open(run / "renderers.txt", "w"), stderr=subprocess.STDOUT))
        cams = {}
        t0 = time.time()
        while time.time() - t0 < 120:
            cams = get(TW + "/api/phase2/vcam").get("cameras", {})
            if all(cams.get(c, {}).get("seq", 0) > 5 for c in ("wrist", "site")):
                break
            time.sleep(1)
        check("E3_both_rendered_views_streaming", all(cams.get(c, {}).get("seq", 0) > 5 for c in ("wrist", "site")),
              json.dumps({c: {k: cams.get(c, {}).get(k) for k in ("seq", "fps_recent", "width", "height")} for c in ("wrist", "site")}))
        sessions = run / "sessions"
        # 23 Nov 2026: the web facilitator consoles' relay runs too (the scripted trial's facilitators stay automatic): the full trial
        # must work with the console sync going, and the relay must see the app throughout
        import secrets
        rk = {k: secrets.token_urlsafe(16) for k in ("app", "a", "b")}
        RL = "http://127.0.0.1:{}".format(a.relay_port)
        procs.append(subprocess.Popen([sys.executable, str(UNITY / "Tools" / "facilitator_relay" / "facilitator_relay.py"), "--port", str(a.relay_port),
                                       "--app-key=" + rk["app"], "--a-key=" + rk["a"], "--b-key=" + rk["b"], "--log", str(run / "relay_actions.jsonl")],
                                      stdout=open(run / "relay.txt", "w"), stderr=subprocess.STDOUT))
        wait_url(RL + "/api/health", 20)
        relay_seen = []
        pl = subprocess.Popen([str(PLAYER), "-s4Relay", RL, "-s4RelayKey", rk["app"], "-screen-fullscreen", "0", "-screen-width", "1600", "-screen-height", "900", "-s4",
                               "-s4Protocol", str(PROTOCOL), "-s4CorolTrialScript", "-s4Root", str(sessions), "-s4Viewing",
                               "-s3AMode", "virtual", "-s3AVcam", "site", "-s3ASiteRendered", "-s3BMode", "virtual", "-s3BVcam", "wrist",
                               "-s3VcamHost", TW, "-s4CorolHost", HO, "-s3Shots", "-s3Quit", "-s3Seconds", str(int(a.player_seconds)),
                               "-logFile", str(run / "player.log")])
        procs.append(pl)
        t0 = time.time()
        while pl.poll() is None and time.time() - t0 < a.player_seconds + 60:
            time.sleep(10)
            try:
                relay_seen.append(bool(get(RL + "/api/health").get("app_connected")))
                v = get(RL + "/api/role/a/view?k=" + rk["a"])
                if v.get("console") and v.get("status"): relay_seen.append("view")
            except Exception:  # noqa: BLE001
                relay_seen.append(False)
            try:
                st = get(HO + "/api/status")
                print("  {:6.0f}s host active: {}".format(time.time() - t0, st.get("active")), flush=True)
            except Exception:  # noqa: BLE001
                pass
        code = pl.poll()
        check("E4_player_exit_0", code == 0, "exit {}".format(code))
        conn = [x for x in relay_seen if isinstance(x, bool)]
        check("E13_web_console_relay_synced_throughout", conn and sum(conn) >= len(conn) - 1 and "view" in relay_seen,
              "connected {}/{} samples, role view served {}".format(sum(conn), len(conn), "view" in relay_seen))
        pres = sorted((UNITY / "test_results").glob("ai2_s4_*_win64player"), key=lambda p: p.stat().st_mtime)
        if pres:
            summ = json.loads((pres[-1] / "s4_summary.json").read_text(encoding="utf-8")) if (pres[-1] / "s4_summary.json").exists() else {}
            rep["player_dir"] = str(pres[-1])
            rep["player_checks"] = [(c["name"], c["pass"], c.get("detail")) for c in summ.get("checks", [])]
            bad = [c for c in rep["player_checks"] if not c[1]]
            check("E5_player_checks_all_pass", rep["player_checks"] and not bad, "{} checks; failing: {}".format(len(rep["player_checks"]), json.dumps(bad)[:2000]))
        led = jsonl(run / "host_state" / "requests_ledger.jsonl")
        final = {}
        for r in led:
            final[r["request_id"]] = r
        steps = [r["step"] for r in final.values()]
        check("E6_ledger_no_unknown_outcomes", not any(r["state"] == "UNKNOWN_OUTCOME" for r in final.values()), json.dumps({s: steps.count(s) for s in sorted(set(steps))}))
        check("E7_baseline_then_16_placements_each_once", steps.count("trial_baseline") == 1 and all(steps.count("place_p{:02d}".format(i)) == 1 for i in range(1, 17)))
        motions = [s for s in steps if s.startswith(("recover_", "nudge_", "place_release", "retry_", "guide_"))]
        # 23 Nov 2026: a recovery is either recover_pNN (automatic re-grasp) or the guided one (recover_approach_pNN, guide_*, recover_grip_pNN)
        # (and, from 23 Nov 2026 later, the tray-slot recovery recover_slot_pNN: Facilitator A returns the brick to its slot by hand)
        rec = lambda p: "recover_" + p in motions or "recover_slot_" + p in motions or ("recover_approach_" + p in motions and "recover_grip_" + p in motions)
        check("E8_interventions_executed_on_the_twin", rec("p07") and motions.count("place_release") >= 2
              and rec("p10") and "place_release" in motions and sum(s.startswith("nudge_") for s in motions) >= 5
              and all(s.endswith("_10mm") for s in motions if s.startswith("nudge_")), ", ".join(motions))
        slot = [r for r in final.values() if r["step"] == "recover_slot_p10" and r.get("state") == "COMPLETED"]
        sres = (slot[0].get("result") or {}) if slot else {}
        check("E14_recovery_p10_via_recovery_slot_held_above_original_target", slot and sres.get("recovery") in ("tray_slot", "recovery_slot")
              and (sres.get("object") or {}).get("state") == "attached" and not any(s.startswith(("guide_", "recover_grip_")) for s in steps),
              "slot recoveries {}, object {}, hold {}".format(len(slot), (sres.get("object") or {}).get("state"), sres.get("hold")))
        base = next((r for r in final.values() if r["step"] == "trial_baseline"), {})
        ts = (base.get("result") or {}).get("trial_schedule") or {}
        check("E11_trial_errors_from_the_variation_schedule", ts.get("entry") == "DEV/early-middle/middle" and ts.get("errors_at") == ["P05", "P10"], json.dumps(ts)[:400])
        ev = jsonl(run / "twin_state" / "object_events.jsonl")
        # 23 Nov 2026: Facilitator A's by-hand return of a brick to its tray slot (tray-slot recovery) is also a settle; it is checked by E14
        # 25 Nov 2026 (researcher): every release happens 10 mm short of the rest pose and the brick then settles the last 10 mm
        # ('settle_after_release'); those are checked by E15, the trial rule's settles to nominal by E12
        settles = [e for e in ev if e.get("event") == "settle" and e.get("by") not in ("facilitator_a_by_hand", "settle_after_release")]
        check("E12_left_and_corrected_bricks_settled_to_nominal", len(settles) >= 1 and all(e.get("by") == "trial_rule_settle_to_nominal" for e in settles),
              json.dumps([(e.get("object"), round(e.get("moved_mm", 0), 2)) for e in settles]))
        rels = [e for e in ev if e.get("event") == "release" and "10 mm" in str(e.get("milestone", ""))]
        gaps = [e for e in ev if e.get("event") == "settle" and e.get("by") == "settle_after_release"]
        check("E15_every_release_10mm_short_then_settled", len(rels) >= 16 and len(gaps) == len(rels)
              and all(abs(e.get("moved_mm", 0) - 10.0) <= 0.1 for e in gaps),
              "{} releases 10 mm short, {} settles; moved {}".format(len(rels), len(gaps), sorted({round(e.get("moved_mm", 0), 2) for e in gaps})))
        objs = get(TW + "/api/phase2/objects?all=1")["objects"]
        import collections
        cnt = collections.Counter(o["state"] for o in objs.values())
        check("E9_final_assembly_16_released_20_preinstalled", cnt.get("released") == 16 and cnt.get("preinstalled") == 20 and not cnt.get("attached"), json.dumps(cnt))
        log = srv_log.read_text(encoding="utf-8", errors="replace")
        # anything that ACTS on the real cell: a POST to a physical route, or the real-gripper pass-through (the viewer pages poll the
        # live-sync status with GETs on their own; that is a read of the server's memory)
        hits = [l for l in log.splitlines() if any('"POST {}'.format(p) in l for p in PHYSICAL) or '"GET /api/gripper' in l]
        check("E10_no_physical_endpoint_requested", not hits, json.dumps(hits[:5]))
    finally:
        for p in procs[::-1]:
            try:
                p.terminate(); p.wait(10)
            except Exception:  # noqa: BLE001
                p.kill()
    rep["checks"] = checks
    (run / "twin_trial_e2e.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    n = sum(c["pass"] for c in checks)
    print("{}: {}/{} checks; evidence {}".format("PASS" if n == len(checks) else "FAIL", n, len(checks), run))
    return 0 if n == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

"""Offline tests for tools/analyse_stage2.py (Task 06 Stage 2). Synthetic gateway evidence with KNOWN
latencies (capture->host 73 ms, host->send 1.5 ms; the fake Unity adds send->arrival 2.5 ms) and the fake
Unity generator; every integrity criterion has a designed-to-fail case.
Run: camera_gateway\\.venv\\Scripts\\python.exe -I camera_gateway\\tests\\test_stage2_analysis.py
"""
import csv
import json
import pathlib
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
GW = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(GW), str(GW / "tools")]

import analyse_stage2 as a2  # noqa: E402
import camera_gateway_a as cga  # noqa: E402
import fake_unity_player as fu  # noqa: E402

RESULTS = []
MS = 1_000_000
T0 = 50_000 * MS
OFF = 1_700_000_000 * 10**9


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + str(detail)[:300]) if detail and not cond else ""))


def gw_report(**over):
    ok = {"setIrLaserDotProjectorIntensity": True, "setIrFloodLightIntensity": True}
    r = {"selection": {"actual_device_id": cga.CAMERA_A_ID, "actual_ip": "169.254.1.222", "preflight_seen_state": "XLinkDeviceState.X_LINK_BOOTLOADER"},
         "device_read_only": {"getBootloaderVersion": "0.0.26"},
         "calibration_vs_baselines_before_start": [{"equal": True}, {"equal": True}], "calibration_in_session": {"equal": True},
         "calibration_post_run": {"status": "read_ok", "equal": True, "last_precheck": {"seen_state": "XLinkDeviceState.X_LINK_BOOTLOADER"}},
         "calibration_unchanged": True, "auto_calibration_mode": "AutoCalibrationMode.OFF", "ir_off_before_start": ok, "ir_off_after_start": ok,
         "stop_reason": "stop_file", "errors": [], "pipeline_stopped": True, "device_closed": True,
         "senders": {e: {"sent": 100, "packaging_errors": 0, "joined": True} for e in ("left", "right")},
         "gop_queues": {}}
    r.update(over)
    return r


def make_gw(d, n=600, stall=range(60, 69), dropped=range(60, 100), link_loss_at=None):
    d.mkdir(parents=True)
    cap, sent = [], []
    for q in range(n):
        for e in ("left", "right"):
            th = T0 + q * 50 * MS
            lat = 73.0 + ((700 - (q - 60) * 37) if q in stall else 0)
            tr = th + int(lat * MS)
            cap.append({"eye": e, "seq": q, "t_dev_ns": th - 5 * 10**9, "t_host_mono_ns": th, "t_received_mono_ns": tr,
                        "host_receipt_minus_capture_ms": round(lat, 2)})
            if q not in dropped:
                sent.append({"eye": e, "seq": q, "segment": 1, "t_dev_ns": th - 5 * 10**9, "t_host_mono_ns": th, "t_utc_ns": th + OFF,
                             "flags": 0, "keyframe": int(q % 20 == 0), "bytes": 40000, "t_sent_mono_ns": tr + 1_500_000,
                             "capture_to_send_ms": 0})
    for name, rows_ in (("captured.csv", cap), ("sent.csv", sent)):
        with open(d / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_[0]))
            w.writeheader()
            w.writerows(rows_)
    ev = [{"type": "link_up", "t_mono_ns": T0, "payload": {"eye": e}} for e in ("left", "right")]
    if link_loss_at is not None:
        ev.append({"type": "link_down", "t_mono_ns": T0 + link_loss_at * 50 * MS, "payload": {"eye": "left"}})
    (d / "events.jsonl").write_text("\n".join(json.dumps(x) for x in ev), encoding="utf-8")
    return sent


def make_unity(d, sent, fault="none", counts_over=None, t_lo=T0, t_hi=T0 + 30 * 10**9, frames_edit=None):
    arr, frames, events, counts = fu.generate([{k: int(v) if k != "eye" else v for k, v in s.items() if k != "capture_to_send_ms"}
                                               for s in sent], t_lo, t_hi, OFF, fault=fault)
    if frames_edit:
        frames = frames_edit(frames)
    counts.update(counts_over or {})
    d.mkdir(parents=True)
    for name, rows_, cols in (("arrivals.csv", arr, fu.ARR_COLS), ("frames.csv", frames, fu.FRAME_COLS)):
        with open(d / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows_)
    (d / "events.jsonl").write_text("\n".join(json.dumps({"type": t, "t_mono_ns": tm, "payload": p}) for t, tm, p in
                                              [("run_start", t_lo, {})] + events), encoding="utf-8")
    summ = {"stop_reason": "max_seconds", "presenter": {"counts": counts, "freshness_policy": {"fresh_age_ms": 150}},
            "readers": {e: {"sei_errors": 0, "decode_errors": 0, "no_sei": 0} for e in ("left", "right")},
            "unity": {"source": "camera", "mode": "rtsp", "render_check": {"pass": True, "crop": [39, 6, 1238, 770]},
                      "render_check_right": {"pass": True, "crop": [39, 6, 1238, 770]}, "shutdown": {"readers_joined": True}}}
    (d / "summary.json").write_text(json.dumps(summ), encoding="utf-8")


def runner_status(d, **over):
    s = {"mediamtx_config_verified": True, "port_8554_free_before": True, "mediamtx_started": True, "mediamtx_stopped": True,
         "mediamtx_sockets": [{"proto": "TCP", "address": "127.0.0.1", "port": 8554}], "unity_exit_code": 0, "new_crash_dumps": [],
         "final_check": {"gateway_processes": [], "unity_processes": [], "mediamtx_processes": [], "port_8554_free": True}}
    s.update(over)
    d.mkdir(parents=True, exist_ok=True)
    (d / "runner_status.json").write_text(json.dumps(s), encoding="utf-8")


def case(tmp, name, report=None, unity_fault="none", counts_over=None, run_over=None, link_loss_at=None, frames_edit=None):
    base = tmp / name
    sent = make_gw(base / "gw", link_loss_at=link_loss_at)
    (base / "gw" / "report.json").write_text(json.dumps(report or gw_report()), encoding="utf-8")
    make_unity(base / "u", sent, unity_fault, counts_over, frames_edit=frames_edit)
    runner_status(base / "run", **(run_over or {}))
    return a2.analyse(base / "gw", base / "u", base / "run", oracle=False)


tmp = pathlib.Path(tempfile.mkdtemp(prefix="s2test_"))
try:
    r = case(tmp, "ok")
    C = r["criteria"]
    check("normal run: S1-S9 and S11 PASS; S10 NOT_TESTED without ops.csv -> overall INCOMPLETE",
          all(C[k] == "PASS" for k in C if k != "S10_oracle_replay") and C["S10_oracle_replay"] == "NOT_TESTED"
          and r["overall_integrity"] == "INCOMPLETE", C)
    L = r["measurements"]["latency_ms"]
    dp = L["displayed_pairs"]
    check("capture->host median 73.0 ms (all frames)", L["all_frames"]["capture_to_host"]["median"] == 73.0, L["all_frames"])
    check("host->send 1.5 ms, send->Unity arrival 2.5 ms", dp["host_to_send"]["median"] == 1.5 and dp["send_to_unity_arrival"]["median"] == 2.5, dp)
    check("arrival->selection within one 60 Hz tick (<= 16.7 ms) and >= decode 1.6 ms",
          1.6 <= dp["arrival_to_selection"]["min"] and dp["arrival_to_selection"]["max"] <= 16.7 + 1.6, dp["arrival_to_selection"])
    check("total capture->selection = capture->host + host->selection (medians consistent within 1 ms)",
          abs(dp["capture_to_selection"]["median"] - (73.0 + dp["host_to_selection"]["median"])) < 1.0, dp)
    check("Unity age_mono equals the recomputed total", L["unity_age_mono_matches_recomputed_total"] is True)
    ev = r["measurements"]["events"]
    st0 = ev["capture_to_host_episodes_over_150ms"]
    check("start-up stall listed individually (seq 60-..., peak 773 ms), not hidden in averages",
          len(st0) == 1 and st0[0]["first_seq"] == 60 and st0[0]["peak_ms"] == 773.0, st0)
    check("GOP drop 60-99 listed as captured-not-sent", ev["captured_not_sent_ranges"]["left"] == [[60, 99]], ev["captured_not_sent_ranges"])
    check("display freeze over the dropped GOP recorded with its duration",
          any(f["duration_ms"] and f["duration_ms"] > 1900 for f in ev["unity_freezes"]), ev["unity_freezes"])

    r = case(tmp, "stale", unity_fault="stale")
    check("stale replay (older pair shown again) -> S9 FAIL (designed to fail)", r["criteria"]["S9_no_stale_replay"] == "FAIL")
    r = case(tmp, "meta", unity_fault="meta")
    check("metadata differs from what the gateway sent -> S7 FAIL (designed to fail)", r["criteria"]["S7_frame_identity_metadata"] == "FAIL")
    r = case(tmp, "integ", counts_over={"integrity_errors": 1, "source_mismatch": 1})
    check("integrity error / source mismatch -> S8 FAIL (designed to fail)", r["criteria"]["S8_stereo_pairing_integrity"] == "FAIL")

    r = case(tmp, "loss", link_loss_at=200)
    check("link loss without stale display -> S9 PASS", r["criteria"]["S9_no_stale_replay"] == "PASS", r["measurements"]["stale_checks"])

    def replay_old(frames):
        # seq 195 (captured before the loss at seq-200 time) is held and shown 300 ms AFTER the loss; the
        # display stays strictly increasing because seq 196-215 are never shown
        loss = T0 + 200 * 50 * MS
        out = []
        for f in frames:
            q = int(f["seq"])
            if 196 <= q <= 215:
                continue
            if q == 195:
                f = dict(f, t_display_mono_ns=loss + 300 * MS)
            out.append(f)
        return sorted(out, key=lambda f: int(f["t_display_mono_ns"]))
    r = case(tmp, "loss2", link_loss_at=200, frames_edit=replay_old)
    check("a displayed pair captured before a link loss, shown after it -> S9 FAIL (designed to fail)",
          r["criteria"]["S9_no_stale_replay"] == "FAIL", r["measurements"]["stale_checks"])
    r = case(tmp, "boot", report=gw_report(device_read_only={"getBootloaderVersion": "0.0.29"}))
    check("bootloader not 0.0.26 -> S1 FAIL", r["criteria"]["S1_identity_persistent_state"] == "FAIL")
    r = case(tmp, "calib", report=gw_report(calibration_unchanged=False))
    check("calibration changed -> S2 FAIL", r["criteria"]["S2_calibration"] == "FAIL")
    r = case(tmp, "ir", report=gw_report(ir_off_after_start={"setIrLaserDotProjectorIntensity": False, "setIrFloodLightIntensity": True}))
    check("IR not acknowledged off -> S3 FAIL", r["criteria"]["S3_safety_settings"] == "FAIL")
    r = case(tmp, "gwerr", report=gw_report(errors=["x"]))
    check("gateway error -> S4 FAIL", r["criteria"]["S4_gateway_stream"] == "FAIL")
    r = case(tmp, "mtx", run_over={"mediamtx_sockets": [{"proto": "TCP", "address": "127.0.0.1", "port": 8554},
                                                        {"proto": "UDP", "address": "0.0.0.0", "port": 8000}]})
    check("MediaMTX with an extra socket -> S5 FAIL", r["criteria"]["S5_mediamtx"] == "FAIL")
    r = case(tmp, "left", run_over={"final_check": {"gateway_processes": [], "unity_processes": [123], "mediamtx_processes": [],
                                                    "port_8554_free": True}})
    check("Unity process left running -> S11 FAIL", r["criteria"]["S11_clean_shutdown_cleanup"] == "FAIL")
    r = case(tmp, "port", run_over={"final_check": {"gateway_processes": [], "unity_processes": [], "mediamtx_processes": [],
                                                    "port_8554_free": False}})
    check("port 8554 still open -> S11 FAIL", r["criteria"]["S11_clean_shutdown_cleanup"] == "FAIL")
    r = case(tmp, "barcode", frames_edit=lambda fr: [dict(f, barcode_ok="1") for f in fr])
    check("a synthetic-barcode verdict on real imagery (barcode_ok not 'na') -> S8 FAIL", r["criteria"]["S8_stereo_pairing_integrity"] == "FAIL")
    r = a2.analyse(tmp / "ok" / "gw", None, None, oracle=False)
    check("no Unity folder (Unity never launched) -> S6-S9 NOT_TESTED, never PASS",
          all(r["criteria"][k] == "NOT_TESTED" for k in ("S6_unity_display", "S7_frame_identity_metadata", "S8_stereo_pairing_integrity",
                                                        "S9_no_stale_replay")), r["criteria"])

    # ---- s4demo S6 variant (13 Nov 2026, extended live walkthrough): one live receiver per trial reset
    def demo(name, rx_stop="s4_trial_reset", player_stop="application_quit", status="completed", integ=True, checks_failed=0):
        base = tmp / name
        sent = make_gw(base / "gw")
        (base / "gw" / "report.json").write_text(json.dumps(gw_report()), encoding="utf-8")
        make_unity(base / "u", sent)
        sj = json.loads((base / "u" / "summary.json").read_text(encoding="utf-8"))
        sj["stop_reason"] = rx_stop
        (base / "u" / "summary.json").write_text(json.dumps(sj), encoding="utf-8")
        runner_status(base / "run")
        (base / "s4").mkdir()
        (base / "s4" / "s4_summary.json").write_text(json.dumps({"stop_reason": player_stop, "checks_failed": checks_failed, "checks": []}), encoding="utf-8")
        (base / "ses").mkdir()
        (base / "ses" / "session_summary.json").write_text(json.dumps({"status": status, "integrity": {"pass": integ}}), encoding="utf-8")
        return a2.analyse(base / "gw", base / "u", base / "run", oracle=False, player="s4demo", s4_out=base / "s4", s4_session=base / "ses")
    r = demo("demo_ok")
    check("s4demo: receiver ended at a trial reset, session completed -> S6_site_window_live_demo PASS; S1-S5, S7-S9, S11 unchanged",
          r["criteria"].get("S6_site_window_live_demo") == "PASS" and "S6_unity_display" not in r["criteria"]
          and all(r["criteria"][k] == "PASS" for k in r["criteria"] if k != "S10_oracle_replay"), r["criteria"])
    check("s4demo: the last receiver ending with the window closed (s3_application_quit) is a planned end",
          demo("demo_last", rx_stop="s3_application_quit")["criteria"]["S6_site_window_live_demo"] == "PASS")
    for nm, kw, what in (("demo_rxfail", {"rx_stop": "link_lost"}, "receiver ended unplanned"),
                         ("demo_maxsec", {"rx_stop": "max_seconds"}, "receiver ran to its own M1 deadline (not a session end)"),
                         ("demo_incomplete", {"status": "in_progress"}, "session not completed"),
                         ("demo_integ", {"integ": False}, "session integrity failed"),
                         ("demo_player", {"player_stop": "script_done"}, "player end not an interactive end"),
                         ("demo_checks", {"checks_failed": 1}, "a player check failed")):
        check("s4demo: {} -> S6 FAIL (designed to fail)".format(what), demo(nm, **kw)["criteria"]["S6_site_window_live_demo"] == "FAIL")
    import subprocess
    p = subprocess.run([sys.executable, "-I", str(GW / "tools" / "analyse_stage2.py"), "--gw", str(tmp / "ok" / "gw"), "--runner", str(tmp / "ok" / "run"),
                        "--out", "..\\escape.json"], capture_output=True, text=True)
    check("--out refuses a path (only a plain .json file name inside the runner folder)", p.returncode != 0 and not (tmp / "ok" / "escape.json").exists(), p.stderr)
    p = subprocess.run([sys.executable, "-I", str(GW / "tools" / "analyse_stage2.py"), "--gw", str(tmp / "ok" / "gw"), "--runner", str(tmp / "ok" / "run"),
                        "--unity", str(tmp / "ok" / "u"), "--out", "stage2_analysis_rx1.json"], capture_output=True, text=True)
    check("--out writes the named file into the runner folder; the default name is untouched",
          p.returncode == 0 and (tmp / "ok" / "run" / "stage2_analysis_rx1.json").exists() and not (tmp / "ok" / "run" / "stage2_analysis.json").exists(), p.stderr[-300:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
n_fail = sum(1 for _, ok in RESULTS if not ok)
print("{} checks, {} failed".format(len(RESULTS), n_fail))
sys.exit(1 if n_fail else 0)

"""Task 06 Stage 2 analysis: Camera A -> gateway -> MediaMTX -> Unity, 60 s preview (offline, read-only).

A DEVELOPMENT PREVIEW: no performance threshold is gating. Integrity criteria
(PASS / FAIL / NOT_TESTED; fixed on 6 Nov 2026 before any live Stage 2 run):

  S1  identity and persistent state   Camera A 19443010B14C872F00 at 169.254.1.222 from X_LINK_BOOTLOADER;
                                      bootloader 0.0.26; back in X_LINK_BOOTLOADER after the run (read_ok)
  S2  calibration                     user and factory = both baselines before start; in-session and post-run equal
  S3  safety settings                 AutoCalibrationMode OFF; IR dot and flood 0, acknowledged before and after start
  S4  gateway stream                  stop at stop_file or seconds_reached without error; both eyes published
                                      (link_up), frames sent on both eyes, 0 packaging errors, pipeline stopped,
                                      device closed, senders joined
  S5  MediaMTX                        config hash = verified; port 8554 free before; its ONLY socket was TCP
                                      127.0.0.1:8554; stopped at the end
  S6  Unity display                   camera source, rtsp mode; pairs displayed; ran to max_seconds; render
                                      checks left and right pass at crop [39, 6, 1238, 770]; readers joined
  S7  frame identity and metadata     every Unity arrival with SEI: its (eye, seq) was sent by the gateway and
                                      t_dev, t_host_mono, t_utc, flags (0 = camera), config 6001 are identical;
                                      0 SEI errors, 0 decode errors after sync
  S8  stereo pairing and integrity    every displayed pair: eye_ok 1, barcode_ok "na", both eyes sent by the
                                      gateway; integrity_errors 0; source_mismatch 0
  S9  no stale replay                 displayed seq strictly increasing; no pair displayed > 200 ms after a
                                      gateway link loss whose capture precedes that loss; no "fresh" label
                                      with an absolute age over the freshness limit
  S10 oracle replay                   Unity's live presenter inputs replayed through the validated Python
                                      presenter (verify_unity_run, camera semantics) match exactly
  S11 clean shutdown and cleanup      runner final check: no gateway, Unity or MediaMTX process left; port 8554
                                      closed; Unity (if launched) exited 0; no runner deviation (forced stop,
                                      timeout); no new DepthAI crash dump

MEASUREMENTS (median / p95 / max, all frames AND displayed frames; never hidden in averages):
  capture -> host receipt         gateway captured.csv (t_received - t_host)
  host receipt -> gateway send    sent.csv - captured.csv
  gateway send -> Unity arrival   Unity arrivals.csv - sent.csv (same host QPC)
  Unity arrival -> selection      frames.csv tick - later eye's arrival
  host receipt -> selection       displayed pair: tick - later eye's host receipt
  capture -> selection (total)    displayed pair: tick - earlier eye's capture (= Unity age_mono_ms)
EVENTS (listed individually): start-up stalls and every capture->host episode > 150 ms; Unity freezes
with durations; device sequence gaps; frames captured but not sent (GOP drops) and sent but not
displayed; gateway and Unity link losses / reconnects; freshness labels and absolute-age states.

Run: camera_gateway\\.venv\\Scripts\\python.exe -I camera_gateway\\tools\\analyse_stage2.py --gw <gw_dir> --unity <unity_rx_dir> [--runner <runner_dir>]
Writes <runner_dir or unity_dir>/stage2_analysis.json; never modifies evidence.
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import sys

sys.dont_write_bytecode = True
GW = pathlib.Path(__file__).resolve().parents[1]
ROOT = GW.parent
sys.path[:0] = [str(GW)]

import numpy as np  # noqa: E402

import camera_gateway_a as cga  # noqa: E402

CROP = [39, 6, 1238, 770]
STALL_MS = 150.0


def V(ok, tested=True):
    return "NOT_TESTED" if not tested else ("PASS" if ok else "FAIL")


def rows(p):
    p = pathlib.Path(p)
    if not p.exists():
        return []
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def jsonl(p):
    p = pathlib.Path(p)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.lstrip("﻿").strip()
        if line:
            out.append(json.loads(line))
    return out


def st(v):
    v = [x for x in v if x is not None]
    if not v:
        return {"n": 0}
    a = np.asarray(v, dtype=float)
    return {"n": int(a.size), "median": round(float(np.median(a)), 2), "p95": round(float(np.percentile(a, 95)), 2),
            "max": round(float(a.max()), 2), "min": round(float(a.min()), 2)}


def as_list(v):
    return [] if v is None else (v if isinstance(v, list) else [v])


def ranges(seqs):
    seqs = sorted(seqs)
    out = []
    for s in seqs:
        if out and s == out[-1][1] + 1:
            out[-1][1] = s
        else:
            out.append([s, s])
    return out


LIVE_SMOKE_REQUIRED = ("smoke_live_camera_A_source_declared", "smoke_live_camera_A_in_site_window", "smoke_probe_hides_imagery",
                       "smoke_current_live_view_restored_after_probe", "smoke_inspect_switch_and_return_to_live_view",
                       "smoke_first_commitment_locked_before_execution", "smoke_commitment_executes_after_rating", "smoke_session_closed",
                       "smoke_session_integrity_checks_pass", "smoke_view_restoration_verified_no_timeout")


# s4demo (13 Nov 2026): planned ends of a live receiver and of the interactive player
DEMO_PLANNED_RX_STOPS = ("s4_trial_reset", "s3_application_quit", "s3_max_seconds", "s3_dev_finish")
DEMO_PLAYER_STOPS = ("application_quit", "max_seconds", "dev_finish")
# commissioning (16 Nov 2026): the commissioning view ends its own receiver ("cv_" + its end reason)
CV_PLANNED_ENDS = ("operator_end", "time_limit", "window_closed")


def analyse(gw_dir, unity_dir, runner_dir=None, oracle=True, player="m1", s4_out=None, s4_session=None, cv_out=None):
    gw_dir, unity_dir = pathlib.Path(gw_dir), pathlib.Path(unity_dir) if unity_dir else None
    rep = json.loads((gw_dir / "report.json").read_text(encoding="utf-8")) if (gw_dir / "report.json").exists() else {}
    cap, sent, gev = rows(gw_dir / "captured.csv"), rows(gw_dir / "sent.csv"), jsonl(gw_dir / "events.jsonl")
    run = json.loads((pathlib.Path(runner_dir) / "runner_status.json").read_text(encoding="utf-8-sig")) if runner_dir and \
        (pathlib.Path(runner_dir) / "runner_status.json").exists() else None
    us = json.loads((unity_dir / "summary.json").read_text(encoding="utf-8")) if unity_dir and (unity_dir / "summary.json").exists() else None
    uarr = rows(unity_dir / "arrivals.csv") if unity_dir else []
    ufr = rows(unity_dir / "frames.csv") if unity_dir else []
    uev = jsonl(unity_dir / "events.jsonl") if unity_dir else []
    C, M = {}, {}

    # ---- S1-S3 (as Stage 1 H1-H4)
    sel, post = rep.get("selection", {}), rep.get("calibration_post_run") or {}
    bl = (rep.get("device_read_only") or {}).get("getBootloaderVersion")
    scope = rep.get("network_scope") or {}
    if scope.get("mode") == "ethernet_scoped":
        # S1, ethernet_scoped variant (12 Nov 2026, researcher-approved mode): there is no broadcast pre-check, so the
        # "seen in X_LINK_BOOTLOADER" sub-item is replaced by: the scoped network pre-check passed (camera route on one
        # wired link-local interface, ARP = recorded Camera A MAC) and the unicast connection succeeded (it fails while
        # the camera runs firmware for another host). Every other S1 condition is unchanged.
        pre_ok = (scope.get("pre_check") or {}).get("ok") is True
        C["S1_identity_persistent_state"] = "FAIL" if bl is not None and bl != cga.EXPECTED_BOOTLOADER else V(
            sel.get("actual_device_id") == cga.CAMERA_A_ID and sel.get("actual_ip") == "169.254.1.222" and pre_ok
            and "unicast" in str(sel.get("method")) and bl == cga.EXPECTED_BOOTLOADER and post.get("status") == "read_ok"
            and (scope.get("monitor") or {}).get("failure") is None,
            bool(sel) and bl is not None and bool(post))
        M["S1_variant"] = "ethernet_scoped (no broadcast discovery; ARP MAC + unicast connect replace the bootloader-state pre-check)"
    else:
        C["S1_identity_persistent_state"] = "FAIL" if bl is not None and bl != cga.EXPECTED_BOOTLOADER else V(
            sel.get("actual_device_id") == cga.CAMERA_A_ID and sel.get("actual_ip") == "169.254.1.222"
            and "BOOTLOADER" in str(sel.get("preflight_seen_state")) and bl == cga.EXPECTED_BOOTLOADER
            and post.get("status") == "read_ok" and "BOOTLOADER" in str((post.get("last_precheck") or {}).get("seen_state")),
            bool(sel) and bl is not None and bool(post))

    pre = rep.get("calibration_vs_baselines_before_start") or []
    C["S2_calibration"] = V(len(pre) == 2 and all(c["equal"] for c in pre) and (rep.get("calibration_in_session") or {}).get("equal") is True
                            and post.get("equal") is True and rep.get("calibration_unchanged") is True, bool(pre))
    ir_ok = {"setIrLaserDotProjectorIntensity": True, "setIrFloodLightIntensity": True}
    C["S3_safety_settings"] = V("OFF" in str(rep.get("auto_calibration_mode")) and rep.get("ir_off_before_start") == ir_ok
                                and rep.get("ir_off_after_start") == ir_ok, "auto_calibration_mode" in rep)
    # ---- S4 gateway stream
    snd = rep.get("senders") or {}
    ups = {e["payload"].get("eye") for e in gev if e.get("type") == "link_up"}
    C["S4_gateway_stream"] = V(rep.get("stop_reason") in ("stop_file", "seconds_reached") and not rep.get("errors")
                               and ups >= {"left", "right"} and all(snd.get(e, {}).get("sent", 0) > 0 for e in ("left", "right"))
                               and all(s.get("packaging_errors", 1) == 0 and s.get("joined") for s in snd.values())
                               and rep.get("pipeline_stopped") is True and rep.get("device_closed") is True, bool(rep) and bool(snd))
    # ---- S5 MediaMTX
    if run is not None:
        socks = as_list(run.get("mediamtx_sockets"))
        C["S5_mediamtx"] = V(run.get("mediamtx_config_verified") is True and run.get("port_8554_free_before") is True
                             and socks == [{"proto": "TCP", "address": "127.0.0.1", "port": 8554}]
                             and run.get("mediamtx_stopped") is True, run.get("mediamtx_started") is True)
    else:
        C["S5_mediamtx"] = "NOT_TESTED"
    # ---- S6 Unity display
    u = (us or {}).get("unity", {})
    rc, rcr = u.get("render_check") or {}, u.get("render_check_right") or {}
    if player == "s4":
        # S6, S4 Site Window variant (13 Nov 2026, approved live smoke test): the live Camera A receiver of the session (camera
        # source, rtsp, pairs displayed, readers joined; it ends at the planned session end, not at max_seconds, and has no M1
        # display rig, so no render check), every live-smoke check passed (none as "_rehearsal"), and the session's own
        # integrity checks passed. S1-S5 and S7-S11 are unchanged.
        s4 = json.loads((pathlib.Path(s4_out) / "s4_summary.json").read_text(encoding="utf-8")) if s4_out and (pathlib.Path(s4_out) / "s4_summary.json").exists() else None
        ss = json.loads((pathlib.Path(s4_session) / "session_summary.json").read_text(encoding="utf-8")) if s4_session and (pathlib.Path(s4_session) / "session_summary.json").exists() else None
        chk = {c["name"]: c["pass"] for c in (s4 or {}).get("checks", [])}
        missing = [n for n in LIVE_SMOKE_REQUIRED if n not in chk]
        C["S6_site_window_live_session"] = V(us is not None and u.get("source") == "camera" and u.get("mode") == "rtsp" and len(ufr) > 0
                                             and (u.get("shutdown") or {}).get("readers_joined") is True and s4 is not None
                                             and s4.get("stop_reason") == "script_done" and s4.get("checks_failed") == 0 and not missing
                                             and ((ss or {}).get("integrity") or {}).get("pass") is True, us is not None and s4 is not None)
        M["s4_session"] = {"ui_out": s4_out, "session_dir": s4_session, "stop_reason": (s4 or {}).get("stop_reason"), "elapsed_s": (s4 or {}).get("elapsed_s"),
                           "checks": chk, "checks_failed": (s4 or {}).get("checks_failed"), "required_missing": missing,
                           "session_status": (ss or {}).get("status"), "session_integrity_pass": ((ss or {}).get("integrity") or {}).get("pass"),
                           "live_receiver_stop_reason": (us or {}).get("stop_reason"),
                           "note": "receiver stop at the planned session end (s3_script_done / s4_trial_reset) is a planned source shutdown, not a failure"}
    elif player == "s4demo":
        # S6, S4 interactive-demonstration variant (13 Nov 2026, approved extended test): ONE live Camera A receiver of the
        # session (the player restarts the receivers at every trial reset, so each receiver is analysed separately): camera
        # source, rtsp, pairs displayed, readers joined, and a planned receiver end (trial reset, or the player's own end:
        # window closed / deadline / facilitator finish). The demonstration session must have completed with its integrity
        # checks passing. A person plays the participant, so there are no scripted smoke checks. S1-S5, S7-S11 unchanged.
        s4 = json.loads((pathlib.Path(s4_out) / "s4_summary.json").read_text(encoding="utf-8")) if s4_out and (pathlib.Path(s4_out) / "s4_summary.json").exists() else None
        ss = json.loads((pathlib.Path(s4_session) / "session_summary.json").read_text(encoding="utf-8")) if s4_session and (pathlib.Path(s4_session) / "session_summary.json").exists() else None
        rx_stop = (us or {}).get("stop_reason")
        planned_rx = rx_stop in DEMO_PLANNED_RX_STOPS
        C["S6_site_window_live_demo"] = V(us is not None and u.get("source") == "camera" and u.get("mode") == "rtsp" and len(ufr) > 0
                                          and (u.get("shutdown") or {}).get("readers_joined") is True and planned_rx and s4 is not None
                                          and s4.get("stop_reason") in DEMO_PLAYER_STOPS and (s4.get("checks_failed") or 0) == 0
                                          and (ss or {}).get("status") == "completed" and ((ss or {}).get("integrity") or {}).get("pass") is True,
                                          us is not None and s4 is not None)
        M["s4_session"] = {"ui_out": s4_out, "session_dir": s4_session, "player_stop_reason": (s4 or {}).get("stop_reason"),
                           "elapsed_s": (s4 or {}).get("elapsed_s"), "checks_failed": (s4 or {}).get("checks_failed"),
                           "session_status": (ss or {}).get("status"), "session_integrity_pass": ((ss or {}).get("integrity") or {}).get("pass"),
                           "live_receiver": unity_dir.name if unity_dir else None, "live_receiver_stop_reason": rx_stop,
                           "live_receiver_stop_planned": planned_rx,
                           "note": "receiver stop at a trial reset (s4_trial_reset) or at the player's end is a planned source shutdown, not a failure"}
    elif player == "commissioning":
        # S6, commissioning-view variant (16 Nov 2026): ONE live Camera A receiver (camera source, rtsp, pairs displayed,
        # readers joined) ended by the commissioning view itself at a planned end (operator End view, the time limit, or the
        # window closed), and the view's own summary written with the same end. Not participant data; no trials, no robot.
        # The view has no M1 display rig, so there is no render check. S1-S5 and S7-S11 unchanged.
        cv = json.loads((pathlib.Path(cv_out) / "commissioning_summary.json").read_text(encoding="utf-8")) if cv_out and (pathlib.Path(cv_out) / "commissioning_summary.json").exists() else None
        rx_stop = (us or {}).get("stop_reason")
        planned_rx = rx_stop in tuple("cv_" + e for e in CV_PLANNED_ENDS)
        C["S6_commissioning_live_view"] = V(us is not None and u.get("source") == "camera" and u.get("mode") == "rtsp" and len(ufr) > 0
                                            and (u.get("shutdown") or {}).get("readers_joined") is True and planned_rx and cv is not None
                                            and cv.get("end_reason") in CV_PLANNED_ENDS and (cv.get("checks_failed") or 0) == 0
                                            and cv.get("valid_image_shown") is True, us is not None and cv is not None)
        M["commissioning_view"] = {"cv_out": cv_out, "end_reason": (cv or {}).get("end_reason"), "elapsed_s": (cv or {}).get("elapsed_s"),
                                   "view_seconds": (cv or {}).get("view_seconds"), "first_image_after_s": (cv or {}).get("first_image_after_s"),
                                   "continuity": {k: ((cv or {}).get("continuity") or {}).get(k) for k in ("valid_visible_ms", "not_valid_ms", "interruptions")},
                                   "zoom_changes": (cv or {}).get("zoom_changes"), "pans": (cv or {}).get("pans"),
                                   "live_receiver_stop_reason": rx_stop, "live_receiver_stop_planned": planned_rx,
                                   "note": "commissioning evidence, not participant data; a cv_* receiver stop is a planned source shutdown"}
    else:
        C["S6_unity_display"] = V(us is not None and u.get("source") == "camera" and u.get("mode") == "rtsp" and len(ufr) > 0
                                  and us.get("stop_reason") == "max_seconds" and rc.get("pass") and rcr.get("pass")
                                  and rc.get("crop") == CROP and (u.get("shutdown") or {}).get("readers_joined") is True, us is not None)
    # ---- S7 identity and metadata
    sent_key = {(r["eye"], int(r["seq"])): r for r in sent}
    mism, not_sent = [], []
    for a in uarr:
        if a.get("sei") != "ok":
            continue
        k = (a["eye"], int(a["seq"]))
        s = sent_key.get(k)
        if s is None:
            not_sent.append(k)
            continue
        if not (a["t_dev_ns"] == s["t_dev_ns"] and a["t_host_mono_ns"] == s["t_host_mono_ns"] and a["t_utc_ns"] == s["t_utc_ns"]
                and a["flags"] == s["flags"] == "0" and a["config_id"] == "6001" and a["meta_eye"] == a["eye"] and a["camera"] == "A"):
            mism.append(k)
    rd = (us or {}).get("readers", {})
    sei_err = sum(int(r.get("sei_errors", 0)) for r in rd.values())
    dec_err = sum(int(r.get("decode_errors", 0)) for r in rd.values())
    C["S7_frame_identity_metadata"] = V(bool(uarr) and not mism and not not_sent and sei_err == 0 and dec_err == 0, bool(uarr))
    M["identity"] = {"unity_arrivals": len(uarr), "metadata_mismatch": mism[:20], "arrived_but_not_sent": not_sent[:20],
                     "sei_errors": sei_err, "decode_errors_after_sync": dec_err,
                     "no_sei_frames": sum(int(r.get("no_sei", 0)) for r in rd.values())}
    # ---- S8 pairing and integrity
    counts = ((us or {}).get("presenter") or {}).get("counts", {})
    shown = [int(f["seq"]) for f in ufr]
    both_sent = all(("left", q) in sent_key and ("right", q) in sent_key for q in shown)
    C["S8_stereo_pairing_integrity"] = V(bool(ufr) and all(f["eye_ok"] == "1" and f["barcode_ok"] == "na" for f in ufr) and both_sent
                                         and counts.get("integrity_errors") == 0 and counts.get("source_mismatch") == 0, bool(ufr))
    # ---- S9 no stale replay
    increasing = all(b > a for a, b in zip(shown, shown[1:]))
    downs = [e["t_mono_ns"] for e in gev if e.get("type") == "link_down"]
    cap_host = {}
    for r in cap:
        cap_host.setdefault(int(r["seq"]), []).append(int(r["t_host_mono_ns"]))
    stale_after_loss = []
    for f in ufr:
        td, q = int(f["t_display_mono_ns"]), int(f["seq"])
        for d in downs:
            if td > d + 200_000_000 and min(cap_host.get(q, [1 << 62])) < d:
                stale_after_loss.append(q)
                break
    lim = ((us or {}).get("presenter") or {}).get("freshness_policy", {}).get("fresh_age_ms", 150.0) or 150.0
    fresh_over = [int(f["seq"]) for f in ufr if f["freshness"] == "fresh" and f.get("abs_age_ms") not in ("", None)
                  and float(f["abs_age_ms"]) > lim]
    C["S9_no_stale_replay"] = V(increasing and not stale_after_loss and not fresh_over, bool(ufr))
    M["stale_checks"] = {"display_strictly_increasing": increasing, "displayed_after_gateway_link_loss_but_captured_before": stale_after_loss[:20],
                         "fresh_label_over_limit": fresh_over[:20], "fresh_limit_ms": lim, "gateway_link_losses": len(downs)}
    # ---- S10 oracle
    if oracle and unity_dir and (unity_dir / "ops.csv").exists() and us is not None:
        sys.path[:0] = [str(ROOT / "unity" / "Phase2Client" / "Tools"), str(ROOT / "streaming_poc")]
        import verify_unity_run as vur
        o = vur.oracle(unity_dir, us, vur._csv(unity_dir / "arrivals.csv"))
        C["S10_oracle_replay"] = o["verdict"]
        M["oracle"] = {k: o[k] for k in ("ops", "displayed", "presenter_events", "source", "mismatches")}
    else:
        C["S10_oracle_replay"] = "NOT_TESTED"
    # ---- S11 cleanup
    if run is not None:
        fin = run.get("final_check") or {}
        C["S11_clean_shutdown_cleanup"] = V(fin.get("gateway_processes") == [] and fin.get("unity_processes") == []
                                            and fin.get("mediamtx_processes") == [] and fin.get("port_8554_free") is True
                                            and (not run.get("unity_launched") or run.get("unity_exit_code") == 0)
                                            and not as_list(run.get("deviations"))
                                            and as_list(run.get("new_crash_dumps")) == [],
                                            bool(fin))
    else:
        C["S11_clean_shutdown_cleanup"] = "NOT_TESTED"

    # ---- measurements
    capk = {(r["eye"], int(r["seq"])): r for r in cap}
    arrk = {(a["eye"], int(a["seq"])): a for a in uarr if a.get("sei") == "ok"}
    c2h_all = [float(r["host_receipt_minus_capture_ms"]) for r in cap]
    h2s_all = [(int(s["t_sent_mono_ns"]) - int(capk[(s["eye"], int(s["seq"]))]["t_received_mono_ns"])) / 1e6
               for s in sent if (s["eye"], int(s["seq"])) in capk]
    s2a_all = [(int(a["t_arrival_mono_ns"]) - int(sent_key[k]["t_sent_mono_ns"])) / 1e6 for k, a in arrk.items() if k in sent_key]
    disp = {"capture_to_host": [], "host_to_send": [], "send_to_unity_arrival": [], "arrival_to_selection": [],
            "host_to_selection": [], "capture_to_selection": []}
    for f in ufr:
        q, td = int(f["seq"]), int(f["t_display_mono_ns"])
        ks = [("left", q), ("right", q)]
        if not all(k in capk and k in sent_key and k in arrk for k in ks):
            continue
        disp["capture_to_host"].append(max(float(capk[k]["host_receipt_minus_capture_ms"]) for k in ks))
        disp["host_to_send"].append(max((int(sent_key[k]["t_sent_mono_ns"]) - int(capk[k]["t_received_mono_ns"])) / 1e6 for k in ks))
        disp["send_to_unity_arrival"].append(max((int(arrk[k]["t_arrival_mono_ns"]) - int(sent_key[k]["t_sent_mono_ns"])) / 1e6 for k in ks))
        disp["arrival_to_selection"].append((td - max(int(arrk[k]["t_arrival_mono_ns"]) for k in ks)) / 1e6)
        disp["host_to_selection"].append((td - max(int(capk[k]["t_received_mono_ns"]) for k in ks)) / 1e6)
        disp["capture_to_selection"].append((td - min(int(capk[k]["t_host_mono_ns"]) for k in ks)) / 1e6)
    age_check = [abs(float(f["age_mono_ms"]) - (int(f["t_display_mono_ns"]) - min(int(capk[(e, int(f["seq"]))]["t_host_mono_ns"])
                                                                                 for e in ("left", "right"))) / 1e6)
                 for f in ufr if ("left", int(f["seq"])) in capk and ("right", int(f["seq"])) in capk]
    M["latency_ms"] = {"all_frames": {"capture_to_host": st(c2h_all), "host_to_send": st(h2s_all), "send_to_unity_arrival": st(s2a_all)},
                       "displayed_pairs": {k: st(v) for k, v in disp.items()},
                       "unity_age_mono_matches_recomputed_total": (max(age_check) < 0.02) if age_check else None}
    # events
    stalls, cur = [], None
    for r in sorted(cap, key=lambda r: (int(r["seq"]), r["eye"])):
        v, q = float(r["host_receipt_minus_capture_ms"]), int(r["seq"])
        if v > STALL_MS:
            if cur and q <= cur["last_seq"] + 1:
                cur["last_seq"], cur["peak_ms"] = q, max(cur["peak_ms"], v)
            else:
                cur = {"first_seq": q, "last_seq": q, "peak_ms": v}
                stalls.append(cur)
    t0 = min((int(r["t_host_mono_ns"]) for r in cap), default=None)
    for s in stalls:
        s["starts_s_after_first_capture"] = round((min(cap_host.get(s["first_seq"], [t0])) - t0) / 1e9, 2) if t0 else None
        s["peak_ms"] = round(s["peak_ms"], 1)
    fz = [e for e in uev if e.get("type") == "freeze_end"]
    seqs = {e: sorted({int(r["seq"]) for r in cap if r["eye"] == e}) for e in ("left", "right")}
    gaps = {e: [(a, b - a - 1) for a, b in zip(s, s[1:]) if b - a > 1] for e, s in seqs.items()}
    not_sent = {e: ranges(set(seqs[e]) - {int(s["seq"]) for s in sent if s["eye"] == e}) for e in ("left", "right")}
    shown_set = set(shown)
    u_lo, u_hi = (min(shown), max(shown)) if shown else (0, -1)
    sent_not_shown = ranges({int(s["seq"]) for s in sent if s["eye"] == "left" and u_lo <= int(s["seq"]) <= u_hi} - shown_set)
    first_disp_utc = int(ufr[0]["t_display_utc_ns"]) if ufr else None
    launch = run.get("unity_launched") if run else None
    launch_ns = int(dt.datetime.fromisoformat(launch).timestamp() * 1e9) if launch else None
    M["events"] = {
        "capture_to_host_episodes_over_150ms": stalls,
        "unity_freezes": [{"t_s_after_unity_start": round((e["t_mono_ns"] - uev[0]["t_mono_ns"]) / 1e9, 2) if uev else None,
                           "duration_ms": e["payload"].get("duration_ms"), "resumed_seq": e["payload"].get("resumed_seq")} for e in fz],
        "device_sequence_gaps": gaps,
        "captured_not_sent_ranges": not_sent,
        "sent_not_displayed_ranges_in_unity_window": sent_not_shown[:50],
        "gateway_gop_queues": rep.get("gop_queues"), "gateway_senders": rep.get("senders"),
        "gateway_link_events": [(e["type"], e["payload"].get("eye")) for e in gev if e.get("type") in ("link_down", "link_up", "link_connect_failed")],
        "unity_link_events": [(e["type"], e["payload"].get("eye")) for e in uev if e.get("type") in ("link_down", "link_up")],
        "unity_presenter_counts": counts,
        "unity_launch_to_first_display_s": round((first_disp_utc - launch_ns) / 1e9, 2) if first_disp_utc and launch_ns else None}
    def tally(col):
        out = {}
        for f in ufr:
            out[f.get(col, "")] = out.get(f.get(col, ""), 0) + 1
        return out
    M["freshness"] = {"labels": tally("freshness"), "abs_status": tally("abs_status"), "rel_status": tally("rel_status"),
                      "clock_source": tally("clock_source")}
    gating = list(C.values())
    return {"criteria": C, "measurements": M,
            "overall_integrity": "PASS" if all(v == "PASS" for v in gating) else ("FAIL" if "FAIL" in gating else "INCOMPLETE"),
            "gw_dir": str(gw_dir), "unity_dir": str(unity_dir) if unity_dir else None, "runner": str(runner_dir) if runner_dir else None,
            "fake": bool(rep.get("fake_device")) or bool((us or {}).get("fake"))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gw", required=True)
    ap.add_argument("--unity")
    ap.add_argument("--runner")
    ap.add_argument("--player", choices=("m1", "s4", "s4demo", "commissioning"), default="m1")
    ap.add_argument("--out", default="stage2_analysis.json", help="output file name (written into the runner/unity/gw folder)")
    ap.add_argument("--s4-out")
    ap.add_argument("--s4-session")
    ap.add_argument("--cv-out", help="commissioning view output folder (commissioning_summary.json), --player commissioning")
    a = ap.parse_args(argv)
    out = analyse(a.gw, a.unity, a.runner, player=a.player, s4_out=a.s4_out, s4_session=a.s4_session, cv_out=a.cv_out)

    if pathlib.Path(a.out).name != a.out or not a.out.endswith(".json"):
        ap.error("--out must be a plain .json file name")
    dest = pathlib.Path(a.runner or a.unity or a.gw) / a.out

    dest.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    for k, v in out["criteria"].items():
        print("{:32s} {}".format(k, v))
    lat = out["measurements"]["latency_ms"]["displayed_pairs"]
    for k, v in lat.items():
        print("  {:24s} {}".format(k, v))
    print("OVERALL (integrity)", out["overall_integrity"], "(FAKE DRY RUN)" if out["fake"] else "", "->", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())

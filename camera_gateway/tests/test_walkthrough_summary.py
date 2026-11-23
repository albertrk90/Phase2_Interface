"""Offline tests for tools/summarise_live_walkthrough.py (13 Nov 2026). A synthetic two-trial walkthrough with KNOWN
events, one of every kind:
  trial 1:  site window 1.5 s, first image 2.0 s       -> planned restart wait, 500 ms visible
            images stop 4.0-4.6 s with Camera A shown  -> UNEXPECTED visible interruption, 600 ms
            SAGAT probe 6.0-6.5 s (no rendered rows); images stop 6.1-6.4 s -> hidden by the planned probe
            Camera B selected 7.9-8.6 s; images stop 8.0-8.4 s             -> hidden by the Camera B selection
            receiver 1 ends at the trial reset (s4_trial_reset)
  trial 2:  site window 13.5 s, receiver 2 first image 14.2 s -> planned restart wait, 700 ms visible
Run: camera_gateway\\.venv\\Scripts\\python.exe -I camera_gateway\\tests\\test_walkthrough_summary.py
"""
import csv
import json
import pathlib
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
GW = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(GW / "tools")]
import summarise_live_walkthrough as sw  # noqa: E402

RESULTS = []
MS = 1_000_000
T0 = 9_000_000 * MS
OFF = 1_790_000_000 * 10**9
FCOLS = ["t_display_mono_ns", "seq", "interval_ms", "freshness", "abs_age_ms", "abs_status"]
VCOLS = ["t_mono_ns", "workflow", "inspecting", "camera", "video_A", "video_B"]


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + str(detail)[:400]) if detail and not cond else ""))


def t(ms):
    return T0 + int(ms * MS)


def write_csv(p, cols, rs):
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rs)


def ev(type_, ms, **payload):
    return {"type": type_, "t_mono_ns": t(ms), "t_utc_ns": t(ms) + OFF, "payload": payload}


def build(root, rx2_stop="s3_application_quit", extra_gap=None, outcome="completed", port_free=True, view_gap=None):
    run = root / "run"
    run.mkdir(parents=True)
    # receivers
    specs = [("unity_rx_20261113_120001_win64player_A_s3", 1000, 2000, 11950, [(4000, 4600), (6100, 6400), (8000, 8400)], 12100, "s4_trial_reset"),
             ("unity_rx_20261113_120013_win64player_A_s3", 12500, 14200, 18000 if rx2_stop == "link_lost" else 19950, [extra_gap] if extra_gap else [], 18100 if rx2_stop == "link_lost" else 20100, rx2_stop)]
    seq = 0
    for name, start, first, last, gaps, end, stop in specs:
        d = run / name
        d.mkdir()
        fr, evs, prev, ms = [], [ev("run_start", start)], None, first
        while ms <= last:
            if any(a < ms < b for a, b in gaps):
                ms += 50
                continue
            fr.append({"t_display_mono_ns": t(ms), "seq": seq, "interval_ms": "" if prev is None else ms - prev, "freshness": "fresh",
                       "abs_age_ms": 90 + (seq % 5), "abs_status": "within"})
            prev, seq, ms = ms, seq + 1, ms + 50
        for a, b in gaps:
            evs.append(ev("freeze_start", a + 125, camera="A"))
            evs.append(ev("freeze_end", b, camera="A", duration_ms=b - a, resumed_seq=0, skipped=0))
        evs.append(ev("run_end", end, stop_reason=stop))
        write_csv(d / "frames.csv", FCOLS, fr)
        (d / "events.jsonl").write_text("\n".join(json.dumps(e) for e in evs), encoding="utf-8")
        (d / "summary.json").write_text(json.dumps({"stop_reason": stop}), encoding="utf-8")
    (run / "unity_rx_20261113_120002_win64player_B_s3").mkdir()   # the synthetic Camera B receiver is ignored
    # participant interface
    ui = root / "ui"
    ui.mkdir()
    scr = [(0, "welcome", False), (1000, "trial_ready", False), (1500, "trial", True), (6000, "probe", False), (6500, "probe_restoring", True),
           (6600, "trial", True), (12000, "break", False), (13000, "trial_ready", False), (13500, "trial", True), (20000, "complete", False)]
    uiev = [ev("ui_session_screen", ms, screen=s, site_window=w) for ms, s, w in scr]
    uiev += [ev("video_state", 1000, camera="A", state="live", on_screen=True), ev("video_state", 2000 - 1, camera="A", state="live", on_screen=True),
             ev("video_state", 4500, camera="A", state="interrupted", on_screen=True), ev("video_state", 4600, camera="A", state="live", on_screen=True)]
    uiev.sort(key=lambda e: e["t_mono_ns"])
    (ui / "ui_events.jsonl").write_text("\n".join(json.dumps(e) for e in uiev), encoding="utf-8")
    vr, ms = [], 1500
    while ms < 20000:
        if (1500 <= ms < 6000 or 6500 <= ms < 12000 or 13500 <= ms < 20000) and not (view_gap and view_gap[0] < ms < view_gap[1]):
            cam = "B" if 7900 <= ms < 8600 else "A"
            vr.append({"t_mono_ns": t(ms), "workflow": "monitoring", "inspecting": int(cam == "B"), "camera": cam,
                       "video_A": "interrupted" if 4500 <= ms < 4600 else "live", "video_B": "live"})
        ms += 16
    write_csv(ui / "view_frames.csv", VCOLS, vr)
    (ui / "s4_summary.json").write_text(json.dumps({"stop_reason": "application_quit", "elapsed_s": 20.2, "checks_failed": 0}), encoding="utf-8")
    # session
    ses = run / "s4_sessions" / "S4-P001-01"
    ses.mkdir(parents=True)
    sev = [{"type": "sagat_freeze", "t_mono_ns": t(6000), "t_utc": "x", "ids": {"trial_id": "B1-T1"}},
           {"type": "view_restore_begin", "t_mono_ns": t(6500)}, {"type": "view_restored", "t_mono_ns": t(6650)}]
    (ses / "session_events.jsonl").write_text("\n".join(json.dumps(e) for e in sev), encoding="utf-8")
    (ses / "session_summary.json").write_text(json.dumps({"status": "completed", "integrity": {"pass": True}, "session_id": "S4-P001-01",
                                                          "trials": [{}, {}], "definition": {"protocol_id": "phase2_s41_interactive_demo"}}), encoding="utf-8")
    gw = root / "gw"
    gw.mkdir()
    (gw / "report.json").write_text(json.dumps({"stop_reason": "stop_file", "errors": [], "pipeline_stopped": True, "device_closed": True,
                                                "calibration_unchanged": True}), encoding="utf-8")
    write_csv(run / "wifi_probe.csv", ["t", "url", "status", "ms", "interface", "source"],
              [{"t": "12:00:%02d.000" % s, "url": "u", "status": 200 if s != 15 else "ERR timeout", "ms": 100 + s, "interface": "WiFi", "source": "x"}
               for s in range(0, 30, 5)])
    st = {"s4_ui_out": str(ui), "s4_session_dir": str(ses), "gateway_dir": str(gw), "outcome": outcome, "deviations": [],
          "unity_exit_code": 0, "gateway_exit_code": 0, "new_crash_dumps": [], "extended_test": True, "gateway_seconds": 600, "preview_seconds": 525,
          "final_check": {"gateway_processes": [], "unity_processes": [], "mediamtx_processes": [], "port_8554_free": port_free}}
    (run / "runner_status.json").write_text(json.dumps(st), encoding="utf-8")
    return run


tmp = pathlib.Path(tempfile.mkdtemp(prefix="wtsum_"))
try:
    s = sw.summarise(build(tmp / "ok"))
    h, st = s["headline"], s["visible_stalls"]
    kinds = [(x["kind"], round(x["visible_ms"])) for x in st]
    check("visible stalls: two planned trial-start waits (~500, ~700 ms) and ONE unexpected interruption (~600 ms); nothing else",
          len(st) == 3 and [k for k, _ in kinds] == ["trial_start_receiver_restart", "unexpected_visible_interruption", "trial_start_receiver_restart"]
          and abs(kinds[0][1] - 500) <= 20 and abs(kinds[1][1] - 600) <= 20 and abs(kinds[2][1] - 700) <= 20, kinds)
    check("headline: 1 unexpected visible interruption, 2 trial-start waits (longest ~700 ms)",
          h["unexpected_visible_interruptions"] == 1 and h["trial_start_restart_waits"] == 2 and abs(h["longest_trial_start_wait_ms"] - 700) <= 20, h)
    check("the unexpected interruption shows the participant-facing 'interrupted' label", "interrupted" in st[1]["ui_video_states"], st[1])
    lab = sorted((round(f["duration_ms"]), f["label"]) for f in s["receiver_freezes"])
    check("receiver freezes labelled by what was on screen: 300 ms SAGAT probe (planned hiding), 400 ms Camera B, 600 ms visible",
          lab == [(300, "hidden_planned_sagat_probe"), (400, "hidden_camera_B_selected"), (600, "visible_camera_A_on_screen")], lab)
    check("headline: 3 receiver freezes, 1 visible, longest 600 ms",
          h["receiver_freezes"] == 3 and h["receiver_freezes_visible"] == 1 and h["longest_receiver_freeze_ms"] == 600, h)
    p = s["sagat_probes"]
    check("SAGAT probe: hidden 500 ms, restore 150 ms, restored, no timeout",
          len(p) == 1 and p[0]["hidden_ms"] == 500 and p[0]["restore_ms"] == 150 and p[0]["restored"] and not p[0]["restore_timeout"], p)
    b = s["camera_b_selection"]
    check("Camera B selection: 1 episode of ~0.7 s (planned, not an interruption)", b["episodes"] == 1 and abs(b["total_s"] - 0.7) < 0.05, b)
    rx = s["receivers"]
    check("two live Camera A receivers (Camera B receiver ignored); restart start->first image 1000 / 1700 ms; stops planned",
          len(rx) == 2 and rx[0]["start_to_first_image_ms"] == 1000 and rx[1]["start_to_first_image_ms"] == 1700
          and all(r["stop_planned"] for r in rx), rx)
    la = s["latency_capture_to_selection_ms"]["all_displayed"]
    check("latency distribution from abs_age_ms (90-94 ms): median 92, max 94", la["median"] == 92 and la["max"] == 94, la)
    check("freshness: all displayed pairs fresh", h["fresh_pairs"].split("/")[0] == h["fresh_pairs"].split("/")[1], h["fresh_pairs"])
    w = s["wifi"]
    check("Wi-Fi: 5/6 HTTPS 200, the failure listed, longest gap between successes 10 s",
          w["probes"] == 6 and w["ok_200"] == 5 and len(w["failures"]) == 1 and w["longest_gap_between_ok_s"] == 10.0, w)
    check("shutdown clean, session completed, nothing missing", h["shutdown_clean"] and h["session_completed"] and not h["inputs_missing"], h)
    md = sw.markdown(s)
    check("markdown written with the headline and the unexpected interruption", "unexpected_visible_interruption" in md and "## Wi-Fi" in md)

    s = sw.summarise(build(tmp / "lost", rx2_stop="link_lost"))
    check("receiver ending UNPLANNED while Camera A is on screen -> end_of_stream_while_visible counted as unexpected",
          any(x["kind"] == "end_of_stream_while_visible" and not x["planned"] for x in s["visible_stalls"])
          and s["headline"]["unexpected_visible_interruptions"] == 2 and not s["receivers"][1]["stop_planned"], s["visible_stalls"])
    s = sw.summarise(build(tmp / "port", port_free=False))
    check("port 8554 still open -> shutdown not clean (designed to fail)", s["headline"]["shutdown_clean"] is False)
    s = sw.summarise(build(tmp / "short", extra_gap=(16000, 16100)))
    check("a 100 ms gap (< 125 ms freeze threshold) is not a visible stall",
          s["headline"]["unexpected_visible_interruptions"] == 1, s["visible_stalls"])
    s = sw.summarise(build(tmp / "hitch", view_gap=(17000, 17400)))
    hh = s["render_hitches"]
    check("a 400 ms gap in rendered Site Window frames (no screen change) -> one render hitch; probe/break gaps are not hitches",
          len(hh) == 1 and 380 <= hh[0]["duration_ms"] <= 420 and s["headline"]["render_hitches"] == 1, hh)
    check("baseline run: no render hitches", sw.summarise(tmp / "ok" / "run")["headline"]["render_hitches"] == 0)
    e = tmp / "empty"

    e.mkdir()
    s = sw.summarise(e)
    check("no evidence -> inputs listed as missing, never a clean result",
          len(s["headline"]["inputs_missing"]) >= 4 and s["headline"]["session_completed"] is False and s["headline"]["shutdown_clean"] is False, s["headline"])
    r = sw.main(["--runner", str(tmp / "ok" / "run")])
    check("CLI writes walkthrough_summary.json and .md into the runner folder",
          r == 0 and (tmp / "ok" / "run" / "walkthrough_summary.json").exists() and (tmp / "ok" / "run" / "walkthrough_summary.md").exists())
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
n_fail = sum(1 for _, ok in RESULTS if not ok)
print("{} checks, {} failed".format(len(RESULTS), n_fail))
sys.exit(1 if n_fail else 0)

"""Summary of a live S4.1 interactive walkthrough (run_stage2.ps1 -Player S4Demo -ExtendedTest; 13 Nov 2026).

Reads only the evidence a runner folder already holds; writes walkthrough_summary.json and walkthrough_summary.md there.
It never modifies evidence.

Sources (all on the same host monotonic clock):
  unity_rx_*_A_*/frames.csv, events.jsonl, summary.json
      the live Camera A receivers (one per trial reset).
  <s4_ui_out>/view_frames.csv
      one row per rendered Site Window frame (camera on screen, video states). There are no rows while a session screen
      (welcome, SAGAT probe, break, ...) covers the stage.
  <s4_ui_out>/ui_events.jsonl
      session screens, plate on/off, participant-facing video states.
  <s4_session>/session_events.jsonl
      sagat_freeze, view_restore_begin, view_restored, view_restore_timeout, trial_prepared, ...
  wifi_probe.csv, runner_status.json, the gateway report.json, stage2_analysis_*.json.

What the participant saw is separated from what the stream did:

  visible stall
      Camera A on screen with no new image for >= STALL_MS (the receiver's freeze threshold). Classified as:
      - trial_start_receiver_restart: the first image of a receiver restarted at a trial reset. A planned restart, but
        the wait is visible.
      - unexpected_visible_interruption: a mid-stream stall while Camera A was on screen.
      - end_of_stream_while_visible: no further image before Camera A left the screen.
  receiver freeze (freeze_start / freeze_end)
      a stream-level stall, whatever was on screen. Each is labelled by what was on screen during it:
      Camera A (visible), Camera B selected, the SAGAT probe (planned hiding), or another session screen.
  planned hiding
      SAGAT probes (hide and restore timing) and Camera B selections. These are NOT video interruptions.
"""
import argparse
import bisect
import csv
import datetime as dt
import json
import pathlib
import statistics
import sys

STALL_MS = 125.0          # = the receiver's freeze threshold (StereoPresenter freeze_start threshold_ms)
SEGMENT_GAP_MS = 500.0    # rendered rows further apart than this split an on-screen segment
PLANNED_RX_STOPS = ("s4_trial_reset", "s3_application_quit", "s3_max_seconds", "s3_dev_finish", "s3_script_done")


def rows(p):
    p = pathlib.Path(p)
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def jsonl(p):
    p = pathlib.Path(p)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def jload(p, enc="utf-8"):
    p = pathlib.Path(p) if p else None
    return json.loads(p.read_text(encoding=enc)) if p and p.exists() else None


def pct(xs, q):
    if not xs:
        return None
    s = sorted(xs)
    k = (len(s) - 1) * q / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 2)


def dist(xs):
    xs = [float(x) for x in xs]
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "min": round(min(xs), 2), "median": pct(xs, 50), "p90": pct(xs, 90), "p95": pct(xs, 95),
            "p99": pct(xs, 99), "max": round(max(xs), 2), "mean": round(statistics.fmean(xs), 2)}


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class Screens:
    """Session screen and plate state as a step function of time (from ui_session_screen events)."""

    def __init__(self, ui_events):
        ev = [e for e in ui_events if e.get("type") == "ui_session_screen"]
        self.t = [e["t_mono_ns"] for e in ev]
        self.v = [(e["payload"].get("screen"), bool(e["payload"].get("site_window"))) for e in ev]

    def at(self, t):
        i = bisect.bisect_right(self.t, t) - 1
        return self.v[i] if i >= 0 else (None, False)

    def intervals(self, name):
        out, start = [], None
        for t, (s, _) in zip(self.t, self.v):
            if s == name and start is None:
                start = t
            elif s != name and start is not None:
                out.append((start, t))
                start = None
        if start is not None:
            out.append((start, None))
        return out


def receivers(run):
    out = []
    for d in sorted(pathlib.Path(run).glob("unity_rx_*_A_*")):
        if not d.is_dir():
            continue
        fr, ev, sm = rows(d / "frames.csv"), jsonl(d / "events.jsonl"), jload(d / "summary.json") or {}
        start = next((e["t_mono_ns"] for e in ev if e.get("type") == "run_start"), None)
        end_ev = next((e for e in ev if e.get("type") == "run_end"), None)
        disp = [int(f["t_display_mono_ns"]) for f in fr]
        out.append({"dir": d.name, "frames": fr, "events": ev, "summary": sm, "start": start,
                    "end": end_ev["t_mono_ns"] if end_ev else None,
                    "stop_reason": sm.get("stop_reason") or ((end_ev or {}).get("payload") or {}).get("stop_reason"),
                    "disp": disp})
    out.sort(key=lambda r: r["start"] or 0)
    return out


def on_screen_segments(view_rows, camera):
    """Contiguous runs of rendered Site Window frames showing `camera` -> [(t_first, t_last, n_rows)]."""
    segs, cur = [], None
    for r in view_rows:
        t = int(r["t_mono_ns"])
        if r.get("camera") == camera:
            if cur and (t - cur[1]) / 1e6 <= SEGMENT_GAP_MS:
                cur[1], cur[2] = t, cur[2] + 1
            else:
                if cur:
                    segs.append(tuple(cur))
                cur = [t, t, 1]
        elif cur:
            segs.append(tuple(cur))
            cur = None
    if cur:
        segs.append(tuple(cur))
    return segs


def overlap(a0, a1, b0, b1):
    return max(0, min(a1, b1) - max(a0, b0))


def summarise(run):
    run = pathlib.Path(run)
    st = jload(run / "runner_status.json", "utf-8-sig") or {}
    ui_dir = pathlib.Path(st["s4_ui_out"]) if st.get("s4_ui_out") else None
    ses_dir = pathlib.Path(st["s4_session_dir"]) if st.get("s4_session_dir") else None
    gw_dir = pathlib.Path(st["gateway_dir"]) if st.get("gateway_dir") else None
    view = rows(ui_dir / "view_frames.csv") if ui_dir else []
    uiev = jsonl(ui_dir / "ui_events.jsonl") if ui_dir else []
    s4 = jload(ui_dir / "s4_summary.json") if ui_dir else None
    sev = jsonl(ses_dir / "session_events.jsonl") if ses_dir else []
    ss = jload(ses_dir / "session_summary.json") if ses_dir else None
    gwr = jload(gw_dir / "report.json") if gw_dir else None
    rx = receivers(run)
    missing = [n for n, ok in (("runner_status.json", bool(st)), ("s4_ui_out", bool(view or uiev)), ("session_events", bool(sev)),
                               ("live Camera A receivers", bool(rx)), ("gateway report", bool(gwr))) if not ok]

    t0 = uiev[0]["t_mono_ns"] if uiev else (rx[0]["start"] if rx else 0)
    utc_off = (uiev[0]["t_utc_ns"] - uiev[0]["t_mono_ns"]) if uiev else None

    def rel(t):
        return round((t - t0) / 1e9, 3) if t is not None else None

    def utc(t):
        if t is None or utc_off is None:
            return None
        return dt.datetime.fromtimestamp((t + utc_off) / 1e9, dt.timezone.utc).isoformat(timespec="milliseconds")

    screens = Screens(uiev)
    probes = screens.intervals("probe")

    # ---- every displayed Camera A pair, in time order, tagged with its receiver
    disp = sorted((t, i) for i, r in enumerate(rx) for t in r["disp"])
    dt_ = [d[0] for d in disp]

    # ---- what was on screen at a time: "A", "B" (Site Window) or the session screen name
    vt = [int(r["t_mono_ns"]) for r in view]

    def on_screen(t0_, t1_):
        """Dominant on-screen content over [t0_, t1_]: A / B (rendered rows) else the session screen."""
        i, j = bisect.bisect_left(vt, t0_), bisect.bisect_right(vt, t1_)
        cams = [view[k].get("camera") for k in range(i, j)]
        if cams:
            return {"A": cams.count("A"), "B": cams.count("B"), "rows": len(cams)}
        scr, _ = screens.at((t0_ + t1_) // 2)
        return {"screen": scr}

    # ---- visible stalls (what the participant saw)
    segA = on_screen_segments(view, "A")
    stalls = []
    for s0, s1, n in segA:
        # displays bounding and inside the segment
        k = bisect.bisect_right(dt_, s0) - 1          # last display at/before the segment start
        k0 = max(k, 0)
        pts = disp[k0:bisect.bisect_right(dt_, s1) + 1]
        if k < 0:
            pts = [(None, None)] + pts
        if not pts or (pts[-1][0] is not None and pts[-1][0] <= s1):
            pts = pts + [(None, None)]                  # no display after the segment's end -> open end
        for (ta, ia), (tb, ib) in zip(pts, pts[1:]):
            a = s0 if ta is None else max(ta, s0)
            b = s1 if tb is None else min(tb, s1)
            vis = (b - a) / 1e6
            if b <= a or vis < STALL_MS:
                continue
            if tb is None:
                kind = "end_of_stream_while_visible"
            elif ta is None or ia != ib:
                kind = "trial_start_receiver_restart"
            else:
                kind = "unexpected_visible_interruption"
            states = sorted({view[q].get("video_A") for q in range(bisect.bisect_left(vt, a), bisect.bisect_right(vt, b))} - {None})
            stalls.append({"kind": kind, "t_s": rel(a), "utc": utc(a), "visible_ms": round(vis, 1),
                           "gap_between_images_ms": round((tb - ta) / 1e6, 1) if ta is not None and tb is not None else None,
                           "receiver": rx[ib]["dir"] if ib is not None else (rx[ia]["dir"] if ia is not None else None),
                           "receiver_stop_reason": (rx[ia]["stop_reason"] if (tb is None and ia is not None) else None),
                           "ui_video_states": states,
                           "planned": kind == "trial_start_receiver_restart" or (kind == "end_of_stream_while_visible" and ia is not None
                                                                                   and rx[ia]["stop_reason"] in PLANNED_RX_STOPS)})

    # ---- receiver freezes (stream level), labelled by what was on screen
    freezes = []
    for r in rx:
        for e in r["events"]:
            if e.get("type") != "freeze_end":
                continue
            p = e.get("payload") or {}
            d = float(p.get("duration_ms") or 0)
            b = e["t_mono_ns"]
            a = b - int(d * 1e6)
            ctx = on_screen(a, b)
            in_probe = any(overlap(a, b, p0, p1 if p1 else b) > 0 for p0, p1 in probes)
            if ctx.get("A"):
                label = "visible_camera_A_on_screen"
            elif ctx.get("B"):
                label = "hidden_camera_B_selected"
            elif in_probe:
                label = "hidden_planned_sagat_probe"
            else:
                label = "hidden_session_screen:" + str(ctx.get("screen"))
            freezes.append({"receiver": r["dir"], "t_s": rel(a), "utc": utc(a), "duration_ms": d, "on_screen": ctx, "label": label,
                            "resumed_seq": p.get("resumed_seq"), "skipped": p.get("skipped")})

    # ---- UI-declared video states for Camera A (participant-facing labels)
    uivs, open_ = [], None
    for e in uiev:
        if e.get("type") != "video_state" or (e.get("payload") or {}).get("camera") != "A":
            continue
        p = e["payload"]
        if p.get("state") != "live" and open_ is None:
            open_ = (e["t_mono_ns"], p.get("state"), p.get("on_screen"), p.get("receiver_done"))
        elif p.get("state") == "live" and open_ is not None:
            uivs.append({"t_s": rel(open_[0]), "state": open_[1], "duration_ms": round((e["t_mono_ns"] - open_[0]) / 1e6, 1),
                         "on_screen_at_start": open_[2], "receiver_done": open_[3]})
            open_ = None
    if open_ is not None:
        uivs.append({"t_s": rel(open_[0]), "state": open_[1], "duration_ms": None, "on_screen_at_start": open_[2],
                     "receiver_done": open_[3], "note": "not live again before the end of the log"})

    # ---- planned hiding: SAGAT probes and their view restoration
    sagat = []
    for e in sev:
        if e.get("type") == "sagat_freeze":
            sagat.append({"t_s": rel(e["t_mono_ns"]), "utc": e.get("t_utc"), "trial": (e.get("ids") or {}).get("trial_id"), "_t": e["t_mono_ns"]})
    for s in sagat:
        nxt = [e for e in sev if e["t_mono_ns"] > s["_t"] and e.get("type") in ("view_restore_begin", "view_restored", "view_restore_timeout", "sagat_freeze")]
        rb = next((e for e in nxt if e["type"] == "view_restore_begin"), None)
        rd = next((e for e in nxt if e["type"] in ("view_restored", "view_restore_timeout", "sagat_freeze")), None)
        s["hidden_ms"] = round((rb["t_mono_ns"] - s["_t"]) / 1e6, 1) if rb else None
        s["restore_ms"] = round((rd["t_mono_ns"] - rb["t_mono_ns"]) / 1e6, 1) if rb and rd and rd["type"] == "view_restored" else None
        s["restored"] = bool(rd and rd["type"] == "view_restored")
        s["restore_timeout"] = bool(rd and rd["type"] == "view_restore_timeout")
        if rd and rd["type"] == "view_restored":
            k = bisect.bisect_right(dt_, rd["t_mono_ns"]) - 1
            s["image_age_at_restore_ms"] = round((rd["t_mono_ns"] - dt_[k]) / 1e6, 1) if k >= 0 else None
        s.pop("_t")
    view_restored = [e for e in sev if e.get("type") in ("view_restored", "view_restore_timeout")]

    # ---- render hitches: the Site Window itself not rendering (no view row) for >= STALL_MS with no session-screen change
    #      in between; whatever camera was shown, the participant saw a frozen window
    scr_t = screens.t
    hitches = []
    for r0, r1 in zip(view, view[1:]):
        a, b = int(r0["t_mono_ns"]), int(r1["t_mono_ns"])
        if (b - a) / 1e6 < STALL_MS:
            continue
        if bisect.bisect_right(scr_t, b) - bisect.bisect_right(scr_t, a) > 0:
            continue                                   # a session screen (probe, break, ...) replaced the window: planned
        in_wait = any(x["kind"] == "trial_start_receiver_restart" and x["t_s"] - 0.001 <= rel(a) <= x["t_s"] + x["visible_ms"] / 1000.0
                      for x in stalls)
        hitches.append({"t_s": rel(a), "utc": utc(a), "duration_ms": round((b - a) / 1e6, 1), "camera": r0.get("camera"),
                        "video_A": r0.get("video_A"), "during_trial_start_wait": in_wait})


    # ---- Camera B selections (planned, participant-initiated Inspect switching)
    segB = on_screen_segments(view, "B")
    bsel = {"episodes": len(segB), "total_s": round(sum((b - a) / 1e9 for a, b, _ in segB), 2),
            "longest_s": round(max(((b - a) / 1e9 for a, b, _ in segB), default=0), 2)}

    # ---- freshness and latency (displayed pairs; and the subset rendered while Camera A was on screen)
    allf = [f for r in rx for f in r["frames"]]

    def onA(t):
        return any(a <= t <= b for a, b, _ in segA)

    visf = [f for f in allf if onA(int(f["t_display_mono_ns"]))]

    def fresh(fs):
        tl = {}
        for f in fs:
            tl[f.get("freshness", "")] = tl.get(f.get("freshness", ""), 0) + 1
        ab = {}
        for f in fs:
            ab[f.get("abs_status", "")] = ab.get(f.get("abs_status", ""), 0) + 1
        return {"pairs": len(fs), "freshness": tl, "abs_status": ab}

    lat_all = [fnum(f.get("abs_age_ms")) for f in allf]
    lat_vis = [fnum(f.get("abs_age_ms")) for f in visf]
    hist = {"<100": 0, "100-125": 0, "125-150": 0, ">=150": 0}
    for x in (x for x in lat_all if x is not None):
        hist["<100" if x < 100 else "100-125" if x < 125 else "125-150" if x < 150 else ">=150"] += 1
    intervals = [fnum(f.get("interval_ms")) for f in allf if fnum(f.get("interval_ms")) is not None]

    rxs = []
    for r in rx:
        lat = [fnum(f.get("abs_age_ms")) for f in r["frames"] if fnum(f.get("abs_age_ms")) is not None]
        rxs.append({"dir": r["dir"], "start_s": rel(r["start"]), "first_image_s": rel(r["disp"][0]) if r["disp"] else None,
                    "start_to_first_image_ms": round((r["disp"][0] - r["start"]) / 1e6, 1) if r["disp"] and r["start"] else None,
                    "end_s": rel(r["end"]), "stop_reason": r["stop_reason"], "stop_planned": r["stop_reason"] in PLANNED_RX_STOPS,
                    "pairs": len(r["frames"]), "freezes": sum(1 for e in r["events"] if e.get("type") == "freeze_end"),
                    "link_events": [(e["type"], (e.get("payload") or {}).get("eye")) for e in r["events"] if e.get("type") in ("link_down", "link_up")],
                    "latency_abs_age_ms": dist(lat), "freshness": fresh(r["frames"])["freshness"]})

    # ---- Wi-Fi
    wf = rows(run / "wifi_probe.csv")
    okt, fails, gaps = [], [], []
    for w in wf:
        if str(w.get("status")) == "200":
            okt.append(w.get("t"))
        else:
            fails.append({"t": w.get("t"), "status": w.get("status"), "interface": w.get("interface")})

    def secs(s):
        try:
            h, m, x = s.split(":")
            return int(h) * 3600 + int(m) * 60 + float(x)
        except (ValueError, AttributeError):
            return None
    ts = [secs(t) for t in okt if secs(t) is not None]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    wifi = {"probes": len(wf), "ok_200": len(okt), "failures": fails, "interfaces": sorted({w.get("interface") for w in wf}),
            "latency_ms": dist([fnum(w.get("ms")) for w in wf if fnum(w.get("ms")) is not None]),
            "longest_gap_between_ok_s": round(max(gaps), 1) if gaps else None, "first": wf[0]["t"] if wf else None, "last": wf[-1]["t"] if wf else None}

    # ---- shutdown and duration
    fc = st.get("final_check") or {}
    shutdown = {"runner_outcome": st.get("outcome"), "shutdown_reason": st.get("shutdown_reason"), "deviations": st.get("deviations"),
                "runner_error": st.get("error"), "player_stop_reason": (s4 or {}).get("stop_reason"), "player_elapsed_s": (s4 or {}).get("elapsed_s"),
                "unity_exit_code": st.get("unity_exit_code"), "unity_seconds": st.get("unity_seconds"),
                "gateway_exit_code": st.get("gateway_exit_code"), "gateway_stop_reason": (gwr or {}).get("stop_reason"),
                "gateway_errors": (gwr or {}).get("errors"), "pipeline_stopped": (gwr or {}).get("pipeline_stopped"),
                "device_closed": (gwr or {}).get("device_closed"), "calibration_unchanged": (gwr or {}).get("calibration_unchanged"),
                "mediamtx_stopped": st.get("mediamtx_stopped"), "new_crash_dumps": st.get("new_crash_dumps"),
                "final_check": {k: fc.get(k) for k in ("gateway_processes", "unity_processes", "mediamtx_processes", "port_8554_free")},
                "network_scope_checks": st.get("network_scope_checks"), "network_scope_monitor": ((gwr or {}).get("network_scope") or {}).get("monitor"),
                "receiver_stops": {r["dir"]: r["stop_reason"] for r in rx}}
    pre = (st.get("pre_checks") or {}).get("duration") or {}
    duration = {"extended_test": st.get("extended_test"), "gateway_seconds": st.get("gateway_seconds"), "player_deadline_s": st.get("preview_seconds"),
                "gateway_streaming_after_s": st.get("gateway_streaming_after_s"),
                "gateway_seconds_left_at_player_launch": st.get("gateway_seconds_left_at_player_launch"),
                "player_hit_deadline": (s4 or {}).get("stop_reason") == "max_seconds", "limits": pre}

    # ---- the per-receiver Stage 2 analyses
    analyses = {}
    for p in sorted(run.glob("stage2_analysis_*.json")):
        a = jload(p) or {}
        analyses[p.name] = {"overall_integrity": a.get("overall_integrity"), "criteria": a.get("criteria"),
                            "latency_displayed_pairs": ((a.get("measurements") or {}).get("latency_ms") or {}).get("displayed_pairs")}

    unexpected = [s for s in stalls if s["kind"] == "unexpected_visible_interruption" or (s["kind"] == "end_of_stream_while_visible" and not s["planned"])]
    vis_frz = [f for f in freezes if f["label"] == "visible_camera_A_on_screen"]
    session = {"status": (ss or {}).get("status"), "integrity_pass": ((ss or {}).get("integrity") or {}).get("pass"),
               "session_id": (ss or {}).get("session_id"), "trials": len((ss or {}).get("trials") or []),
               "protocol_id": (((ss or {}).get("definition") or {}).get("protocol_id"))}
    headline = {
        "inputs_missing": missing,
        "session_completed": session["status"] == "completed" and session["integrity_pass"] is True,
        "unexpected_visible_interruptions": len(unexpected),
        "longest_unexpected_visible_ms": max((s["visible_ms"] for s in unexpected), default=0),
        "trial_start_restart_waits": len([s for s in stalls if s["kind"] == "trial_start_receiver_restart"]),
        "longest_trial_start_wait_ms": max((s["visible_ms"] for s in stalls if s["kind"] == "trial_start_receiver_restart"), default=0),
        "receiver_freezes": len(freezes), "receiver_freezes_visible": len(vis_frz),
        "longest_receiver_freeze_ms": max((f["duration_ms"] for f in freezes), default=0),
        "sagat_probes": len(sagat), "sagat_restored": sum(1 for s in sagat if s["restored"]), "sagat_restore_timeouts": sum(1 for s in sagat if s["restore_timeout"]),
        "camera_b_selections": bsel["episodes"],
        "render_hitches": len(hitches), "longest_render_hitch_ms": max((x["duration_ms"] for x in hitches), default=0),
        "fresh_pairs": "{}/{}".format(fresh(allf)["freshness"].get("fresh", 0), len(allf)),
        "latency_median_ms": pct([x for x in lat_all if x is not None], 50), "latency_p95_ms": pct([x for x in lat_all if x is not None], 95),
        "latency_max_ms": max((x for x in lat_all if x is not None), default=None),
        "wifi_ok": "{}/{}".format(wifi["ok_200"], wifi["probes"]),
        "shutdown_clean": (st.get("outcome") == "completed" and not st.get("deviations") and st.get("gateway_exit_code") == 0
                           and st.get("unity_exit_code") == 0 and fc.get("port_8554_free") is True and not st.get("new_crash_dumps")
                           and not fc.get("gateway_processes") and not fc.get("unity_processes") and not fc.get("mediamtx_processes")
                           and (gwr or {}).get("calibration_unchanged") is True)}
    return {"schema": "ai2-live-walkthrough-summary-v1", "runner_dir": str(run), "generated": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "fake": bool((gwr or {}).get("fake_device")) or bool(st.get("dry_run")),
            "definitions": {"stall_ms": STALL_MS, "time_zero": "first participant-interface event (t_s)",
                            "visible_stall": "Camera A rendered on screen with no new image for >= stall_ms",
                            "planned": "SAGAT probe hiding, Camera B selection and receiver restarts at trial resets are planned; "
                                       "their visible start-up waits are reported separately from unexpected interruptions"},
            "headline": headline, "session": session, "duration": duration,
            "visible_stalls": stalls, "receiver_freezes": freezes, "render_hitches": hitches, "ui_video_states_camera_A": uivs,
            "sagat_probes": sagat, "view_restoration_events": [{"type": e["type"], "t_s": rel(e["t_mono_ns"])} for e in view_restored],
            "camera_b_selection": bsel,
            "camera_a_on_screen": {"segments": len(segA), "total_s": round(sum((b - a) / 1e9 for a, b, _ in segA), 2)},
            "freshness": {"all_displayed": fresh(allf), "while_on_screen": fresh(visf)},
            "latency_capture_to_selection_ms": {"all_displayed": dist([x for x in lat_all if x is not None]),
                                                "while_on_screen": dist([x for x in lat_vis if x is not None]), "histogram_all": hist},
            "display_interval_ms": dist(intervals), "receivers": rxs, "wifi": wifi, "shutdown": shutdown, "stage2_analyses": analyses}


def markdown(s):
    h, L = s["headline"], []
    L.append("# Live S4.1 walkthrough summary{}".format(" (FAKE DRY RUN)" if s["fake"] else ""))
    L.append("")
    L.append("Runner folder: `{}`. Generated {}.".format(s["runner_dir"], s["generated"]))
    if h["inputs_missing"]:
        L.append("")
        L.append("**Inputs missing:** " + ", ".join(h["inputs_missing"]))
    L += ["", "## Headline", "", "| Item | Result |", "|---|---|"]
    rowsmd = [("Session completed (integrity pass)", h["session_completed"]),
              ("Unexpected visible interruptions (Camera A on screen, mid-stream)", "{} (longest {} ms)".format(h["unexpected_visible_interruptions"], h["longest_unexpected_visible_ms"])),
              ("Trial-start waits after the planned receiver restart (visible)", "{} (longest {} ms)".format(h["trial_start_restart_waits"], h["longest_trial_start_wait_ms"])),
              ("Receiver freezes (stream level; visible)", "{} ({} visible; longest {} ms)".format(h["receiver_freezes"], h["receiver_freezes_visible"], h["longest_receiver_freeze_ms"])),
              ("SAGAT probes (planned hiding) restored / timeouts", "{} / {} restored, {} timeouts".format(h["sagat_probes"], h["sagat_restored"], h["sagat_restore_timeouts"])),
              ("Camera B selections (planned)", h["camera_b_selections"]),
              ("Render hitches (window not redrawn, no screen change)", "{} (longest {} ms)".format(h["render_hitches"], h["longest_render_hitch_ms"])),

              ("Fresh displayed pairs", h["fresh_pairs"]),
              ("Capture to selection (median / p95 / max)", "{} / {} / {} ms".format(h["latency_median_ms"], h["latency_p95_ms"], h["latency_max_ms"])),
              ("Wi-Fi HTTPS 200", h["wifi_ok"]),
              ("Clean shutdown", h["shutdown_clean"])]
    L += ["| {} | {} |".format(a, b) for a, b in rowsmd]
    L += ["", "## Visible stalls (what the participant saw)", ""]
    if s["visible_stalls"]:
        L += ["| t (s) | kind | visible ms | gap between images ms | UI states | receiver |", "|---|---|---|---|---|---|"]
        L += ["| {} | {} | {} | {} | {} | {} |".format(x["t_s"], x["kind"], x["visible_ms"], x["gap_between_images_ms"], ",".join(x["ui_video_states"]), x["receiver"]) for x in s["visible_stalls"]]
    else:
        L.append("None.")
    L += ["", "## Receiver freezes (stream level)", ""]
    if s["receiver_freezes"]:
        L += ["| t (s) | duration ms | on screen | label |", "|---|---|---|---|"]
        L += ["| {} | {} | {} | {} |".format(x["t_s"], x["duration_ms"], json.dumps(x["on_screen"]), x["label"]) for x in s["receiver_freezes"]]
    else:
        L.append("None.")
    L += ["", "## Render hitches (Site Window not redrawn, no screen change)", ""]
    L += ["- {} s: {} ms (camera {}{})".format(x["t_s"], x["duration_ms"], x["camera"], ", inside a trial-start wait" if x["during_trial_start_wait"] else "")
          for x in s["render_hitches"]] or ["None."]
    L += ["", "## Planned hiding (not interruptions)", ""]

    L += ["- SAGAT probes: " + ("; ".join("{} at {} s: hidden {} ms, restore {} ms, image age at restore {} ms{}".format(
        p["trial"], p["t_s"], p["hidden_ms"], p["restore_ms"], p.get("image_age_at_restore_ms"), " (RESTORE TIMEOUT)" if p["restore_timeout"] else "")
        for p in s["sagat_probes"]) or "none")]
    b = s["camera_b_selection"]
    L += ["- Camera B selections: {} episodes, {} s in total (longest {} s).".format(b["episodes"], b["total_s"], b["longest_s"])]
    L += ["", "## Receivers (one per trial reset)", "", "| receiver | start→first image ms | pairs | freezes | stop | latency median/p95/max |", "|---|---|---|---|---|---|"]
    for r in s["receivers"]:
        la = r["latency_abs_age_ms"]
        L.append("| {} | {} | {} | {} | {}{} | {}/{}/{} |".format(r["dir"], r["start_to_first_image_ms"], r["pairs"], r["freezes"], r["stop_reason"],
                                                          "" if r["stop_planned"] else " (UNPLANNED)", la.get("median"), la.get("p95"), la.get("max")))
    lt = s["latency_capture_to_selection_ms"]
    L += ["", "## Freshness and latency", "",
          "- All displayed pairs: {}".format(json.dumps(s["freshness"]["all_displayed"])),
          "- While Camera A was on screen: {}".format(json.dumps(s["freshness"]["while_on_screen"])),
          "- Capture to selection, all: {}".format(json.dumps(lt["all_displayed"])),
          "- Capture to selection, on screen: {}".format(json.dumps(lt["while_on_screen"])),
          "- Histogram: {}".format(json.dumps(lt["histogram_all"])),
          "- Display interval: {}".format(json.dumps(s["display_interval_ms"]))]
    w = s["wifi"]
    L += ["", "## Wi-Fi", "", "- {} / {} HTTPS 200 via {}; longest gap between successes {} s; latency {}; failures {}.".format(
        w["ok_200"], w["probes"], ",".join(str(i) for i in w["interfaces"]), w["longest_gap_between_ok_s"], json.dumps(w["latency_ms"]), json.dumps(w["failures"]))]
    L += ["", "## Duration and shutdown", "", "```", json.dumps({"duration": s["duration"], "shutdown": s["shutdown"]}, indent=1, default=str), "```"]
    L += ["", "## Stage 2 analyses (per live receiver)", ""]
    L += ["- {}: {}".format(k, v["overall_integrity"]) for k, v in s["stage2_analyses"].items()] or ["None."]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runner", required=True)
    a = ap.parse_args(argv)
    try:
        s = summarise(a.runner)
    except Exception as e:  # noqa: BLE001 - report and exit non-zero; evidence is untouched
        print("summary failed:", repr(e), file=sys.stderr)
        return 3
    run = pathlib.Path(a.runner)
    (run / "walkthrough_summary.json").write_text(json.dumps(s, indent=1, default=str), encoding="utf-8")
    (run / "walkthrough_summary.md").write_text(markdown(s), encoding="utf-8")
    for k, v in s["headline"].items():
        print("{:40s} {}".format(k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Live verification of the 13 Nov 2026 video readiness / continuity fixes (checkpoint §13.32) from one S4Demo runner folder.

Reads only logs (nothing changed): runner_status.json -> the S4 UI folder (ui_events.jsonl, view_frames.csv), the session folder
(session_events.jsonl) and the Unity receivers (unity_rx_*_{A,B}_*/frames.csv, events.jsonl). All on the host monotonic clock.

Checks (each PASS / FAIL / UNTESTED_LIVE when the behaviour did not occur naturally):
  V1 no empty buffer accepted: after every receiver restart both cameras report "waiting" until that receiver's first displayed
     pair; no render frame shows a non-waiting state without a received pair; every video_ready names a received, current pair.
  V2 observation timing starts only on a current, visible view of the intended camera (record + render log agree).
  V3 stale imagery: every render frame labelled live has on-screen age <= 150 ms; every frame over 150 ms (validated pair) is
     not labelled live; "interrupted" only after > 500 ms without a new image. Counts and durations of "Image not current",
     and brief excursions (flicker) during otherwise normal delivery.
  V4 continuity records at observation end, SAGAT freeze, view restoration and first commitment carry camera, source,
     receiver generation and a frame seq that the named receiver actually displayed.
  V5 SAGAT hides all construction imagery (no plate render frames between freeze and restoration) and decisions become
     available only after a restored current view.
  V6 startup waits, camera switches, source exhaustion and unexpected interruptions are separately identifiable.
Usage: verify_live_video_fixes.py <runner_dir> [--out live_video_verification.json]
"""
import argparse, bisect, csv, json, pathlib, statistics

ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("--out", default="live_video_verification.json")
a = ap.parse_args()
run = pathlib.Path(a.run)
st = json.loads((run / "runner_status.json").read_text(encoding="utf-8-sig"))
ui = pathlib.Path(st["s4_ui_out"]); sess = pathlib.Path(st["s4_session_dir"])
jl = lambda p: [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
rows = lambda p: list(csv.DictReader(open(p, encoding="utf-8-sig")))
MS = 1e6
sev = jl(sess / "session_events.jsonl"); uev = jl(ui / "ui_events.jsonl"); vf = rows(ui / "view_frames.csv")
ty = lambda evs, t: [e for e in evs if e["type"] == t]
P = lambda e: e.get("payload") or {}

# receivers per camera, in generation order, with their displayed pairs
rx = {"A": [], "B": []}
for cam in rx:
    for d in sorted(run.glob(f"unity_rx_*_{cam}_*")):
        fr = rows(d / "frames.csv")
        ev = jl(d / "events.jsonl")
        rx[cam].append({"dir": d.name, "start": ev[0]["t_mono_ns"], "end": [e for e in ev if e["type"] == "run_end"][-1]["t_mono_ns"] if any(e["type"] == "run_end" for e in ev) else None,
                        "first_display": int(fr[0]["t_display_mono_ns"]) if fr else None, "seqs": {int(r["seq"]) for r in fr},
                        "stop": next((P(e).get("reason") for e in ev if e["type"] == "run_end"), None)})
prep = ty(sev, "video_prepared")
R = {}

# ---------------- V1
v1 = []
for g, pe in enumerate(prep, 1):
    t0 = pe["t_mono_ns"]; t1 = prep[g]["t_mono_ns"] if g < len(prep) else float("inf")
    for cam in ("A", "B"):
        r = rx[cam][g - 1] if g - 1 < len(rx[cam]) else None
        vs = [e for e in ty(uev, "video_state") if P(e).get("camera") == cam and t0 <= e["t_mono_ns"] < t1]
        first = vs[0] if vs else None
        leave = next((e for e in vs if P(e).get("state") != "waiting"), None)
        lseq = (P(leave).get("status") or {}).get("seq") if leave else None
        # UI events are stamped on the session clock BEFORE that frame's advance (about one frame behind the receiver's display
        # stamp), so the check is by reference: the status that leaves "waiting" must name a pair this new receiver displayed.
        v1.append({"generation": g, "camera": cam, "receiver": r and r["dir"], "first_state": first and P(first).get("state"),
                   "left_waiting_ms_after_prepare": round((leave["t_mono_ns"] - t0) / MS, 1) if leave else None,
                   "first_pair_ms_after_prepare": round((r["first_display"] - t0) / MS, 1) if r and r["first_display"] else None,
                   "left_waiting_seq": lseq, "left_waiting_seq_displayed_by_new_receiver": bool(r and lseq is not None and lseq in r["seqs"]) if leave else None})
bad_render = [x for x in vf for cam in ("A", "B") if x["camera"] == cam and not x["seq_" + cam] and x["video_" + cam] not in ("waiting", "unavailable")]
vr = []
for e in ty(sev, "video_ready"):
    g = P(e)["receivers"]
    for cam in ("A", "B"):
        v = P(e)["video_" + cam]; r = rx[cam][g - 1] if g - 1 < len(rx[cam]) else None
        vr.append({"generation": g, "camera": cam, "state": v.get("state"), "seq": v.get("seq"), "freshness": v.get("freshness"),
                   "seq_displayed_by_receiver": bool(r and v.get("seq") in r["seqs"]), "since_prepare_ms": P(e).get("since_video_prepared_ms")})
ok1 = all(x["first_state"] == "waiting" and x["left_waiting_seq_displayed_by_new_receiver"] is not False for x in v1) and not bad_render and vr and all(x["state"] == "current" and x["seq_displayed_by_receiver"] for x in vr)
R["V1_no_empty_buffer_accepted"] = {"verdict": "PASS" if ok1 else "FAIL", "per_restart": v1, "render_frames_with_state_but_no_pair": len(bad_render), "video_ready": vr}

# ---------------- V2
vt = [int(x["t_mono_ns"]) for x in vf]
def frame_at(t):
    i = bisect.bisect_right(vt, t) - 1
    return vf[i] if i >= 0 else None
def frame_after(t):
    i = bisect.bisect_left(vt, t)
    return vf[i] if i < len(vf) else None
v2 = []
for e in ty(sev, "observation_begin"):
    v = P(e).get("video") or {}
    f = frame_after(e["t_mono_ns"])
    v2.append({"episode": P(e)["episode_id"][-24:], "deferred_ms": P(e).get("start_deferred_ms"), "camera": v.get("camera"), "state": v.get("state"), "visible": v.get("visible"),
               "on_screen_age_ms": v.get("on_screen_age_ms"), "exhausted_override": P(e).get("exhausted_recording_development_override"),
               "next_render": None if not f else {"dt_ms": round((int(f["t_mono_ns"]) - e["t_mono_ns"]) / MS, 1), "camera": f["camera"], "plate_visible": f.get("plate_visible"),
                                                  "state": f.get("video_" + (v.get("camera") or "A")), "on_screen_age_ms": f.get("shown_on_screen_age_ms")}})
defs = [{"episode": P(e)["episode_id"][-24:], "state": (P(e).get("video") or {}).get("state"), "reason": (P(e).get("video") or {}).get("reason"), "camera": (P(e).get("video") or {}).get("camera")} for e in ty(sev, "observation_deferred")]
beg_src = {P(e)["episode_id"][-24:]: (P(e).get("video") or {}) for e in ty(sev, "observation_begin")}
exc = [x for x in v2 if x["exhausted_override"]]
# the development-override exception is allowed only for recorded footage that genuinely ended, never for the live source
exc_ok = all(x["state"] == "ended" and beg_src[x["episode"]].get("mode") == "file_replay" and beg_src[x["episode"]].get("receiver_stop_reason") == "replay_done_and_drained" for x in exc)
ok2 = v2 and exc_ok and all((x["state"] == "current" and x["visible"]) for x in v2 if not x["exhausted_override"])
R["V2_observation_starts_on_current_visible_view"] = {"verdict": ("PASS" if not exc else "PASS_WITH_LOGGED_EXCEPTION") if ok2 else ("FAIL" if v2 else "UNTESTED_LIVE"),
                                                      "observations": v2, "deferrals": defs, "deferral_exercised": bool(defs),
                                                      "exhausted_recording_exceptions": exc, "exceptions_only_on_recorded_footage": exc_ok}

# ---------------- V3 (render frames with the plate visible)
vis = [x for x in vf if x.get("plate_visible") == "1" and x.get("shown_on_screen_age_ms")]
lab = lambda x: x["video_" + x["camera"]]
live_over = [x for x in vis if lab(x) == "live" and float(x["shown_on_screen_age_ms"]) > 150.0]
over_live = live_over
stale_rows = [x for x in vis if lab(x) in ("stale", "interrupted")]
stale_under = [x for x in stale_rows if float(x["shown_on_screen_age_ms"]) <= 150.0]   # allowed only when the pair is not validated
# episodes of "Image not current" (stale or interrupted) per camera while visible
eps = []; cur = None
for x in vis:
    t = int(x["t_mono_ns"]); bad = lab(x) in ("stale", "interrupted")
    if bad and (cur is None or cur["camera"] != x["camera"]):
        if cur: eps.append(cur)
        cur = {"camera": x["camera"], "t0": t, "t1": t, "frames": 1, "max_age": float(x["shown_on_screen_age_ms"]), "interrupted": lab(x) == "interrupted"}
    elif bad:
        cur["t1"] = t; cur["frames"] += 1; cur["max_age"] = max(cur["max_age"], float(x["shown_on_screen_age_ms"])); cur["interrupted"] |= lab(x) == "interrupted"
    elif cur:
        cur["t1"] = t; eps.append(cur); cur = None
if cur: eps.append(cur)
for e in eps: e["duration_ms"] = round((e["t1"] - e["t0"]) / MS, 1)
ivs = [e for e in ty(uev, "video_state") if P(e).get("state") == "interrupted"]
int_early = [e for e in ivs if (P(e).get("status") or {}).get("since_new_image_ms") is not None and P(e)["status"]["since_new_image_ms"] <= 500]
vis_ms_by_cam = {}
for i in range(1, len(vis)):
    dt = (int(vis[i]["t_mono_ns"]) - int(vis[i - 1]["t_mono_ns"])) / MS
    if dt < 200: vis_ms_by_cam[vis[i]["camera"]] = vis_ms_by_cam.get(vis[i]["camera"], 0) + dt
brief = [e for e in eps if e["duration_ms"] < 100]
def summ(lst):
    d = [e["duration_ms"] for e in lst]
    return {"n": len(d), "median_ms": round(statistics.median(d), 1) if d else None, "max_ms": max(d) if d else None, "total_ms": round(sum(d), 1)}
R["V3_stale_image_loses_live_and_is_dimmed"] = {
    "verdict": "PASS" if not live_over and not int_early else "FAIL",
    "render_frames_visible": len(vis), "frames_live_with_on_screen_age_over_150": len(live_over),
    "frames_not_current_with_age_le_150 (pair not validated)": len(stale_under),
    "interrupted_transitions": len(ivs), "interrupted_before_500ms": len(int_early),
    "image_not_current_episodes": {c: summ([e for e in eps if e["camera"] == c]) for c in ("A", "B")},
    "episodes_reaching_interrupted": {c: sum(e["interrupted"] for e in eps if e["camera"] == c) for c in ("A", "B")},
    "brief_under_100ms_flicker": {c: summ([e for e in brief if e["camera"] == c]) for c in ("A", "B")},
    "camera_visible_s": {c: round(v / 1000, 1) for c, v in vis_ms_by_cam.items()},
    "per_minute_visible": {c: round(len([e for e in eps if e["camera"] == c]) / (vis_ms_by_cam[c] / 60000), 2) for c in vis_ms_by_cam if vis_ms_by_cam[c] > 0},
    "dimming": "driven by the logged plate condition (stale/interrupted); pixels not measured live",
    "episodes": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in e.items() if k not in ("t0", "t1")} | {"t_s": round((e["t0"] - prep[0]["t_mono_ns"]) / 1e9, 2) if prep else None} for e in eps],
}

# ---------------- V4
def ref_ok(v, t):
    if not v or v.get("camera") not in rx: return False
    g = v.get("receiver_generation"); r = rx[v["camera"]][g - 1] if g and g - 1 < len(rx[v["camera"]]) else None
    src_ok = (v["camera"] == "A" and v.get("mode") == "rtsp" and v.get("source") == "camera") or (v["camera"] == "B" and v.get("source") == "synthetic")
    return bool(r and (v.get("seq") is None or v["seq"] in r["seqs"]) and src_ok)
v4 = {}
for name, t, key in (("observation_end", "observation_end", None), ("sagat_freeze", "sagat_freeze", "video"), ("view_restored", "view_restored", "video"), ("first_commitment", "first_commitment", "video")):
    recs = ty(sev, t); out = []
    for e in recs:
        if name == "observation_end":
            vc = P(e).get("video_continuity") or {}
            vv = [vc.get("at_start"), vc.get("at_end")]
            out.append({"episode": P(e)["episode_id"][-24:], "interrupted": P(e).get("video_interrupted"), "interruptions": vc.get("interruptions"),
                        "not_valid_ms": vc.get("not_valid_ms"), "refs_ok": all(ref_ok(v, e["t_mono_ns"]) for v in vv if v), "losses": vc.get("interruption_list")})
        else:
            v = P(e).get(key)
            extra = {"decision_video_interruptions": (P(e).get("decision_video_continuity") or {}).get("interruptions")} if name == "first_commitment" else {}
            if name == "sagat_freeze": extra = {"observation_video_interrupted": P(e).get("observation_video_interrupted")}
            out.append({"episode": P(e)["episode_id"][-24:], "camera": v and v.get("camera"), "state": v and v.get("state"), "seq": v and v.get("seq"),
                        "source": v and v.get("source"), "generation": v and v.get("receiver_generation"), "refs_ok": ref_ok(v, e["t_mono_ns"]), **extra})
    v4[name] = out
recorded = all(v4[k] for k in v4)
ok4 = recorded and all(x["refs_ok"] for k in v4 for x in v4[k])
any_loss = any(x.get("interrupted") for x in v4["observation_end"]) or any(x.get("decision_video_interruptions") for x in v4["first_commitment"])
R["V4_continuity_records_with_source_and_frame_refs"] = {"verdict": "PASS" if ok4 else ("FAIL" if recorded else "UNTESTED_LIVE"), "loss_recorded_live": any_loss, **v4}

# ---------------- V5
v5 = []
pc = sorted((e["t_mono_ns"], P(e).get("enabled")) for e in ty(uev, "plate_camera"))
for fz in ty(sev, "sagat_freeze"):
    ep = P(fz)["episode_id"]
    rs = next((e for e in ty(sev, "view_restored") + ty(sev, "view_restore_timeout") if P(e)["episode_id"] == ep), None)
    dr = next((e for e in ty(sev, "decision_ready") if P(e)["episode_id"] == ep), None)
    se = next((e for e in ty(sev, "sagat_end") if P(e)["episode_id"] == ep), None)
    t0 = fz["t_mono_ns"]; t1 = se["t_mono_ns"] if se else (rs["t_mono_ns"] if rs else t0)
    # 50 ms margins: the freeze is stamped at its scheduled time and a click-driven sagat_end after that frame's render stamp
    leak = [x for x in vf if t0 + 50 * MS < int(x["t_mono_ns"]) < t1 - 50 * MS and x.get("plate_visible") == "1"]
    off = next((t for t, en in pc if en is False and t >= t0 - 100 * MS), None)
    on = next((t for t, en in pc if en is True and off is not None and t > off), None)
    v5.append({"episode": ep[-24:], "plate_off_ms_after_freeze": round((off - t0) / MS, 1) if off else None,
               "plate_back_on_ms_after_freeze": round((on - t0) / MS, 1) if on else None, "probe_ms": round((t1 - t0) / MS, 1), "visible_plate_frames_during_probe": len(leak),
               "restored_state": rs and (P(rs).get("video") or {}).get("state"), "restored_visible": rs and (P(rs).get("video") or {}).get("visible"),
               "restore_type": rs and rs["type"], "decision_ready_after_restore": bool(dr and rs and dr["t_mono_ns"] >= rs["t_mono_ns"])})
ok5 = v5 and all(x["visible_plate_frames_during_probe"] == 0 and x["restore_type"] == "view_restored" and x["restored_state"] == "current" and x["restored_visible"] and x["decision_ready_after_restore"] for x in v5)
R["V5_sagat_hides_then_restores_current_view"] = {"verdict": "PASS" if ok5 else ("FAIL" if v5 else "UNTESTED_LIVE"), "probes": v5}

# ---------------- V6
cats = {"startup_wait": [], "camera_switch": [], "source_exhaustion": [], "exhaustion_drain_shown_as_not_current": [], "receiver_failure": [],
        "unexpected_interruption_visible": [], "hidden_not_current": []}
vse = ty(uev, "video_state")
ended_t = [(P(e).get("camera"), e["t_mono_ns"]) for e in vse if P(e).get("state") == "unavailable" and (P(e).get("status") or {}).get("state") == "ended"]
for e in vse:
    s = P(e).get("state"); stt = P(e).get("status") or {}
    rec = {"t_s": round((e["t_mono_ns"] - prep[0]["t_mono_ns"]) / 1e9, 2) if prep else None, "camera": P(e).get("camera"), "state": s, "reason": stt.get("reason"), "on_screen": P(e).get("on_screen")}
    # after a recording's last frame the receiver drains for a fixed time before declaring exhaustion; the not-current states in that
    # window (same seq, ended within 3.5 s) are exhaustion, although the live status could not yet know it
    drain = s in ("stale", "interrupted") and any(c == P(e).get("camera") and 0 <= t - e["t_mono_ns"] <= 3.5e9 for c, t in ended_t)
    if s == "waiting": cats["startup_wait"].append(rec)
    elif drain: cats["exhaustion_drain_shown_as_not_current"].append(rec)
    elif s == "unavailable" and stt.get("state") == "ended": cats["source_exhaustion"].append(rec)
    elif s == "unavailable" and stt.get("state") == "failed": cats["receiver_failure"].append(rec)
    elif s in ("stale", "interrupted") and P(e).get("on_screen") and (stt.get("reason") or "").startswith("on_screen_age"): cats["unexpected_interruption_visible"].append(rec)
    elif s in ("stale", "interrupted"): cats["hidden_not_current"].append(rec)
prev = None
for x in vf:
    if prev and x["camera"] != prev["camera"]:
        cats["camera_switch"].append({"t_s": round((int(x["t_mono_ns"]) - prep[0]["t_mono_ns"]) / 1e9, 2), "from": prev["camera"], "to": x["camera"], "state_after": lab(x)})
    prev = x
R["V6_categories_distinguishable"] = {"verdict": "PASS", "counts": {k: len(v) for k, v in cats.items()},
                                      "untested_live": [k for k in ("source_exhaustion", "receiver_failure", "unexpected_interruption_visible", "camera_switch", "startup_wait") if not cats[k]],
                                      "examples": {k: v[:6] for k, v in cats.items()}}
out = run / a.out
out.write_text(json.dumps(R, indent=1), encoding="utf-8")
for k, v in R.items(): print(f"{k:52s} {v['verdict']}")
print("->", out)

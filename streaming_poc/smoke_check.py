"""Task 04B localhost smoke test: per-criterion verdicts from saved evidence.

Offline: reads result folders only.

    smoke_check.py --evidence DIR --stream PUB_DIR RX_DIR [--stream PUB_DIR RX_DIR ...]
                   [--previous PREV_EVIDENCE_DIR PUB_DIR RX_DIR]

  --evidence  folder with preflight.json, listeners.json, cleanup.json and the
              MediaMTX log (mediamtx.log) of THIS run
  --stream    one publisher folder (events.jsonl, report.json, sent.csv) and
              its receiver folder (events.jsonl, frames.csv, arrivals.csv,
              summary.json, optional probe.csv and frames/*.pgm)
  --previous  an earlier run, re-analysed with the same code for comparison

Global criteria: S1 listener, S2 port free, S3 no security block, S8 cleanup.
Per stream: S4 publish/decode, S5a-e identity/numbers/order/image/metadata,
S6 recording, S7 (the original newest-pair criterion, unchanged), and the two
separate verdicts requested after the first smoke test:

  S7a FRAME-BOUNDARY LATENCY: frames are released when they are complete, not
      when the next one is sent. PASS if the median send->release time is
      <= 15 ms, <= 2 % of frames are released by the next frame's send, and the
      last frame before the injected stall is released within 50 ms of its send.
      With probe.csv, the parser stage is also timed against the raw
      (pre-parser) arrival of the same frame.
  S7b STALE-FRAME REJECTION: no displayed pair exceeds the freshness
      threshold, no pair is labelled fresh without verification, at most 2
      backlog (burst-held) frames are shown, the held frames are rejected with
      logged reasons, the displayed sequence is strictly increasing, and frame
      age is back to baseline at the first display after the stall.

  S7b v2 / v3: separate keys; see s7b_v2() and s7b_v3_check(). v3 (6 Nov 2026,
      post-hoc after T4) is reported only with --s7b-v3, so runs without the
      flag reproduce earlier reports exactly.

Verdicts: PASS, FAIL, NOT_TESTED (never PASS by default).
Writes smoke_report.json into the evidence folder.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import re
import sys

import poc_common as pc
import synthetic_stereo as ss

META_FIELDS = ("t_dev_ns", "t_host_mono_ns", "t_utc_ns", "flags", "host", "session",
               "trial", "config_id")


def _csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _json(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))


def V(ok, tested=True):
    return "NOT_TESTED" if not tested else ("PASS" if ok else "FAIL")


def stats(values):
    v = [x for x in values if x is not None]
    if not v:
        return {"n": 0}
    return {"n": len(v), "min": round(min(v), 2), "median": round(pc.percentile(v, 50), 2),
            "p95": round(pc.percentile(v, 95), 2), "max": round(max(v), 2)}


def psnr(path, seq, eye, camera):
    raw = pathlib.Path(path).read_bytes()
    m = re.match(rb"P5\n(\d+) (\d+)\n255\n", raw)
    w, h = int(m.group(1)), int(m.group(2))
    got = raw[m.end():]
    ref = ss.make_luma(seq, eye, camera)
    if (w, h) != (ss.WIDTH, ss.HEIGHT) or len(got) != len(ref):
        return None
    se = sum((a - b) * (a - b) for a, b in zip(got, ref))
    mse = se / len(ref)
    return 99.0 if mse == 0 else 10 * math.log10(255 * 255 / mse)


def page_age(f):
    return max(float(f["age_utc_ms_left"]), float(f["age_utc_ms_right"]))


# ---------------------------------------------------------------------------
# global criteria
# ---------------------------------------------------------------------------

def mediamtx_text(ev):
    """All MediaMTX log output of a run: per-instance stdout files plus the log file."""
    ev = pathlib.Path(ev)
    parts = []
    for p in sorted(ev.glob("mediamtx_stdout*.txt")) + [ev / "mediamtx.log"]:
        if p.exists():
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def global_criteria(ev, streams):
    """S1 for every MediaMTX instance (listeners*.json; one per launch), S2 for
    every pre-launch check (preflight*.json), S3, S8."""
    ev = pathlib.Path(ev)
    pres_ = [(_p.name, _json(_p)) for _p in sorted(ev.glob("preflight*.json"))]
    post = _json(ev / "cleanup.json")
    mtx = mediamtx_text(ev)
    instances = []
    for f in sorted(ev.glob("listeners*.json")):
        lis = _json(f)
        if isinstance(lis, dict):
            lis = [lis]
        instances.append({"file": f.name,
                          "sockets": sorted({"{}:{}:{}".format(x["proto"], x["address"], x["port"]) for x in lis})})
    per_stdout = []
    for p in sorted(ev.glob("mediamtx_stdout*.txt")):
        per_stdout.append({"file": p.name, "listeners": re.findall(r"\[(\w+)\] started with listeners on (.+)",
                                                                   p.read_text(encoding="utf-8", errors="replace"))})
    want = [("RTSP", "127.0.0.1:8554 (TCP/RTSP)")]
    ok1 = bool(instances) and all(i["sockets"] == ["TCP:127.0.0.1:8554"] for i in instances) \
        and all(s["listeners"] == want for s in per_stdout)
    C = {}
    C["S1_listener_localhost_only"] = {
        "verdict": V(ok1, tested=bool(instances)), "instances": instances,
        "mediamtx_log_listeners_per_instance": per_stdout}
    C["S2_port_free_before_launch"] = {
        "verdict": V(bool(pres_) and all(p.get("port_8554_free") is True and not p.get("mediamtx_already_running")
                                          for _n, p in pres_)),
        "checks": {n: {k: p.get(k) for k in ("port_8554_free", "mediamtx_already_running", "config_sha256",
                                              "config_unchanged_from_verified")} for n, p in pres_}}
    blocked = any(p.get("launch_blocked") for _n, p in pres_) or post.get("launch_blocked")
    C["S3_no_security_block"] = {
        "verdict": V(not blocked and bool(instances)),
        "note": "No block, error or exit observed from the process. A GUI prompt (Defender, "
                "SmartScreen, firewall) is not visible to the automated checks: operator to confirm."}
    clean = (post.get("mediamtx_running") is False and post.get("port_8554_listening") is False
             and not post.get("poc_python_pids"))
    C["S8_processes_and_ports_closed"] = {"verdict": V(clean), "detail": post}
    return C, mtx


# ---------------------------------------------------------------------------
# per stream
# ---------------------------------------------------------------------------

def restart_and_freshness(C, M, sent, arr, frames, pev, rev, pres, pol, camera, cam_code, rx, restart):
    """R1-R5 (controlled server restart) and F1-F3 (two freshness measures)."""
    thr = pol.get("max_excess_ms")
    ok_arr = [a for a in arr if a["sei"] == "ok"]
    # F1: both measures on every displayed pair
    need = ("excess_ms", "rel_status", "abs_age_lo_ms", "abs_age_hi_ms", "abs_uncertainty_ms",
            "clock_source", "abs_status")
    has_cols = bool(frames) and all(k in frames[0] for k in need)
    complete = has_cols and all(f["rel_status"] and f["abs_status"] and f["clock_source"] for f in frames)
    rel = [float(f["excess_ms"]) for f in frames if has_cols and f["excess_ms"] != ""]
    absd = [float(f["abs_age_ms"]) for f in frames if has_cols and f["abs_age_ms"] != ""]
    C["F1_two_freshness_measures_recorded"] = {
        "verdict": V(complete, tested=has_cols),
        "relative_excess_ms": stats(rel), "absolute_age_est_ms": stats(absd),
        "clock_sources": sorted({f["clock_source"] for f in frames}) if has_cols else [],
        "abs_uncertainty_ms": sorted({f["abs_uncertainty_ms"] for f in frames}) if has_cols else [],
        "abs_status_counts": {s: sum(1 for f in frames if f.get("abs_status") == s)
                              for s in ("within", "uncertain", "over", "unknown")} if has_cols else {},
        "label_counts": {s: sum(1 for f in frames if f.get("freshness") == s)
                         for s in ("fresh", "late", "fresh_relative", "relative_adapted", "unverified")}}
    rb_events = [e for e in rev if e["type"] == "delay_rebaseline"]
    C["F2_rebaselines_logged"] = {"verdict": V(len(rb_events) == pres.get("rebaselines", 0), tested=has_cols),
                                  "rebaseline_events": [e["payload"] for e in rb_events],
                                  "counter": pres.get("rebaselines")}
    bad = [f for f in frames if has_cols and f["freshness"] == "fresh" and f["abs_status"] != "within"]
    adapted_fresh = [f for f in frames if has_cols and f["freshness"] == "fresh" and f["baseline_shift_ms"] != ""
                     and thr is not None and float(f["baseline_shift_ms"]) > thr and f["abs_status"] != "within"]
    C["F3_no_absolute_fresh_claim_without_absolute_check"] = {
        "verdict": V(not bad and not adapted_fresh, tested=has_cols),
        "fresh_without_absolute_within": len(bad), "fresh_after_baseline_shift_without_absolute": len(adapted_fresh),
        "note": "rule checked on every displayed pair; a persistently delayed stream (re-baselining) was "
                "exercised offline only -- see F3b"}
    C["F3b_persistent_delay_live"] = {"verdict": "NOT_TESTED",
                                      "note": "no persistent delay was injected live; offline tests cover it"}

    if not restart or "stop_issued_utc_ns" not in restart or "start_issued_utc_ns" not in restart:
        for k in ("R1_publisher_reconnect", "R2_receiver_reconnect_and_resume",
                  "R3_no_stale_replay_after_reconnect", "R4_freshness_reference_reset",
                  "R5_integrity_across_restart"):
            C[k] = {"verdict": "NOT_TESTED", "note": "no controlled restart in this run"}
        return
    stop, start = restart["stop_issued_utc_ns"], restart["start_issued_utc_ns"]
    up_again = restart.get("listening_again_utc_ns", start)
    pdown = [e for e in pev if e["type"] == "link_down" and e["t_utc_ns"] >= stop]
    pup = [e for e in pev if e["type"] == "link_up" and e["t_utc_ns"] >= start]
    C["R1_publisher_reconnect"] = {
        "verdict": V(bool(pdown) and bool(pup)),
        "link_down_after_stop_s": round((pdown[0]["t_utc_ns"] - stop) / 1e9, 3) if pdown else None,
        "link_up_after_server_listening_s": round((pup[0]["t_utc_ns"] - up_again) / 1e9, 3) if pup else None,
        "open_failures_while_down": sum(1 for e in pev if e["type"] == "link_open_failed" and stop <= e["t_utc_ns"]
                                        <= (pup[0]["t_utc_ns"] if pup else 1 << 62))}
    rdown = {e["payload"].get("eye") for e in rev if e["type"] == "link_down" and e["t_utc_ns"] >= stop}
    rup = [e for e in rev if e["type"] == "link_up" and e["t_utc_ns"] >= start]
    rup_eyes = {e["payload"].get("eye") for e in rup}
    resume = None
    if pup:
        nxt = next((f for f in frames if int(f["t_display_utc_ns"]) >= pup[0]["t_utc_ns"]), None)
        resume = None if nxt is None else (int(nxt["t_display_utc_ns"]) - pup[0]["t_utc_ns"]) / 1e9
    C["R2_receiver_reconnect_and_resume"] = {
        "verdict": V({"left", "right"} <= rdown and {"left", "right"} <= rup_eyes and resume is not None
                     and resume <= 3.0),
        "eyes_link_down": sorted(x for x in rdown if x), "eyes_link_up_again": sorted(x for x in rup_eyes if x),
        "display_resume_after_publisher_reconnect_s": round(resume, 3) if resume is not None else None,
        "limit_s": 3.0}
    after_stop = [f for f in frames if int(f["t_display_utc_ns"]) > stop + 200_000_000]
    cap = {(a["eye"], a["seq"]): int(a["t_utc_ns"]) for a in ok_arr}
    stale_replay = [int(f["seq"]) for f in after_stop
                    if min(cap.get(("left", f["seq"]), 1 << 62), cap.get(("right", f["seq"]), 1 << 62)) < stop]
    first_post = next((f for f in frames if int(f["t_display_utc_ns"]) >= start), None)
    fp_ok = first_post is not None and (first_post.get("excess_ms") in ("", None) or thr is None
                                        or float(first_post["excess_ms"]) <= thr) \
        and first_post.get("abs_status", "within") == "within" and first_post["burst"] == "0"
    C["R3_no_stale_replay_after_reconnect"] = {
        "verdict": V(not stale_replay and fp_ok, tested=first_post is not None),
        "pairs_shown_after_stop_but_captured_before_it": stale_replay,
        "first_pair_after_restart": first_post and {k: first_post.get(k) for k in
                                                    ("seq", "freshness", "excess_ms", "abs_age_ms", "abs_status",
                                                     "pairs_since_reset", "skipped_missing")},
        "late_discarded_total": pres.get("late_discarded"), "obsolete_discarded_total": pres.get("obsolete_discarded")}
    resets = [e for e in rev if e["type"] == "freshness_reset" and e["t_utc_ns"] >= start]
    reset_eyes = {e["payload"].get("eye") for e in resets}
    psr = int(first_post["pairs_since_reset"]) if first_post and first_post.get("pairs_since_reset") not in ("", None) else None
    C["R4_freshness_reference_reset"] = {
        "verdict": V({"left", "right"} <= reset_eyes and psr is not None and psr < (pol.get("warmup_pairs") or 20)),
        "reset_events_after_restart": sorted(x for x in reset_eyes if x),
        "first_post_restart_pairs_since_reset": psr,
        "note": "the delay reference is rebuilt only from post-restart pairs"}
    truth = {(s["eye"], s["seq"]): s for s in sent}
    post_arr = [a for a in ok_arr if int(a["t_arrival_utc_ns"]) >= start]
    meta_bad = sum(1 for a in post_arr if (a["eye"], a["seq"]) in truth
                   and any(str(a[k]) != str(truth[(a["eye"], a["seq"])][k]) for k in META_FIELDS))
    bc_bad = sum(1 for a in post_arr if a["barcode_seq"] != a["seq"] or a["meta_eye"] != a["eye"]
                 or a["barcode_eye"] != str(pc.EYES[a["eye"]]))
    post_frames = [f for f in frames if int(f["t_display_utc_ns"]) >= start]
    dseq = [int(f["seq"]) for f in frames]
    mono = all(b > a for a, b in zip(dseq, dseq[1:]))
    pgms = sorted((pathlib.Path(rx) / "frames").glob("*.pgm")) if (pathlib.Path(rx) / "frames").exists() else []
    first_post_seq = int(post_frames[0]["seq"]) if post_frames else None
    ps = {}
    for p in pgms:
        eye, seq = p.stem.split("_")
        if first_post_seq is not None and int(seq) >= first_post_seq:
            ps[p.name] = round(psnr(p, int(seq), pc.EYES[eye], cam_code) or 0, 2)
    pre_seqs = {int(f["seq"]) for f in frames if int(f["t_display_utc_ns"]) < stop}
    lost = sorted({int(s["seq"]) for s in sent if s["eye"] == "left"} -
                  {int(a["seq"]) for a in ok_arr if a["eye"] == "left"})
    lost_mid = [s for s in lost if pre_seqs and min(pre_seqs) < s]
    C["R5_integrity_across_restart"] = {
        "verdict": V(bool(post_arr) and meta_bad == 0 and bc_bad == 0 and mono
                     and all(f["barcode_ok"] == "1" and f["eye_ok"] == "1" for f in post_frames)
                     and bool(ps) and min(ps.values()) >= 35.0, tested=bool(post_arr)),
        "post_restart_arrivals": len(post_arr), "post_restart_displayed": len(post_frames),
        "metadata_fields_changed": meta_bad, "barcode_or_eye_mismatch": bc_bad,
        "display_strictly_increasing_whole_run": mono, "post_restart_psnr_db": ps,
        "left_seqs_sent_never_received_after_first_display": {"count": len(lost_mid),
                                                              "ranges": _ranges(lost_mid)}}


def _ranges(seqs):
    out, start, prev = [], None, None
    for s in seqs:
        if start is None:
            start = prev = s
        elif s == prev + 1:
            prev = s
        else:
            out.append([start, prev])
            start = prev = s
    if start is not None:
        out.append([start, prev])
    return out


def stream_analysis(pub, rx, mtx="", restart=None, s7b_v3=False):
    """s7b_v3=True adds the separate key S7b_v3_stale_frame_rejection (approved
    6 Nov 2026). Off by default, so existing invocations, reports and recorded
    verdicts are reproduced exactly."""
    pub, rx = pathlib.Path(pub), pathlib.Path(rx)
    prep = _json(pub / "report.json")
    camera = prep["camera"]
    cam_code = pc.CAMERAS[camera]
    sent = _csv(pub / "sent.csv")
    arr = _csv(rx / "arrivals.csv")
    frames = _csv(rx / "frames.csv")
    rsum = _json(rx / "summary.json")
    pev = pc.read_events(pub / "events.jsonl")
    rev = pc.read_events(rx / "events.jsonl")
    pres = rsum["presenter"]["counts"]
    pol = rsum["presenter"].get("freshness_policy") or {"enabled": False}
    C, M = {}, {"camera": camera, "frame_end": prep.get("frame_end", "none"),
                "freshness": pol.get("enabled", False)}
    ok_arr = [a for a in arr if a["sei"] == "ok"]

    # S4
    pubs = sorted(set(re.findall(r"is publishing to path '(cam{}_\w+)'".format(camera), mtx)))
    reads = sorted(set(re.findall(r"is reading from path '(cam{}_\w+)'".format(camera), mtx)))
    first_rx = min((int(a["seq"]) for a in ok_arr), default=None)
    sent_n = {e: sum(1 for s in sent if s["eye"] == e and first_rx is not None
                     and int(s["seq"]) >= first_rx) for e in ("left", "right")}
    dec_n = {e: sum(1 for a in arr if a["eye"] == e) for e in ("left", "right")}
    dec_err = sum(r["decode_errors"] for r in rsum["readers"].values())
    want = ["cam{}_left".format(camera), "cam{}_right".format(camera)]
    C["S4_rtsp_publish_and_decode"] = {
        "verdict": V((not mtx or (pubs == want and reads == want)) and dec_err == 0
                     and all(dec_n[e] >= 0.95 * sent_n[e] > 0 for e in dec_n)),
        "mediamtx_publishing": pubs, "mediamtx_reading": reads, "receiver_first_seq": first_rx,
        "sent_frames_from_first_rx_seq": sent_n, "decoded_frames": dec_n,
        "decode_errors_after_sync": dec_err,
        "non_vcl_packets_skipped": sum(r.get("non_vcl_packets", 0) for r in rsum["readers"].values())}

    # S5
    ok_ident = all(a["meta_eye"] == a["eye"] and a["barcode_eye"] == str(pc.EYES[a["eye"]])
                   and a["camera"] == camera and a["barcode_camera"] == str(cam_code) for a in ok_arr)
    ok_match = all(a["barcode_seq"] == a["seq"] for a in ok_arr)
    order_ok = {}
    for e in ("left", "right"):
        seqs = [int(a["seq"]) for a in ok_arr if a["eye"] == e]
        order_ok[e] = all(b > a for a, b in zip(seqs, seqs[1:]))
    dseq = [int(f["seq"]) for f in frames]
    disp_order = all(b > a for a, b in zip(dseq, dseq[1:]))
    pgms = sorted((rx / "frames").glob("*.pgm")) if (rx / "frames").exists() else []
    ps = {}
    for p in pgms:
        eye, seq = p.stem.split("_")
        ps[p.name] = round(psnr(p, int(seq), pc.EYES[eye], cam_code) or 0, 2)
    C["S5a_left_right_identity"] = {"verdict": V(ok_ident and pres["eye_mismatch"] == 0
                                                 and pres["camera_mismatch"] == 0, tested=bool(arr))}
    C["S5b_matching_frame_numbers"] = {"verdict": V(ok_match and pres["integrity_errors"] == 0
                                                    and all(f["barcode_ok"] == "1" for f in frames),
                                                    tested=bool(frames)),
                                       "displayed_pairs": len(frames), "integrity_errors": pres["integrity_errors"]}
    C["S5c_ordering"] = {"verdict": V(all(order_ok.values()) and disp_order, tested=bool(frames)),
                         "arrival_order_strictly_increasing": order_ok,
                         "display_order_strictly_increasing": disp_order}
    C["S5d_decoded_image_integrity"] = {"verdict": V(ok_match and bool(ps) and min(ps.values()) >= 35.0,
                                                     tested=bool(ps)),
                                        "psnr_db": ps, "threshold_db": 35.0}
    truth = {(s["eye"], s["seq"]): s for s in sent}
    compared = mismatched = 0
    for a in ok_arr:
        s = truth.get((a["eye"], a["seq"]))
        if s is None:
            continue
        compared += 1
        if any(str(a[k]) != str(s[k]) for k in META_FIELDS):
            mismatched += 1
    sei_missing = sum(1 for a in arr if a["sei"] == "missing")
    sei_err = sum(1 for a in arr if a["sei"] == "error")
    C["S5e_metadata_survival"] = {
        "verdict": V(compared > 0 and mismatched == 0 and sei_err == 0 and sei_missing == 0,
                     tested=compared > 0),
        "frames_compared": compared, "frames_with_any_field_changed": mismatched,
        "sei_missing": sei_missing, "sei_crc_or_format_errors": sei_err}

    # S6 measurements
    by = {}
    for a in ok_arr:
        by.setdefault(a["seq"], {})[a["eye"]] = int(a["t_arrival_mono_ns"])
    skew = [(v["right"] - v["left"]) / 1e6 for v in by.values() if "left" in v and "right" in v]
    lat = [(int(a["t_arrival_utc_ns"]) - int(a["t_utc_ns"])) / 1e6 for a in ok_arr]
    ages = [page_age(f) for f in frames]
    sent_seqs = {e: {int(s["seq"]) for s in sent if s["eye"] == e and first_rx is not None
                     and int(s["seq"]) >= first_rx} for e in ("left", "right")}
    got_seqs = {e: {int(a["seq"]) for a in ok_arr if a["eye"] == e} for e in ("left", "right")}
    M.update({"capture_to_arrival_ms": stats(lat), "pair_arrival_skew_ms": stats(skew),
              "frame_age_at_display_ms": stats(ages),
              "display_interval_ms": stats([float(f["interval_ms"]) for f in frames if f["interval_ms"]]),
              "freezes": [{"type": e["type"], **{k: e["payload"].get(k) for k in ("duration_ms", "last_seq",
                                                                                  "resumed_seq")}}
                          for e in rev if e["type"] in ("freeze_start", "freeze_end")],
              "late_join_first_seq": first_rx,
              "sent_but_never_received": {e: len(sent_seqs[e] - got_seqs[e]) for e in sent_seqs},
              "presenter_counts": pres, "publisher_counts": prep["counts"]})
    C["S6_timing_and_loss_recorded"] = {"verdict": V(bool(lat) and bool(skew) and bool(ages))}

    # stall context
    stalls = []
    starts = {e["payload"]["index"]: e for e in pev if e["type"] == "stall_start"}
    for e in pev:
        if e["type"] == "stall_end":
            stalls.append({"start_ns": starts[e["payload"]["index"]]["t_utc_ns"], "end_ns": e["t_utc_ns"],
                           **e["payload"]})
    base = M["frame_age_at_display_ms"].get("median")

    # S7 (original criterion, unchanged)
    s7 = []
    for s in stalls:
        after = [f for f in frames if int(f["t_display_utc_ns"]) >= s["end_ns"]]
        first = after[0] if after else None
        rec = next((i for i, f in enumerate(after) if base is not None and page_age(f) <= base + 20), None)
        s7.append({"held_seq": [s["seq_first"], s["seq_last"]],
                   "first_display_after": first and {"seq": int(first["seq"]), "age_ms": page_age(first),
                                                     "freshness": first.get("freshness")},
                   "burst_frames_displayed": sum(1 for f in after[:20] if f["burst"] == "1"),
                   "frames_to_recover_age": rec})
    ok7 = all(x["first_display_after"] and x["first_display_after"]["seq"] >= x["held_seq"][1]
              and x["burst_frames_displayed"] <= 2 and x["frames_to_recover_age"] is not None
              and x["frames_to_recover_age"] <= 2 for x in s7)
    C["S7_newest_complete_pair_no_stale_replay"] = {
        "verdict": V(ok7 and disp_order and len(set(dseq)) == len(dseq), tested=bool(s7)), "stalls": s7}

    # S7a frame-boundary latency
    send = {(s["eye"], int(s["seq"])): int(s["t_sent_mono_ns"]) for s in sent}
    own, by_next = [], 0
    for a in ok_arr:
        k = (a["eye"], int(a["seq"]))
        if k not in send:
            continue
        t = int(a["t_arrival_mono_ns"])
        own.append((t - send[k]) / 1e6)
        nk = (a["eye"], int(a["seq"]) + 1)
        if nk in send and abs(t - send[nk]) <= 3e6 and t - send[k] > 20e6:
            by_next += 1
    frac_next = by_next / len(own) if own else None
    pre_stall = []
    for s in stalls:
        q = s["seq_first"] - 1
        for e in ("left", "right"):
            a = next((x for x in ok_arr if x["eye"] == e and int(x["seq"]) == q), None)
            if a and (e, q) in send:
                pre_stall.append({"eye": e, "seq": q,
                                  "send_to_release_ms": round((int(a["t_arrival_mono_ns"]) - send[(e, q)]) / 1e6, 2)})
    probe = probe_trace(rx, ok_arr, send)
    s_own = stats(own)
    ok7a = (s_own.get("median") is not None and s_own["median"] <= 15 and frac_next is not None
            and frac_next <= 0.02 and all(p["send_to_release_ms"] <= 50 for p in pre_stall))
    C["S7a_frame_boundary_latency"] = {
        "verdict": V(ok7a, tested=bool(own)),
        "send_to_release_ms": s_own, "released_by_next_frame_fraction": round(frac_next, 4) if own else None,
        "pre_stall_frame": pre_stall, "parser_trace": probe}

    # S7b stale-frame rejection
    thr = pol.get("max_excess_ms")
    exc = [float(f["excess_ms"]) for f in frames if f.get("excess_ms") not in (None, "")]
    over = [f for f in frames if f.get("excess_ms") not in (None, "") and thr is not None
            and float(f["excess_ms"]) > thr]
    fresh_bad = [f for f in frames if f.get("freshness") == "fresh" and (
        (f.get("excess_ms") not in (None, "") and thr is not None and float(f["excess_ms"]) > thr)
        or ("abs_status" in f and f["abs_status"] != "within"))]
    rejects = [e for e in rev if e["type"] == "pair_rejected"]
    s7b = []
    for s, x in zip(stalls, s7):
        held = set(range(s["seq_first"], s["seq_last"] + 1)) | {s["seq_first"] - 1}
        rej_seqs = set()
        for e in rejects:
            if e["t_utc_ns"] >= s["start_ns"]:
                rej_seqs.add(e["payload"]["seq"])
                rej_seqs.update(e["payload"].get("obsolete_older") or [])
        shown_held = [int(f["seq"]) for f in frames if int(f["seq"]) in held
                      and int(f["t_display_utc_ns"]) >= s["start_ns"]]
        s7b.append({"held_seq": [s["seq_first"], s["seq_last"]],
                    "held_shown_after_stall_start": shown_held,
                    "held_rejected_with_reason": sorted(held & rej_seqs),
                    "rejection_events": sum(1 for e in rejects if e["t_utc_ns"] >= s["start_ns"]),
                    "reasons": sorted({r for e in rejects if e["t_utc_ns"] >= s["start_ns"]
                                       for r in e["payload"]["reasons"]}),
                    "first_display_after": x["first_display_after"],
                    "frames_to_recover_age": x["frames_to_recover_age"]})
    ok7b = (pol.get("enabled") and not over and not fresh_bad and disp_order
            and len(set(dseq)) == len(dseq)
            and all(len(x["held_shown_after_stall_start"]) <= 2 and x["rejection_events"] > 0
                    and x["frames_to_recover_age"] == 0 for x in s7b))
    C["S7b_stale_frame_rejection"] = {
        "verdict": V(bool(ok7b), tested=bool(s7b) and bool(pol.get("enabled"))),
        "threshold_ms": thr, "displayed_over_threshold": len(over), "fresh_label_without_verification": len(fresh_bad),
        "excess_ms_displayed": stats(exc), "stalls": s7b,
        "labels": {k: pres.get(k) for k in ("fresh_displayed", "unverified_displayed")},
        "rejections": {k: pres.get(k) for k in ("rejected_excess_delay", "rejected_absolute_age",
                                                 "rejected_obsolete", "obsolete_discarded",
                                                 "rebaselines", "freshness_resets")}}
    C["S7b_v2_stale_frame_rejection"] = s7b_v2(stalls, s7, frames, ok_arr, rejects, pol, over, fresh_bad,
                                                disp_order, dseq, thr)
    if s7b_v3:
        C["S7b_v3_stale_frame_rejection"] = s7b_v3_check(stalls, frames, ok_arr, send, sent, rejects, pol, over,
                                                         fresh_bad, disp_order, dseq, thr)
    restart_and_freshness(C, M, sent, arr, frames, pev, rev, pres, pol, camera, cam_code, rx, restart)
    publisher_outage(C, M, pub, prep, sent, pev, restart)
    return C, M


S7B_V2_WINDOW_NS = 2_000_000_000


def s7b_v2(stalls, s7, frames, ok_arr, rejects, pol, over, fresh_bad, disp_order, dseq, thr):
    """S7b v2 (adopted by the researcher on 5 Nov 2026 for future tests; v1 above
    is unchanged and keeps every historical verdict). Same global conditions and
    per-stall "<= 2 held frames shown" and "0-frame recovery" as v1. Changed:
      1. applicability: a stall needs a rejection only if at least one of its held
         frames ARRIVED at the receiver after the stall start (a drop stall whose
         frames never arrive is "not applicable" for the rejection part);
      2. bounded window: rejections count only within [stall start, stall end + 2 s]
         and only when they reject a held frame or carry one in their obsolete backlog.
    Held frames = the stall's frames plus the frame before it (as in v1)."""
    out = []
    for s, x in zip(stalls, s7):
        held = set(range(s["seq_first"], s["seq_last"] + 1)) | {s["seq_first"] - 1}
        arrived = sorted({int(a["seq"]) for a in ok_arr
                          if int(a["seq"]) in held and int(a["t_arrival_utc_ns"]) >= s["start_ns"]})
        lo, hi = s["start_ns"], s["end_ns"] + S7B_V2_WINDOW_NS
        win = [e for e in rejects if lo <= e["t_utc_ns"] <= hi
               and (int(e["payload"]["seq"]) in held or held & set(e["payload"].get("obsolete_older") or []))]
        shown_held = [int(f["seq"]) for f in frames if int(f["seq"]) in held and int(f["t_display_utc_ns"]) >= s["start_ns"]]
        applicable = bool(arrived)
        ok = (len(shown_held) <= 2 and x["frames_to_recover_age"] == 0 and (not applicable or bool(win)))
        out.append({"held_seq": [s["seq_first"], s["seq_last"]], "mode": s.get("mode"),
                    "held_arrived_after_stall_start": len(arrived),
                    "rejection_requirement": "applicable" if applicable else "not applicable (no held frame arrived)",
                    "rejections_in_window_on_held_frames": len(win),
                    "held_shown_after_stall_start": shown_held,
                    "first_display_after": x["first_display_after"],
                    "frames_to_recover_age": x["frames_to_recover_age"], "stall_ok": ok})
    ok_all = (bool(pol.get("enabled")) and not over and not fresh_bad and disp_order and len(set(dseq)) == len(dseq)
              and all(x["stall_ok"] for x in out))
    return {"verdict": V(ok_all, tested=bool(out) and bool(pol.get("enabled"))), "version": 2,
            "threshold_ms": thr, "window_after_stall_end_s": S7B_V2_WINDOW_NS / 1e9,
            "displayed_over_threshold": len(over), "fresh_label_without_verification": len(fresh_bad),
            "stalls": out}


S7B_V3_PRE_STALL_HELD_MS = 50.0   # S7a's established pre-stall send->release limit


def s7b_v3_check(stalls, frames, ok_arr, send, sent, rejects, pol, over, fresh_bad, disp_order, dseq, thr):
    """S7b v3 (approved by the researcher on 6 Nov 2026, POST-HOC after the T4 v1
    FAIL; for future use; v1 and v2 above are unchanged and keep every historical
    verdict). Changes from v2:
      1. No per-stall recovery requirement. v1/v2 demanded recovery in 0 frames,
         which contradicts M1.4/G1.4's "<= 2 frames"; recovery is scored once, by
         M1.4 / G1.4. (It is not reported here.)
      2. The pre-stall frame (seq_first - 1) is in the held set only when it was
         TRANSPORT-HELD: its send->receipt time (same-host monotonic clock) exceeds
         S7B_V3_PRE_STALL_HELD_MS (50 ms, S7a's limit) for either eye. Otherwise the
         held set is exactly the publisher's stall frames [seq_first, seq_last].
    Unchanged from v2: the global conditions (safeguard on, no displayed pair over
    the excess threshold, no "fresh" label without verification, strictly
    increasing unique display order); per stall <= 2 held frames shown after the
    stall start; the rejection requirement applies only if a held frame arrived
    after the stall start, and counts rejections in [stall start, stall end + 2 s]
    that reject a held frame or carry one in their obsolete backlog.
    Per stall, three measurements are reported separately:
      transport_delay        the pre-stall frame's capture->send (publisher side)
                             and send->receipt (transport) times, and whether it is
                             transport-held (informational; decides membership only)
      freshness              displays in [stall start, stall end + 2 s]: count, max
                             excess and absolute age, count over the threshold or
                             not "within" (informational; the gating freshness
                             conditions are the global ones)
      inappropriate_display  held frames shown after the stall start, and the
                             rejection requirement (gating)"""
    cap = {(s["eye"], int(s["seq"])): int(s["t_host_mono_ns"]) for s in sent}
    out = []
    for s in stalls:
        q = s["seq_first"] - 1
        eyes = []
        for e in ("left", "right"):
            a = next((x for x in ok_arr if x["eye"] == e and int(x["seq"]) == q), None)
            snd = send.get((e, q))
            eyes.append({"eye": e, "sent": snd is not None, "received": a is not None,
                         "capture_to_send_ms": None if snd is None or (e, q) not in cap
                         else round((snd - cap[(e, q)]) / 1e6, 2),
                         "send_to_receipt_ms": None if snd is None or a is None
                         else round((int(a["t_arrival_mono_ns"]) - snd) / 1e6, 2)})
        s2r = [x["send_to_receipt_ms"] for x in eyes if x["send_to_receipt_ms"] is not None]
        pre_held = bool(s2r) and max(s2r) > S7B_V3_PRE_STALL_HELD_MS
        held = set(range(s["seq_first"], s["seq_last"] + 1)) | ({q} if pre_held else set())
        arrived = sorted({int(a["seq"]) for a in ok_arr
                          if int(a["seq"]) in held and int(a["t_arrival_utc_ns"]) >= s["start_ns"]})
        lo, hi = s["start_ns"], s["end_ns"] + S7B_V2_WINDOW_NS
        win = [e for e in rejects if lo <= e["t_utc_ns"] <= hi
               and (int(e["payload"]["seq"]) in held or held & set(e["payload"].get("obsolete_older") or []))]
        shown_held = [int(f["seq"]) for f in frames if int(f["seq"]) in held and int(f["t_display_utc_ns"]) >= s["start_ns"]]
        applicable = bool(arrived)
        ok = len(shown_held) <= 2 and (not applicable or bool(win))
        disp = [f for f in frames if lo <= int(f["t_display_utc_ns"]) <= hi]
        exc = [float(f["excess_ms"]) for f in disp if f.get("excess_ms") not in (None, "")]
        absa = [float(f["abs_age_ms"]) for f in disp if f.get("abs_age_ms") not in (None, "")]
        out.append({
            "held_seq": [s["seq_first"], s["seq_last"]], "mode": s.get("mode"),
            "transport_delay": {"pre_stall_seq": q, "eyes": eyes, "threshold_ms": S7B_V3_PRE_STALL_HELD_MS,
                                "transport_held": pre_held,
                                "pre_stall_in_held_set": pre_held},
            "freshness": {"displays_in_window": len(disp),
                          "max_excess_ms": max(exc) if exc else None,
                          "max_abs_age_ms": max(absa) if absa else None,
                          "over_threshold": sum(1 for x in exc if thr is not None and x > thr),
                          "abs_status_not_within": sum(1 for f in disp if f.get("abs_status", "within") != "within")},
            "inappropriate_display": {"held_shown_after_stall_start": shown_held,
                                      "held_arrived_after_stall_start": len(arrived),
                                      "rejection_requirement": "applicable" if applicable
                                      else "not applicable (no held frame arrived)",
                                      "rejections_in_window_on_held_frames": len(win)},
            "stall_ok": ok})
    ok_all = (bool(pol.get("enabled")) and not over and not fresh_bad and disp_order and len(set(dseq)) == len(dseq)
              and all(x["stall_ok"] for x in out))
    return {"verdict": V(ok_all, tested=bool(out) and bool(pol.get("enabled"))), "version": 3,
            "post_hoc": "POST-HOC: approved 6 Nov 2026 after the T4 v1 FAIL",
            "threshold_ms": thr, "window_after_stall_end_s": S7B_V2_WINDOW_NS / 1e9,
            "pre_stall_transport_held_ms": S7B_V3_PRE_STALL_HELD_MS,
            "recovery": "not scored here; M1.4 / G1.4 (<= 2 frames) is authoritative",
            "displayed_over_threshold": len(over), "fresh_label_without_verification": len(fresh_bad),
            "display_order_strictly_increasing": bool(disp_order and len(set(dseq)) == len(dseq)),
            "stalls": out}


def publisher_outage(C, M, pub, prep, sent, pev, restart):
    """P1: generation continues during the outage; P2: bounded queue, no stale
    backlog sent after recovery (publishers since the final Task 04B fixes)."""
    gpath = pathlib.Path(pub) / "generated.csv"
    if not gpath.exists() or not restart or "stop_issued_utc_ns" not in restart:
        C["P1_generation_continues_during_outage"] = {"verdict": "NOT_TESTED",
                                                      "note": "no generated.csv or no restart"}
        C["P2_bounded_queue_no_stale_backlog"] = {"verdict": "NOT_TESTED"}
        return
    gen = _csv(gpath)
    fps = 20.0
    stop, back = restart["stop_issued_utc_ns"], restart.get("listening_again_utc_ns", restart["start_issued_utc_ns"])
    ups = [e for e in pev if e["type"] == "link_up" and e["t_utc_ns"] >= stop]
    rec = ups[0]["t_utc_ns"] if ups else back
    win = [g for g in gen if stop <= int(g["t_utc_ns"]) <= rec + 2_000_000_000]
    tm = [int(g["t_mono_ns"]) for g in win]
    gaps = [(b - a) / 1e6 for a, b in zip(tm, tm[1:])]
    expected = (rec + 2_000_000_000 - stop) / 1e9 * fps
    allm = [int(g["t_mono_ns"]) for g in gen]
    all_gaps = [(b - a) / 1e6 for a, b in zip(allm, allm[1:])]
    C["P1_generation_continues_during_outage"] = {
        "verdict": V(bool(gaps) and max(gaps) <= 2000 / fps and len(win) >= 0.95 * expected),
        "generated_in_outage_window": len(win), "expected": round(expected),
        "max_gap_ms_in_window": round(max(gaps), 1) if gaps else None,
        "max_gap_ms_whole_run": round(max(all_gaps), 1) if all_gaps else None,
        "late_frames_whole_run": prep["counts"].get("late_frames"),
        "window": "server stop -> publisher reconnect + 2 s"}
    qmax, qcap = prep.get("queue_max_depth"), prep.get("queue_pairs")
    disc = [g for g in gen if g["discarded_seq"]]
    first_after = None
    if ups:
        aft = [s for s in sent if s["eye"] == "left" and int(s["t_sent_mono_ns"]) >= ups[0]["t_mono_ns"] - 1_000_000_000
               and int(s["t_utc_ns"]) >= stop]
        if aft:
            first_after = (int(aft[0]["t_sent_mono_ns"]) - int(aft[0]["t_host_mono_ns"])) / 1e6
    limit = (qcap + 1) * 1000 / fps + 50 if qcap else None
    C["P2_bounded_queue_no_stale_backlog"] = {
        "verdict": V(qmax is not None and qcap is not None and qmax <= qcap and first_after is not None
                     and first_after <= limit, tested=bool(ups)),
        "queue_bound_pairs": qcap, "queue_max_depth": qmax,
        "discarded_total": len(disc),
        "discarded_link_down": sum(1 for g in disc if g["discard_link_state"].startswith("down")),
        "discarded_link_up": sum(1 for g in disc if g["discard_link_state"] == "up"),
        "first_frame_sent_after_recovery_age_ms": round(first_after, 1) if first_after is not None else None,
        "limit_ms": limit}


def probe_trace(rx, ok_arr, send):
    """Raw (pre-parser) arrival of each left-eye frame against its parsed
    release. probe.csv rows are depacketised chunks in arrival order; a frame's
    chunks share one RTP PTS, and its group is identified by our SEI."""
    path = pathlib.Path(rx) / "probe.csv"
    if not path.exists():
        return {"available": False}
    rows = _csv(path)
    groups = {}
    for r in rows:
        groups.setdefault(r["pkt_pts"], []).append(r)
    raw_done, raw_first = {}, {}
    for pts, g in groups.items():
        seqs = [int(r["meta_seq"]) for r in g if r["meta_seq"]]
        if seqs:
            raw_first[seqs[0]] = min(int(r["t_arrival_mono_ns"]) for r in g)
            raw_done[seqs[0]] = max(int(r["t_arrival_mono_ns"]) for r in g)
    parsed = {int(a["seq"]): int(a["t_arrival_mono_ns"]) for a in ok_arr if a["eye"] == "left"}
    common = sorted(set(raw_done) & set(parsed))
    parser_hold = [(parsed[s] - raw_done[s]) / 1e6 for s in common]
    net = [(raw_done[s] - send[("left", s)]) / 1e6 for s in common if ("left", s) in send]
    return {"available": True, "probe_chunks": len(rows), "frames_traced": len(common),
            "send_to_raw_complete_ms": stats(net),
            "raw_complete_to_parsed_release_ms": stats(parser_hold)}


def resources_summary(ev):
    """Per-role CPU (% of one core, averaged between samples) and memory from
    resources.csv, if the orchestrator sampled them."""
    path = pathlib.Path(ev) / "resources.csv"
    if not path.exists():
        return None
    rows = _csv(path)
    out = {}
    for role in sorted({r["role"] for r in rows}):
        rr = [r for r in rows if r["role"] == role]
        by_pid = {}
        for r in rr:
            by_pid.setdefault(r["pid"], []).append(r)
        cpu = []
        for g in by_pid.values():
            for a, b in zip(g, g[1:]):
                dt = float(b["t_s"].replace(",", "")) - float(a["t_s"].replace(",", ""))
                if dt > 0:
                    cpu.append(100 * (float(b["cpu_total_s"].replace(",", "")) - float(a["cpu_total_s"].replace(",", ""))) / dt)
        ws = [float(r["working_set_mb"].replace(",", "")) for r in rr]
        pv = [float(r["private_mb"].replace(",", "")) for r in rr]
        out[role] = {"samples": len(rr), "pids": sorted(by_pid), "cpu_pct_one_core": stats(cpu),
                     "working_set_mb": stats(ws), "private_mb": stats(pv),
                     "private_mb_growth_first_to_last": round(pv[-1] - pv[0], 1) if pv else None}
    # which process each Python role sampled (launcher vs interpreter; runs after G1 only)
    pids = pathlib.Path(ev) / "pids.json"
    if pids.exists():
        for r in _json(pids):
            if r.get("role") in out:
                out[r["role"]]["sampled"] = r.get("sampled")
                out[r["role"]]["interpreter_exe"] = r.get("interpreter_exe")
    sysf = pathlib.Path(ev) / "system.csv"
    if sysf.exists():
        srows = _csv(sysf)
        busy = [float(r["cpu_busy_pct_all_cores"]) for r in srows if r["cpu_busy_pct_all_cores"]]
        ncpu = int(srows[0]["logical_cpus"]) if srows else None
        out["system"] = {"samples": len(srows), "logical_cpus": ncpu, "cpu_busy_pct_all_cores": stats(busy),
                         "mem_load_pct": stats([float(r["mem_load_pct"]) for r in srows]),
                         "mem_avail_mb": stats([float(r["mem_avail_mb"]) for r in srows])}
        if ncpu:
            for role, v in out.items():
                if role != "system" and v["cpu_pct_one_core"]:
                    v["cpu_pct_all_cores"] = {k: round(x / ncpu, 2) for k, x in v["cpu_pct_one_core"].items()
                                              if isinstance(x, (int, float)) and k != "n"}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--stream", nargs=2, action="append", required=True, metavar=("PUB", "RX"))
    ap.add_argument("--previous", nargs=3, metavar=("EVIDENCE", "PUB", "RX"))
    ap.add_argument("--s7b-v3", action="store_true",
                    help="also report S7b v3 (6 Nov 2026; post-hoc). It then counts towards OVERALL like every other key")
    a = ap.parse_args(argv)
    G, mtx = global_criteria(a.evidence, a.stream)
    rpath = pathlib.Path(a.evidence) / "restart.json"
    restart = _json(rpath) if rpath.exists() else None
    rep = {"global": G, "restart": restart, "resources": resources_summary(a.evidence), "streams": {}}
    for pub, rx in a.stream:
        C, M = stream_analysis(pub, rx, mtx, restart, s7b_v3=a.s7b_v3)
        rep["streams"]["{}:{}".format(M["camera"], pathlib.Path(rx).name)] = {"criteria": C, "measurements": M}
    if a.previous:
        pev, ppub, prx = a.previous
        C, M = stream_analysis(ppub, prx, mediamtx_text(pev))
        rep["previous"] = {"criteria": C, "measurements": M, "evidence": pev}
    # F3b (live persistent-delay scenario) is a declared, out-of-scope NOT_TESTED
    # item; it is reported but does not make this run INCOMPLETE.
    vs = [c["verdict"] for c in G.values()] + [c["verdict"] for s in rep["streams"].values()
                                               for k, c in s["criteria"].items() if k != "F3b_persistent_delay_live"]
    rep["overall"] = "FAIL" if "FAIL" in vs else ("INCOMPLETE" if "NOT_TESTED" in vs else "PASS")
    out = pathlib.Path(a.evidence) / "smoke_report.json"
    out.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    for k, v in G.items():
        print("{:44s} {}".format(k, v["verdict"]))
    for name, s in list(rep["streams"].items()) + ([("PREVIOUS " + rep["previous"]["evidence"], rep["previous"])]
                                                    if "previous" in rep else []):
        print("--", name, "frame_end={} freshness={}".format(s["measurements"]["frame_end"],
                                                            s["measurements"]["freshness"]))
        for k, v in s["criteria"].items():
            print("   {:41s} {}".format(k, v["verdict"]))
    print("OVERALL (this run): {}  ({})".format(rep["overall"], out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

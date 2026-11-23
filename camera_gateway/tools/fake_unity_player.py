"""FAKE stand-in for the Unity Phase2M1 player, for OFFLINE Stage 2 dry runs only.

The real player must not be launched during preparation. This process takes the
same command line (-m1Out, -m1Seconds, -m1Label, -m1Source, ...), "starts up" for
--fake-startup-s, runs for -m1Seconds, then writes a run folder in the player's
schema (unity_rx_<stamp>_win64player_A_<label>/: arrivals.csv, frames.csv,
events.jsonl, summary.json) generated from the gateway's sent.csv, i.e. what an
ideal receiver on the same host would have seen: arrival = send + 2.5 ms, decode
+ 1.6 ms, a 60 Hz display tick choosing the newest complete pair, freezes after
125 ms without a new pair. No video is decoded; there is no ops.csv, so the
oracle replay is NOT_TESTED on fake runs.

Faults (--fake-fault): hang (never exits), crash (exit 3 after start-up, no
outputs), stale (an already-shown older pair is displayed again at the end),
meta (one arrival's capture time differs from what the gateway sent).
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import sys
import time

TICK_NS = 16_666_667
FREEZE_NS = 125_000_000
FRAME_COLS = ["t_display_utc_ns", "t_display_mono_ns", "seq", "age_utc_ms_left", "age_utc_ms_right", "age_mono_ms",
              "arrival_skew_ms", "interval_ms", "skipped_superseded", "skipped_incomplete", "skipped_missing",
              "skipped_rejected", "burst", "barcode_ok", "eye_ok", "freshness", "delay_ms", "excess_ms", "ref_delay_ms",
              "abs_age_ms", "clock_trusted", "rel_status", "baseline_shift_ms", "pairs_since_reset", "abs_age_lo_ms",
              "abs_age_hi_ms", "abs_uncertainty_ms", "clock_source", "abs_status"]
ARR_COLS = ["eye", "sei", "seq", "camera", "meta_eye", "t_dev_ns", "t_host_mono_ns", "t_utc_ns", "flags", "host", "session",
            "trial", "config_id", "t_arrival_utc_ns", "t_arrival_mono_ns", "t_decoded_mono_ns", "pkt_pts", "pkt_time_base",
            "keyframe", "bytes", "barcode_seq", "barcode_eye", "barcode_camera", "aud", "eof_seq"]


def read_sent(path):
    rows = []
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                try:
                    rows.append({k: (int(r[k]) if k not in ("eye", "capture_to_send_ms") else r[k]) for k in
                                 ("eye", "seq", "segment", "t_dev_ns", "t_host_mono_ns", "t_utc_ns", "flags", "keyframe",
                                  "bytes", "t_sent_mono_ns")})
                except (ValueError, KeyError, TypeError):
                    pass                                   # a partially written last line
    except FileNotFoundError:
        pass
    return rows


def generate(sent, t_lo, t_hi, utc_minus_mono, host="", fault="none"):
    """Unity-schema records for a receiver connected over [t_lo, t_hi] (host monotonic ns)."""
    arr = []
    for r in sent:
        if not t_lo <= r["t_sent_mono_ns"] <= t_hi:
            continue
        ta = r["t_sent_mono_ns"] + 2_500_000
        arr.append({"eye": r["eye"], "sei": "ok", "seq": r["seq"], "camera": "A", "meta_eye": r["eye"], "t_dev_ns": r["t_dev_ns"],
                    "t_host_mono_ns": r["t_host_mono_ns"], "t_utc_ns": r["t_utc_ns"], "flags": r["flags"], "host": host,
                    "session": "camgw", "trial": "stage2", "config_id": 6001, "t_arrival_utc_ns": ta + utc_minus_mono,
                    "t_arrival_mono_ns": ta, "t_decoded_mono_ns": ta + 1_600_000, "pkt_pts": "", "pkt_time_base": "1/90000",
                    "keyframe": r["keyframe"], "bytes": r["bytes"], "barcode_seq": "", "barcode_eye": "", "barcode_camera": "",
                    "aud": 1, "eof_seq": ""})
    arr.sort(key=lambda a: a["t_arrival_mono_ns"])
    if fault == "meta" and len(arr) > 10:
        arr[10] = dict(arr[10], t_host_mono_ns=arr[10]["t_host_mono_ns"] + 1_000_000)
    by = {}
    for a in arr:
        by.setdefault(a["seq"], {})[a["eye"]] = a
    complete = sorted((max(v["left"]["t_decoded_mono_ns"], v["right"]["t_decoded_mono_ns"]), s, v)
                      for s, v in by.items() if "left" in v and "right" in v)
    frames, events, last_seq, last_t, i = [], [], None, None, 0
    in_freeze, n_freeze = False, 0
    t = t_lo
    while t <= t_hi:
        newest = None
        while i < len(complete) and complete[i][0] <= t:
            newest = complete[i]
            i += 1
        if newest is not None and (last_seq is None or newest[1] > last_seq):
            tc, s, v = newest
            l, r = v["left"], v["right"]
            skipped = 0 if last_seq is None else max(0, s - last_seq - 1)
            if in_freeze:
                events.append(("freeze_end", t, {"camera": "A", "duration_ms": round((t - last_t) / 1e6, 1), "resumed_seq": s,
                                                 "last_seq": last_seq, "skipped": skipped}))
                in_freeze = False
            age_mono = (t - min(l["t_host_mono_ns"], r["t_host_mono_ns"])) / 1e6
            frames.append({"t_display_utc_ns": t + utc_minus_mono, "t_display_mono_ns": t, "seq": s,
                           "age_utc_ms_left": round((t + utc_minus_mono - l["t_utc_ns"]) / 1e6, 2),
                           "age_utc_ms_right": round((t + utc_minus_mono - r["t_utc_ns"]) / 1e6, 2),
                           "age_mono_ms": round(age_mono, 2),
                           "arrival_skew_ms": round((r["t_arrival_mono_ns"] - l["t_arrival_mono_ns"]) / 1e6, 2),
                           "interval_ms": "" if last_t is None else round((t - last_t) / 1e6, 2),
                           "skipped_superseded": 0, "skipped_incomplete": 0, "skipped_missing": skipped, "skipped_rejected": 0,
                           "burst": 0, "barcode_ok": "na", "eye_ok": 1, "freshness": "fresh",
                           "delay_ms": round((tc - min(l["t_host_mono_ns"], r["t_host_mono_ns"])) / 1e6, 2), "excess_ms": 0,
                           "ref_delay_ms": "", "abs_age_ms": round(age_mono, 2), "clock_trusted": 1, "rel_status": "ok",
                           "baseline_shift_ms": 0, "pairs_since_reset": len(frames) + 1, "abs_age_lo_ms": round(age_mono - 1, 2),
                           "abs_age_hi_ms": round(age_mono + 1, 2), "abs_uncertainty_ms": 1, "clock_source": "same_host_monotonic",
                           "abs_status": "within"})
            last_seq, last_t = s, t
        elif last_t is not None and not in_freeze and t - last_t > FREEZE_NS:
            in_freeze, n_freeze = True, n_freeze + 1
            events.append(("freeze_start", t, {"camera": "A", "last_seq": last_seq, "since_last_new_ms": round((t - last_t) / 1e6, 1),
                                               "threshold_ms": 125.0}))
        t += TICK_NS
    if fault == "stale" and len(frames) > 30:
        old = dict(frames[5])
        old["t_display_mono_ns"] = frames[-1]["t_display_mono_ns"] + TICK_NS
        old["t_display_utc_ns"] = old["t_display_mono_ns"] + utc_minus_mono
        frames.append(old)
    first = {}
    for a in arr:
        first.setdefault(a["eye"], a["t_arrival_mono_ns"])
    for eye, tm in first.items():
        events.append(("link_up", tm, {"eye": eye, "url": "rtsp://127.0.0.1:8554/camA_" + eye}))
    events.sort(key=lambda e: e[1])
    counts = {"displayed": len(frames), "superseded": 0, "incomplete": 0, "missing": sum(int(f["skipped_missing"]) for f in frames),
              "late_discarded": 0, "obsolete_discarded": 0, "integrity_errors": 0, "barcode_fail": 0, "eye_mismatch": 0,
              "camera_mismatch": 0, "freezes": n_freeze, "burst_displayed": 0, "rejected_excess_delay": 0, "rejected_absolute_age": 0,
              "rejected_obsolete": 0, "fresh_displayed": len(frames), "unverified_displayed": 0, "late_displayed": 0,
              "fresh_relative_displayed": 0, "relative_adapted_displayed": 0, "rebaselines": 0, "freshness_resets": len(first),
              "skipped_rejected": 0, "source_mismatch": 0}
    return arr, frames, events, counts


def main(argv=None):
    ap = argparse.ArgumentParser()
    for a in ("-m1Mode", "-m1Server", "-m1Source", "-m1Label", "-m1Out", "-logFile", "-screen-fullscreen", "-screen-width",
              "-screen-height", "-m1SaveEvery"):
        ap.add_argument(a)
    ap.add_argument("-m1Seconds", type=float, default=60)
    ap.add_argument("-m1Quit", action="store_true")
    ap.add_argument("--fake-gateway-dir", required=True)
    ap.add_argument("--fake-startup-s", type=float, default=3.0)
    ap.add_argument("--fake-fault", choices=("none", "hang", "crash", "stale", "meta"), default="none")
    a = ap.parse_args(argv)
    time.sleep(a.fake_startup_s)
    if a.fake_fault == "crash":
        return 3
    t_lo = time.monotonic_ns()
    utc_minus_mono = time.time_ns() - time.monotonic_ns()
    out = pathlib.Path(a.m1Out) / "unity_rx_{}_win64player_A_{}".format(dt.datetime.now().strftime("%Y%m%d_%H%M%S"), a.m1Label)
    out.mkdir(parents=True)
    t_end = t_lo + int(a.m1Seconds * 1e9)
    while time.monotonic_ns() < t_end or a.fake_fault == "hang":
        time.sleep(0.2)
    sent = read_sent(pathlib.Path(a.fake_gateway_dir) / "sent.csv")
    arr, frames, events, counts = generate(sent, t_lo, t_end, utc_minus_mono, fault=a.fake_fault)
    with open(out / "arrivals.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ARR_COLS)
        w.writeheader()
        w.writerows(arr)
    with open(out / "frames.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FRAME_COLS)
        w.writeheader()
        w.writerows(frames)
    with open(out / "events.jsonl", "w", encoding="utf-8") as fh:
        for typ, tm, p in [("run_start", t_lo, {"receiver": "FAKE Unity stand-in", "mode": "rtsp", "source": a.m1Source})] + events + \
                          [("run_end", t_end, {"stop_reason": "max_seconds"})]:
            fh.write(json.dumps({"type": typ, "t_mono_ns": tm, "t_utc_ns": tm + utc_minus_mono, "payload": p}) + "\n")
    readers = {e: {"packets": sum(1 for x in arr if x["eye"] == e), "frames": sum(1 for x in arr if x["eye"] == e), "no_sei": 0,
                   "sei_errors": 0, "decode_errors": 0, "decode_errors_before_sync": 0, "non_vcl_packets": 0, "connects": 1,
                   "link_downs": 0, "bytes": 0} for e in ("left", "right")}
    summary = {"camera": "A", "label": a.m1Label, "seconds": a.m1Seconds, "stop_reason": "max_seconds", "fake": True,
               "presenter": {"counts": counts, "integrity_checks": {"barcode": "not applicable (real-camera imagery)"},
                             "freshness_policy": {"enabled": True}},
               "readers": readers,
               "unity": {"mode": a.m1Mode, "source": a.m1Source, "backend_threads_joined": True, "display_image_missing": 0,
                         "log_lines_dropped": 0, "render_check": {"pass": True, "crop": [39, 6, 1238, 770], "max_abs_diff": 0},
                         "render_check_right": {"pass": True, "crop": [39, 6, 1238, 770], "max_abs_diff": 0},
                         "frame_time_ms": {"p99": 17.0},
                         "shutdown": {"readers_joined": True, "readers_joined_ms": 5.0}}}
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

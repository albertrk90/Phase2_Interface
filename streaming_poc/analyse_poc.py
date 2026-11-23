"""Gate G1 verdict for one Task 04B run (offline; reads result folders only).

Combines a publisher folder (pub_*) and the matching receiver folder (rx_*)
for the same camera and checks the G1 criteria of the Task 04A audit, section 7:

  G1.1 pairing      no integrity error (unequal pair, wrong eye/camera,
                    barcode != SEI) in any displayed pair
  G1.2 duration     run >= --min-seconds (default 600) with no decoder error
                    after the first keyframe
  G1.3 frame age    median <= 60 ms and p95 <= 100 ms (UTC capture -> display),
                    outside the injected-fault windows
  G1.4 stale frames after each injected stall, displayed age is back within
                    baseline + 20 ms within <= 2 displayed frames, and at most
                    2 burst-held frames are ever displayed
  G1.5 logging      every injected stall produces a receiver freeze event, and
                    the receiver's count of missing sequence numbers equals the
                    publisher's count of frames it never sent
  G1.6 reconnect    after a server restart, display resumes within <= 3 s of
                    the publisher reconnecting
  G1.7 metadata     no SEI CRC failure and no packet without SEI after sync

A criterion with nothing to test (e.g. no restart was done) is NOT_TESTED,
never PASS. Writes g1_report.json beside the receiver folder's files.

    .venv\\Scripts\\python.exe analyse_poc.py --pub results\\pub_..._A_run --rx results\\rx_..._A_run
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

import poc_common as pc

FAULT_GUARD_S = 1.0          # excluded from G1.3 after each injected fault
RECOVERY_TOL_MS = 20.0


def load_frames(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ("t_display_utc_ns", "t_display_mono_ns", "seq", "skipped_superseded",
                  "skipped_incomplete", "skipped_missing", "burst", "barcode_ok", "eye_ok"):
            r[k] = int(r[k])
        for k in ("age_utc_ms_left", "age_utc_ms_right", "age_mono_ms"):
            r[k] = float(r[k])
        r["age"] = max(r["age_utc_ms_left"], r["age_utc_ms_right"])
    return rows


def verdict(ok, tested=True):
    return "NOT_TESTED" if not tested else ("PASS" if ok else "FAIL")


def analyse(pub_dir, rx_dir, min_seconds=600.0):
    pub_dir, rx_dir = pathlib.Path(pub_dir), pathlib.Path(rx_dir)
    pev = pc.read_events(pub_dir / "events.jsonl")
    rev = pc.read_events(rx_dir / "events.jsonl")
    frames = load_frames(rx_dir / "frames.csv")
    rx_sum = json.loads((rx_dir / "summary.json").read_text(encoding="utf-8"))
    pub_rep = json.loads((pub_dir / "report.json").read_text(encoding="utf-8"))
    out = {"pub": str(pub_dir), "rx": str(rx_dir), "criteria": {}}
    crit = out["criteria"]

    pres = rx_sum["presenter"]["counts"]
    readers = rx_sum["readers"]

    # fault windows (UTC ns): injected stalls/drops and link loss on either side
    windows = []
    stalls = []
    starts = {}
    for e in pev:
        if e["type"] == "stall_start":
            starts[e["payload"]["index"]] = e
        elif e["type"] == "stall_end":
            s = starts.get(e["payload"]["index"])
            if s:
                stalls.append({"start": s["t_utc_ns"], "end": e["t_utc_ns"], **e["payload"]})
                windows.append((s["t_utc_ns"], e["t_utc_ns"] + int(FAULT_GUARD_S * 1e9)))
        elif e["type"] in ("drop_start", "link_down", "link_up"):
            windows.append((e["t_utc_ns"], e["t_utc_ns"] + int(3 * FAULT_GUARD_S * 1e9)))
    for e in rev:
        if e["type"] in ("link_down",):
            windows.append((e["t_utc_ns"], e["t_utc_ns"] + int(3 * FAULT_GUARD_S * 1e9)))

    def in_window(t):
        return any(a <= t <= b for a, b in windows)

    clean = [r["age"] for r in frames if not in_window(r["t_display_utc_ns"])]
    allages = [r["age"] for r in frames]
    med, p95 = pc.percentile(clean, 50), pc.percentile(clean, 95)
    out["age_ms"] = {"clean_median": med, "clean_p95": p95, "clean_n": len(clean),
                     "all_median": pc.percentile(allages, 50), "all_p95": pc.percentile(allages, 95),
                     "all_max": max(allages) if allages else None}

    # G1.1
    crit["G1.1_pairing"] = {"verdict": verdict(pres["integrity_errors"] == 0 and pres["displayed"] > 0,
                                               tested=pres["displayed"] > 0),
                            "displayed": pres["displayed"], "integrity_errors": pres["integrity_errors"]}
    # G1.2
    dec_err = sum(r["decode_errors"] for r in readers.values())
    # measured run time; "seconds" is only a cap when the receiver stops on
    # the publisher's done flag (receivers since smoke test 3)
    dur = rx_sum.get("elapsed_s", rx_sum["seconds"])
    crit["G1.2_duration_decoder"] = {"verdict": verdict(dur >= min_seconds and dec_err == 0),
                                     "seconds": dur, "min_seconds": min_seconds,
                                     "decode_errors_after_sync": dec_err}
    # G1.3
    crit["G1.3_frame_age"] = {"verdict": verdict(med is not None and med <= 60 and p95 <= 100,
                                                 tested=bool(clean)),
                              "median_ms": med, "p95_ms": p95}
    # G1.4
    rec = []
    for s in stalls:
        after = [r for r in frames if r["t_display_utc_ns"] > s["end"]]
        n = None
        for i, r in enumerate(after):
            if med is not None and r["age"] <= med + RECOVERY_TOL_MS:
                n = i
                break
        rec.append({"index": s["index"], "mode": s["mode"], "count": s["count"],
                    "frames_to_recover": n})
    burst_shown = pres["burst_displayed"]
    ok4 = all(x["frames_to_recover"] is not None and x["frames_to_recover"] <= 2 for x in rec) \
        and burst_shown <= 2
    crit["G1.4_stale_frames"] = {"verdict": verdict(ok4, tested=bool(rec)), "stalls": rec,
                                 "burst_frames_displayed": burst_shown}
    # G1.5
    freezes = [e for e in rev if e["type"] == "freeze_start"]
    matched = []
    for s in stalls:
        hit = any(s["start"] - int(2e8) <= f["t_utc_ns"] <= s["end"] + int(5e8) for f in freezes)
        matched.append({"index": s["index"], "freeze_logged": hit})
    if frames:
        lo, hi = frames[0]["seq"], frames[-1]["seq"]
        unsent = set()
        for e in pev:
            p = e["payload"]
            if e["type"] == "stall_end" and p.get("mode") == "drop":
                unsent.update(range(p["seq_first"], p["seq_last"] + 1))
            elif e["type"] == "drop_start":
                unsent.update(range(p["seq_first"], p["seq_first"] + p["count"]))
        expected_missing = len([s for s in unsent if lo < s < hi])
    else:
        expected_missing = None
    link_down_unsent = pub_rep["counts"].get("unsent_link_down", 0)
    rx_missing = pres["missing"]
    exact = expected_missing is not None and (
        rx_missing == expected_missing if link_down_unsent == 0 else rx_missing >= expected_missing)
    crit["G1.5_logging"] = {"verdict": verdict(all(m["freeze_logged"] for m in matched) and exact,
                                               tested=bool(stalls) or bool(unsent if frames else False)),
                            "stalls": matched, "rx_missing": rx_missing,
                            "publisher_unsent_injected": expected_missing,
                            "publisher_unsent_link_down": link_down_unsent,
                            "note": ("exact match required" if link_down_unsent == 0 else
                                     "link-down losses present: receiver count must be >= injected")}
    # G1.6
    ups = [e for e in pev if e["type"] == "link_up"][1:]      # first is the initial connect
    res = []
    for u in ups:
        nxt = next((r for r in frames if r["t_display_utc_ns"] >= u["t_utc_ns"]), None)
        res.append({"publisher_link_up": u["t_utc"],
                    "resume_s": None if nxt is None else (nxt["t_display_utc_ns"] - u["t_utc_ns"]) / 1e9})
    crit["G1.6_reconnect"] = {"verdict": verdict(all(x["resume_s"] is not None and x["resume_s"] <= 3.0
                                                     for x in res), tested=bool(res)),
                              "restarts": res}
    # G1.7
    sei_err = sum(r["sei_errors"] for r in readers.values())
    no_sei = sum(r["no_sei"] for r in readers.values())
    crit["G1.7_metadata"] = {"verdict": verdict(sei_err == 0 and no_sei == 0,
                                                tested=sum(r["packets"] for r in readers.values()) > 0),
                             "sei_errors": sei_err, "packets_without_sei": no_sei}

    vs = [c["verdict"] for c in crit.values()]
    out["overall"] = "FAIL" if "FAIL" in vs else ("INCOMPLETE" if "NOT_TESTED" in vs else "PASS")
    out["publisher_baseline_profile"] = pub_rep.get("baseline")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pub", required=True)
    ap.add_argument("--rx", required=True)
    ap.add_argument("--min-seconds", type=float, default=600.0)
    args = ap.parse_args(argv)
    rep = analyse(args.pub, args.rx, args.min_seconds)
    path = pathlib.Path(args.rx) / "g1_report.json"
    path.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    for k, v in rep["criteria"].items():
        print("{:24s} {}".format(k, v["verdict"]))
    print("OVERALL: {}  ({})".format(rep["overall"], path))
    return 0 if rep["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

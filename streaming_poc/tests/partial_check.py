"""Offline: summary of a run that ended abnormally (no report.json / summary.json).
Reads only the per-frame files that were flushed before the processes stopped."""
import csv
import json
import statistics as st
import sys


def q(v):
    v = sorted(v)
    return "n={} median={:.1f} p95={:.1f} max={:.1f}".format(len(v), st.median(v), v[int(0.95 * (len(v) - 1))], v[-1]) if v else "n=0"


for pub, rx in zip(sys.argv[1::2], sys.argv[2::2]):
    sent = list(csv.DictReader(open(pub + r"\sent.csv", encoding="utf-8")))
    arr = [a for a in csv.DictReader(open(rx + r"\arrivals.csv", encoding="utf-8")) if a["sei"] == "ok"]
    fr = list(csv.DictReader(open(rx + r"\frames.csv", encoding="utf-8")))
    rev = [json.loads(l) for l in open(rx + r"\events.jsonl", encoding="utf-8") if l.strip()]
    pev = [json.loads(l) for l in open(pub + r"\events.jsonl", encoding="utf-8") if l.strip()]
    send = {(s["eye"], s["seq"]): int(s["t_sent_mono_ns"]) for s in sent}
    rel = [(int(a["t_arrival_mono_ns"]) - send[(a["eye"], a["seq"])]) / 1e6 for a in arr if (a["eye"], a["seq"]) in send]
    seqs = [int(f["seq"]) for f in fr]
    se = next((e for e in pev if e["type"] == "stall_end"), None)
    after = [f for f in fr if se and int(f["t_display_utc_ns"]) >= se["t_utc_ns"]]
    rej = [e["payload"] for e in rev if e["type"] == "pair_rejected"]
    print(rx)
    print("  frames sent (both eyes):", len(sent), " decoded with SEI:", len(arr), " displayed pairs:", len(fr),
          " last displayed seq:", seqs[-1] if seqs else None)
    print("  send -> release ms:", q(rel))
    print("  abs age ms:", q([float(f["abs_age_ms"]) for f in fr if f["abs_age_ms"]]),
          "| excess ms:", q([float(f["excess_ms"]) for f in fr if f["excess_ms"]]))
    print("  labels:", {k: sum(1 for f in fr if f["freshness"] == k) for k in sorted({f["freshness"] for f in fr})},
          "abs_status:", {k: sum(1 for f in fr if f["abs_status"] == k) for k in sorted({f["abs_status"] for f in fr})})
    print("  display strictly increasing:", all(b > a for a, b in zip(seqs, seqs[1:])),
          " barcode/eye ok all:", all(f["barcode_ok"] == "1" and f["eye_ok"] == "1" for f in fr))
    if se:
        print("  stall held seq {}..{}; first display after stall: seq {} label {} excess {} abs {}; burst shown {}".format(
            se["payload"]["seq_first"], se["payload"]["seq_last"], after[0]["seq"] if after else None,
            after[0]["freshness"] if after else None, after[0]["excess_ms"] if after else None,
            after[0]["abs_age_ms"] if after else None, sum(1 for f in after[:20] if f["burst"] == "1")))
    print("  rejections:", len(rej), "reasons:", sorted({r for p in rej for r in p["reasons"]}),
          "seqs:", [p["seq"] for p in rej])
    print("  receiver link events:", [(e["type"], e["payload"].get("eye")) for e in rev if e["type"].startswith("link")])

"""Offline: trace given left-eye frames through send -> raw (pre-parser)
arrival -> parsed release, from sent.csv, probe.csv and arrivals.csv."""
import csv
import sys

pub, rx = sys.argv[1], sys.argv[2]
seqs = [int(s) for s in sys.argv[3:]]
sent = {int(r["seq"]): int(r["t_sent_mono_ns"]) for r in csv.DictReader(open(pub + r"\sent.csv", encoding="utf-8"))
        if r["eye"] == "left"}
arr = {int(a["seq"]): int(a["t_arrival_mono_ns"]) for a in csv.DictReader(open(rx + r"\arrivals.csv", encoding="utf-8"))
       if a["eye"] == "left" and a["sei"] == "ok"}
rows = list(csv.DictReader(open(rx + r"\probe.csv", encoding="utf-8")))
groups = {}
for r in rows:
    groups.setdefault(r["pkt_pts"], []).append(r)
raw = {}
for g in groups.values():
    ms = [int(r["meta_seq"]) for r in g if r["meta_seq"]]
    if ms:
        raw[ms[0]] = (min(int(r["t_arrival_mono_ns"]) for r in g), max(int(r["t_arrival_mono_ns"]) for r in g),
                      len(g), [r["nal_types"] for r in g][-1], any(r["eof_seq"] for r in g))
for s in seqs:
    if s not in sent:
        print(s, "not sent")
        continue
    t = sent[s]
    r = raw.get(s)
    print("seq {}: raw first +{:.1f} ms, raw complete +{:.1f} ms ({} chunks, last NALs [{}], EOF marker seen in group: {}), "
          "parsed release +{:.1f} ms; next frame sent +{:.1f} ms".format(
              s, (r[0] - t) / 1e6 if r else float("nan"), (r[1] - t) / 1e6 if r else float("nan"),
              r[2] if r else 0, r[3] if r else "", r[4] if r else None,
              (arr[s] - t) / 1e6 if s in arr else float("nan"),
              (sent[s + 1] - t) / 1e6 if s + 1 in sent else float("nan")))

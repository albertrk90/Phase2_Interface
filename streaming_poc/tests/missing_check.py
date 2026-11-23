"""Offline: which sent frames were never received, and when did the receiver stop?"""
import csv
import json
import sys

for pub, rx in zip(sys.argv[1::2], sys.argv[2::2]):
    sent = list(csv.DictReader(open(pub + r"\sent.csv", encoding="utf-8")))
    arr = [a for a in csv.DictReader(open(rx + r"\arrivals.csv", encoding="utf-8")) if a["sei"] == "ok"]
    ev = [json.loads(l) for l in open(rx + r"\events.jsonl", encoding="utf-8")]
    pev = [json.loads(l) for l in open(pub + r"\events.jsonl", encoding="utf-8")]
    rx_end = next(e for e in ev if e["type"] == "run_end")["t_mono_ns"]
    rx_start = next(e for e in ev if e["type"] == "run_start")["t_mono_ns"]
    first_up = next(e for e in ev if e["type"] == "link_up")["t_mono_ns"]
    pub_start = next(e for e in pev if e["type"] == "run_start")["t_mono_ns"]
    pub_end = next(e for e in pev if e["type"] == "run_end")["t_mono_ns"]
    first = min(int(a["seq"]) for a in arr)
    got = {int(a["seq"]) for a in arr if a["eye"] == "left"}
    miss = sorted(int(s["seq"]) for s in sent if s["eye"] == "left" and int(s["seq"]) >= first and int(s["seq"]) not in got)
    sent_after_rx_end = sorted(int(s["seq"]) for s in sent if s["eye"] == "left" and int(s["t_sent_mono_ns"]) > rx_end)
    contiguous_tail = bool(miss) and miss == list(range(miss[0], miss[-1] + 1)) and miss[-1] == max(int(s["seq"]) for s in sent)
    print(rx)
    print("  receiver started {:.1f} s before publisher; first link_up {:.1f} s after receiver start".format(
        (pub_start - rx_start) / 1e9, (first_up - rx_start) / 1e9))
    print("  receiver window ended {:.2f} s before publisher finished".format((pub_end - rx_end) / 1e9))
    print("  never received (from first rx seq {}): {} -> {}..{}; contiguous tail: {}".format(
        first, len(miss), miss[:1], miss[-1:], contiguous_tail))
    print("  frames sent after receiver stopped: {} ({}..{})".format(
        len(sent_after_rx_end), sent_after_rx_end[:1], sent_after_rx_end[-1:]))
    in_window = [s for s in miss if s not in sent_after_rx_end]
    print("  missing frames sent while the receiver was still running: {} {}".format(len(in_window), in_window[:10]))

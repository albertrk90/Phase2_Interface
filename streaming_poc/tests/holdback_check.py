"""Offline: is each frame released only when the next one is sent? (reads smoke results only)"""
import csv
import statistics as st
import sys

pub, rx = sys.argv[1], sys.argv[2]
sent = {(r["eye"], int(r["seq"])): r for r in csv.DictReader(open(pub + r"\sent.csv"))}
arr = [r for r in csv.DictReader(open(rx + r"\arrivals.csv")) if r["sei"] == "ok"]
own, nxt, dec = [], [], []
for a in arr:
    e, s = a["eye"], int(a["seq"])
    t_arr = int(a["t_arrival_mono_ns"])
    if (e, s) in sent:
        own.append((t_arr - int(sent[(e, s)]["t_sent_mono_ns"])) / 1e6)
    if (e, s + 1) in sent:
        nxt.append((t_arr - int(sent[(e, s + 1)]["t_sent_mono_ns"])) / 1e6)
    dec.append((int(a["t_decoded_mono_ns"]) - t_arr) / 1e6)


def q(v):
    v = sorted(v)
    return "n={} min={:.1f} median={:.1f} p95={:.1f} max={:.1f}".format(
        len(v), v[0], st.median(v), v[int(0.95 * (len(v) - 1))], v[-1])


print("arrival - own send-complete   (ms):", q(own))
print("arrival - NEXT frame send     (ms):", q(nxt))
print("decode time after arrival     (ms):", q(dec))
send_cost = [(int(r["t_sent_mono_ns"]) - int(r["t_host_mono_ns"])) / 1e6 for r in sent.values()]
print("capture -> send-complete      (ms):", q(send_cost))
for s in (598, 599, 600, 613, 614):
    a = next((x for x in arr if x["eye"] == "left" and int(x["seq"]) == s), None)
    sr = sent.get(("left", s))
    if a and sr:
        print("left seq {}: sent +{:.0f} ms, arrived +{:.0f} ms (rel. to seq 598 send)".format(
            s, (int(sr["t_sent_mono_ns"]) - int(sent[("left", 598)]["t_sent_mono_ns"])) / 1e6,
            (int(a["t_arrival_mono_ns"]) - int(sent[("left", 598)]["t_sent_mono_ns"])) / 1e6))

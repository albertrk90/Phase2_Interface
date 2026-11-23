"""Offline: are queue discards while the link is up explained by slow sends?

For each publisher: the sender's write time per frame (t_sent of the left eye
minus that of the previous frame's right eye is not available directly, so the
gap between consecutive sends is used), and whether each 'up' queue discard
falls within 1 s after a frame whose receiver release was > 100 ms late."""
import csv
import sys

for pub, rx in zip(sys.argv[1::2], sys.argv[2::2]):
    sent = list(csv.DictReader(open(pub + r"\sent.csv", encoding="utf-8")))
    gen = list(csv.DictReader(open(pub + r"\generated.csv", encoding="utf-8")))
    send = {(r["eye"], r["seq"]): int(r["t_sent_mono_ns"]) for r in sent}
    slow = sorted(send[(a["eye"], a["seq"])] for a in csv.DictReader(open(rx + r"\arrivals.csv", encoding="utf-8"))
                  if a["sei"] == "ok" and (a["eye"], a["seq"]) in send
                  and int(a["t_arrival_mono_ns"]) - send[(a["eye"], a["seq"])] > 100e6)
    ups = [int(g["t_mono_ns"]) for g in gen if g["discard_link_state"] == "up"]
    t_suspend = int(gen[12312]["t_mono_ns"]) if len(gen) > 12312 else 1 << 62
    ups = [t for t in ups if t < t_suspend]
    near = sum(1 for t in ups if any(0 <= t - s <= 1_000_000_000 or 0 <= s - t <= 400_000_000 for s in slow))
    ts = sorted(int(r["t_sent_mono_ns"]) for r in sent if r["eye"] == "right")
    gaps = sorted((b - a) / 1e6 for a, b in zip(ts, ts[1:]))
    big = [g for g in gaps if g > 150]
    print(pub)
    print("  'up' discards before the suspend: {}; within 1 s after / 0.4 s before a >100 ms-late frame: {} ({:.0f} %)".format(
        len(ups), near, 100 * near / len(ups) if ups else 0))
    print("  frames released >100 ms late: {}; sender inter-send gaps > 150 ms: {} (max {:.0f} ms)".format(
        len(slow), len(big), max(gaps)))

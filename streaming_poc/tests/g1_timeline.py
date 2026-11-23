"""Offline: generation and sending timeline of a run, in 30 s bins.

For each publisher: frames generated per bin, how far generation lags its
schedule, queue discards (link up / down), frames sent; plus orchestrator
resource samples per bin. Reads result folders only.
"""
import csv
import json
import pathlib
import sys

ev = pathlib.Path(sys.argv[1])
pubs = [pathlib.Path(p) for p in sys.argv[2:]]
BIN = 30.0
for pub in pubs:
    gen = list(csv.DictReader(open(pub / "generated.csv", encoding="utf-8")))
    sent = [r for r in csv.DictReader(open(pub / "sent.csv", encoding="utf-8")) if r["eye"] == "left"]
    evs = [json.loads(l) for l in open(pub / "events.jsonl", encoding="utf-8")]
    t0 = int(gen[0]["t_mono_ns"]) - int(float(gen[0]["late_ms"]) * 1e6)
    end = (int(gen[-1]["t_mono_ns"]) - t0) / 1e9
    print("==", pub.name, "generation span {:.1f} s for {} frames ({:.2f} fps)".format(end, len(gen), len(gen) / end))
    nb = int(end // BIN) + 1
    rows = [{"gen": 0, "lag_max": 0.0, "disc_up": 0, "disc_down": 0, "sent": 0} for _ in range(nb)]
    for g in gen:
        b = int(((int(g["t_mono_ns"]) - t0) / 1e9) // BIN)
        rows[b]["gen"] += 1
        rows[b]["lag_max"] = max(rows[b]["lag_max"], float(g["late_ms"]))
        if g["discarded_seq"]:
            rows[b]["disc_up" if g["discard_link_state"] == "up" else "disc_down"] += 1
    for s in sent:
        b = int(((int(s["t_sent_mono_ns"]) - t0) / 1e9) // BIN)
        if b < nb:
            rows[b]["sent"] += 1
    print("  bin_s   generated  max_lag_ms  sent  discard_up  discard_down")
    for i, r in enumerate(rows):
        print("  {:5.0f}   {:9d}  {:10.0f}  {:4d}  {:10d}  {:12d}".format(i * BIN, r["gen"], r["lag_max"], r["sent"],
                                                                    r["disc_up"], r["disc_down"]))
    for e in evs:
        if e["type"] in ("link_up", "link_down", "link_connect_failed", "stall_start", "drop_start", "run_end"):
            print("  {:8.1f}s {}".format((e["t_mono_ns"] - t0) / 1e9, e["type"]))

res = ev / "resources.csv"
if res.exists():
    rows = list(csv.DictReader(open(res, encoding="utf-8")))
    print("== resources.csv: {} samples, t {}..{} s".format(len(rows), rows[0]["t_s"], rows[-1]["t_s"]))
    by = {}
    for r in rows:
        by.setdefault((r["role"], r["pid"]), []).append(r)
    for (role, pid), g in sorted(by.items()):
        prev = None
        line = []
        for r in g:
            t, c = float(r["t_s"]), float(r["cpu_total_s"])
            if prev and int(t // 60) != int(prev[0] // 60):
                line.append("{:.0f}s:{:.0f}%".format(t, 100 * (c - prev[1]) / (t - prev[0])))
            prev = (t, c) if prev is None or int(t // 60) != int(prev[0] // 60) else prev
        print("  {:9s} pid {:6s} samples {:4d} ws {}..{} MB  cpu% per minute: {}".format(
            role, pid, len(g), g[0]["working_set_mb"], g[-1]["working_set_mb"], " ".join(line[:25])))

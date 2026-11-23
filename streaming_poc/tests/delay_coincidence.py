"""Offline diagnostic for the ~300 ms localhost transport delays in the G1 run.

Read-only over existing evidence. For each publish connection (camera x eye),
a frame is "delayed" when its first arrival at the reference receiver is more
than 100 ms after the publisher's write returned. Delayed frames are grouped
into episodes, and episodes are compared ACROSS connections: one MediaMTX
process serves all four publish connections, so a server-wide pause (or a
host-wide scheduling stall) should hit them together, whereas a per-connection
TCP event (e.g. a retransmission timeout) should not.

Run: .venv\\Scripts\\python.exe -I tests\\delay_coincidence.py <pub_A> <rx_A> <pub_B> <rx_B> [valid_s]
"""
import csv
import pathlib
import statistics
import sys

FAULTS_S = [(119, 123), (239, 243), (359, 363), (479, 482), (539, 552)]   # injected faults +-margin


def load(pub, rx):
    sent, cap, size = {}, {}, {}
    for r in csv.DictReader(open(pathlib.Path(pub) / "sent.csv", encoding="utf-8")):
        k = (r["eye"], int(r["seq"]))
        sent[k], cap[k], size[k] = int(r["t_sent_mono_ns"]), int(r["t_host_mono_ns"]), int(r["bytes"])
        if int(r["flags"]) & 2:                                   # burst-held frames are late by design
            cap[k] = None
    arr, key = {}, {}
    for r in csv.DictReader(open(pathlib.Path(rx) / "arrivals.csv", encoding="utf-8")):
        if r["sei"] != "ok":
            continue
        k = (r["eye"], int(r["seq"]))
        if k not in arr:
            arr[k], key[k] = int(r["t_arrival_mono_ns"]), r["keyframe"] == "1"
    return sent, cap, size, arr, key


def main(argv):
    pubA, rxA, pubB, rxB = argv[:4]
    valid_s = float(argv[4]) if len(argv) > 4 else 610.0
    data = {"A": load(pubA, rxA), "B": load(pubB, rxB)}
    t0 = min(c for d in data.values() for c in d[1].values() if c)
    rel = lambda ns: (ns - t0) / 1e9  # noqa: E731
    out = []
    eps = {}            # (cam, eye) -> list of (start_sent_ns, end_arrival_ns, n, max_delay_ms)
    delayed_all, sizes_d, sizes_all, key_d, key_all = [], [], [], 0, 0
    for cam, (sent, cap, size, arr, key) in data.items():
        for eye in ("left", "right"):
            ks = sorted(k for k in sent if k[0] == eye and k in arr and cap[k] and rel(sent[k]) < valid_s
                        and not any(a <= rel(sent[k]) <= b for a, b in FAULTS_S))
            cur = None
            ep = []
            for k in ks:
                d = (arr[k] - sent[k]) / 1e6
                sizes_all.append(size[k])
                key_all += key[k]
                if d > 100:
                    delayed_all.append(d)
                    sizes_d.append(size[k])
                    key_d += key[k]
                    if cur and sent[k] - cur[1] < 1_000_000_000:
                        cur = [cur[0], max(cur[1], arr[k]), cur[2] + 1, max(cur[3], d)]
                        ep[-1] = cur
                    else:
                        cur = [sent[k], arr[k], 1, d]
                        ep.append(cur)
            eps[(cam, eye)] = ep
    conns = list(eps)
    span = valid_s - sum(b - a for a, b in FAULTS_S)
    out.append("valid window: t < {:.0f} s, injected-fault windows excluded ({:.0f} s analysed)".format(valid_s, span))
    out.append("delayed frame-eyes (>100 ms send->arrival): {}; delay median {:.0f} ms, min {:.0f}, max {:.0f}".format(
        len(delayed_all), statistics.median(delayed_all), min(delayed_all), max(delayed_all)))
    hist = {}
    for d in delayed_all:
        b = int(d // 25) * 25
        hist[b] = hist.get(b, 0) + 1
    out.append("delay histogram (25 ms bins): " + ", ".join("{}-{}: {}".format(b, b + 25, n) for b, n in sorted(hist.items())))
    out.append("delayed frames' size median {:.0f} B vs all {:.0f} B; keyframes {}/{} delayed vs {}/{} overall ({:.1f} % vs {:.1f} %)".format(
        statistics.median(sizes_d), statistics.median(sizes_all), key_d, len(sizes_d), key_all, len(sizes_all),
        100 * key_d / len(sizes_d), 100 * key_all / len(sizes_all)))
    for c in conns:
        e = eps[c]
        gaps = [(b[0] - a[0]) / 1e9 for a, b in zip(e, e[1:])]
        out.append("{} {}: {} episodes; frames per episode max {}; inter-episode gap median {:.1f} s (min {:.1f}, max {:.1f})".format(
            c[0], c[1], len(e), max(x[2] for x in e) if e else 0,
            statistics.median(gaps) if gaps else 0, min(gaps) if gaps else 0, max(gaps) if gaps else 0))
    # coincidence: an episode's delayed interval [first send, last arrival] overlapping
    # an episode of another connection
    out.append("")
    out.append("coincidence of episodes across connections (interval overlap, +-20 ms):")
    for i, a in enumerate(conns):
        for b in conns[i + 1:]:
            hits = sum(1 for x in eps[a] if any(x[0] - 20e6 <= y[1] and y[0] <= x[1] + 20e6 for y in eps[b]))
            busy_b = sum((y[1] - y[0]) / 1e9 + 0.04 for y in eps[b])
            chance = len(eps[a]) * min(1.0, busy_b / span)
            out.append("  {}-{} vs {}-{}: {}/{} overlap (chance expectation about {:.1f})".format(
                a[0], a[1], b[0], b[1], hits, len(eps[a]), chance))
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1:])

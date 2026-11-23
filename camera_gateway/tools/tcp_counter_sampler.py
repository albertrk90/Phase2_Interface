"""Read-only sampler of the Windows system-wide TCP counters (O1 diagnosis, approved 13 Nov 2026).

Reads iphlpapi GetTcpStatisticsEx for IPv4 and IPv6 every --interval-ms and writes one CSV row per
sample with the host monotonic time (time.monotonic_ns = QueryPerformanceCounter on this Python, the
same clock as the gateway and Unity logs). No admin rights, no installs, no socket of its own, no
network traffic, no setting changed.

WHAT THE COUNTERS ARE: system-wide totals per address family (all TCP connections on the host,
every interface), NOT per connection. A step in RetransSegs near a hold therefore SUPPORTS but does
not PROVE that the held camera connection retransmitted. Whether loopback connections are counted
is checked separately (tools/tcp_counter_loopback_check.py).

Stops on --stop-file, on --max-seconds (hard cap 900), or Ctrl+C; always writes <out>.summary.json.
"""
import argparse, csv, ctypes, ctypes.wintypes as w, json, os, statistics, sys, time

AF_INET, AF_INET6 = 2, 23
FIELDS = ("dwRtoAlgorithm", "dwRtoMin", "dwRtoMax", "dwMaxConn", "dwActiveOpens", "dwPassiveOpens", "dwAttemptFails",
          "dwEstabResets", "dwCurrEstab", "dwInSegs", "dwOutSegs", "dwRetransSegs", "dwInErrs", "dwOutRsts", "dwNumConns")


class MIB_TCPSTATS(ctypes.Structure):
    _fields_ = [(n, w.DWORD) for n in FIELDS]


_get = ctypes.windll.iphlpapi.GetTcpStatisticsEx


def read(family):
    s = MIB_TCPSTATS()
    rc = _get(ctypes.byref(s), family)
    if rc != 0:
        raise OSError("GetTcpStatisticsEx({}) returned {}".format(family, rc))
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="CSV path")
    ap.add_argument("--interval-ms", type=float, default=10.0)
    ap.add_argument("--stop-file", default=None)
    ap.add_argument("--max-seconds", type=float, default=600.0)
    a = ap.parse_args(argv)
    if not (1.0 <= a.interval_ms <= 1000.0):
        ap.error("--interval-ms must be 1-1000")
    if not (1.0 <= a.max_seconds <= 900.0):
        ap.error("--max-seconds must be 1-900")
    t_start = time.monotonic_ns(); cpu0 = time.process_time()
    first4, first6 = read(AF_INET), read(AF_INET6)
    period = int(a.interval_ms * 1e6); nxt = t_start
    n, costs, stamps, stop_reason = 0, [], [], "max_seconds"
    last = None; steps4 = 0; steps6 = 0
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["t_mono_ns", "call_us", "v4_retrans", "v4_out", "v4_in", "v4_estab", "v6_retrans", "v6_out", "v6_in", "v6_estab"])
        try:
            while True:
                t0 = time.monotonic_ns()
                s4 = read(AF_INET); s6 = read(AF_INET6)
                t1 = time.monotonic_ns()
                wr.writerow([t0, round((t1 - t0) / 1e3, 1), s4.dwRetransSegs, s4.dwOutSegs, s4.dwInSegs, s4.dwCurrEstab,
                             s6.dwRetransSegs, s6.dwOutSegs, s6.dwInSegs, s6.dwCurrEstab])
                if last is not None:
                    steps4 += s4.dwRetransSegs != last[0]; steps6 += s6.dwRetransSegs != last[1]
                last = (s4.dwRetransSegs, s6.dwRetransSegs)
                n += 1; costs.append((t1 - t0) / 1e3); stamps.append(t0)
                if n % 100 == 0:
                    fh.flush()
                    if a.stop_file and os.path.exists(a.stop_file):
                        stop_reason = "stop_file"; break
                if (t1 - t_start) / 1e9 >= a.max_seconds:
                    break
                nxt += period
                d = nxt - time.monotonic_ns()
                if d > 0:
                    time.sleep(d / 1e9)
                else:
                    nxt = time.monotonic_ns()      # fell behind: do not burst
        except KeyboardInterrupt:
            stop_reason = "interrupted"
    iv = [(b - a_) / 1e6 for a_, b in zip(stamps, stamps[1:])]
    s4e, s6e = read(AF_INET), read(AF_INET6)
    wall = (time.monotonic_ns() - t_start) / 1e9; cpu = time.process_time() - cpu0
    q = lambda v, p: sorted(v)[min(len(v) - 1, int(p * len(v)))]
    summ = {
        "tool": "tcp_counter_sampler.py", "out": os.path.abspath(a.out), "stop_reason": stop_reason,
        "scope": "system-wide totals per address family (all TCP connections, all interfaces); not per connection",
        "clock": "time.monotonic_ns ({})".format(time.get_clock_info("monotonic").implementation),
        "t_start_mono_ns": t_start, "wall_s": round(wall, 2), "samples": n,
        "requested_interval_ms": a.interval_ms,
        "actual_interval_ms": None if not iv else {"median": round(statistics.median(iv), 3), "p95": round(q(iv, .95), 3),
                                                   "p99": round(q(iv, .99), 3), "max": round(max(iv), 3), "min": round(min(iv), 3)},
        "call_cost_us": None if not costs else {"median": round(statistics.median(costs), 1), "p99": round(q(costs, .99), 1), "max": round(max(costs), 1)},
        "process_cpu_s": round(cpu, 3), "process_cpu_percent_of_one_core": round(100 * cpu / wall, 2) if wall else None,
        "v4": {"rto_algorithm": first4.dwRtoAlgorithm, "rto_min_reported": first4.dwRtoMin, "retrans_start": first4.dwRetransSegs,
               "retrans_end": s4e.dwRetransSegs, "out_start": first4.dwOutSegs, "out_end": s4e.dwOutSegs, "retrans_step_samples": steps4},
        "v6": {"retrans_start": first6.dwRetransSegs, "retrans_end": s6e.dwRetransSegs, "out_start": first6.dwOutSegs,
               "out_end": s6e.dwOutSegs, "retrans_step_samples": steps6},
    }
    with open(a.out + ".summary.json", "w", encoding="utf-8") as fh:
        json.dump(summ, fh, indent=1)
    print(json.dumps(summ))
    return 0


if __name__ == "__main__":
    sys.exit(main())

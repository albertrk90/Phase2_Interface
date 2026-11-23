"""O2 (camera shutdown anomaly): one timeline, on the host monotonic clock, of the gateway stop, the
post-run unicast reconnect, depthai's log lines, Camera A ICMP replies and TCP retransmission steps.
ICMP replies show only that the camera's network stack answers, not that its application is ready.
Usage: analyse_o2_shutdown.py <gateway_dir> <runner_dir> <diag_dir>"""
import csv, json, pathlib, re, sys, datetime as dt
gw, run, diag = (pathlib.Path(x) for x in sys.argv[1:4])
ev = [json.loads(l) for l in (gw / "events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
start = next(e for e in ev if e["type"] == "run_start")
utc_minus_mono = start["t_utc_ns"] - start["t_mono_ns"]
stop = next(e["t_mono_ns"] for e in ev if e["type"] in ("stop_file_seen", "duration_reached"))
end = [e for e in ev if e["type"] == "run_end"][-1]["t_mono_ns"]
rep = json.loads((gw / "report.json").read_text(encoding="utf-8-sig"))
rel = lambda t: round((t - stop) / 1e9, 2)
tl = [(stop, "gateway: stop file seen"), (end, "gateway: run_end (after post-run calibration read)")]
p = rep.get("calibration_post_run", {})
t_ok = end  # approximate: the read finished just before run_end
if p.get("waited_s") is not None:
    t_first = end - int((p["waited_s"] + 0.0) * 1e9)
    tl.append((t_first, "gateway: first unicast reconnect attempt starts (approx. = run_end - waited_s - read time)"))
    if p.get("connect_seconds"):
        tl.append((t_first + int((p["waited_s"] - p["connect_seconds"]) * 1e9), "gateway: final (successful) connect attempt starts (approx.)"))
# depthai log lines in the runner's captured gateway stdout
for line in (run / "gateway_stdout.txt").read_text(encoding="utf-8", errors="replace").splitlines():
    m = re.match(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\] \[depthai\] \[(\w+)\] (.*)", line)
    if m:
        t_local = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f")
        t_utc_ns = int(t_local.timestamp() * 1e9)
        tl.append((t_utc_ns - utc_minus_mono, "depthai {}: {}".format(m.group(2), m.group(3)[:60])))
    m = re.match(r"\[\w+\] \[[\d.]+\] \[([\d.]+)\] \[host\] \[(\w+)\] (.*)", line)
    if m:
        tl.append((int(float(m.group(1)) * 1e9) - utc_minus_mono, "depthai device {}: {}".format(m.group(2), m.group(3)[:60])))
# ping transitions
pings = [(int(r["t_send_mono_ns"]), r["reply"] == "1") for r in csv.DictReader(open(diag / "camera_ping.csv", encoding="utf-8"))]
prev = None
for t, ok in pings:
    if ok != prev:
        tl.append((t, "ping: {}".format("REPLY" if ok else "no reply"))); prev = ok
# retransmission steps after the stop
smp = [(int(r["t_mono_ns"]), int(r["v4_retrans"])) for r in csv.DictReader(open(diag / "tcp_counters.csv", encoding="utf-8"))]
for k in range(1, len(smp)):
    d = smp[k][1] - smp[k - 1][1]
    if d and smp[k][0] > stop:
        tl.append((smp[k][0], "tcp: RetransSegs +{}".format(d)))
tl.sort()
out = {"post_run": {k: p.get(k) for k in ("status", "connect_attempts", "waited_s", "connect_seconds", "last_connect_error")},
       "pings": len(pings), "replies": sum(ok for _, ok in pings),
       "first_reply_after_stop_s": next((rel(t) for t, ok in pings if ok), None),
       "timeline_s_after_stop": [(rel(t), what) for t, what in tl]}
print(json.dumps(out, indent=1))

"""O2 evidence (approved 13 Nov 2026): ICMP availability of Camera A during gateway shutdown.

Waits for the runner's GATEWAY_STOP file in a runner folder created after this script started, then
pings ONLY Camera A (169.254.1.222; any other address is refused) once per second with Windows ping.exe
until the runner records that it has finished (runner_status.json "finished") or --max-seconds.
Writes camera_ping.csv with host monotonic timestamps (same clock as the gateway logs).

Ping availability shows only that the camera's network stack answers. It does NOT show that the camera
application (bootloader / DepthAI firmware) is ready to accept a connection.
"""
import argparse, csv, json, os, pathlib, re, subprocess, sys, time

CAMERA_A = "169.254.1.222"


def ping_once(ip, timeout_ms):
    t0 = time.monotonic_ns()
    p = subprocess.run(["ping", "-4", "-n", "1", "-w", str(timeout_ms), ip], capture_output=True, text=True, timeout=timeout_ms / 1000 + 5)
    t1 = time.monotonic_ns()
    m = re.search(r"time[=<](\d+)ms.*TTL=(\d+)", p.stdout)
    reply = bool(m) and ("Reply from " + ip) in p.stdout
    return t0, t1, reply, (int(m.group(1)) if m else None), (int(m.group(2)) if m else None), p.returncode


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="camera_gateway/results")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ip", default=CAMERA_A)
    ap.add_argument("--wait-runner-s", type=float, default=600)
    ap.add_argument("--max-seconds", type=float, default=300)
    a = ap.parse_args(argv)
    if a.ip != CAMERA_A:
        ap.error("only Camera A ({}) may be pinged".format(CAMERA_A))
    res = pathlib.Path(a.results); t_start = time.time()
    before = {p.name for p in res.glob("stage2_runner_*")}
    runner = None; deadline = time.monotonic() + a.wait_runner_s
    while time.monotonic() < deadline:                       # wait for this run's folder and its stop file
        if runner is None:
            new = [p for p in res.glob("stage2_runner_*") if p.name not in before and p.stat().st_ctime >= t_start - 1]
            runner = sorted(new)[-1] if new else None
        if runner is not None and (runner / "GATEWAY_STOP").exists():
            break
        if runner is not None and (runner / "runner_status.json").exists():
            try:
                if json.loads((runner / "runner_status.json").read_text(encoding="utf-8-sig")).get("finished"):
                    break
            except Exception:                                 # noqa: BLE001  (being rewritten)
                pass
        time.sleep(0.2)
    stop_seen = time.monotonic_ns()
    meta = {"runner": str(runner) if runner else None, "stop_file_seen_mono_ns": stop_seen if runner and (runner / "GATEWAY_STOP").exists() else None,
            "ip": a.ip, "note": "ICMP only: availability of the network stack, not readiness of the camera application"}
    rows = []
    t_end = time.monotonic() + a.max_seconds
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh); wr.writerow(["t_send_mono_ns", "t_done_mono_ns", "reply", "rtt_ms", "ttl", "rc"])
        while runner is not None and time.monotonic() < t_end:
            t0, t1, ok, rtt, ttl, rc = ping_once(a.ip, 800)
            wr.writerow([t0, t1, int(ok), rtt, ttl, rc]); fh.flush(); rows.append((t0, ok))
            try:
                if json.loads((runner / "runner_status.json").read_text(encoding="utf-8-sig")).get("finished"):
                    break
            except Exception:                                 # noqa: BLE001
                pass
            time.sleep(max(0.0, 1.0 - (time.monotonic_ns() - t0) / 1e9))
    # transitions
    trans, prev = [], None
    for t, ok in rows:
        if ok != prev:
            trans.append({"t_mono_ns": t, "reply": ok}); prev = ok
    meta.update({"pings": len(rows), "replies": sum(ok for _, ok in rows), "transitions": trans})
    with open(a.out + ".summary.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    print(json.dumps(meta))
    return 0


if __name__ == "__main__":
    sys.exit(main())

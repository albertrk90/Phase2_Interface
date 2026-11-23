"""O1 ETW alignment marker (13 Nov 2026): one short 127.0.0.1 connection with recorded clocks, so the trace's own connection events
can be aligned with the gateway clock near the START and the END of a capture. Local only; ephemeral ports; nothing else.
Records time.monotonic_ns (QPC, the gateway/Unity clock) and time.time_ns (UTC) immediately before and after connect().
Usage: o1_etw_marker.py --label start|end --out marker_<label>.json"""
import argparse, json, socket, time
ap = argparse.ArgumentParser(); ap.add_argument("--label", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
ls = socket.socket(); ls.bind(("127.0.0.1", 0)); ls.listen(1)
b = {"mono_ns": time.monotonic_ns(), "utc_ns": time.time_ns()}
c = socket.create_connection(ls.getsockname()); s, _ = ls.accept()
e = {"mono_ns": time.monotonic_ns(), "utc_ns": time.time_ns()}
m = {"label": a.label, "before": b, "after": e, "client_port": c.getsockname()[1], "server_port": ls.getsockname()[1]}
c.close(); s.close(); ls.close()
json.dump(m, open(a.out, "w", encoding="utf-8"), indent=1)
print(json.dumps(m))

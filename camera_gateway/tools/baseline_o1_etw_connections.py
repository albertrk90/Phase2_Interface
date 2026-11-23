"""Clean-streaming baseline of the O1 ETW capture's port-8554 connections (13 Nov 2026). Observations only; nothing is interpreted.

Input : <extract dir> from extract_o1_etw.py (extract.jsonl.gz + connections.json), the analysis JSON (alignment + eye identity from
        mediamtx.log) and the gateway events.jsonl (for the gateway's own resync events in the same window).
Output: <out>/o1_baseline.json, per connection instance:
        - role/path (from the analysis' mediamtx.log identity; client port -> path), pid, lifetime (local time)
        - event counts by TCPIP / AFD event id (raw ids; no labels assigned beyond the field schema)
        - from 1332 (TcpDataTransferSend): send count, min RcvWnd / SndWnd, max in flight (SndMax - SndUna), max RTO
        - max gap between successive 1332 sends inside the steady window (first event + 1 s .. close - 1 s), and the number of gaps
          > 100 ms and > 250 ms (a hold of the O1 kind would show as a long send gap on the server->reader instance)
        - 1214 drop events on port 8554 counted by RAW Reason code (NOT interpreted; codes are undocumented)
Usage: baseline_o1_etw_connections.py --extract <dir> --analysis <o1_capture_analysis.json> --gw-events <events.jsonl> --out <dir>
"""
import argparse, collections, datetime, gzip, json, pathlib, sys

def loc(ns):
    return datetime.datetime.fromtimestamp(ns / 1e9).strftime("%H:%M:%S.%f")[:-3]

def num(v):
    try: return int(str(v).strip(), 0)
    except (TypeError, ValueError):
        try: return int(float(v))
        except (TypeError, ValueError): return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", required=True); ap.add_argument("--analysis", required=True)
    ap.add_argument("--gw-events", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ex = pathlib.Path(a.extract); out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    conns = json.load(open(ex / "connections.json", encoding="utf-8"))["relevant_or_marker"]
    an = json.load(open(a.analysis, encoding="utf-8"))
    ident = {c["client_port"]: (c["role"], c["path"]) for c in an["connections"]}
    port = lambda s: int(s.rsplit(":", 1)[1])
    inst = {}
    for c in conns:
        if c.get("marker"): continue
        lp, rp = port(c["local"]), port(c["remote"])
        cp = rp if lp == 8554 else lp
        role, path = ident.get(cp, ("unidentified", None))
        side = "server(MediaMTX) side" if lp == 8554 else "client side"
        inst[c["id"]] = {"id": c["id"], "local": c["local"], "remote": c["remote"], "pid": c["pid"], "role": role, "path": path, "side": side,
                         "first": loc(c["first_utc_ns"]), "close": loc(c["close_utc_ns"]) if c["close_utc_ns"] else None,
                         "_t0": c["first_utc_ns"], "_t1": c["close_utc_ns"] or c["last_utc_ns"],
                         "counts": collections.Counter(), "sends": 0, "min_rcvwnd": None, "min_sndwnd": None, "max_inflight": 0, "max_rto": None,
                         "_last_send": None, "max_send_gap_ms": 0.0, "max_send_gap_at": None, "gaps_gt_100ms": 0, "gaps_gt_250ms": 0}
    drops = collections.Counter()
    with gzip.open(ex / "extract.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line); d = r["d"]
            if r["p"] == "TCPIP" and r["id"] == "1214":
                drops[f"reason={d.get('Reason')}"] += num(d.get("PacketCount")) or 1
            s = inst.get(r["inst"])
            if s is None: continue
            s["counts"][f"{r['p']}:{r['id']}"] += 1
            if r["p"] == "TCPIP" and r["id"] == "1332":
                s["sends"] += 1
                for k, f in (("min_rcvwnd", "RcvWnd"), ("min_sndwnd", "SndWnd")):
                    v = num(d.get(f))
                    if v is not None and (s[k] is None or v < s[k]): s[k] = v
                una, mx, rto = num(d.get("SndUna")), num(d.get("SndMax")), num(d.get("RTO"))
                if una is not None and mx is not None: s["max_inflight"] = max(s["max_inflight"], (mx - una) & 0xFFFFFFFF)
                if rto is not None and (s["max_rto"] is None or rto > s["max_rto"]): s["max_rto"] = rto
                t = r["t"]
                if s["_t0"] + 1e9 <= t <= s["_t1"] - 1e9:
                    if s["_last_send"] is not None:
                        g = (t - s["_last_send"]) / 1e6
                        if g > s["max_send_gap_ms"]: s["max_send_gap_ms"], s["max_send_gap_at"] = round(g, 3), loc(s["_last_send"])
                        s["gaps_gt_100ms"] += g > 100; s["gaps_gt_250ms"] += g > 250
                    s["_last_send"] = t
    gw = [json.loads(l) for l in open(a.gw_events, encoding="utf-8") if l.strip()]
    gw_types = collections.Counter(e["type"] for e in gw)
    rows = []
    for s in inst.values():
        s["counts"] = dict(sorted(s["counts"].items()))
        rows.append({k: v for k, v in s.items() if not k.startswith("_")})
    res = {"note": "observations only; event ids are raw; drop Reason codes are NOT interpreted; steady window = first event + 1 s .. close - 1 s",
           "instances": sorted(rows, key=lambda r: (r["path"] or "", r["role"], r["side"])),
           "drops_port_8554_by_raw_reason": dict(drops), "gateway_event_types": dict(gw_types),
           "gateway_resync_events": [{"t": e["t_utc"], **e["payload"]} for e in gw if e["type"] in ("gop_resync", "write_stall", "hold")]}
    json.dump(res, open(out / "o1_baseline.json", "w", encoding="utf-8"), indent=1)
    for r in res["instances"]:
        print(f"{r['id']} {r['role']:9} {str(r['path']):10} {r['side']:22} pid {r['pid']}: sends {r['sends']}, max send gap {r['max_send_gap_ms']} ms "
              f"(>100 ms: {r['gaps_gt_100ms']}, >250 ms: {r['gaps_gt_250ms']}), min RcvWnd {r['min_rcvwnd']}, max in flight {r['max_inflight']}, "
              f"max RTO {r['max_rto']}, retrans-type ids {[k for k in r['counts'] if k.split(':')[1] in ('1186','1187','1351','1584','1102')]}")
    print("drops on 8554 by raw reason:", dict(drops)); print("gateway event types:", dict(gw_types))

if __name__ == "__main__":
    sys.exit(main())

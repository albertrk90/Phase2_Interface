"""Streaming extraction of the relevant connections from an O1 ETW capture (13 Nov 2026).

Input : tracerpt CSV of the raw .etl (tracerpt o1.etl -o decoded.csv -of CSV -y), the positional field schema
        tools/o1_etw_schema.json (field names per provider|event id|version, taken from the feasibility capture), the port(s) of
        interest (default 8554) and the alignment marker files (marker_start.json / marker_end.json).
Output: <out>/extract.jsonl.gz      every event of a RELEVANT connection instance (all its fields), drop events (1214) on the ports
                                    of interest (reason codes kept raw, NOT interpreted), Winsock-AFD events in the process context of
                                    the processes owning those connections, and the marker connections' events
        <out>/connections.json      connection instances (Tcb + local/remote address:port + pid + first/last/close time)
        <out>/extract_summary.json  row counts (total / kept / unrelated / unassigned / parse errors), unknown schema keys
Connection identity = Tcb + address pair + lifetime: an instance starts when a Tcb is first seen with an address pair (rundown,
connect, accept or send events carry addresses) and ends at its close events (1038 / 1043 / 1044 / 1039 / 1040); a Tcb seen later with
another address pair is a NEW instance (Tcb pointers are reused, as shown in the feasibility capture).
Time: the CSV "Clock-Time" column is a Windows FILETIME (100 ns since 1601, UTC) converted by ETW from the session's QPC clock; it is
converted to UTC ns here (t_utc_ns = (clock - 116444736000000000) * 100). Mapping to the gateway's monotonic clock is done in the
analysis from the markers. Unrelated rows are counted, never written.
Usage: extract_o1_etw.py <decoded.csv> --out <dir> [--ports 8554] [--markers m1.json m2.json] [--schema tools/o1_etw_schema.json]
"""
import argparse, csv, gzip, json, os, pathlib, re, sys

FILETIME_EPOCH = 116444736000000000
# tracerpt CSV names the Winsock-AFD provider by its display name; the XML (schema source) uses the provider name
PROVIDER_ALIAS = {"Microsoft-Windows-Winsock Network Event": "Microsoft-Windows-Winsock-AFD"}
CLOSE_IDS = {"1038", "1039", "1040", "1043", "1044"}
ADDR_RE = re.compile(r":(\d+)$")

def port(a):
    m = ADDR_RE.search(a or ""); return int(m.group(1)) if m else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv"); ap.add_argument("--out", required=True); ap.add_argument("--ports", type=int, nargs="+", default=[8554])
    ap.add_argument("--markers", nargs="*", default=[]); ap.add_argument("--schema", default=str(pathlib.Path(__file__).with_name("o1_etw_schema.json")))
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    schema = json.load(open(a.schema, encoding="utf-8"))
    ports = set(a.ports)
    marker_ports = {}
    for mf in a.markers:
        m = json.load(open(mf, encoding="utf-8-sig")); marker_ports[m["label"]] = {m["client_port"], m["server_port"]}
    mports = set().union(*marker_ports.values()) if marker_ports else set()
    inst = {}            # instance id -> record
    cur = {}             # Tcb -> instance id (open)
    rel_pids = set()
    n = {"rows": 0, "kept": 0, "unrelated": 0, "unassigned_tcb": 0, "no_tcb_other": 0, "parse_errors": 0, "header_rows": 0}
    unknown = {}; errs = []
    gz = gzip.open(out / "extract.jsonl.gz", "wt", encoding="utf-8")
    with open(a.csv, encoding="utf-8", errors="replace", newline="") as fh:
        rd = csv.reader(fh, skipinitialspace=True)
        hdr = [h.strip() for h in next(rd)]
        ix = {h: i for i, h in enumerate(hdr)}
        i_name, i_id, i_ver, i_pid, i_clock = ix["Event Name"], ix["Event ID"], ix["Version"], ix["PID"], ix["Clock-Time"]
        i_ud = ix["User Data"]
        for row in rd:
            n["rows"] += 1
            # tracerpt writes some message-text lines into the CSV (not events): counted as non-event rows
            if len(row) <= i_ud or not row[i_name].strip().startswith("Microsoft-Windows"): n["header_rows"] += 1; continue
            try:
                prov = PROVIDER_ALIAS.get(row[i_name].strip(), row[i_name].strip()); eid = row[i_id].strip(); ver = row[i_ver].strip()
                t = (int(row[i_clock].strip()) - FILETIME_EPOCH) * 100
                hpid = int(row[i_pid].strip(), 16) if row[i_pid].strip().startswith("0x") else int(row[i_pid].strip() or 0)
                names = schema.get(f"{prov}|{eid}|{ver}")
                vals = [v.strip() for v in row[i_ud:]]
                if names is None:
                    unknown[f"{prov}|{eid}|{ver}"] = unknown.get(f"{prov}|{eid}|{ver}", 0) + 1
                    d = {f"_{k}": v for k, v in enumerate(vals)}
                else:
                    d = dict(zip(names, vals))
            except Exception as exc:              # noqa: BLE001
                n["parse_errors"] += 1
                if n["parse_errors"] <= 5: errs.append({"row": n["rows"], "error": f"{type(exc).__name__}: {exc}", "head": row[:4]})
                continue
            p_short = "TCPIP" if "TCPIP" in prov else "AFD" if "AFD" in prov else prov
            tcb = d.get("Tcb")
            la = d.get("LocalAddress") or d.get("LocalSockAddr"); ra = d.get("RemoteAddress") or d.get("RemoteSockAddr")
            iid = None
            if tcb and la and ra:
                c = cur.get(tcb)
                # a NEW instance only when the address pair changes (Tcb pointer reuse); the close sequence spans several events of
                # the same connection, which must not fragment it
                if c is None or (inst[c]["local"], inst[c]["remote"]) != (la, ra):
                    c = f"I{len(inst) + 1:05d}"
                    lp, rp = port(la), port(ra)
                    inst[c] = {"id": c, "tcb": tcb, "local": la, "remote": ra, "pid": None, "first_utc_ns": t, "last_utc_ns": t, "close_utc_ns": None,
                               "first_event": eid, "relevant": lp in ports or rp in ports, "marker": next((k for k, v in marker_ports.items() if lp in v and rp in v), None), "events": 0}
                    cur[tcb] = c
                pv = d.get("Pid") or d.get("ProcessId")
                if pv and not inst[c]["pid"]:          # first NON-ZERO process id (some events carry 0)
                    try:
                        v = int(pv.strip(), 0)
                        if v: inst[c]["pid"] = v
                    except ValueError: pass
                iid = c
            elif tcb:
                iid = cur.get(tcb)
                if iid is None: n["unassigned_tcb"] += 1
            if iid is not None:
                r = inst[iid]; r["last_utc_ns"] = t; r["events"] += 1
                if eid in CLOSE_IDS and p_short == "TCPIP" and r["close_utc_ns"] is None: r["close_utc_ns"] = t   # first close event
                if r["relevant"] and r["pid"]: rel_pids.add(r["pid"])
            keep = False
            if iid is not None and (inst[iid]["relevant"] or inst[iid]["marker"]): keep = True
            elif eid == "1214" and p_short == "TCPIP" and (port(la) in ports or port(ra) in ports): keep = True
            elif p_short == "AFD" and hpid in rel_pids: keep = True
            if keep:
                gz.write(json.dumps({"t": t, "p": p_short, "id": eid, "v": ver, "pid": hpid, "inst": iid, "d": d}, separators=(",", ":")) + "\n"); n["kept"] += 1
            else:
                n["unrelated"] += 1 if (iid is not None or p_short == "AFD" or eid == "1214") else 0
                if iid is None and not tcb and not (p_short == "AFD" or eid == "1214"): n["no_tcb_other"] += 1
    gz.close()
    rel = [r for r in inst.values() if r["relevant"] or r["marker"]]
    json.dump({"relevant_or_marker": rel, "relevant_pids": sorted(rel_pids)}, open(out / "connections.json", "w", encoding="utf-8"), indent=1)
    summ = {"csv": os.path.abspath(a.csv), "ports": sorted(ports), "markers": {k: sorted(v) for k, v in marker_ports.items()}, "counts": n,
            "instances_total": len(inst), "instances_relevant": sum(1 for r in inst.values() if r["relevant"]), "instances_marker": sum(1 for r in inst.values() if r["marker"]),
            "unrelated_instances": sum(1 for r in inst.values() if not r["relevant"] and not r["marker"]), "relevant_pids": sorted(rel_pids),
            "unknown_schema_keys": unknown, "parse_error_samples": errs, "reconcile_ok": n["rows"] == n["kept"] + n["unrelated"] + n["unassigned_tcb"] + n["no_tcb_other"] + n["parse_errors"] + n["header_rows"],
            "time": "Clock-Time FILETIME (UTC, 100 ns) -> t_utc_ns; ETW converted it from the session QPC clock"}
    json.dump(summ, open(out / "extract_summary.json", "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: summ[k] for k in ("counts", "instances_total", "instances_relevant", "instances_marker", "relevant_pids", "reconcile_ok")}, indent=1))
    print("unknown schema keys:", len(unknown))

if __name__ == "__main__":
    sys.exit(main())

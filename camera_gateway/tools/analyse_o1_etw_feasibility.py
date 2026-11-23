"""Analyse the O1 ETW FEASIBILITY capture (prepared 13 Nov 2026): what do the selected providers actually expose?

Input : tracerpt XML of the feasibility .etl (tracerpt <etl> -o events.xml -of XML), the traffic markers JSON from
        o1_etw_feasibility_traffic.py, and optionally the tracerpt -summary text (events / buffers lost).
Output: feasibility_report.json with, per provider and event (id, task, opcode): count, the data FIELD NAMES seen, example values;
        then evidence capabilities established ONLY from fields actually present:
          - connection identity (local/remote address and port; process id)          - per-segment sequence / ACK numbers
          - window / zero-window information                                         - retransmission events (P4 SYN retries)
          - drop events with a reason                                                - socket-level send/receive completions (AFD)
          - timestamp alignment: ETW time of the P1 connect vs the recorded marker (offset and uncertainty)
        A capability not demonstrated here must not be promised for the camera run.
The analysis reads only the decoded XML; it never deletes the raw files.
Usage: analyse_o1_etw_feasibility.py <events.xml> <markers.json> [--summary o1_summary.txt] [--out feasibility_report.json]
"""
import argparse, collections, datetime as dt, json, re, xml.etree.ElementTree as ET

CAPS = {   # capability -> regex over field names (case-insensitive); verified only if a field matches in a relevant event
    "connection_identity_ports": r"(local|remote|src|dst).*port|^port$",
    "connection_identity_address": r"(local|remote|src|dst).*addr",
    "process_id": r"^(pid|processid|process)$",
    "sequence_numbers": r"seq|sndnxt|snduna|iss\b",
    "ack_numbers": r"ack|rcvnxt",
    "window_information": r"wnd|window",
    "retransmission_information": r"retrans|rexmit|rto",
    "drop_reason": r"drop|discard|reason",
    "byte_counts": r"bytes|length|size|numbytes",
    "socket_or_endpoint_id": r"endpoint|socket|tcb|afdendpoint",
}

def ns(tag): return tag.split("}")[-1]

def parse(path):
    root = ET.parse(path).getroot()
    for ev in root.iter():
        if ns(ev.tag) != "Event": continue
        sysn = next((c for c in ev if ns(c.tag) == "System"), None)
        if sysn is None: continue
        rec = {"provider": None, "id": None, "time": None, "pid": None, "fields": {}, "task": None, "opcode": None}
        for c in sysn:
            t = ns(c.tag)
            if t == "Provider": rec["provider"] = c.get("Name") or c.get("Guid")
            elif t == "EventID": rec["id"] = (c.text or "").strip()
            elif t == "TimeCreated": rec["time"] = c.get("SystemTime")
            elif t == "Execution": rec["pid"] = c.get("ProcessID")
            elif t == "Task" and rec["task"] is None: rec["task"] = (c.text or "").strip()
            elif t == "Opcode" and rec["opcode"] is None: rec["opcode"] = (c.text or "").strip()
        for c in ev:
            t = ns(c.tag)
            if t == "EventData":
                for d in c:
                    if ns(d.tag) == "Data": rec["fields"][d.get("Name") or "_"] = (d.text or "").strip()
            elif t == "RenderingInfo":
                for d in c:
                    if ns(d.tag) == "Task" and d.text: rec["task"] = d.text.strip()
                    if ns(d.tag) == "Opcode" and d.text: rec["opcode"] = d.text.strip()
        yield rec

def utc_ns(s):
    if not s: return None
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.(\d+))?Z?", s)
    if not m: return None
    base = dt.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
    frac = (m.group(3) or "0").ljust(9, "0")[:9]
    return int(base.timestamp()) * 1_000_000_000 + int(frac)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("xml"); ap.add_argument("markers"); ap.add_argument("--summary"); ap.add_argument("--out", default="feasibility_report.json")
    a = ap.parse_args()
    markers = json.load(open(a.markers, encoding="utf-8"))
    ph = {p["phase"]: p for p in markers["phases"]}
    test_ports = set()
    for p in markers["phases"]:
        for k in ("server_port",):
            if p.get(k): test_ports.add(str(p[k]))
        if p.get("client"): test_ports.update(str(v) for v in p["client"].values() if v)
        test_ports.update(str(v) for v in p.get("client_ports", []))
    groups = collections.OrderedDict(); evs = []
    for r in parse(a.xml):
        evs.append(r)
        k = (r["provider"], r["id"], r["task"], r["opcode"])
        g = groups.setdefault(k, {"provider": r["provider"], "event_id": r["id"], "task": r["task"], "opcode": r["opcode"], "count": 0, "fields": collections.Counter(), "example": None, "touches_test_ports": 0})
        g["count"] += 1; g["fields"].update(r["fields"].keys())
        if any(v in test_ports for v in r["fields"].values()): g["touches_test_ports"] += 1
        if g["example"] is None: g["example"] = dict(list(r["fields"].items())[:16])
    caps = {}
    for cap, rx in CAPS.items():
        hits = [{"provider": g["provider"], "event_id": g["event_id"], "task": g["task"], "fields": sorted(f for f in g["fields"] if re.search(rx, f, re.I)), "events_touching_test_ports": g["touches_test_ports"]}
                for g in groups.values() if any(re.search(rx, f, re.I) for f in g["fields"])]
        caps[cap] = {"verified_in_field_names": bool(hits), "events": hits[:12]}
    # retransmission evidence must coincide with the P4 forced SYN retries (test ports)
    p4 = set(str(x) for x in ph.get("P4_syn_retransmission", {}).get("client_ports", []))
    retrans_ev = [r for r in evs if re.search(r"retrans|rexmit", (r["task"] or "") + " " + " ".join(r["fields"].keys()), re.I)]
    caps["retransmission_information"]["coincides_with_forced_syn_retries"] = any(any(v in p4 for v in r["fields"].values()) for r in retrans_ev)
    # timestamp alignment: first event mentioning the P1 client port vs the recorded marker interval
    p1 = ph.get("P1_marker_connect", {}); port = str((p1.get("client") or {}).get("local"))
    hit = next((r for r in evs if port in r["fields"].values()), None)
    align = None
    if hit and p1:
        t = utc_ns(hit["time"])
        align = {"etw_event": {"provider": hit["provider"], "event_id": hit["id"], "task": hit["task"], "time": hit["time"]},
                 "marker_before_utc_ns": p1["before"]["utc_ns"], "marker_after_utc_ns": p1["after"]["utc_ns"],
                 "etw_minus_marker_before_ms": round((t - p1["before"]["utc_ns"]) / 1e6, 3) if t else None,
                 "within_marker_interval": bool(t and p1["before"]["utc_ns"] - 2_000_000 <= t <= p1["after"]["utc_ns"] + 2_000_000),
                 "note": "tracerpt renders UTC; the gateway maps UTC<->QPC with its recorded utc_minus_mono offset"}
    lost = None
    if a.summary:
        txt = open(a.summary, encoding="utf-8", errors="replace").read()
        lost = {k: (re.search(k + r"\s*[:=]\s*(\d+)", txt, re.I).group(1) if re.search(k + r"\s*[:=]\s*(\d+)", txt, re.I) else None) for k in ("Events Lost", "Buffers Lost")}
    rep = {"events_total": len(evs), "event_groups": [dict(g, fields=sorted(g["fields"])) for g in groups.values()], "capabilities": caps,
           "timestamp_alignment": align, "loss": lost, "test_ports": sorted(test_ports),
           "rule": "promise only capabilities verified here (field present in the relevant events, retransmission coinciding with P4)"}
    json.dump(rep, open(a.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps({"events_total": len(evs), "groups": len(groups), "verified": {k: v["verified_in_field_names"] for k, v in caps.items()},
                      "retransmission_coincides_with_P4": caps["retransmission_information"]["coincides_with_forced_syn_retries"],
                      "alignment": align and {k: align[k] for k in ("etw_minus_marker_before_ms", "within_marker_interval")}}, indent=1))

if __name__ == "__main__":
    main()

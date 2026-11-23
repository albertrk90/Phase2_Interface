"""O1 ETW feasibility, second pass against the REAL schema seen in the capture (13 Nov 2026).

The first-pass analyser compared bare port numbers, but the providers render addresses as "127.0.0.1:<port>", and tracerpt renders
local times with an offset (seen as +10:29). Its "ports false / retransmission not matched / alignment off by 10.5 h" verdicts were
artefacts. This pass:
  - maps every TCP control block (Tcb) to its local/remote address:port and process id (from events that carry both),
  - selects the TEST connections from the markers (P1-P3 client/server ports; P4 SYN-retry client ports and listener),
  - checks each capability ON THE TEST CONNECTIONS ONLY (P2 data: seq / ack / window per segment; P3 receiver stall: receive window,
    receiver-limited bytes, zero-window probing, socket send completions; P4: SYN retransmission events and their spacing; drops),
  - maps Winsock-AFD endpoints to process ids (AfdCreate) and measures send/receive call durations (enter/exit) for the test process,
  - calibrates timestamps from the P1 connect marker and checks the calibration against the P4 marker (drift),
  - counts unrelated local connections and processes in the raw trace (numbers only; no details are reported).
Reads the decoded XML only; never deletes raw files.
Usage: analyse_o1_etw_feasibility_v2.py <events.xml> <markers.json> [--out feasibility_report_v2.json]
"""
import argparse, collections, datetime as dt, json, re, statistics, xml.etree.ElementTree as ET

ns = lambda t: t.split("}")[-1]

LOCAL_OFFSET = None   # set in main() from the machine's actual UTC offset at the capture time

def t_ns(s):
    # tracerpt renders LOCAL time digits with an unreliable offset label (+10:29 on 136,520 events and +10:30 on 20 in the feasibility
    # capture, while the zone is +10:30; Get-WinEvent labels the same digits +10:30). The digits are correct (they match the markers),
    # so the label is ignored and the machine's actual offset is applied.
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?", s or "")
    if not m: return None
    base = dt.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S") - LOCAL_OFFSET
    base = base.replace(tzinfo=dt.timezone.utc)
    return int(base.timestamp()) * 1_000_000_000 + int((m.group(2) or "0").ljust(9, "0")[:9])

def port(a):
    m = re.search(r":(\d+)$", a or ""); return int(m.group(1)) if m else None

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("xml"); ap.add_argument("markers"); ap.add_argument("--out", default="feasibility_report_v2.json")
    a = ap.parse_args()
    M = {p["phase"]: p for p in json.load(open(a.markers, encoding="utf-8"))["phases"]}
    p1, p4 = M["P1_marker_connect"], M["P4_syn_retransmission"]
    global LOCAL_OFFSET
    LOCAL_OFFSET = dt.datetime.fromtimestamp(p1["before"]["utc_ns"] / 1e9).astimezone().utcoffset()
    test_ports = {p1["client"]["local"], p1["client"]["remote"], p4["server_port"], *p4["client_ports"]}
    evs = []
    tcb = {}            # Tcb -> (local, remote, pid)
    afd_pid = {}        # AFD endpoint -> pid (AfdCreate)
    for _, el in ET.iterparse(a.xml, events=("end",)):
        if ns(el.tag) != "Event": continue
        sysn = next((c for c in el if ns(c.tag) == "System"), None)
        if sysn is None: el.clear(); continue
        prov = next((c.get("Name") for c in sysn if ns(c.tag) == "Provider"), None) or ""
        eid = next((c.text for c in sysn if ns(c.tag) == "EventID"), None)
        tt = t_ns(next((c.get("SystemTime") for c in sysn if ns(c.tag) == "TimeCreated"), None))
        xpid = next((c.get("ProcessID") for c in sysn if ns(c.tag) == "Execution"), None)
        d = {x.get("Name"): (x.text or "").strip() for c in el if ns(c.tag) == "EventData" for x in c}
        task = next((x.text for c in el if ns(c.tag) == "RenderingInfo" for x in c if ns(x.tag) == "Task"), None)
        el.clear()
        if not prov.startswith("Microsoft-Windows"): continue
        e = {"p": "TCPIP" if "TCPIP" in prov else "AFD", "id": eid, "task": task, "t": tt, "xpid": int(xpid) if xpid and xpid.isdigit() else None, "d": d}
        evs.append(e)
        la = d.get("LocalAddress") or d.get("LocalSockAddr"); ra = d.get("RemoteAddress") or d.get("RemoteSockAddr")
        if d.get("Tcb") and la and ra:
            pid = d.get("Pid") or d.get("ProcessId")
            prev = tcb.get(d["Tcb"])
            tcb[d["Tcb"]] = (la, ra, int(pid.strip(), 0) if pid and pid.strip() else (prev[2] if prev else None))
        if e["p"] == "AFD" and eid == "1000" and d.get("Endpoint") and d.get("ProcessId"):
            afd_pid[d["Endpoint"]] = int(d["ProcessId"], 16)
    is_test = lambda t: t in tcb and (port(tcb[t][0]) in test_ports or port(tcb[t][1]) in test_ports)
    test_tcbs = {t for t in tcb if is_test(t)}
    main_tcbs = {t for t in test_tcbs if {port(tcb[t][0]), port(tcb[t][1])} == {p1["client"]["local"], p1["client"]["remote"]}}
    test_pids = {tcb[t][2] for t in main_tcbs if tcb[t][2]}
    per = collections.defaultdict(list)
    for e in evs:
        if e["d"].get("Tcb") in test_tcbs: per[e["d"]["Tcb"]].append(e)
    # ---- timestamp calibration: first event naming the P1 connection vs the P1 marker interval
    p1ev = sorted((e for t in main_tcbs for e in per[t] if e["id"] in ("1031", "1033")), key=lambda e: e["t"]) or sorted((e for t in main_tcbs for e in per[t]), key=lambda e: e["t"])
    cal = None
    if p1ev:
        off = p1ev[0]["t"] - p1["before"]["utc_ns"]
        p4ev = sorted((e for t in test_tcbs if port(tcb[t][1]) == p4["server_port"] for e in per[t] if e["id"] in ("1031", "1033")), key=lambda e: e["t"])
        drift = (p4ev[0]["t"] - off - p4["start"]["utc_ns"]) / 1e6 if p4ev else None
        cal = {"first_P1_event": {"id": p1ev[0]["id"], "task": p1ev[0]["task"]},
               "etw_minus_marker_ms": round(off / 1e6, 3),
               "marker_interval_ms": round((p1["after"]["utc_ns"] - p1["before"]["utc_ns"]) / 1e6, 3),
               "P4_check_after_calibration_ms (first P4 event minus P4 start marker)": None if drift is None else round(drift, 3),
               "note": "tracerpt renders local time with an offset string (+10:29 here, not the zone's +10:30), so absolute ETW times are offset; "
                       "calibrate per capture from a marker. Within one capture the P4 check bounds the residual."}
    cnt = lambda tcbs, eid: sum(1 for t in tcbs for e in per[t] if e["id"] == eid)
    vals = lambda tcbs, eid, f: [int(e["d"][f].strip(), 0) for t in tcbs for e in per[t] if e["id"] == eid and e["d"].get(f, "").strip().lstrip("-").isdigit()]
    p3a = (p1["before"]["utc_ns"] + (cal and cal["etw_minus_marker_ms"] * 1e6 or 0))
    st = M["P3_receiver_stall"]; off_ns = int(cal["etw_minus_marker_ms"] * 1e6) if cal else 0
    w0, w1 = st["start"]["utc_ns"] + off_ns, st["drained"]["utc_ns"] + off_ns
    inwin = lambda e: w0 <= e["t"] <= w1
    p3 = [e for t in main_tcbs for e in per[t] if inwin(e)]
    rl = [int(e["d"]["ReceiverLimitedBytes"]) for e in p3 if e["id"] == "1626" and e["d"].get("ReceiverLimitedBytes", "").isdigit()]
    sndwnd = [int(e["d"]["SndWnd"].strip()) for e in p3 if e["id"] == "1330" and e["d"].get("SndWnd", "").strip().isdigit()]
    zwp = [e for e in p3 if e["id"] == "1102"]
    # AFD: send / receive call durations for the test process (pair enter 0 / exit 1 per endpoint)
    afd = collections.defaultdict(list)
    for e in evs:
        if e["p"] == "AFD" and e["id"] in ("1003", "1004") and afd_pid.get(e["d"].get("Endpoint")) in test_pids:
            afd[(e["d"]["Endpoint"], e["id"])].append(e)
    dur = {"1003": [], "1004": []}
    status = collections.Counter()
    for (ep, eid), lst in afd.items():
        lst.sort(key=lambda e: e["t"]); opened = None
        for e in lst:
            ee = e["d"].get("EnterExit", "").strip()
            if ee == "0": opened = e
            elif ee == "1" and opened is not None: dur[eid].append((e["t"] - opened["t"]) / 1e6); status[(eid, e["d"].get("Status"))] += 1; opened = None
    q = lambda v, p: sorted(v)[min(len(v) - 1, int(p * len(v)))] if v else None
    p4_rex = [e for t in test_tcbs for e in per[t] if e["id"] in ("1186", "1351") and port(tcb[t][1]) == p4["server_port"]]
    p4_1186 = sorted((e for e in p4_rex if e["id"] == "1186"), key=lambda e: e["t"])
    p4_rto = vals({t for t in test_tcbs if port(tcb[t][1]) == p4["server_port"]}, "1351", "RTO")
    drops_test = [e for e in evs if e["id"] == "1214" and (port(e["d"].get("LocalSockAddr")) in test_ports or port(e["d"].get("RemoteSockAddr")) in test_ports)]
    drops_all = [e for e in evs if e["id"] == "1214"]
    unrelated_tcbs = [t for t in tcb if t not in test_tcbs]
    rep = {
        "events_parsed": len(evs), "connections_mapped": len(tcb), "test_connections": len(test_tcbs), "test_process_ids": sorted(test_pids),
        "timestamp_calibration": cal,
        "capabilities_on_test_connections": {
            "connection_identity (Tcb -> address:port, pid)": {"verified": bool(main_tcbs), "via_events": sorted({e["id"] for t in main_tcbs for e in per[t] if e["d"].get("LocalAddress")})},
            "per_segment_send (1332 TcpDataTransferSend: SeqNo, SndUna, SndWnd, RcvWnd, Cwnd, RTO)": {"events": cnt(main_tcbs, "1332")},
            "per_segment_receive_header (1601 TcpRx: ThSeq, ThAck, ThFlags)": {"events": cnt(main_tcbs, "1601")},
            "cumulative_ack (1330 TcpDataTransferCumAck: SeqNo, BytesAcked, SndWnd)": {"events": cnt(main_tcbs, "1330")},
            "delivery_to_application (1157 TcpDeliveryIndicated: RcvNxt, NumBytes)": {"events": cnt(main_tcbs, "1157")},
            "P3_receiver_stall": {"events_in_window": len(p3), "receiver_limited_bytes_max": max(rl) if rl else None, "receiver_limited_samples>0": sum(x > 0 for x in rl),
                                  "send_window_min": min(sndwnd) if sndwnd else None, "send_window_samples": len(sndwnd), "zero_window_probe_events": len(zwp),
                                  "note": "window collapse / receiver limitation on the test connection is what distinguishes receiver backpressure"},
            "P4_syn_retransmission (1186 TcpConnectRestransmit, 1351 RetransmitRound)": {"events_1186": len(p4_1186), "events_1351": sum(1 for e in p4_rex if e["id"] == "1351"),
                                  "first_spacing_ms": [round((b["t"] - a_["t"]) / 1e6, 1) for a_, b in zip(p4_1186, p4_1186[1:])][:6], "RTO_values_ms": sorted(set(p4_rto))[:6],
                                  "verified": bool(p4_1186)},
            "data_retransmission_events_available (1187 TcpDataTransferRestransmit / 1069 Timeout / 1584 MarkRexmit)": {
                "seen_anywhere_in_trace": sorted({e["id"] for e in evs if e["id"] in ("1187", "1069", "1584")}),
                "seen_on_test_connections": sorted({e["id"] for t in test_tcbs for e in per[t] if e["id"] in ("1187", "1069", "1584")}),
                "note": "a DATA-segment retransmission did not occur on the test connections (none was provoked); schema seen on other connections only"},
            "drops (1214 TcpipTransportPacketDrops: Reason, PacketCount, sock addrs)": {"on_test_ports": len(drops_test), "reasons_on_test_ports": sorted({e["d"]["Reason"] for e in drops_test}),
                                  "total_in_trace": len(drops_all)},
            "socket_calls_test_process (Winsock-AFD 1003 send / 1004 receive, enter->exit)": {
                "send_calls": len(dur["1003"]), "send_ms_p50_p99_max": [round(q(dur["1003"], .5), 3) if dur["1003"] else None, round(q(dur["1003"], .99), 3) if dur["1003"] else None, round(max(dur["1003"]), 3) if dur["1003"] else None],
                "receive_calls": len(dur["1004"]), "receive_ms_p50_p99_max": [round(q(dur["1004"], .5), 3) if dur["1004"] else None, round(q(dur["1004"], .99), 3) if dur["1004"] else None, round(max(dur["1004"]), 3) if dur["1004"] else None],
                "exit_status_counts": {f"{k[0]}:{k[1]}": v for k, v in status.items()}, "endpoint_to_pid_mapped": len(afd_pid),
                "note": "AFD events carry Endpoint and a kernel process pointer; the pid comes from AfdCreate. Endpoint->TCP connection mapping is not in these events"},
        },
        "unrelated_local_metadata_in_raw_trace": {"other_connections": len(unrelated_tcbs), "other_process_ids": len({tcb[t][2] for t in unrelated_tcbs if tcb[t][2]} - test_pids),
                                                  "other_afd_endpoints": len([ep for ep, pid in afd_pid.items() if pid not in test_pids]),
                                                  "note": "counts only; collected because the providers are system-wide (Wi-Fi off)"},
    }
    json.dump(rep, open(a.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps(rep, indent=1))

if __name__ == "__main__":
    main()

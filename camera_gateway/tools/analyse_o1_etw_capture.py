"""Analyse the O1 connection-specific ETW capture (13 Nov 2026) against the gateway holds.

Inputs : --extract <dir> (extract.jsonl.gz, connections.json from tools/extract_o1_etw.py), --gw <gateway dir>, --run <runner dir>
         (unity_rx_*_A_*/arrivals.csv, mediamtx.log), --markers marker_start.json marker_end.json, --capture <capture dir> (summary,
         size check). Test mode: --test-hold <onset_utc_ns> <release_utc_ns> <publisher_local_port> (no gateway / MediaMTX inputs).
Method :
  1 ALIGNMENT  ETW times are the CSV FILETIME (UTC, converted by ETW from the session QPC clock). Each marker records QPC-based
               time.monotonic_ns and time.time_ns around its own loopback connect; the marker connection's first trace event gives
               residual = etw_utc - marker_utc_before (expected within the marker interval). ETW -> gateway monotonic clock:
               etw_mono = etw_utc - (marker_utc_before - marker_mono_before), using the START marker; the END marker checks drift.
  2 CONNECTIONS by endpoints + process + lifetime (extractor instances), never by Tcb alone. Eye identity of a connection comes from
               MediaMTX's own log ("[session X] created by 127.0.0.1:P" + "is publishing to / reading from path 'camA_left|right'").
  3 HOLDS      from the gateway (stale resyncs; sent.csv write returns) and Unity arrivals (as tools/analyse_tcp_holds.py).
  4 PER HOLD   on that eye's publisher connection, both ends, in [onset - 200 ms, release + 200 ms]: sequence / ACK progression,
               retransmission and timer events, windows and receiver-limited bytes, receiver-side segment arrivals and delivery
               indications, drops (raw codes, NOT interpreted), and process-level Winsock calls (NOT assigned to an eye).
  5 STATEMENTS observations (measured) | supported inferences (rule stated) | unresolved. No holds -> INCONCLUSIVE.
"""
import argparse, bisect, csv, gzip, json, pathlib, re, statistics, sys

MS = 1e6
RETRANS_IDS = {"1351", "1187", "1069", "1584", "1186"}
WANT = {"1332", "1330", "1601", "1074", "1157", "1626", "1064", "1065", "1066", "1102", "1214", "1003", "1004"} | RETRANS_IDS
INT = lambda v: int(str(v).strip(), 0) if str(v).strip().lstrip("-").replace("x", "").replace("X", "").isalnum() else None

def ival(d, k):
    try: return int(str(d.get(k, "")).strip(), 0)
    except (ValueError, TypeError): return None

def load_extract(ex):
    ev = []
    with gzip.open(pathlib.Path(ex) / "extract.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            e = json.loads(line)
            if e["id"] in WANT: ev.append(e)
    ev.sort(key=lambda e: e["t"])
    conns = json.load(open(pathlib.Path(ex) / "connections.json", encoding="utf-8"))
    return ev, conns

def alignment(ev, conns, markers):
    out = {}
    inst_by_marker = {}
    for c in conns["relevant_or_marker"]:
        if c.get("marker"): inst_by_marker.setdefault(c["marker"], []).append(c["id"])
    for m in markers:
        ids = set(inst_by_marker.get(m["label"], []))
        first = next((e for e in ev if e.get("inst") in ids), None)
        if first is None:
            # marker connections may carry only connection events, not in WANT: use the instance's first time
            ft = min((c["first_utc_ns"] for c in conns["relevant_or_marker"] if c["id"] in ids), default=None)
        else: ft = first["t"]
        out[m["label"]] = None if ft is None else {
            "etw_first_utc_ns": ft, "residual_ms": round((ft - m["before"]["utc_ns"]) / MS, 3),
            "marker_interval_ms": round((m["after"]["utc_ns"] - m["before"]["utc_ns"]) / MS, 3),
            "utc_minus_mono_at_marker_ns": m["before"]["utc_ns"] - m["before"]["mono_ns"]}
    if out.get("start"):
        d = out["start"]["utc_minus_mono_at_marker_ns"]
        out["etw_to_mono_offset_ns"] = d
        if out.get("end"):
            out["drift_ms_end_vs_start"] = round((out["end"]["utc_minus_mono_at_marker_ns"] - d) / MS, 3)
            out["end_residual_minus_start_residual_ms"] = round(out["end"]["residual_ms"] - out["start"]["residual_ms"], 3)
    out["conversion"] = ("ETW FILETIME (UTC, from session QPC) -> etw_mono = etw_utc - (marker utc - marker mono) at the START marker; "
                         "the residuals are the marker connection's first trace event minus the marker's 'before' clock reading")
    return out

def mediamtx_ports(log):
    created, role = {}, {}
    for line in open(log, encoding="utf-8", errors="replace"):
        m = re.search(r"\[session (\w+)\] created by 127\.0\.0\.1:(\d+)", line)
        if m: created[m.group(1)] = int(m.group(2))
        m = re.search(r"\[session (\w+)\] is (publishing to|reading from) path '([^']+)'", line)
        if m and m.group(1) in created: role[created[m.group(1)]] = ("publisher" if m.group(2).startswith("publishing") else "reader", m.group(3))
    return role

def holds_from_gateway(gw, run):
    rows = lambda p: list(csv.DictReader(open(p, encoding="utf-8-sig")))
    ev = [json.loads(l) for l in open(pathlib.Path(gw) / "events.jsonl", encoding="utf-8") if l.strip()]
    cap = {(r["eye"], int(r["seq"])): int(r["t_received_mono_ns"]) for r in rows(pathlib.Path(gw) / "captured.csv")}
    sent = {"left": [], "right": []}
    for r in rows(pathlib.Path(gw) / "sent.csv"): sent[r["eye"]].append((int(r["t_sent_mono_ns"]), int(r["seq"])))
    for e in sent: sent[e].sort()
    arr = {"left": {}, "right": {}}
    for d in sorted(pathlib.Path(run).glob("unity_rx_*_A_*")):
        for r in rows(d / "arrivals.csv"): arr[r["eye"]][int(r["seq"])] = int(r["t_arrival_mono_ns"])
    H = []
    for e in ev:
        if e["type"] != "gop_resync" or e["payload"]["seq"] == 0: continue
        eye = e["payload"]["eye"]; s = sent[eye]; ts = [x[0] for x in s]
        i = bisect.bisect_left(ts, e["t_mono_ns"]) - 1
        blk, prev = s[i], s[i - 1]; ws = max(prev[0], cap[(eye, blk[1])])
        held = []; j = i - 1
        while blk[1] in arr[eye] and j > 0 and i - j <= 8:
            ta = arr[eye].get(s[j][1])
            if ta is not None and ta - s[j][0] > 30 * MS: held.append(j); j -= 1
            else: break
        onset = s[held[-1]][0] if held else ws
        rel = [arr[eye][x[1]] for x in (s[held[-1]:i + 1] if held else [blk]) if x[1] in arr[eye]]
        H.append({"eye": eye, "resync_mono_ns": e["t_mono_ns"], "onset_mono_ns": onset, "release_mono_ns": min(rel) if rel else blk[0],
                  "release_basis": "first held data arrival in Unity" if rel else "blocked write return (no reader)", "held_frames": len(held), "age_ms": e["payload"]["age_ms"]})
    return H

def per_hold(ev, conns, h, d_mono, pub_port, pids):
    """Observations on the publisher connection (both ends) around one hold. Times relative to the hold onset (ms)."""
    on = h["onset_mono_ns"] + d_mono; rl = h["release_mono_ns"] + d_mono       # -> ETW utc
    w0, w1 = on - 200 * MS, rl + 200 * MS
    ins = {c["id"]: c for c in conns["relevant_or_marker"]}
    # instances alive in the window (lifetime-bounded), gateway side = local port pub_port, server side = remote port pub_port
    alive = lambda c: c["first_utc_ns"] <= w1 and (c["close_utc_ns"] is None or c["close_utc_ns"] >= w0)
    g = [c["id"] for c in ins.values() if c["local"].endswith(f":{pub_port}") and alive(c)]
    s = [c["id"] for c in ins.values() if c["remote"].endswith(f":{pub_port}") and alive(c)]
    i0 = bisect.bisect_left([e["t"] for e in ev], w0); W = []
    for e in ev[i0:]:
        if e["t"] > w1: break
        W.append(e)
    r = lambda t: round((t - on) / MS, 1)
    G = [e for e in W if e.get("inst") in g]; S = [e for e in W if e.get("inst") in s]
    obs = {"gateway_side_instances": g, "server_side_instances": s, "window_ms": [-200, round((rl - on) / MS + 200, 1)], "hold_ms": round((rl - on) / MS, 1)}
    snd = [(e["t"], ival(e["d"], "SeqNo"), ival(e["d"], "SndUna"), ival(e["d"], "SndMax"), ival(e["d"], "SndWnd"), ival(e["d"], "RcvWnd"), ival(e["d"], "BytesSent")) for e in G if e["id"] == "1332"]
    acks = [(e["t"], ival(e["d"], "SeqNo"), ival(e["d"], "BytesAcked"), ival(e["d"], "SndWnd")) for e in G if e["id"] == "1330"]
    obs["gateway_sends"] = len(snd); obs["gateway_cum_acks"] = len(acks)
    if acks:
        at = [a[0] for a in acks]; gaps = [(b - a, a) for a, b in zip([w0] + at, at + [w1])]
        mg = max(gaps); obs["longest_ack_gap_ms"] = round(mg[0] / MS, 1); obs["longest_ack_gap_from_ms"] = r(mg[1])
        obs["send_window_min"] = min((a[3] for a in acks if a[3] is not None), default=None)
    else: obs["longest_ack_gap_ms"] = None
    if snd:
        st = [x[0] for x in snd]; gaps = [(b - a, a) for a, b in zip(st, st[1:])]
        if gaps: mg = max(gaps); obs["longest_send_gap_ms"] = round(mg[0] / MS, 1); obs["longest_send_gap_from_ms"] = r(mg[1])
        out = [(x[3] - x[2]) for x in snd if x[2] is not None and x[3] is not None]
        obs["max_unacked_bytes"] = max(out) if out else None
        obs["peer_receive_window_min_seen_by_gateway"] = min((x[4] for x in snd if x[4] is not None), default=None)
    rex = [e for e in W if e.get("inst") in g + s and e["id"] in RETRANS_IDS]
    obs["retransmission_events"] = [{"t_ms": r(e["t"]), "side": "gateway" if e["inst"] in g else "server", "id": e["id"],
                                     "RexmitCount": e["d"].get("RexmitCount"), "RTO": e["d"].get("RTO"), "SndUna": e["d"].get("SndUna")} for e in rex]
    tim = [e for e in G if e["id"] in ("1064", "1066")]
    obs["gateway_timer_events"] = [{"t_ms": r(e["t"]), "id": e["id"], "TimerType": e["d"].get("TimerType"), "WaitTimeMilliseconds": e["d"].get("WaitTimeMilliseconds")} for e in tim][:30]
    lim = [ival(e["d"], "ReceiverLimitedBytes") for e in G if e["id"] == "1626"]
    obs["gateway_receiver_limited_bytes_max"] = max((x for x in lim if x is not None), default=None)
    obs["zero_window_probes"] = sum(1 for e in G if e["id"] == "1102")
    rx = [e["t"] for e in S if e["id"] == "1601"]
    if rx:
        gaps = [(b - a, a) for a, b in zip(rx, rx[1:])]; mg = max(gaps) if gaps else (0, rx[0])
        obs["server_longest_segment_arrival_gap_ms"] = round(mg[0] / MS, 1); obs["server_longest_arrival_gap_from_ms"] = r(mg[1])
    seqs = [ival(e["d"], "ThSeq") for e in S if e["id"] == "1601"]
    obs["server_out_of_order_arrivals"] = sum(1 for a, b in zip(seqs, seqs[1:]) if a is not None and b is not None and b < a and a - b < 2**31)
    dl = [e["t"] for e in S if e["id"] == "1157"]
    if dl:
        gaps = [(b - a, a) for a, b in zip(dl, dl[1:])]; mg = max(gaps) if gaps else (0, dl[0])
        obs["server_longest_delivery_gap_ms"] = round(mg[0] / MS, 1); obs["server_longest_delivery_gap_from_ms"] = r(mg[1])
    drops = [e for e in W if e["id"] == "1214"]
    obs["drop_events"] = [{"t_ms": r(e["t"]), "reason_code_uninterpreted": e["d"].get("Reason"), "local": e["d"].get("LocalSockAddr"), "remote": e["d"].get("RemoteSockAddr")} for e in drops][:20]
    afd = {}
    for role, pid in pids.items():
        calls = [e for e in W if e["p"] == "AFD" and e["pid"] == pid and e["id"] in ("1003", "1004")]
        opened, dur = {}, []
        for e in calls:
            k = (e["d"].get("Endpoint"), e["id"])
            if str(e["d"].get("EnterExit")).strip() == "0": opened[k] = e["t"]
            elif str(e["d"].get("EnterExit")).strip() == "1" and k in opened: dur.append((e["t"] - opened.pop(k), e["id"], opened.get(k)))
        sends = sorted((x for x in dur if x[1] == "1003"), reverse=True)[:3]
        afd[role] = {"pid": pid, "calls": len(calls), "longest_send_calls_ms": [round(x[0] / MS, 2) for x in sends],
                     "note": "process-level only: not assigned to an eye or a connection"}
    obs["winsock_process_level"] = afd
    return obs

def classify(o):
    S, U = [], []
    hold = o.get("hold_ms") or 0
    rex = o.get("retransmission_events") or []
    near_release = [x for x in rex if -50 <= x["t_ms"] - hold <= 50]
    ack_stall = (o.get("longest_ack_gap_ms") or 0) >= 0.6 * hold if hold else False
    rwin_limited = (o.get("gateway_receiver_limited_bytes_max") or 0) > 0 or (o.get("zero_window_probes") or 0) > 0 or o.get("peer_receive_window_min_seen_by_gateway") == 0
    arrivals_continue = (o.get("server_longest_segment_arrival_gap_ms") or 1e9) < 0.3 * hold if hold else False
    if near_release and ack_stall:
        S.append("retransmission recovery: a retransmission event on the publisher connection within 50 ms of the release, after an ACK gap "
                 f"of {o.get('longest_ack_gap_ms')} ms covering most of the {hold} ms hold")
    if rwin_limited and not rex:
        S.append("receiver backpressure: the gateway's send was receive-window limited (receiver-limited bytes / zero window) during the hold, without retransmission")
    if arrivals_continue and not rex and not rwin_limited:
        S.append("server-side reading delay: segments kept reaching MediaMTX's TCP during the hold with no retransmission or window limitation")
    if not S: U.append("no rule matched: the observations do not single out retransmission recovery, receiver backpressure or a server-side reading delay")
    if o.get("drop_events"): U.append(f"{len(o['drop_events'])} drop event(s) in the window: reason codes are undocumented and NOT interpreted")
    return S, U

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", required=True); ap.add_argument("--gw"); ap.add_argument("--run"); ap.add_argument("--markers", nargs=2, required=True)
    ap.add_argument("--capture"); ap.add_argument("--test-hold", nargs=3, type=int); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ev, conns = load_extract(a.extract)
    markers = [json.load(open(m, encoding="utf-8-sig")) for m in a.markers]
    al = alignment(ev, conns, markers)
    d = al.get("etw_to_mono_offset_ns")
    rep = {"alignment": al, "connections": [], "holds": [], "verdict": None}
    if a.test_hold:
        on_utc, rl_utc, pport = a.test_hold
        H = [{"eye": "test", "onset_mono_ns": on_utc - d, "release_mono_ns": rl_utc - d, "release_basis": "test", "held_frames": None, "age_ms": None}]
        pub = {"test": pport}; pids = {"test_process": conns["relevant_pids"][0]} if conns["relevant_pids"] else {}
    else:
        roles = mediamtx_ports(pathlib.Path(a.run) / "mediamtx.log")
        pub = {path.split("_")[-1]: p for p, (role, path) in roles.items() if role == "publisher"}
        rep["connections"] = [{"client_port": p, "role": role, "path": path, "source": "mediamtx.log"} for p, (role, path) in sorted(roles.items())]
        H = holds_from_gateway(a.gw, a.run)
        rs = json.load(open(pathlib.Path(a.run) / "runner_status.json", encoding="utf-8-sig"))
        inst = conns["relevant_or_marker"]
        gpid = next((c["pid"] for c in inst if c["remote"].endswith(":8554") and port_of(c["local"]) in pub.values()), None)
        mpid = next((c["pid"] for c in inst if c["local"].endswith(":8554")), None)
        pids = {k: v for k, v in (("gateway", gpid), ("mediamtx", mpid)) if v}
    for h in H:
        eye = h["eye"]; pport = pub.get(eye)
        if pport is None or d is None: h["observations"] = None; h["supported_inferences"] = []; h["unresolved"] = ["no publisher connection or no alignment"]; rep["holds"].append(h); continue
        o = per_hold(ev, conns, h, d, pport, pids)
        sinf, unres = classify(o)
        h.update({"publisher_port": pport, "observations": o, "supported_inferences": sinf, "unresolved": unres})
        rep["holds"].append(h)
    if not H: rep["verdict"] = "INCONCLUSIVE: no holds occurred during the capture"
    else:
        k = [bool(h["supported_inferences"]) for h in rep["holds"]]
        rep["verdict"] = f"{len(H)} hold(s); {sum(k)} with a supported inference, {len(k) - sum(k)} unresolved"
    if a.capture:
        cp = pathlib.Path(a.capture)
        for f in ("trace_size_check.json", "capture_times.json"):
            if (cp / f).exists(): rep[f.replace(".json", "")] = json.load(open(cp / f, encoding="utf-8-sig"))
        if (cp / "o1_summary.txt").exists():
            txt = open(cp / "o1_summary.txt", encoding="utf-8", errors="replace").read()
            rep["events_lost"] = (re.search(r"Total Events\s+Lost\s+(\d+)", txt) or [None, None])[1]
            rep["buffers_lost_line"] = next((l.strip() for l in txt.splitlines() if "Buffers" in l and "Lost" in l), None)
    pathlib.Path(a.out).mkdir(parents=True, exist_ok=True)
    json.dump(rep, open(pathlib.Path(a.out) / "o1_capture_analysis.json", "w", encoding="utf-8"), indent=1, default=str)
    print(json.dumps({"verdict": rep["verdict"], "alignment": {k: v for k, v in al.items() if k != "conversion"}}, indent=1, default=str))

def port_of(a):
    m = re.search(r":(\d+)$", a or ""); return int(m.group(1)) if m else None

if __name__ == "__main__":
    sys.exit(main())

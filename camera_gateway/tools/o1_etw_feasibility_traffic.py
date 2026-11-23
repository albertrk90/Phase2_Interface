"""O1 ETW feasibility traffic (prepared 13 Nov 2026; run only inside the approved elevated, isolated capture window).

Generates KNOWN local loopback TCP activity (127.0.0.1, ephemeral ports created and closed here; nothing leaves the machine), with
clock markers, so the feasibility analysis can establish what the selected ETW providers actually expose and how their timestamps
align with the gateway's clock. Each phase records its local/remote ports and time.monotonic_ns (QPC) + time.time_ns (UTC):

  P1 marker connect       one connection opened at a recorded instant (timestamp alignment: ETW connect event vs marker)
  P2 data transfer        2,000 small TCP_NODELAY messages each way (are send/receive, sequence/ACK fields present?)
  P3 receiver stall       the receiver stops reading for 1.0 s while the sender fills the buffers (does any window / zero-window /
                          send-blocked information appear? does the socket-level provider show the late read?)
  P4 SYN retransmission   connects to a full-backlog listener (the stack retries the SYN: does a retransmission event appear?)
Writes the markers as JSON (stdout and --out). Bounded to about 10 s. No setting is changed.
"""
import argparse, json, socket, threading, time

def now(): return {"mono_ns": time.monotonic_ns(), "utc_ns": time.time_ns()}

def ports(s):
    try: a, b = s.getsockname(), s.getpeername(); return {"local": a[1], "remote": b[1]}
    except OSError: return {"local": s.getsockname()[1], "remote": None}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=None); a = ap.parse_args()
    M = {"tool": "o1_etw_feasibility_traffic.py", "clock": "time.monotonic_ns (QPC) and time.time_ns (UTC)", "phases": []}
    # P1 marker connect
    ls = socket.socket(); ls.bind(("127.0.0.1", 0)); ls.listen(4)
    t = now(); c = socket.create_connection(ls.getsockname()); s, _ = ls.accept(); t2 = now()
    M["phases"].append({"phase": "P1_marker_connect", "before": t, "after": t2, "client": ports(c), "server_port": ls.getsockname()[1]})
    # P2 data transfer
    for x in (c, s): x.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    t = now()
    for _ in range(2000): c.sendall(b"x"); s.recv(1); s.sendall(b"y"); c.recv(1)
    M["phases"].append({"phase": "P2_data_transfer", "start": t, "end": now(), "client": ports(c), "messages_each_way": 2000})
    # P3 receiver stall: the server side does not read for 1 s while the client keeps sending (non-blocking, counts what was accepted)
    c.setblocking(False); sent = 0; blocked_at = None; t = now(); chunk = b"z" * 16384
    while time.monotonic_ns() - t["mono_ns"] < 1.0e9:
        try: sent += c.send(chunk)
        except BlockingIOError:
            if blocked_at is None: blocked_at = now()
            time.sleep(0.005)
    stall_end = now(); c.setblocking(True)
    got = 0; s.settimeout(2.0)
    try:
        while got < sent: got += len(s.recv(1 << 20))
    except socket.timeout: pass
    M["phases"].append({"phase": "P3_receiver_stall", "start": t, "stall_end": stall_end, "first_send_would_block": blocked_at, "drained": now(),
                        "bytes_accepted_by_socket": sent, "bytes_read_after_stall": got, "client": ports(c)})
    c.close(); s.close(); ls.close()
    # P4 SYN retransmission against a full backlog
    ls = socket.socket(); ls.bind(("127.0.0.1", 0)); ls.listen(0); addr = ls.getsockname(); held = []; out = []
    t = now()
    for i in range(6):
        k = socket.socket(); k.settimeout(3.0 if i == 5 else 0.5)
        try: k.connect(addr); out.append("connected")
        except Exception as e: out.append(type(e).__name__)
        held.append(k)
    M["phases"].append({"phase": "P4_syn_retransmission", "start": t, "end": now(), "server_port": addr[1], "outcomes": out,
                        "client_ports": [k.getsockname()[1] for k in held]})
    for k in held: k.close()
    ls.close()
    js = json.dumps(M, indent=1)
    if a.out: open(a.out, "w", encoding="utf-8").write(js)
    print(js)

if __name__ == "__main__":
    main()

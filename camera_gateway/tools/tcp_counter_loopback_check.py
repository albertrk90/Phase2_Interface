"""Does the system-wide IPv4 TCP MIB (GetTcpStatisticsEx) count LOOPBACK traffic? (O1 diagnosis, 13 Nov 2026)

Local-only check, no admin, no external traffic: everything stays on 127.0.0.1 with ephemeral ports
created and closed by this script. No setting is changed.

Test 1  segments: N small TCP_NODELAY messages over a private 127.0.0.1 connection (each echoed, so each
        is its own segment). If loopback is counted, OutSegs rises by >= ~2N more than in an equal idle
        control window.
Test 2  retransmission positive control (best effort): connect() to a 127.0.0.1 listener that never
        accepts and whose backlog is already full. If Windows silently drops the SYN, the client
        retransmits it and RetransSegs rises; if Windows refuses (RST), no retransmission occurs and the
        test is INCONCLUSIVE (it then shows nothing about retransmission counting).
Prints one JSON object.
"""
import ctypes, ctypes.wintypes as w, json, socket, sys, time

class MIB_TCPSTATS(ctypes.Structure):
    _fields_ = [(n, w.DWORD) for n in ("dwRtoAlgorithm", "dwRtoMin", "dwRtoMax", "dwMaxConn", "dwActiveOpens", "dwPassiveOpens",
                                       "dwAttemptFails", "dwEstabResets", "dwCurrEstab", "dwInSegs", "dwOutSegs", "dwRetransSegs",
                                       "dwInErrs", "dwOutRsts", "dwNumConns")]
def snap():
    s = MIB_TCPSTATS(); rc = ctypes.windll.iphlpapi.GetTcpStatisticsEx(ctypes.byref(s), 2)
    assert rc == 0, rc
    return {"out": s.dwOutSegs, "in": s.dwInSegs, "retrans": s.dwRetransSegs, "attempt_fails": s.dwAttemptFails, "active_opens": s.dwActiveOpens}
def delta(a, b): return {k: b[k] - a[k] for k in a}

def test1(n=20000):
    ls = socket.socket(); ls.bind(("127.0.0.1", 0)); ls.listen(1)
    c = socket.create_connection(ls.getsockname()); s, _ = ls.accept()
    for x in (c, s): x.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    a = snap(); t0 = time.monotonic()
    for _ in range(n):
        c.sendall(b"x"); s.recv(1); s.sendall(b"y"); c.recv(1)
    dt = time.monotonic() - t0; b = snap()
    c.close(); s.close(); ls.close()
    time.sleep(0.2)
    ca = snap(); time.sleep(dt); cb = snap()          # idle control of equal length
    return {"messages_each_way": n, "seconds": round(dt, 3), "test_delta": delta(a, b), "idle_control_delta": delta(ca, cb)}

def test2(wait_s=8.0):
    ls = socket.socket(); ls.bind(("127.0.0.1", 0)); ls.listen(0)
    addr = ls.getsockname(); fill = []; outcome = []
    a = snap()
    for i in range(6):                              # fill the backlog, then one more
        c = socket.socket(); c.settimeout(wait_s if i == 5 else 1.0)
        t0 = time.monotonic()
        try:
            c.connect(addr); outcome.append(("connected", round(time.monotonic() - t0, 3)))
        except Exception as e:                       # noqa: BLE001
            outcome.append((type(e).__name__ + ": " + str(e)[:60], round(time.monotonic() - t0, 3)))
        fill.append(c)
    b = snap()
    for c in fill: c.close()
    ls.close()
    return {"connect_outcomes": outcome, "delta": delta(a, b)}

if __name__ == "__main__":
    r1 = test1(); r2 = test2()
    extra = r1["test_delta"]["out"] - r1["idle_control_delta"]["out"]
    res = {"test1_segments": r1, "loopback_segments_counted": extra >= r1["messages_each_way"],
           "test1_extra_out_segments": extra,
           "test2_retransmission_control": r2,
           "test2_retransmission_observed": r2["delta"]["retrans"] > 0}
    print(json.dumps(res, indent=1))

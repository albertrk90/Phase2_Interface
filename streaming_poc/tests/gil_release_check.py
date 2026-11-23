"""Offline: does PyAV release the GIL while FFmpeg is blocked writing?

No network: the muxer writes MPEG-TS into a local Windows named pipe (created
here with ctypes; FFmpeg opens it as a plain file path) that nobody reads for
3 s, so FFmpeg's C-level write blocks once the 4 KiB pipe buffer is full --
the same situation as a TCP send to a stalled server. A second thread counts
10 ms ticks meanwhile.
If the ticks keep coming, the GIL is released during the blocked write and a
sender THREAD is enough to keep frame generation running during an outage.

Prints JSON; exit code 0 when ticks continued during the blocked write.
"""
import json
import os
import pathlib
import sys
import threading
import time
from fractions import Fraction

POC = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))

import av  # noqa: E402
import synthetic_stereo as ss  # noqa: E402


def named_pipe():
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateNamedPipeW.restype = wintypes.HANDLE
    name = r"\\.\pipe\phase2_poc_gil_{}".format(os.getpid())
    PIPE_ACCESS_INBOUND, PIPE_TYPE_BYTE, PIPE_WAIT = 0x1, 0x0, 0x0
    h = k32.CreateNamedPipeW(name, PIPE_ACCESS_INBOUND, PIPE_TYPE_BYTE | PIPE_WAIT, 1, 4096, 4096, 0, None)
    if h in (None, wintypes.HANDLE(-1).value):
        raise OSError(ctypes.get_last_error(), "CreateNamedPipeW failed")

    def read_all():
        buf = ctypes.create_string_buffer(1 << 16)
        n = wintypes.DWORD()
        total = 0
        while k32.ReadFile(h, buf, len(buf), ctypes.byref(n), None) and n.value:
            total += n.value
        return total
    return name, read_all, lambda: k32.CloseHandle(h)


def main():
    name, read_all, close_pipe = named_pipe()
    ticks = []
    stop = threading.Event()

    def ticker():
        while not stop.is_set():
            ticks.append(time.monotonic())
            time.sleep(0.01)

    state = {"block_started": None, "unblocked": None, "error": None, "frames_muxed": 0}

    def writer():
        try:
            out = av.open("file:" + name, mode="w", format="mpegts")
            st = out.add_stream("libx264", rate=20)
            st.width, st.height, st.pix_fmt = ss.WIDTH, ss.HEIGHT, "yuv420p"
            st.codec_context.options = {"preset": "ultrafast", "tune": "zerolatency"}
            for s in range(400):
                f = av.VideoFrame(ss.WIDTH, ss.HEIGHT, "yuv420p")
                f.planes[0].update(ss.make_luma(s, 0, 0))
                for p in f.planes[1:]:
                    p.update(b"\x80" * p.buffer_size)
                f.pts = s
                f.time_base = Fraction(1, 20)
                t = time.monotonic()
                for pkt in st.encode(f):
                    out.mux(pkt)
                state["frames_muxed"] = s + 1
                if time.monotonic() - t > 0.5 and state["block_started"] is None:
                    state["block_started"] = t
                    state["unblocked"] = time.monotonic()
                    break
            out.close()
        except Exception as e:                      # noqa: BLE001
            state["error"] = repr(e)

    tk = threading.Thread(target=ticker, daemon=True)
    tk.start()
    wt = threading.Thread(target=writer, daemon=True)
    wt.start()
    # leave the pipe unread for 2 s after the writer has filled it
    time.sleep(3.0)
    t_drain = time.monotonic()
    drained = 0

    def drain():
        nonlocal drained
        drained = read_all()

    dt = threading.Thread(target=drain, daemon=True)
    dt.start()
    wt.join(timeout=20)
    stop.set()
    dt.join(timeout=2)
    close_pipe()
    blocked_ticks = [t for t in ticks if t < t_drain]
    gaps = [b - a for a, b in zip(blocked_ticks, blocked_ticks[1:])]
    res = {"pyav": av.__version__, "frames_muxed_before_block": state["frames_muxed"],
           "writer_error": state["error"],
           "ticks_while_pipe_unread": len(blocked_ticks),
           "max_tick_gap_ms_while_pipe_unread": round(max(gaps) * 1000, 1) if gaps else None,
           "writer_blocked_s": round(state["unblocked"] - state["block_started"], 2)
           if state["block_started"] else None,
           "bytes_drained": drained}
    res["gil_released_during_blocked_write"] = bool(gaps) and max(gaps) < 0.2 and \
        res["writer_blocked_s"] is not None and res["writer_blocked_s"] > 1.0
    print(json.dumps(res, indent=2))
    return 0 if res["gil_released_during_blocked_write"] else 1


if __name__ == "__main__":
    sys.exit(main())

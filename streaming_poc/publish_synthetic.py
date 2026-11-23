"""Task 04B gateway stand-in: synthetic stereo -> H.264 + SEI -> local RTSP.

For one camera ID (A or B) this generates the left and right synthetic frames
at a fixed rate, stamps each pair with one sequence number and one capture
time, encodes each eye as H.264 Constrained Baseline with no B-frames (the
settings the OAK VideoEncoder will use), inserts the FrameMeta SEI before the
first slice of every access unit, and publishes the two eyes to two MediaMTX
paths (cam<ID>_left, cam<ID>_right) over RTSP/TCP.

STRUCTURE (since the final Task 04B fixes):

  * GENERATION (main thread) never blocks on the network. It produces a
    pair every 1/fps on the monotonic clock, stamps the capture times and
    hands the pair to a bounded LatestQueue (--queue-pairs, default 2). If the
    queue is full the OLDEST pair is discarded and counted -- a latest-frame
    policy, so an outage can never build an unbounded transmission backlog.
    Every generated pair is logged in generated.csv.
  * SENDING (one thread) owns the encoders, the RTSP connections and every
    (re)connection attempt, which may block for --io-timeout. While the link
    is down it does not consume the queue, so after recovery it sends at most
    --queue-pairs pairs that are at most that many frame periods old.
  * CONNECT BEFORE TAKING A FRAME (since the G1 run, where a pair taken
    before a lazy connect was sent ~1.65 s old after the server returned):
    PyAV's RTSP output connects inside the container header write
    (ANNOUNCE/SETUP/RECORD), which PyAV otherwise performs during the first
    mux. The sender now writes the header explicitly (start_encoding, bounded
    by --open-timeout) BEFORE it takes a pair from the queue, so no frame is
    in hand while a connection attempt blocks; generation and the bounded
    queue are unaffected. link_connected is logged when the header is
    written; link_up only after the first SUCCESSFUL frame write; a failed
    connection or first write is link_connect_failed, a failure after that
    is link_down.
  * AGE GUARD (defence in depth): a pair older than --max-send-age-ms when
    the sender takes it is discarded BEFORE encoding (so the H.264 stream
    stays decodable) and counted as skipped_stale. Burst-stall frames are
    exempt (they are late by design).

PyAV releases the GIL while FFmpeg is blocked in a write (verified offline:
tests/gil_release_check.py), so a sender thread is enough to keep generation
on schedule.

LOCALHOST ONLY. The URL is checked by poc_common.check_local_url(): loopback
hosts only, never ports 8080/8081 (COROL). No camera, robot or COROL code is
involved.

Fault injection (for gate G1), keyed on each frame's CAPTURE time and applied
in the sender, i.e. below the generation queue (it models the transport):
    --stall AT_S:DUR_MS:MODE   delivery pause at AT_S seconds for DUR_MS.
                               MODE drop  = frames captured in the pause are
                                            never sent (sequence gap);
                               MODE burst = frames captured in the pause are
                                            encoded on time but HELD, and all
                                            sent when it ends (the Stage D
                                            backlog pattern; not limited by the
                                            generation queue).
    --drop AT_S:N              do not send N consecutive frames from AT_S.
Server restarts are done by the orchestrator; the sender notices, logs and
reconnects with backoff (0.25 s doubling to --reconnect-max-s).

Outputs (results/pub_<stamp>_<camera>_<label>/): events.jsonl, report.json,
sent.csv (one row per eye per frame: the exact metadata written into its SEI),
generated.csv (one row per generated pair: capture stamp, lateness, queue
depth, any pair the queue discarded).

Example (after MediaMTX is running; see README):
    .venv\\Scripts\\python.exe publish_synthetic.py --camera A --seconds 660 --frame-end sei ^
        --stall 120:300:burst --stall 240:700:burst --stall 360:700:drop --drop 480:5
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from fractions import Fraction

import av

import poc_common as pc
import synthetic_stereo as ss

HERE = pathlib.Path(__file__).resolve().parent

# Ground truth of what went into each frame's SEI, for the end-to-end
# metadata comparison against the receiver's arrivals.csv.
SENT_FIELDS = ["eye", "seq", "t_dev_ns", "t_host_mono_ns", "t_utc_ns", "flags", "host",
               "session", "trial", "config_id", "bytes", "t_sent_mono_ns"]
GEN_FIELDS = ["seq", "t_mono_ns", "t_utc_ns", "late_ms", "queue_depth", "discarded_seq",
              "discard_link_state"]


def parse_stall(text):
    try:
        at, dur, mode = text.split(":")
        at, dur = float(at), float(dur)
    except ValueError:
        raise argparse.ArgumentTypeError("--stall needs AT_S:DUR_MS:MODE, e.g. 120:300:burst")
    if mode not in ("drop", "burst") or at < 0 or not 0 < dur <= 10000:
        raise argparse.ArgumentTypeError("--stall MODE is drop|burst; 0 < DUR_MS <= 10000")
    return {"at_s": at, "dur_ms": dur, "mode": mode}


def parse_drop(text):
    try:
        at, n = text.split(":")
        at, n = float(at), int(n)
    except ValueError:
        raise argparse.ArgumentTypeError("--drop needs AT_S:N, e.g. 480:5")
    if at < 0 or not 0 < n <= 1000:
        raise argparse.ArgumentTypeError("--drop N must be 1..1000")
    return {"at_s": at, "n": n}


@dataclass
class FramePair:
    seq: int
    t_mono: int
    t_utc: int
    lumas: dict             # eye -> bytes


class LatestQueue:
    """Bounded hand-off from generation to sending. Holds at most `maxlen`
    pairs; putting into a full queue discards the OLDEST pair, which is
    returned so the caller can account for it."""

    def __init__(self, maxlen):
        if maxlen < 1:
            raise ValueError("queue must hold at least one pair")
        self.maxlen = maxlen
        self._d = deque()
        self._cv = threading.Condition()
        self.discarded = 0
        self.max_depth = 0
        self.closed = False

    def put(self, item):
        with self._cv:
            dropped = None
            if len(self._d) >= self.maxlen:
                dropped = self._d.popleft()
                self.discarded += 1
            self._d.append(item)
            self.max_depth = max(self.max_depth, len(self._d))
            self._cv.notify()
            return dropped

    def get(self, timeout):
        with self._cv:
            if not self._d and not self.closed:
                self._cv.wait(timeout)
            return self._d.popleft() if self._d else None

    def close(self):
        with self._cv:
            self.closed = True
            self._cv.notify_all()

    def __len__(self):
        with self._cv:
            return len(self._d)


class EyeOutput:
    """One publish session (one eye): encoder + muxer, SEI insertion.
    `opener` returns an output container; the default is RTSP to `url`.
    Tests pass an opener that writes to an in-memory sink."""

    def __init__(self, url, args, opener=None):
        self.url = pc.check_local_url(url)
        self.args = args
        self.opener = opener or self._rtsp_open
        self.out = None
        self.stream = None
        self.pts0 = None
        self.profile_idc = None
        self._chroma = None
        self.writes = 0

    def _rtsp_open(self):
        return av.open(self.url, mode="w", format="rtsp", options={"rtsp_transport": "tcp"},
                       timeout=(self.args.open_timeout, self.args.io_timeout))

    def open(self):
        a = self.args
        self.out = self.opener()
        st = self.out.add_stream(a.encoder, rate=a.fps)
        st.width, st.height, st.pix_fmt = ss.WIDTH, ss.HEIGHT, "yuv420p"
        st.bit_rate = int(a.bitrate_kbps * 1000)
        st.codec_context.time_base = Fraction(1, a.fps)
        if a.encoder == "libx264":
            st.codec_context.options = {
                "profile": "baseline", "preset": a.preset, "tune": "zerolatency",
                "x264-params": "keyint={0}:min-keyint={0}:scenecut=0:bframes=0:"
                               "repeat-headers=1:nal-hrd=cbr:vbv-maxrate={1}:"
                               "vbv-bufsize={2}".format(a.keyint, int(a.bitrate_kbps),
                                                        int(a.bitrate_kbps / a.fps * 2)),
            }
        else:
            st.codec_context.gop_size = a.keyint
            st.codec_context.max_b_frames = 0
        self.stream = st
        self.pts0 = None
        self.writes = 0

    def connect(self):
        """Write the container header now. For RTSP this is the connection
        itself; may block up to --open-timeout and raises on failure."""
        self.out.start_encoding()

    def _frame(self, luma: bytes, pts: int) -> av.VideoFrame:
        f = av.VideoFrame(ss.WIDTH, ss.HEIGHT, "yuv420p")
        y = f.planes[0]
        if y.line_size == ss.WIDTH:
            y.update(luma)
        else:
            pad = b"\0" * (y.line_size - ss.WIDTH)
            y.update(b"".join(luma[r * ss.WIDTH:(r + 1) * ss.WIDTH] + pad
                              for r in range(ss.HEIGHT)))
        if self._chroma is None:
            self._chroma = [b"\x80" * p.buffer_size for p in f.planes[1:]]
        for p, c in zip(f.planes[1:], self._chroma):
            p.update(c)
        f.pts = pts
        f.time_base = Fraction(1, self.args.fps)
        return f

    def encode(self, luma: bytes, meta: pc.FrameMeta) -> list:
        """Encode one frame; return prepared packets (not yet muxed)."""
        if self.pts0 is None:
            self.pts0 = meta.seq
        sei = pc.build_sei_nal(meta)
        out = []
        for pkt in self.stream.encode(self._frame(luma, meta.seq - self.pts0)):
            data = bytes(pkt)
            if self.profile_idc is None:
                self.profile_idc = pc.sps_profile_idc(bytes(self.stream.codec_context.extradata or b"")) \
                    or pc.sps_profile_idc(data)
            # --frame-end: a trailing NAL that lets the receiver's H.264 parser
            # close this access unit without waiting for the next one.
            au = pc.append_frame_end(pc.insert_sei_before_vcl(data, sei), self.args.frame_end, meta.seq)
            out.append((au, pkt.pts, pkt.dts, pkt.time_base, pkt.is_keyframe))
        return out

    def mux(self, prepared) -> int:
        """Write prepared packets. Raises on link loss (may block up to the I/O timeout)."""
        n = 0
        for au, pts, dts, tb, key in prepared:
            new = av.Packet(au)
            new.pts, new.dts, new.time_base = pts, dts, tb
            new.stream = self.stream
            new.is_keyframe = key
            self.out.mux(new)
            n += new.size
        self.writes += 1
        return n

    def close(self):
        out, self.out = self.out, None
        if out is not None:
            try:
                out.close()
            except Exception:
                pass


class Sender(threading.Thread):
    """Consumes the LatestQueue: fault injection, encode, (re)connect, mux."""

    def __init__(self, args, outs, queue, log, sent_writer, t0_mono, host, cam_code):
        super().__init__(name="sender", daemon=True)
        self.args, self.outs, self.q, self.log = args, outs, queue, log
        self.sent_writer, self.t0, self.host, self.cam_code = sent_writer, t0_mono, host, cam_code
        self.state = "down"                 # down | connecting | up
        self.retry_at = 0.0
        self.backoff = pc.Backoff(lo=0.25, hi=args.reconnect_max_s, cur=0.25)
        self.connect_started = None
        self.held = []                      # burst stall: (pair, prepared per eye)
        self.stall_state = {}
        self.drop_left = {}
        self.c = {"sent": 0, "dropped_stall": 0, "dropped_drop": 0, "burst_sent": 0,
                  "unsent_link_down": 0, "skipped_stale": 0, "bytes": 0, "link_downs": 0,
                  "connect_failures": 0, "connects": 0}
        self.max_age_ns = int(args.max_send_age_ms * 1e6) if args.max_send_age_ms > 0 else None
        self.lock = threading.Lock()
        # A write that eventually fails can block for the whole I/O timeout
        # while the link still LOOKS up. Its start is recorded so that queue
        # discards during that time are attributed to the outage.
        self.write_started = None
        self.failed_intervals = []          # (start_mono_ns, end_mono_ns)

    @property
    def link_up(self):
        return self.state == "up"

    def _wait_backoff(self):
        while self.state == "down" and time.monotonic() < self.retry_at:
            if self.q.closed and not len(self.q):
                return
            time.sleep(min(0.05, max(0.0, self.retry_at - time.monotonic())))

    def _open(self):
        self.connect_started = time.monotonic()
        try:
            for o in self.outs.values():
                o.close()
                o.open()
            for o in self.outs.values():
                o.connect()
            self.state = "connecting"
            self.log.emit("link_connected", {"connect_s": round(time.monotonic() - self.connect_started, 3),
                                             "note": "header written before taking a frame; "
                                                     "link_up follows the first frame write"})
        except Exception as e:                       # noqa: BLE001
            self._fail(e, None)

    def _fail(self, e, seq):
        now = pc.mono_ns()
        self.failed_intervals.append((self.write_started or now, now))
        self.write_started = None
        lost = len(self.held)
        self.held.clear()
        for o in self.outs.values():
            o.close()
        delay = self.backoff.next()
        self.retry_at = time.monotonic() + delay
        if self.state == "up":
            self.c["link_downs"] += 1
            kind = "link_down"
        else:
            self.c["connect_failures"] += 1
            kind = "link_connect_failed"
        self.state = "down"
        self.c["unsent_link_down"] += lost
        self.log.emit(kind, {"seq": seq, "error": "{}: {}".format(type(e).__name__, e),
                             "retry_in_s": delay, "held_burst_frames_lost": lost})

    def _meta(self, pair, eye, flags):
        return pc.FrameMeta(self.args.camera, eye, pair.seq, pair.t_mono - self.t0, pair.t_mono,
                            pair.t_utc, self.host, self.args.session, self.args.trial or self.args.label,
                            self.args.config_id, pc.FLAG_SYNTHETIC | flags)

    def _write(self, pair, prepared, flags):
        for eye in ("left", "right"):
            n = self.outs[eye].mux(prepared[eye])
            self.c["bytes"] += n
            m = self._meta(pair, eye, flags)
            self.sent_writer.writerow({"eye": eye, "seq": pair.seq, "t_dev_ns": m.t_dev_ns,
                                       "t_host_mono_ns": pair.t_mono, "t_utc_ns": pair.t_utc,
                                       "flags": m.flags, "host": self.host, "session": m.session,
                                       "trial": m.trial, "config_id": m.config_id, "bytes": n,
                                       "t_sent_mono_ns": pc.mono_ns()})

    def _faults(self, pair):
        """'drop', 'burst' or None for this pair, from its capture time."""
        t_rel = (pair.t_mono - self.t0) / 1e9
        in_stall = None
        for i, s in enumerate(self.args.stall):
            if s["at_s"] <= t_rel < s["at_s"] + s["dur_ms"] / 1000:
                in_stall = i
        for i in list(self.stall_state):
            if i != in_stall:
                st = self.stall_state.pop(i)
                self.log.emit("stall_end", {"index": i, "mode": self.args.stall[i]["mode"],
                                            "seq_first": st[0], "seq_last": st[-1], "count": len(st)})
        if in_stall is not None:
            if in_stall not in self.stall_state:
                self.stall_state[in_stall] = []
                self.log.emit("stall_start", {"index": in_stall, **self.args.stall[in_stall]})
            self.stall_state[in_stall].append(pair.seq)
            return self.args.stall[in_stall]["mode"]
        for i, d in enumerate(self.args.drop):
            if i not in self.drop_left and t_rel >= d["at_s"]:
                self.drop_left[i] = d["n"]
                self.log.emit("drop_start", {"index": i, "seq_first": pair.seq, "count": d["n"]})
        dropping = next((i for i, n in self.drop_left.items() if n > 0), None)
        if dropping is not None:
            self.drop_left[dropping] -= 1
            return "drop_n"
        return None

    def run(self):
        while True:
            if self.state == "down":
                self._wait_backoff()
                if self.q.closed and not len(self.q):
                    break
                self._open()
                if self.state == "down":
                    continue
            pair = self.q.get(timeout=0.1)
            if pair is None:
                if self.q.closed:
                    break
                continue
            fault = self._faults(pair)
            if fault == "drop":
                self.c["dropped_stall"] += 1
                continue
            if fault == "drop_n":
                self.c["dropped_drop"] += 1
                continue
            age_ns = pc.mono_ns() - pair.t_mono
            if fault is None and self.max_age_ns and age_ns > self.max_age_ns:
                self.c["skipped_stale"] += 1
                self.log.emit("stale_skipped", {"seq": pair.seq, "age_ms": round(age_ns / 1e6, 1),
                                                "state": self.state})
                continue
            flags = pc.FLAG_BURST if fault == "burst" else 0
            try:
                prepared = {eye: self.outs[eye].encode(pair.lumas[eye], self._meta(pair, eye, flags))
                            for eye in ("left", "right")}
                if fault == "burst":
                    self.held.append((pair, prepared))
                    continue
                self.write_started = pc.mono_ns()
                for hp, hprep in self.held:
                    self._write(hp, hprep, pc.FLAG_BURST)
                    self.c["burst_sent"] += 1
                self.held.clear()
                self._write(pair, prepared, 0)
                self.write_started = None
                self.c["sent"] += 1
                if self.state == "connecting":
                    self.state = "up"
                    self.c["connects"] += 1
                    self.backoff.reset()
                    self.log.emit("link_up", {"first_seq": pair.seq,
                                              "connect_s": round(time.monotonic() - self.connect_started, 3),
                                              "note": "first successful write on this connection"})
            except Exception as e:                   # noqa: BLE001
                self.c["unsent_link_down"] += 1
                self._fail(e, pair.seq)
        if self.held:
            self.c["unsent_link_down"] += len(self.held)
            self.held.clear()
        for o in self.outs.values():
            o.close()


def build_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", choices=("A", "B"), required=True)
    ap.add_argument("--server", default="rtsp://127.0.0.1:8554")
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--encoder", default="libx264",
                    choices=("libx264", "h264_nvenc", "h264_qsv", "h264_mf"))
    ap.add_argument("--preset", default="veryfast")
    ap.add_argument("--bitrate-kbps", type=float, default=8000.0, help="per eye")
    ap.add_argument("--keyint", type=int, default=20, help="frames between IDRs")
    ap.add_argument("--frame-end", choices=pc.FRAME_END_MODES, default="none",
                    help="append an AUD or end-of-frame SEI after each frame's last slice "
                         "so the receiver's parser can release it at once (default none)")
    ap.add_argument("--queue-pairs", type=int, default=2,
                    help="generation->sender queue bound (latest-frame policy)")
    ap.add_argument("--max-send-age-ms", type=float, default=None,
                    help="discard (before encoding) a pair older than this when the sender takes it; "
                         "default (queue_pairs + 1) frame periods; 0 disables")
    ap.add_argument("--stall", type=parse_stall, action="append", default=[])
    ap.add_argument("--drop", type=parse_drop, action="append", default=[])
    ap.add_argument("--session", default="poc")
    ap.add_argument("--trial", default="")
    ap.add_argument("--config-id", type=int, default=1)
    ap.add_argument("--label", default="run")
    ap.add_argument("--open-timeout", type=float, default=3.0)
    ap.add_argument("--io-timeout", type=float, default=3.0)
    ap.add_argument("--reconnect-max-s", type=float, default=1.0,
                    help="cap of the reconnect backoff (0.25 s doubling)")
    ap.add_argument("--done-flag", default=None,
                    help="file written after the last frame has been sent (receivers wait for it)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args(argv)
    if a.max_send_age_ms is None:
        a.max_send_age_ms = (a.queue_pairs + 1) * 1000.0 / a.fps
    return a


def main(argv=None, opener_factory=None):
    """opener_factory(eye) -> opener, for offline tests only."""
    args = build_args(argv)
    urls = {eye: pc.check_local_url("{}/cam{}_{}".format(args.server.rstrip("/"),
                                                         args.camera, eye))
            for eye in ("left", "right")}
    out_dir = pathlib.Path(args.out) / "pub_{}_{}_{}".format(pc.stamp(), args.camera, args.label)
    out_dir.mkdir(parents=True, exist_ok=False)
    log = pc.EventLog(out_dir / "events.jsonl", "publisher_" + args.camera,
                      args.session, args.trial or args.label)
    host = pc.host_id()
    cam_code = pc.CAMERAS[args.camera]
    period_ns = int(1e9 / args.fps)
    total = int(args.seconds * args.fps)
    log.emit("run_start", {"argv": sys.argv[1:] if argv is None else argv, "urls": urls, "fps": args.fps,
                           "encoder": args.encoder, "bitrate_kbps": args.bitrate_kbps,
                           "keyint": args.keyint, "frame_end": args.frame_end,
                           "queue_pairs": args.queue_pairs, "max_send_age_ms": args.max_send_age_ms,
                           "stalls": args.stall, "drops": args.drop,
                           "pyav": av.__version__, "frames_planned": total})
    print("[pub {}] {} frames at {} fps -> {}".format(args.camera, total, args.fps,
                                                      ", ".join(urls.values())), flush=True)
    sent_fh = open(out_dir / "sent.csv", "w", newline="", encoding="utf-8")
    sent_writer = csv.DictWriter(sent_fh, fieldnames=SENT_FIELDS)
    sent_writer.writeheader()
    gen_rows = []                           # written at the end, with final discard attribution

    outs = {eye: EyeOutput(url, args, opener_factory(eye) if opener_factory else None)
            for eye, url in urls.items()}
    q = LatestQueue(args.queue_pairs)
    # Build both synthetic backgrounds before the clock starts: the first
    # make_luma per eye computes its background in pure Python (~100 ms).
    for eye in ("left", "right"):
        ss.make_luma(0, pc.EYES[eye], cam_code)
    t0_mono = pc.mono_ns()
    sender = Sender(args, outs, q, log, sent_writer, t0_mono, host, cam_code)
    sender.start()
    gen = {"generated": 0, "late_frames": 0, "max_late_ms": 0.0,
           "discarded_link_down": 0, "discarded_link_up": 0}
    seq = 0
    try:
        while seq < total:
            nominal = t0_mono + seq * period_ns
            wait = (nominal - pc.mono_ns()) / 1e9
            if wait > 0:
                time.sleep(wait)
            t_mono, t_utc = pc.mono_ns(), pc.utc_ns()
            late_ms = (t_mono - nominal) / 1e6
            if late_ms > 1000 / args.fps:
                gen["late_frames"] += 1
            gen["max_late_ms"] = max(gen["max_late_ms"], late_ms)
            pair = FramePair(seq, t_mono, t_utc,
                             {eye: ss.make_luma(seq, pc.EYES[eye], cam_code) for eye in ("left", "right")})
            dropped = q.put(pair)
            state = "up" if sender.link_up else "down"
            gen["generated"] += 1
            gen_rows.append({"seq": seq, "t_mono_ns": t_mono, "t_utc_ns": t_utc,
                             "late_ms": round(late_ms, 3), "queue_depth": len(q),
                             "discarded_seq": dropped.seq if dropped else "",
                             "discard_link_state": state if dropped else ""})
            seq += 1
    except KeyboardInterrupt:
        log.emit("interrupted", {"seq": seq})
    finally:
        q.close()
        sender.join(timeout=args.io_timeout + args.open_timeout + 5)
        for o in outs.values():
            o.close()
        # Final attribution of queue discards: "down" if the sender knew the
        # link was down, or if it was blocked in a write that then failed.
        for r in gen_rows:
            if r["discard_link_state"] == "up" and any(a <= r["t_mono_ns"] <= b
                                                       for a, b in sender.failed_intervals):
                r["discard_link_state"] = "down (blocked in a write that failed)"
            if r["discard_link_state"]:
                gen["discarded_link_" + ("up" if r["discard_link_state"] == "up" else "down")] += 1
        with open(out_dir / "generated.csv", "w", newline="", encoding="utf-8") as gen_fh:
            gw = csv.DictWriter(gen_fh, fieldnames=GEN_FIELDS)
            gw.writeheader()
            gw.writerows(gen_rows)
        counts = dict(sender.c)
        # frames the queue discarded while the link was down are link-down losses
        counts["unsent_link_down"] += gen["discarded_link_down"]
        counts["queue_discarded_link_up"] = gen["discarded_link_up"]
        counts["queue_discarded_total"] = q.discarded
        counts["late_frames"] = gen["late_frames"]
        profile = next((o.profile_idc for o in outs.values() if o.profile_idc), None)
        report = {"camera": args.camera, "label": args.label, "frames_planned": total,
                  "frame_end": args.frame_end, "queue_pairs": args.queue_pairs,
                  "max_send_age_ms": args.max_send_age_ms, "last_seq": seq - 1, "generated": gen["generated"], "counts": counts,
                  "queue_max_depth": q.max_depth, "max_late_ms": round(gen["max_late_ms"], 2),
                  "sps_profile_idc": profile, "baseline": profile == 66,
                  "sender_alive_at_end": sender.is_alive(), "out_dir": str(out_dir)}
        log.emit("run_end", report)
        log.close()
        sent_fh.close()
        (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if args.done_flag:
            # written only after the sender has finished, so a receiver that
            # waits for it plus a drain period has had every frame offered
            pathlib.Path(args.done_flag).write_text(
                json.dumps({"camera": args.camera, "last_seq": seq - 1, "t_utc_ns": pc.utc_ns(),
                            "out_dir": str(out_dir)}), encoding="utf-8")
        print("[pub {}] done: {}".format(args.camera, json.dumps(counts)), flush=True)
    return out_dir


if __name__ == "__main__":
    main()
    sys.exit(0)

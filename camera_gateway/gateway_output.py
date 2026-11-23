"""Camera A gateway output (Task 06): muxing of already-encoded H.264 access units
and one independent sender thread per eye.

PreEncodedOutput: one eye's container. Its stream is created from a TEMPLATE
  demuxed from the camera's own first recovery access unit (SPS + PPS + IDR), so
  the container (MPEG-TS header, or the RTSP ANNOUNCE/SDP) carries the camera's
  parameter sets and no encoder is ever opened (verified offline: PyAV 19.0.2
  leaves the template codec context closed and its extradata unchanged through
  start_encoding()). Packets get pts = dts = seq - first seq of the connection,
  time base 1/fps (no B-frames).

EyeSender: owns its eye's (re)connections. It never touches the device: the
  capture thread only fills the GopQueue. Connect first (header written before a
  frame is taken), then request a GOP resync so the new connection starts at a
  recovery point. Frames older than --max-send-age-ms since capture are discarded
  together with their GOP (GopQueue resync). On a write error: link_down, close,
  capped backoff (0.25 s doubling to reconnect_max_s), reconnect. In file mode
  every connection is a new segment cam<ID>_<eye>_seg<k>.ts (the Unity file-replay
  layout), so a simulated link break produces a reconnect the receiver can replay.

LOCALHOST ONLY: RTSP URLs pass poc_common.check_local_url (loopback, never 8080/8081).
"""
from __future__ import annotations

import csv
import io
import pathlib
import threading
from fractions import Fraction

import av

import gateway_core as gc
from gateway_core import pc


def template_stream(recovery_au: bytes, param_sets: bytes = b""):
    """(container, stream) demuxed from an in-memory recovery AU (SPS/PPS prepended if given)."""
    data = bytes(param_sets) + bytes(recovery_au) if param_sets and not gc.inspect_au(recovery_au).has_sps else bytes(recovery_au)
    tin = av.open(io.BytesIO(data), format="h264")
    st = tin.streams.video[0]
    if not st.codec_context.extradata or not st.codec_context.width:
        tin.close()
        raise gc.PackagingError("could not derive stream parameters from the recovery access unit")
    return tin, st


class PreEncodedOutput:
    def __init__(self, target: str, mode: str, fps: int, open_timeout: float = 3.0, io_timeout: float = 3.0, opener=None):
        if mode == "rtsp":
            target = pc.check_local_url(target)
        elif mode != "file":
            raise ValueError("mode must be rtsp or file")
        self.target, self.mode, self.fps = target, mode, fps
        self.open_timeout, self.io_timeout = open_timeout, io_timeout
        self.opener = opener
        self.out = self.stream = self._tin = None
        self.seq0 = None
        self.writes = 0

    def _open_container(self):
        if self.opener is not None:
            return self.opener()
        if self.mode == "rtsp":
            return av.open(self.target, mode="w", format="rtsp", options={"rtsp_transport": "tcp"},
                           timeout=(self.open_timeout, self.io_timeout))
        return av.open(self.target, mode="w", format="mpegts")

    def connect(self, recovery_au: bytes, param_sets: bytes = b""):
        """Create the stream from the camera's parameters and write the header (= the RTSP connection)."""
        self._tin, tmpl = template_stream(recovery_au, param_sets)
        self.out = self._open_container()
        self.stream = self.out.add_stream_from_template(tmpl)
        self.out.start_encoding()
        if self.stream.codec_context.is_open:
            raise gc.PackagingError("an encoder was opened on the pre-encoded stream")
        self.seq0, self.writes = None, 0

    def write(self, au: bytes, seq: int, keyframe: bool) -> int:
        if self.seq0 is None:
            self.seq0 = seq
        p = av.Packet(au)
        p.pts = p.dts = seq - self.seq0
        p.time_base = Fraction(1, self.fps)
        p.stream = self.stream
        p.is_keyframe = keyframe
        self.out.mux(p)
        self.writes += 1
        return p.size

    def close(self):
        out, self.out = self.out, None
        tin, self._tin = self._tin, None
        for c in (out, tin):
            if c is not None:
                try:
                    c.close()
                except Exception:              # noqa: BLE001
                    pass


class ParamStore:
    """First recovery AU per eye (stream template), filled by the capture thread."""

    def __init__(self):
        self._cv = threading.Condition()
        self._au = {}
        self._ps = {}

    def offer(self, f: gc.CameraFrame):
        if f.recovery_point:
            with self._cv:
                if f.eye not in self._au:
                    self._au[f.eye] = f.au
                if f.info.has_sps:
                    self._ps[f.eye] = gc.parameter_sets(f.au)
                self._cv.notify_all()

    def wait(self, eye, timeout):
        with self._cv:
            if eye not in self._au:
                self._cv.wait(timeout)
            return self._au.get(eye), self._ps.get(eye, b"")


SENT_FIELDS = ("eye", "seq", "segment", "t_dev_ns", "t_host_mono_ns", "t_utc_ns", "flags", "keyframe", "bytes",
               "t_sent_mono_ns", "capture_to_send_ms")


class EyeSender(threading.Thread):
    def __init__(self, eye, queue: gc.GopQueue, params: ParamStore, make_output, log, sent_writer, sent_lock,
                 host, session, trial, frame_end="sei", max_send_age_ms=150.0, reconnect_max_s=1.0,
                 mono=pc.mono_ns, utc_minus_mono=gc.utc_minus_mono_ns, sleep=None,
                 stale_policy="resync", hard_max_age_ms=500.0):
        super().__init__(name="sender_" + eye, daemon=True)
        self.eye, self.q, self.params, self.make_output = eye, queue, params, make_output
        self.log, self.sent_writer, self.sent_lock = log, sent_writer, sent_lock
        self.host, self.session, self.trial, self.frame_end = host, session, trial, frame_end
        self.max_age_ns = int(max_send_age_ms * 1e6) if max_send_age_ms > 0 else None
        if stale_policy not in gc.STALE_POLICIES:
            raise ValueError("stale_policy must be one of {}".format(gc.STALE_POLICIES))
        self.stale_policy, self.hard_age_ns = stale_policy, int(hard_max_age_ms * 1e6)
        self.backoff = pc.Backoff(lo=0.25, hi=reconnect_max_s, cur=0.25)
        self.mono, self.utc_minus_mono = mono, utc_minus_mono
        self._stop = threading.Event()
        self._sleep = sleep or self._stop.wait
        self.out = None
        self.segment = 0
        self.state = "down"
        self.last_sent_seq = None
        self.c = {"sent": 0, "bytes": 0, "connects": 0, "connect_failures": 0, "link_downs": 0,
                  "skipped_stale": 0, "packaging_errors": 0, "keyframes_sent": 0, "sent_late": 0}

    def stop(self):
        self._stop.set()

    def _emit(self, kind, **kw):
        self.log.emit(kind, dict(eye=self.eye, segment=self.segment, **kw))

    def _connect(self) -> bool:
        au, ps = self.params.wait(self.eye, 0.2)
        if au is None:
            return False
        self.segment += 1
        out = self.make_output(self.eye, self.segment)
        try:
            out.connect(au, ps)
        except Exception as exc:                # noqa: BLE001
            out.close()
            self.c["connect_failures"] += 1
            d = self.backoff.next()
            self._emit("link_connect_failed", error="{}: {}".format(type(exc).__name__, exc), retry_in_s=d)
            self._sleep(d)
            return False
        self.out, self.state = out, "connected"
        self.c["connects"] += 1
        self.q.align("connect", segment=self.segment)              # a new connection starts at a recovery point
        self._emit("link_connected")
        return True

    def _down(self, exc):
        self.c["link_downs"] += 1
        if self.out is not None:
            self.out.close()
        self.out, self.state = None, "down"
        d = self.backoff.next()
        self._emit("link_down", error="{}: {}".format(type(exc).__name__, exc), retry_in_s=d)
        self.q.request_resync("link_down")
        self._sleep(d)

    def run(self):
        try:
            while not self._stop.is_set():
                if self.out is None:
                    self._connect()
                    continue
                f = self.q.get(0.1)
                if f is None:
                    continue
                now = self.mono()
                if self.max_age_ns is not None and now - f.t_host_mono_ns > self.max_age_ns:
                    if not gc.on_stale(self.q, f, now - f.t_host_mono_ns, self.stale_policy, self.hard_age_ns):
                        self.c["skipped_stale"] += 1
                        continue
                    self.c["sent_late"] += 1
                meta = gc.make_meta(f, self.host, self.session, self.trial, self.utc_minus_mono())
                try:
                    au = gc.package(f, meta, self.frame_end)
                except gc.PackagingError as exc:
                    self.c["packaging_errors"] += 1
                    self._emit("packaging_error", seq=f.seq, error=str(exc))
                    self.q.request_resync("packaging_error", seq=f.seq)
                    continue
                try:
                    n = self.out.write(au, f.seq, f.recovery_point)
                except Exception as exc:        # noqa: BLE001
                    self._down(exc)
                    continue
                t_sent = self.mono()
                if self.state != "up":
                    self.state = "up"
                    self.backoff.reset()
                    self._emit("link_up", first_seq=f.seq, keyframe=f.recovery_point)
                self.last_sent_seq = f.seq
                self.c["sent"] += 1
                self.c["bytes"] += n
                self.c["keyframes_sent"] += int(f.recovery_point)
                with self.sent_lock:
                    self.sent_writer.writerow({
                        "eye": self.eye, "seq": f.seq, "segment": self.segment, "t_dev_ns": meta.t_dev_ns,
                        "t_host_mono_ns": meta.t_host_mono_ns, "t_utc_ns": meta.t_utc_ns, "flags": meta.flags,
                        "keyframe": int(f.recovery_point), "bytes": n, "t_sent_mono_ns": t_sent,
                        "capture_to_send_ms": round((t_sent - f.t_host_mono_ns) / 1e6, 2)})
        finally:
            if self.out is not None:
                self.out.close()
                self.out = None
            self.state = "stopped"


def sent_writer(path: pathlib.Path):
    fh = open(path, "w", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=SENT_FIELDS)
    w.writeheader()
    return fh, w

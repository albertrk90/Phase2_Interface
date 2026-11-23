"""Camera A gateway core (Task 06): pure packaging and flow-control logic.

No DepthAI, no network, no device. Everything here is exercised offline by
tests/test_gateway.py with recorded or synthetic access units.

WHY THE SYNTHETIC PUBLISHER CANNOT BE REUSED AS IS
  * It queues RAW frames and encodes after dequeue, so dropping a queued frame
    is harmless. With on-device encoding every frame arrives already encoded:
    dropping a P-frame corrupts decoding until the next IDR. The latest-frame
    policy therefore becomes GOP-aware (GopQueue): any discontinuity (device
    queue gap, host overflow, stale frame, (re)connection) discards the queued
    frames and resumes only at the next recovery point (IDR, or SPS+PPS+I).
  * Its RTSP stream takes SPS/PPS from a live libx264 encoder. Here the stream
    parameters come from the camera's own first recovery access unit, and no
    encoder is ever opened (gateway_output.PreEncodedOutput).
  * Sequence numbers and capture times come from the device frames
    (EncodedFrame.getSequenceNum / getTimestamp / getTimestampDevice).

METADATA CARRIED PER FRAME (the FrameMeta v1 SEI of streaming_poc/poc_common,
the format the Unity and Python receivers already parse and validate):
  camera "A"; eye "left"/"right"; seq = device sequence number (shared by the
  rectified pair); t_dev_ns = device monotonic timestamp; t_host_mono_ns =
  DepthAI host-synchronised timestamp (dai::Clock = steady_clock = QPC on
  Windows, the same clock as time.monotonic_ns and Unity's Clocks.MonoNs;
  checked offline by tools/inspect_depthai_api.py); t_utc_ns = t_host_mono_ns
  + (host UTC - host monotonic) sampled at packaging; flags = 0 (FLAG_SYNTHETIC
  clear: a real camera frame); config_id = CONFIG_ID. The SEI is inserted before
  the first slice and an end-of-frame SEI (poc_common frame-end "sei") is
  appended after the last slice, so the receiver's H.264 parser closes the
  access unit without waiting for the next one (the Task 04B S7 fix).
"""
from __future__ import annotations

import pathlib
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field

sys.dont_write_bytecode = True          # never write __pycache__ into streaming_poc / camera_validation
ROOT = pathlib.Path(__file__).resolve().parents[1]
POC = ROOT / "streaming_poc"
if str(POC) not in sys.path:
    sys.path.insert(0, str(POC))

import poc_common as pc  # noqa: E402  (stdlib only; read-only import)

CAMERA = "A"
EYES = ("left", "right")
WIDTH, HEIGHT = 1280, 800
# config_id in every SEI: Camera A, StereoDepth rectification as approved (distortion
# correction ON, alpha unset, edge fill 0, no spec translation), 1280 x 800 GRAY8,
# on-device H.264 Baseline, no B-frames, CBR. 6001 = first gateway configuration.
CONFIG_ID = 6001

NAL_SLICE, NAL_IDR, NAL_SEI, NAL_SPS, NAL_PPS, NAL_AUD = 1, 5, 6, 7, 8, 9
SLICE_TYPES = {0: "P", 1: "B", 2: "I", 3: "SP", 4: "SI"}


# ----------------------------------------------------------------------------- H.264 access units
class _Bits:
    def __init__(self, data: bytes):
        self.d, self.i = data, 0

    def bit(self) -> int:
        if self.i >= len(self.d) * 8:
            raise ValueError("bitstream exhausted")
        b = (self.d[self.i >> 3] >> (7 - (self.i & 7))) & 1
        self.i += 1
        return b

    def ue(self) -> int:
        z = 0
        while self.bit() == 0:
            z += 1
            if z > 31:
                raise ValueError("bad exp-Golomb code")
        v = 0
        for _ in range(z):
            v = (v << 1) | self.bit()
        return (1 << z) - 1 + v


def slice_type(nal: bytes) -> str | None:
    """Slice type of a VCL NAL (header byte first): first_mb_in_slice ue(v), slice_type ue(v)."""
    try:
        rbsp = pc.remove_emulation_prevention(bytes(nal[1:16]))
        r = _Bits(rbsp)
        r.ue()
        return SLICE_TYPES.get(r.ue() % 5)
    except ValueError:
        return None


@dataclass
class AuInfo:
    nal_types: list
    has_idr: bool
    has_sps: bool
    has_pps: bool
    has_aud: bool
    vcl_count: int
    first_slice_type: str | None
    has_frame_meta: bool
    recovery_point: bool


def inspect_au(au: bytes) -> AuInfo:
    au = bytes(au)
    nals = pc.split_nals(au)
    types = [t for t, _s, _e in nals]
    vcl = [(t, s, e) for t, s, e in nals if t in pc.VCL_TYPES]
    first = slice_type(au[vcl[0][1]:vcl[0][2]]) if vcl else None
    meta, _err = pc.extract_meta(au)
    has_sps, has_pps, has_idr = NAL_SPS in types, NAL_PPS in types, NAL_IDR in types
    return AuInfo(types, has_idr, has_sps, has_pps, NAL_AUD in types, len(vcl), first, meta is not None,
                  bool(vcl) and (has_idr or (has_sps and has_pps and first == "I")))


def parameter_sets(au: bytes) -> bytes:
    """Annex-B SPS + PPS NAL units (4-byte start codes) found in an access unit, in order."""
    au = bytes(au)
    return b"".join(b"\x00\x00\x00\x01" + au[s:e] for t, s, e in pc.split_nals(au) if t in (NAL_SPS, NAL_PPS))


# ----------------------------------------------------------------------------- frames and metadata
@dataclass
class CameraFrame:
    eye: str
    seq: int
    t_dev_ns: int
    t_host_mono_ns: int
    au: bytes
    t_received_mono_ns: int
    frame_type: str | None = None          # EncodedFrame.getFrameType(): "I" | "P" | "B"
    width: int = WIDTH
    height: int = HEIGHT
    info: AuInfo = field(default=None, repr=False)

    def __post_init__(self):
        if self.info is None:
            self.info = inspect_au(self.au)

    @property
    def recovery_point(self) -> bool:
        return self.info.recovery_point


def td_ns(td) -> int:
    """datetime.timedelta -> integer ns (DepthAI timestamps are timedelta, 1 us resolution)."""
    return (td.days * 86_400 + td.seconds) * 1_000_000_000 + td.microseconds * 1_000


def frame_from_encoded(eye: str, msg, now_mono_ns: int) -> CameraFrame:
    """Adapter for depthai.EncodedFrame (duck-typed so tests can pass stand-ins)."""
    ft = msg.getFrameType()
    name = getattr(ft, "name", str(ft)).split(".")[-1]
    return CameraFrame(eye=eye, seq=int(msg.getSequenceNum()), t_dev_ns=td_ns(msg.getTimestampDevice()),
                       t_host_mono_ns=td_ns(msg.getTimestamp()), au=bytes(msg.getData()),
                       t_received_mono_ns=now_mono_ns, frame_type=name,
                       width=int(msg.getWidth()), height=int(msg.getHeight()))


def make_meta(frame: CameraFrame, host: str, session: str, trial: str, utc_minus_mono_ns: int) -> pc.FrameMeta:
    return pc.FrameMeta(CAMERA, frame.eye, frame.seq, frame.t_dev_ns, frame.t_host_mono_ns,
                        frame.t_host_mono_ns + utc_minus_mono_ns, host, session, trial, CONFIG_ID, 0)


class PackagingError(ValueError):
    pass


def package(frame: CameraFrame, meta: pc.FrameMeta, frame_end: str = "sei") -> bytes:
    """FrameMeta SEI before the first slice, end-of-frame marker after the last slice."""
    if frame.info.vcl_count == 0:
        raise PackagingError("access unit without a slice (seq {})".format(frame.seq))
    if frame.info.has_frame_meta:
        raise PackagingError("access unit already carries a FrameMeta SEI (seq {})".format(frame.seq))
    if meta.seq != frame.seq or meta.eye != frame.eye or meta.flags & pc.FLAG_SYNTHETIC:
        raise PackagingError("metadata does not describe this camera frame")
    return pc.append_frame_end(pc.insert_sei_before_vcl(frame.au, pc.build_sei_nal(meta)), frame_end, frame.seq)


# ----------------------------------------------------------------------------- GOP-aware latest-frame queue
class GopQueue:
    """Bounded per-eye hand-off from capture to sending (latest-frame policy for an
    already-encoded stream). Never holds more than `maxlen` frames. On any
    discontinuity -- a device sequence gap or reversal, an overflow, or a resync
    requested by the sender (stale frame, (re)connection) -- every queued frame is
    discarded and frames are dropped until the next recovery point, so whatever
    is sent stays decodable. Thread-safe (one producer, one consumer)."""

    def __init__(self, eye: str, maxlen: int, on_event=None):
        if maxlen < 2:
            raise ValueError("queue must hold at least 2 frames")
        self.eye, self.maxlen, self.on_event = eye, maxlen, on_event
        self._d = deque()
        self._cv = threading.Condition()
        self.last_seq = None
        self.waiting = True                 # start at a recovery point
        self.closed = False
        self.c = {"put": 0, "queued": 0, "dropped_waiting": 0, "discarded_resync": 0, "device_gaps": 0,
                  "device_gap_frames": 0, "seq_reversals": 0, "overflows": 0, "resyncs": 0, "max_depth": 0}

    def _event(self, kind, **kw):
        if self.on_event:
            self.on_event(kind, dict(eye=self.eye, **kw))

    def _resync(self, reason, **kw):
        n = len(self._d)
        self._d.clear()
        self.c["discarded_resync"] += n
        self.c["resyncs"] += 1
        if not self.waiting:
            self.waiting = True
        self._event("gop_resync", reason=reason, discarded=n, **kw)

    def put(self, f: CameraFrame) -> bool:
        """Returns True if the frame was queued."""
        with self._cv:
            self.c["put"] += 1
            if self.last_seq is not None:
                if f.seq <= self.last_seq:
                    self.c["seq_reversals"] += 1
                    self._resync("seq_reversal", seq=f.seq, last_seq=self.last_seq)
                elif f.seq != self.last_seq + 1:
                    missing = f.seq - self.last_seq - 1
                    self.c["device_gaps"] += 1
                    self.c["device_gap_frames"] += missing
                    self._resync("device_gap", seq=f.seq, missing=missing)
            self.last_seq = f.seq
            if len(self._d) >= self.maxlen:
                self.c["overflows"] += 1
                self._resync("overflow", seq=f.seq)
            if self.waiting:
                if not f.recovery_point:
                    self.c["dropped_waiting"] += 1
                    return False
                self.waiting = False
                self._event("gop_resume", seq=f.seq)
            self._d.append(f)
            self.c["queued"] += 1
            self.c["max_depth"] = max(self.c["max_depth"], len(self._d))
            self._cv.notify()
            return True

    def get(self, timeout: float):
        with self._cv:
            if not self._d and not self.closed:
                self._cv.wait(timeout)
            return self._d.popleft() if self._d else None

    def request_resync(self, reason: str, **kw):
        with self._cv:
            self._resync(reason, **kw)

    def jump_to_recovery(self, reason: str, **kw) -> bool:
        """If a recovery point is queued, discard everything before it and return True
        (the stream continues, decodable, from that newer keyframe); else change nothing."""
        with self._cv:
            idx = next((i for i, f in enumerate(self._d) if f.recovery_point), None)
            if idx is None:
                return False
            for _ in range(idx):
                self._d.popleft()
            self.c["discarded_resync"] += idx
            self.c["jumps"] = self.c.get("jumps", 0) + 1
            self._event("gop_jump", reason=reason, discarded=idx, to_seq=self._d[0].seq, **kw)
            return True

    def align(self, reason: str, **kw):
        """For a NEW connection: discard queued frames up to the first queued recovery
        point (kept); if none is queued, wait for the next one."""
        with self._cv:
            n = 0
            while self._d and not self._d[0].recovery_point:
                self._d.popleft()
                n += 1
            self.c["discarded_resync"] += n
            if not self._d:
                self.waiting = True
            self._event("gop_align", reason=reason, discarded=n, head_recovery=bool(self._d), **kw)

    def close(self):
        with self._cv:
            self.closed = True
            self._cv.notify_all()

    def __len__(self):
        with self._cv:
            return len(self._d)


# ----------------------------------------------------------------------------- stereo pairing monitor
class PairMonitor:
    """Capture-side check that both eyes carry the same sequence numbers and the
    same device capture time (StereoDepth rectified pairs; Stage D measured
    |L-R| <= 0.03 ms on the raw pairs). Bounded memory."""

    def __init__(self, max_skew_ms: float = 1.0, keep: int = 256):
        self.max_skew_ns = int(max_skew_ms * 1e6)
        self.keep = keep
        self._p = {}
        self._lock = threading.Lock()
        self.c = {"pairs": 0, "skew_violations": 0, "unpaired_dropped": 0}
        self.max_abs_skew_ns = 0

    def add(self, f: CameraFrame):
        with self._lock:
            other = "right" if f.eye == "left" else "left"
            slot = self._p.setdefault(f.seq, {})
            slot[f.eye] = f.t_dev_ns
            if other in slot:
                skew = abs(slot["left"] - slot["right"])
                self.max_abs_skew_ns = max(self.max_abs_skew_ns, skew)
                self.c["pairs"] += 1
                if skew > self.max_skew_ns:
                    self.c["skew_violations"] += 1
                del self._p[f.seq]
            while len(self._p) > self.keep:
                self._p.pop(min(self._p))
                self.c["unpaired_dropped"] += 1

    def summary(self) -> dict:
        with self._lock:
            return dict(self.c, pending=len(self._p), max_abs_skew_ms=round(self.max_abs_skew_ns / 1e6, 4),
                        limit_ms=self.max_skew_ns / 1e6)


STALE_POLICIES = ("resync", "catchup")


def on_stale(q: GopQueue, f: CameraFrame, age_ns: int, policy: str = "resync", hard_age_ns: int = 500_000_000) -> bool:
    """Decide what to do with a frame older than the send-age guard. Returns True to SEND it anyway.

    resync  (default; the validated Stage 1/2 behaviour): drop it and every frame up to the next
            recovery point (GopQueue resync).
    catchup (proposed, opt-in; not used live until reviewed): if a newer recovery point is already
            queued, jump to it (dropping f and the frames before it); otherwise keep the decodable
            chain and send f late -- the receiver's validated freshness safeguard rejects stale pairs,
            so they are never displayed -- unless f is older than hard_age_ns, then resync as above.
    Either way the transmitted stream stays decodable: nothing is ever dropped from the middle of a
    chain without restarting at a recovery point."""
    age_ms = round(age_ns / 1e6, 1)
    if policy == "resync":
        q.request_resync("stale", seq=f.seq, age_ms=age_ms)
        return False
    if policy != "catchup":
        raise ValueError("unknown stale policy " + policy)
    if q.jump_to_recovery("stale", seq=f.seq, age_ms=age_ms):
        return False
    if age_ns > hard_age_ns:
        q.request_resync("stale_hard", seq=f.seq, age_ms=age_ms)
        return False
    return True


def utc_minus_mono_ns() -> int:
    return time.time_ns() - time.monotonic_ns()

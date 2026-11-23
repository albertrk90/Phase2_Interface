"""Shared pieces of the Task 04B offline streaming proof of concept.

No camera, robot or network access happens in this module. It provides:

* FrameMeta and its H.264 SEI encoding: a `user_data_unregistered` SEI
  message (payload type 5) with a fixed UUID, carrying camera, eye, sequence
  number, device / host-monotonic / UTC capture times, host ID, session and
  trial IDs and a configuration ID, protected by a CRC-32. The gateway inserts
  it in front of the first slice of every access unit; receivers read it back
  from the packet bytes, so it does not depend on decoder side-data support.
* Annex B helpers: NAL splitting (3- and 4-byte start codes, with a
  length-prefixed fallback), emulation prevention both ways, and insertion of
  the SEI NAL before the first VCL NAL.
* EventLog: append-only JSONL in the event-record format proposed in the COROL
  integration addendum, section 9 (event_id, session, trial, source, type,
  t_utc, t_utc_ns, t_mono_ns, host, payload).
* check_local_url(): refuses anything other than rtsp://127.0.0.1 / localhost
  / [::1], and COROL's ports 8080 and 8081.

Clock note: on Windows with Python 3.13, time.monotonic_ns() is
QueryPerformanceCounter based and shared by all processes on the host, so
host-monotonic frame ages between the publisher and receiver processes are
meaningful on localhost. Across hosts only t_utc is comparable, and only to
the accuracy of clock synchronisation.
"""

from __future__ import annotations

import json
import os
import socket
import struct
import threading
import time
import uuid
import zlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

# Fixed identifier of our SEI payload. Any other user_data_unregistered SEI
# (x264 writes one with its version string) is ignored.
SEI_UUID = uuid.UUID("6b3f0c1e-04b0-4c2a-9a51-7e2d5a0f4b11").bytes
META_VERSION = 1

CAMERAS = {"A": 0, "B": 1}
CAMERA_NAMES = {v: k for k, v in CAMERAS.items()}
EYES = {"left": 0, "right": 1}
EYE_NAMES = {v: k for k, v in EYES.items()}

FLAG_SYNTHETIC = 0x01        # frame came from synthetic_stereo, not a camera
FLAG_BURST = 0x02            # frame was held back by an injected stall and sent late

# version, camera, eye, flags, seq, t_dev_ns, t_host_mono_ns, t_utc_ns,
# config_id, host[16], session[16], trial[16]; then CRC-32 of all of that.
_META = struct.Struct("<BBBBQqqqI16s16s16s")
_CRC = struct.Struct("<I")
META_BYTES = _META.size + _CRC.size

NAL_SLICE = 1
NAL_IDR = 5
NAL_SEI = 6
NAL_SPS = 7
NAL_PPS = 8
NAL_AUD = 9
VCL_TYPES = (1, 2, 3, 4, 5)

SEI_USER_DATA_UNREGISTERED = 5

FORBIDDEN_PORTS = (8080, 8081)      # COROL twin server, Robotiq gripper server
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def utc_ns() -> int:
    return time.time_ns()


def mono_ns() -> int:
    return time.monotonic_ns()


def iso_utc(t_ns: int) -> str:
    return datetime.fromtimestamp(t_ns / 1e9, tz=timezone.utc).isoformat(timespec="microseconds")


def host_id() -> str:
    """Short host identifier: PHASE2_HOST_ID if set, else the hostname."""
    return (os.environ.get("PHASE2_HOST_ID") or socket.gethostname())[:16]


def _fixed(text: str, n: int = 16) -> bytes:
    raw = (text or "").encode("utf-8")[:n]
    return raw + b"\0" * (n - len(raw))


def _unfixed(raw: bytes) -> str:
    return raw.rstrip(b"\0").decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# Frame metadata
# ---------------------------------------------------------------------------

@dataclass
class FrameMeta:
    camera: str                 # "A" | "B"
    eye: str                    # "left" | "right"
    seq: int
    t_dev_ns: int               # device clock (synthetic: publisher monotonic - t0)
    t_host_mono_ns: int         # host monotonic at capture
    t_utc_ns: int               # host wall clock (UTC) at capture
    host: str = ""
    session: str = ""
    trial: str = ""
    config_id: int = 0          # identifies crop/rectification/encoder config
    flags: int = 0
    version: int = META_VERSION

    def pack(self) -> bytes:
        body = _META.pack(self.version, CAMERAS[self.camera], EYES[self.eye],
                          self.flags & 0xFF, self.seq, self.t_dev_ns,
                          self.t_host_mono_ns, self.t_utc_ns,
                          self.config_id & 0xFFFFFFFF, _fixed(self.host),
                          _fixed(self.session), _fixed(self.trial))
        return body + _CRC.pack(zlib.crc32(body) & 0xFFFFFFFF)

    @classmethod
    def unpack(cls, raw: bytes) -> "FrameMeta":
        """Raises MetaError on a short payload, bad CRC or unknown version."""
        if len(raw) < META_BYTES:
            raise MetaError("metadata too short ({} bytes)".format(len(raw)))
        body, crc = raw[:_META.size], _CRC.unpack(raw[_META.size:META_BYTES])[0]
        if zlib.crc32(body) & 0xFFFFFFFF != crc:
            raise MetaError("metadata CRC mismatch")
        (ver, cam, eye, flags, seq, t_dev, t_mono, t_utc, cfg,
         host, session, trial) = _META.unpack(body)
        if ver != META_VERSION:
            raise MetaError("unknown metadata version {}".format(ver))
        if cam not in CAMERA_NAMES or eye not in EYE_NAMES:
            raise MetaError("bad camera/eye code {}/{}".format(cam, eye))
        return cls(CAMERA_NAMES[cam], EYE_NAMES[eye], seq, t_dev, t_mono, t_utc,
                   _unfixed(host), _unfixed(session), _unfixed(trial), cfg, flags, ver)

    def to_dict(self) -> dict:
        return asdict(self)


class MetaError(ValueError):
    """Our SEI was found but could not be trusted."""


# ---------------------------------------------------------------------------
# Annex B / NAL helpers
# ---------------------------------------------------------------------------

def add_emulation_prevention(rbsp: bytes) -> bytes:
    """RBSP -> EBSP: insert 0x03 after any 00 00 that precedes a byte <= 3."""
    out = bytearray()
    zeros = 0
    for b in rbsp:
        if zeros >= 2 and b <= 3:
            out.append(3)
            zeros = 0
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
    return bytes(out)


def remove_emulation_prevention(ebsp: bytes) -> bytes:
    """EBSP -> RBSP: drop each 0x03 that follows 00 00."""
    out = bytearray()
    zeros = 0
    for b in ebsp:
        if zeros >= 2 and b == 3:
            zeros = 0
            continue
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
    return bytes(out)


def build_sei_nal(meta: FrameMeta) -> bytes:
    """One complete Annex B SEI NAL (4-byte start code) carrying `meta`."""
    payload = SEI_UUID + meta.pack()
    msg = bytearray([SEI_USER_DATA_UNREGISTERED])
    size = len(payload)
    while size >= 255:
        msg.append(255)
        size -= 255
    msg.append(size)
    msg += payload
    msg.append(0x80)                        # rbsp_trailing_bits
    return b"\x00\x00\x00\x01" + bytes([NAL_SEI]) + add_emulation_prevention(bytes(msg))


def _find_start_codes(data: bytes):
    """Yield (start_code_offset, payload_offset) for each Annex B start code."""
    i, n = 0, len(data)
    while i + 3 <= n:
        j = data.find(b"\x00\x00\x01", i)
        if j < 0:
            return
        sc = j - 1 if j > 0 and data[j - 1] == 0 else j
        yield sc, j + 3
        i = j + 3


def split_nals(data: bytes) -> list[tuple[int, int, int]]:
    """Return [(nal_type, start, end)] where data[start:end] is the NAL unit
    (header byte first, no start code). Annex B is expected; a buffer with no
    start code is tried as 4-byte length-prefixed (AVCC) instead."""
    data = bytes(data)
    codes = list(_find_start_codes(data))
    nals = []
    if codes:
        for k, (_sc, start) in enumerate(codes):
            end = codes[k + 1][0] if k + 1 < len(codes) else len(data)
            # trailing_zero_8bits belong to no NAL
            while end > start and data[end - 1] == 0:
                end -= 1
            if end > start:
                nals.append((data[start] & 0x1F, start, end))
        return nals
    i = 0
    while i + 4 <= len(data):
        length = int.from_bytes(data[i:i + 4], "big")
        start, end = i + 4, i + 4 + length
        if length <= 0 or end > len(data):
            return []
        nals.append((data[start] & 0x1F, start, end))
        i = end
    return nals


def insert_sei_before_vcl(au: bytes, sei_nal: bytes) -> bytes:
    """Insert `sei_nal` (with its start code) immediately before the start
    code of the first VCL NAL of an Annex B access unit, so AUD/SPS/PPS and
    any encoder SEI stay in front of it. Appended if no VCL NAL is found."""
    au = bytes(au)
    for sc, start in _find_start_codes(au):
        if au[start] & 0x1F in VCL_TYPES:
            return au[:sc] + sei_nal + au[sc:]
    return au + sei_nal


# ---------------------------------------------------------------------------
# Explicit end-of-frame signalling (Task 04B S7 investigation)
#
# FFmpeg's H.264 parser, which its RTSP demuxer runs on the depacketised NAL
# units, can only end an access unit when it sees the first NAL of the NEXT
# one (an AUD, SPS, PPS or SEI, or a slice starting a new picture). The last
# frame before a pause is therefore held until the stream resumes. Appending a
# NAL that the parser treats as an access-unit start, immediately after the
# last slice, lets it end the frame at once. That NAL then becomes the first
# NAL of the next access unit as far as any decoder is concerned:
#   aud  access unit delimiter (type 9, primary_pic_type 7 = any slice type)
#   sei  user_data_unregistered SEI with SEI_EOF_UUID carrying the seq of the
#        frame it terminates (SEI is permitted before the next AU's slices)
# Whether MediaMTX forwards either NAL unchanged is a live-test question.
# ---------------------------------------------------------------------------

SEI_EOF_UUID = uuid.UUID("6b3f0c1e-04b0-4c2a-9a51-7e2d5a0f4e0f").bytes
AUD_NAL = b"\x00\x00\x00\x01\x09\xf0"
FRAME_END_MODES = ("none", "aud", "sei")


def build_eof_sei_nal(seq: int) -> bytes:
    payload = SEI_EOF_UUID + struct.pack("<Q", seq)
    msg = bytes([SEI_USER_DATA_UNREGISTERED, len(payload)]) + payload + b"\x80"
    return b"\x00\x00\x00\x01" + bytes([NAL_SEI]) + add_emulation_prevention(msg)


def append_frame_end(au: bytes, mode: str, seq: int) -> bytes:
    if mode == "none":
        return bytes(au)
    if mode == "aud":
        return bytes(au) + AUD_NAL
    if mode == "sei":
        return bytes(au) + build_eof_sei_nal(seq)
    raise ValueError("frame-end mode must be one of {}".format(FRAME_END_MODES))


def frame_end_markers(data: bytes) -> dict:
    """{'aud': n, 'eof_seq': [..]} found in a packet (for tracing)."""
    data = bytes(data)
    out = {"aud": 0, "eof_seq": []}
    for ntype, start, end in split_nals(data):
        if ntype == NAL_AUD:
            out["aud"] += 1
        elif ntype == NAL_SEI:
            rbsp = remove_emulation_prevention(data[start + 1:end])
            for ptype, payload in _sei_messages(rbsp):
                if ptype == SEI_USER_DATA_UNREGISTERED and payload[:16] == SEI_EOF_UUID \
                        and len(payload) >= 24:
                    out["eof_seq"].append(struct.unpack("<Q", payload[16:24])[0])
    return out


def _sei_messages(rbsp: bytes):
    """Yield (payload_type, payload) from an SEI RBSP (header byte removed)."""
    i, n = 0, len(rbsp)
    while i < n:
        if rbsp[i] == 0x80 and i == n - 1:       # trailing bits
            return
        ptype = 0
        while i < n and rbsp[i] == 255:
            ptype += 255
            i += 1
        if i >= n:
            return
        ptype += rbsp[i]
        i += 1
        psize = 0
        while i < n and rbsp[i] == 255:
            psize += 255
            i += 1
        if i >= n:
            return
        psize += rbsp[i]
        i += 1
        if i + psize > n:
            return
        yield ptype, rbsp[i:i + psize]
        i += psize


def extract_meta(data: bytes) -> tuple[FrameMeta | None, str | None]:
    """Find our SEI in one packet / access unit.

    Returns (meta, None) on success, (None, None) if the packet carries no SEI
    of ours, and (None, reason) if one was found but failed its checks.
    """
    data = bytes(data)
    error = None
    for ntype, start, end in split_nals(data):
        if ntype != NAL_SEI:
            continue
        rbsp = remove_emulation_prevention(data[start + 1:end])
        for ptype, payload in _sei_messages(rbsp):
            if ptype != SEI_USER_DATA_UNREGISTERED or payload[:16] != SEI_UUID:
                continue
            try:
                return FrameMeta.unpack(payload[16:]), None
            except MetaError as e:
                error = str(e)
    return None, error


def nal_types(data: bytes) -> list[int]:
    return [t for t, _s, _e in split_nals(data)]


def sps_profile_idc(data: bytes) -> int | None:
    """profile_idc of the first SPS in `data` (66 = Baseline), or None."""
    data = bytes(data)
    for ntype, start, end in split_nals(data):
        if ntype == NAL_SPS and end - start >= 4:
            return data[start + 1]
    return None


# ---------------------------------------------------------------------------
# Safety guard: localhost only, never COROL's ports
# ---------------------------------------------------------------------------

def check_local_url(url: str) -> str:
    """Return `url` if it is rtsp:// to a loopback host on an allowed port;
    raise ValueError otherwise. Task 04B is localhost-only by approval."""
    parts = urlsplit(url)
    if parts.scheme != "rtsp":
        raise ValueError("only rtsp:// URLs are used in Task 04B (got {!r})".format(url))
    host = (parts.hostname or "").lower()
    if host not in LOOPBACK_HOSTS:
        raise ValueError("Task 04B is localhost-only; refusing host {!r}".format(host))
    port = parts.port or 554
    if port in FORBIDDEN_PORTS:
        raise ValueError("port {} belongs to COROL (8080 twin, 8081 gripper); "
                         "refusing".format(port))
    return url


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------

class EventLog:
    """Append-only JSONL event records, safe to call from several threads."""

    def __init__(self, path, source: str, session: str = "", trial: str = ""):
        self.path = str(path)
        self.source = source
        self.session = session
        self.trial = trial
        self.host = host_id()
        self._lock = threading.Lock()
        self._n = 0
        self._run = uuid.uuid4().hex[:8]
        self._fh = open(self.path, "a", encoding="utf-8", newline="\n")

    def emit(self, type_: str, payload: dict | None = None,
             t_utc: int | None = None, t_mono: int | None = None) -> dict:
        t_utc = utc_ns() if t_utc is None else t_utc
        t_mono = mono_ns() if t_mono is None else t_mono
        with self._lock:
            self._n += 1
            rec = {"event_id": "{}-{}-{:06d}".format(self.source, self._run, self._n),
                   "session": self.session, "trial": self.trial,
                   "source": self.source, "type": type_,
                   "t_utc": iso_utc(t_utc), "t_utc_ns": t_utc, "t_mono_ns": t_mono,
                   "host": self.host, "payload": payload or {}}
            self._fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
            self._fh.flush()
        return rec

    def close(self):
        with self._lock:
            if not self._fh.closed:
                self._fh.close()


def read_events(path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def percentile(values, p):
    """Nearest-rank-free linear percentile; None for an empty list."""
    v = sorted(values)
    if not v:
        return None
    k = (len(v) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


@dataclass
class Backoff:
    """Capped exponential reconnect backoff (0.5 s doubling to 5 s)."""
    lo: float = 0.5
    hi: float = 5.0
    cur: float = field(default=0.5)

    def next(self) -> float:
        d = self.cur
        self.cur = min(self.cur * 2, self.hi)
        return d

    def reset(self):
        self.cur = self.lo

"""Offline stand-in for the OAK VideoEncoder output (Task 06 tests and recorded input).

NOT the camera's encoder. libx264 is configured like the on-device encoder is
requested to be (H.264 Baseline, keyframe every N, no B-frames, CBR, SPS/PPS
repeated with every IDR, GRAY8 luma with neutral chroma = DepthAI's GRAY8 -> NV12
conversion), so the gateway's packaging, flow control and muxing can be tested
on realistic access units. The real OAK bitstream layout (AUD, SPS/PPS
repetition, slices) is a hardware question recorded by the gateway's
au_stats / hardware_checks on the first physical test.

Real imagery: the five rectified Camera A pairs saved by the approved Stage E E1
run (camera_validation/results/..._E1_A_default/images, read-only).
"""
from __future__ import annotations

import pathlib
from fractions import Fraction

import av
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
E1_IMAGES = ROOT / "camera_validation" / "results" / "rectify_20261104_170326_19443010B14C872F00_E1_A_default" / "images"
W, H = 1280, 800


def read_gray_png(path) -> bytes:
    with av.open(str(path)) as c:
        f = next(c.decode(video=0))
    a = f.to_ndarray(format="gray")
    if a.shape != (H, W):
        raise ValueError("{}: {} not {}x{}".format(path, a.shape, W, H))
    return a.tobytes()


def load_e1_pairs():
    """[(group_name, left_luma, right_luma)] of the saved E1 rectified pairs (real Camera A imagery)."""
    out = []
    for lp in sorted(E1_IMAGES.glob("*_rect_left.png")):
        rp = lp.with_name(lp.name.replace("_rect_left", "_rect_right"))
        out.append((lp.name.split("_rect_left")[0], read_gray_png(lp), read_gray_png(rp)))
    if not out:
        raise FileNotFoundError("no E1 rectified pairs under {}".format(E1_IMAGES))
    return out


def y_plane(frame) -> bytes:
    """The decoded luma exactly as the receivers use it: the raw Y plane (no range conversion;
    to_ndarray(format="gray") would rescale limited-range Y and distort comparisons)."""
    p = frame.planes[0]
    raw = bytes(p)
    if p.line_size == frame.width:
        return raw[:frame.width * frame.height]
    return b"".join(raw[r * p.line_size:r * p.line_size + frame.width] for r in range(frame.height))


class StandInEncoder:
    """One eye. encode(luma) -> list of Annex-B access units (bytes)."""

    def __init__(self, fps=20, keyint=20, bitrate_kbps=8000, aud=False, slices=1, repeat_headers=True, preset="veryfast"):
        c = av.CodecContext.create("libx264", "w")
        c.width, c.height, c.pix_fmt = W, H, "yuv420p"
        c.time_base = Fraction(1, fps)
        c.bit_rate = bitrate_kbps * 1000
        params = ["keyint={0}".format(keyint), "min-keyint={0}".format(keyint), "scenecut=0", "bframes=0",
                  "nal-hrd=cbr", "vbv-maxrate={}".format(bitrate_kbps), "vbv-bufsize={}".format(int(bitrate_kbps / fps * 2)),
                  "slices={}".format(slices), "threads=1", "sliced-threads=0", "aud={}".format(int(aud)), "repeat-headers={}".format(int(repeat_headers))]
        c.options = {"profile": "baseline", "preset": preset, "tune": "zerolatency", "x264-params": ":".join(params)}
        self.c, self.n = c, 0
        self._chroma = None

    def _frame(self, luma: bytes):
        f = av.VideoFrame(W, H, "yuv420p")
        y = np.frombuffer(luma, dtype=np.uint8).reshape(H, W)
        f.planes[0].update(np.ascontiguousarray(np.pad(y, ((0, 0), (0, f.planes[0].line_size - W)))).tobytes()
                           if f.planes[0].line_size != W else y.tobytes())
        for p in f.planes[1:]:
            p.update(b"\x80" * p.buffer_size)
        f.pts, f.time_base = self.n, self.c.time_base
        self.n += 1
        return f

    def encode(self, luma: bytes) -> list:
        return [bytes(p) for p in self.c.encode(self._frame(luma))]

    def flush(self) -> list:
        return [bytes(p) for p in self.c.encode(None)]


def encode_sequence(lumas, **kw) -> list:
    """Encode a list of luma planes; returns one access unit per input frame (zerolatency: no delay)."""
    e = StandInEncoder(**kw)
    aus = []
    for y in lumas:
        aus += e.encode(y)
    aus += e.flush()
    if len(aus) != len(lumas):
        raise RuntimeError("expected one AU per frame, got {} for {}".format(len(aus), len(lumas)))
    return aus


class FakeFrameType:
    def __init__(self, name):
        self.name = name


class FakeEncodedFrame:
    """Duck-typed depthai.EncodedFrame (the methods gateway_core.frame_from_encoded uses)."""

    def __init__(self, seq, t_dev_ns, t_host_mono_ns, au, frame_type, width=W, height=H):
        import datetime as dt
        self._seq, self._au, self._ft = seq, au, FakeFrameType(frame_type)
        self._dev = dt.timedelta(microseconds=t_dev_ns // 1000)
        self._host = dt.timedelta(microseconds=t_host_mono_ns // 1000)
        self._w, self._h = width, height

    def getSequenceNum(self):
        return self._seq

    def getTimestampDevice(self):
        return self._dev

    def getTimestamp(self):
        return self._host

    def getData(self):
        return np.frombuffer(self._au, dtype=np.uint8)

    def getFrameType(self):
        return self._ft

    def getWidth(self):
        return self._w

    def getHeight(self):
        return self._h

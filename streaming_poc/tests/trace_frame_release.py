"""Offline trace of where a frame can be held back (no network, no server).

Stages examined in isolation, with the same PyAV 19.0.2 / FFmpeg build:

  1. PACKETISATION: FFmpeg's RTP muxer (the one inside the RTSP muxer) writing
     to an in-memory sink. Does muxing frame n put all of frame n's RTP
     packets out during that call, with the RTP marker bit on the last one?
  2. PARSER: FFmpeg's H.264 parser (av_parser_parse2), which the RTSP demuxer
     applies to depacketised NAL units (AVSTREAM_PARSE_FULL). Fed NAL by NAL
     as the RTP depacketiser delivers them: after which input is frame n
     released?
  3. DECODER: does decoding parsed packet n return frame n at once?

Each stage is run for three frame-end modes of the publisher:
  none  frames as now
  aud   an access unit delimiter NAL (type 9) appended after the last slice
  sei   an end-of-frame SEI (our EOF UUID) appended after the last slice

Run:  .venv\\Scripts\\python.exe -I tests\\trace_frame_release.py [--json OUT]
"""
import io
import json
import pathlib
import sys
from fractions import Fraction

POC = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))

import av  # noqa: E402
import poc_common as pc  # noqa: E402
import synthetic_stereo as ss  # noqa: E402

N = 30


def encoded_aus(n=N):
    """libx264 Constrained Baseline AUs (Annex B), each with our SEI, plus
    the codec extradata, exactly as publish_synthetic configures it."""
    cc = av.CodecContext.create("libx264", "w")
    cc.width, cc.height, cc.pix_fmt = ss.WIDTH, ss.HEIGHT, "yuv420p"
    cc.time_base = Fraction(1, 20)
    cc.framerate = Fraction(20, 1)
    cc.bit_rate = 8_000_000
    cc.options = {"profile": "baseline", "preset": "veryfast", "tune": "zerolatency",
                  "x264-params": "keyint=20:min-keyint=20:scenecut=0:bframes=0:repeat-headers=1"}
    aus = []
    for s in range(n):
        f = av.VideoFrame(ss.WIDTH, ss.HEIGHT, "yuv420p")
        f.planes[0].update(ss.make_luma(s, 0, 0))
        for p in f.planes[1:]:
            p.update(b"\x80" * p.buffer_size)
        f.pts = s
        for pkt in cc.encode(f):
            m = pc.FrameMeta("A", "left", s, 0, 0, 0, "h", "", "", 1, 1)
            aus.append(pc.insert_sei_before_vcl(bytes(pkt), pc.build_sei_nal(m)))
    for pkt in cc.encode(None):
        aus.append(bytes(pkt))
    return aus[:n]


def with_end(au, mode, seq):
    return pc.append_frame_end(au, mode, seq)


def nal_chunks(au):
    """The AU as the RTP depacketiser emits it: one chunk per NAL, each with
    a 00 00 00 01 start code."""
    return [b"\x00\x00\x00\x01" + au[s:e] for _t, s, e in pc.split_nals(au)]


class Sink(io.RawIOBase):
    def __init__(self):
        self.writes = []

    def writable(self):
        return True

    def write(self, b):
        self.writes.append(bytes(b))
        return len(b)


def stage_packetiser(aus, mode):
    sink = Sink()
    out = av.open(sink, mode="w", format="rtp", options={"packetsize": "1400"})
    st = out.add_stream("h264", rate=20)
    st.width, st.height, st.pix_fmt = ss.WIDTH, ss.HEIGHT, "yuv420p"
    st.time_base = Fraction(1, 90000)
    rows = []
    for s, au in enumerate(aus):
        before = len(sink.writes)
        pkt = av.Packet(with_end(au, mode, s))
        pkt.pts = pkt.dts = s * 4500
        pkt.time_base = Fraction(1, 90000)
        pkt.stream = st
        out.mux(pkt)
        # RTCP (payload types 200-204, e.g. the initial sender report) is not
        # media; only RTP packets count.
        new = [w for w in sink.writes[before:] if not 200 <= w[1] <= 204]
        marker_last = bool(new) and bool(new[-1][1] & 0x80)
        markers_before = sum(1 for w in new[:-1] if w[1] & 0x80)
        ts = {int.from_bytes(w[4:8], "big") for w in new}
        rows.append({"seq": s, "rtp_packets_in_this_mux": len(new), "marker_on_last": marker_last,
                     "markers_before_last": markers_before, "rtp_timestamps": len(ts)})
    out.close()
    return rows


def stage_parser(aus, mode):
    """Feed NAL by NAL; record for each frame the input index (frame, nal)
    after which the parser returned it."""
    parser = av.CodecContext.create("h264", "r")
    out_at = {}
    got = 0
    for s, au in enumerate(aus):
        chunks = nal_chunks(with_end(au, mode, s))
        for k, ch in enumerate(chunks):
            for p in parser.parse(ch):
                meta, _ = pc.extract_meta(bytes(p))
                out_at[meta.seq if meta else -1 - got] = (s, k, len(chunks))
                got += 1
    for p in parser.parse(None):
        meta, _ = pc.extract_meta(bytes(p))
        out_at[meta.seq if meta else -1 - got] = ("flush", None, None)
    rows = []
    for s in range(len(aus)):
        at = out_at.get(s)
        if at is None:
            rows.append({"seq": s, "released_after": None, "same_frame": False})
            continue
        rows.append({"seq": s, "released_after": "frame {} nal {}/{}".format(*at) if at[0] != "flush" else "flush",
                     "same_frame": at[0] == s, "held_one_frame": at[0] == s + 1})
    return rows


def stage_decoder(aus, mode):
    dec = av.CodecContext.create("h264", "r")
    dec.thread_count = 1
    parser = av.CodecContext.create("h264", "r")
    rows, pending = [], []
    stream = b"".join(with_end(a, mode, s) for s, a in enumerate(aus))
    for p in parser.parse(stream):
        pending.append(p)
    pending += parser.parse(None)
    for p in pending:
        meta, _ = pc.extract_meta(bytes(p))
        try:
            frames = dec.decode(p)
        except av.error.InvalidDataError as e:
            rows.append({"seq": meta.seq if meta else None, "frames_out": 0, "barcode_seq": [],
                         "error": str(e), "nal_types": pc.nal_types(bytes(p))})
            continue
        codes = []
        for f in frames:
            y = f.planes[0]
            codes.append(ss.read_barcode(memoryview(y), y.line_size))
        rows.append({"seq": meta.seq if meta else None, "frames_out": len(frames),
                     "barcode_seq": [c[0] if c else None for c in codes]})
    return rows


def summarise(aus):
    res = {}
    for mode in ("none", "aud", "sei"):
        pk = stage_packetiser(aus, mode)
        pa = stage_parser(aus, mode)
        de = stage_decoder(aus, mode)
        res[mode] = {
            "packetiser_all_frames_complete_in_own_mux": all(r["rtp_packets_in_this_mux"] > 0 and r["marker_on_last"]
                                                             and r["markers_before_last"] == 0
                                                             and r["rtp_timestamps"] == 1 for r in pk),
            "packetiser_rtp_packets_per_frame": [r["rtp_packets_in_this_mux"] for r in pk[:5]],
            "parser_released_in_same_frame": sum(1 for r in pa if r["same_frame"]),
            "parser_held_one_frame": sum(1 for r in pa if r.get("held_one_frame")),
            "parser_frames": len(pa),
            "parser_examples": pa[:3] + pa[-2:],
            "decoder_one_frame_per_packet_same_seq": all(r["frames_out"] == 1 and r["barcode_seq"] == [r["seq"]]
                                                         for r in de if r["seq"] is not None),
            "decoder_packets": len(de),
            # A trailing AUD/EOF-SEI left over at end of stream is a packet with
            # no slice; the receiver does not decode such packets.
            "decoder_errors_on_vcl_packets": [r for r in de if "error" in r
                                              and any(t in pc.VCL_TYPES for t in r["nal_types"])],
            "non_vcl_leftover_packets": [r["nal_types"] for r in de if "error" in r
                                         and not any(t in pc.VCL_TYPES for t in r["nal_types"])],
        }
    return res


if __name__ == "__main__":
    res = summarise(encoded_aus())
    txt = json.dumps(res, indent=2)
    print(txt)
    if len(sys.argv) > 2 and sys.argv[1] == "--json":
        pathlib.Path(sys.argv[2]).write_text(txt, encoding="utf-8")

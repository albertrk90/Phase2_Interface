"""Offline DepthAI 3.11.0 API inspection for the Camera A gateway (no device contact).

Only introspection plus a device-less Pipeline (createImplicitDevice=False): no
discovery, no connection, no camera. Records what the installed bindings expose
for on-device H.264 encoding of the rectified stereo pair, the encoded-frame
metadata, and the host clock that DepthAI timestamps use; writes
camera_gateway/results/depthai_api_<stamp>.json.

What this CANNOT establish (needs a physical test): that the RVC2 encoder
accepts the rectified GRAY8 frames at 1280 x 800 / 20 fps on both eyes, that
EncodedFrame keeps the input sequence number and timestamps, and the real
bitstream layout (SPS/PPS repetition, AUD, slices).

Run: camera_gateway\\.venv\\Scripts\\python.exe -I camera_gateway\\tools\\inspect_depthai_api.py
"""
import datetime as dt
import json
import pathlib
import sys
import time

import depthai as dai

OUT = pathlib.Path(__file__).resolve().parents[1] / "results"


def members(obj):
    return sorted(m for m in dir(obj) if not m.startswith("_"))


def enum_values(e):
    return sorted(k for k in dir(e) if not k.startswith("_") and k.isupper())


def doc(obj, name):
    try:
        return (getattr(obj, name).__doc__ or "").strip().splitlines()[:6]
    except Exception as exc:                    # noqa: BLE001
        return ["<{}>".format(exc)]


def main():
    rep = {"depthai": dai.__version__, "python": sys.version, "created": dt.datetime.now().isoformat(),
           "device_contact": "none (introspection and a device-less Pipeline only)"}
    ve = dai.node.VideoEncoder
    rep["VideoEncoder"] = {
        "members": members(ve),
        "Profile": enum_values(dai.VideoEncoderProperties.Profile),
        "RateControlMode": enum_values(dai.VideoEncoderProperties.RateControlMode),
        "docs": {n: doc(ve, n) for n in ("build", "setDefaultProfilePreset", "setProfile", "setKeyframeFrequency",
                                         "setNumBFrames", "setBitrateKbps", "setRateControlMode", "setFrameRate",
                                         "setMaxOutputFrameSize", "setNumFramesPool", "setLossless", "setQuality")
                 if hasattr(ve, n)},
    }
    ef = dai.EncodedFrame
    rep["EncodedFrame"] = {"members": members(ef),
                           "FrameType": enum_values(ef.FrameType) if hasattr(ef, "FrameType") else None,
                           "Profile": enum_values(ef.Profile) if hasattr(ef, "Profile") else None}
    rep["ImgFrame_Type_has_GRAY8_NV12"] = {t: hasattr(dai.ImgFrame.Type, t) for t in ("GRAY8", "NV12", "RAW8")}
    sd = dai.node.StereoDepth
    rep["StereoDepth_outputs"] = [m for m in members(sd) if m.startswith(("rectified", "synced"))]
    rep["Pipeline_autocal"] = {"has_set": hasattr(dai.Pipeline, "setAutoCalibrationMode"),
                               "modes": enum_values(dai.Pipeline.AutoCalibrationMode)}

    # A device-less Pipeline cannot create device nodes in 3.11.0 ("Pipeline is host only"),
    # so encoder defaults cannot be read offline; the setters' signatures are recorded instead.
    try:
        p = dai.Pipeline(False)
        p.create(dai.node.VideoEncoder)
        rep["deviceless_node"] = "created (unexpected)"
    except RuntimeError as exc:
        rep["deviceless_node"] = "refused: {}".format(exc)
    rep["VideoEncoder_setter_signatures"] = {n: doc(ve, n) for n in members(ve) if n.startswith(("set", "build", "get"))}
    rep["EncodedFrame_docs"] = {n: doc(ef, n) for n in members(ef) if n.startswith("get")}

    # host clock: DepthAI host timestamps vs Python's monotonic clock (raw QPC on Windows)
    diffs = []
    for _ in range(200):
        a = time.monotonic_ns()
        d = dai.Clock.now()
        b = time.monotonic_ns()
        dn = int(round(d.total_seconds() * 1e9)) if hasattr(d, "total_seconds") else None
        diffs.append(dn - (a + b) // 2 if dn is not None else None)
    ok = [x for x in diffs if x is not None]
    rep["clock"] = {"dai.Clock.now_type": type(dai.Clock.now()).__name__,
                    "dai_minus_time_monotonic_ns": {"min": min(ok), "max": max(ok), "median": sorted(ok)[len(ok) // 2]} if ok else None,
                    "note": "timedelta resolution is 1 us; |difference| of a few us means the same QPC-based clock"}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "depthai_api_{}.json".format(dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    path.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("deviceless_node", "clock", "ImgFrame_Type_has_GRAY8_NV12", "StereoDepth_outputs")}, indent=1))
    print("Profiles:", rep["VideoEncoder"]["Profile"])
    print("EncodedFrame:", rep["EncodedFrame"]["members"])
    print("FrameType:", rep["EncodedFrame"]["FrameType"])
    print("VideoEncoder members:", rep["VideoEncoder"]["members"])
    print("build doc:", rep["VideoEncoder"]["docs"].get("build"))
    print("->", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

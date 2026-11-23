"""Task 06 Stage 1 analysis: Camera A on-device H.264, 30 s, files only (offline, read-only).

Criteria fixed on 6 Nov 2026 BEFORE the run (PASS / FAIL / NOT_TESTED; NOT_TESTED
when the evidence for a criterion does not exist, never PASS by default):

  H1  identity          connected device = 19443010B14C872F00 at 169.254.1.222; seen in
                        X_LINK_BOOTLOADER before connecting
  H2  persistent state  bootloader read back = 0.0.26 (validated); after the run the
                        device was back in X_LINK_BOOTLOADER and read_ok (post-run check)
  H3  calibration       user AND factory equal the baselines before start; in-session
                        re-read equal; post-run equal to before AND to both baselines
  H4  safety settings   AutoCalibrationMode OFF confirmed; IR dot and flood set to 0 and
                        acknowledged before and after start
  H5  encoder support   pipeline started and ran to --seconds without error; both eyes
                        produced encoded frames; encoders report H264_BASELINE, CBR,
                        keyframe 20, 0 B-frames; SPS profile_idc 66
  H6  frame counts      per eye within +-5 % of seconds x fps; capture rate within 5 %
  H7  sequence          per eye strictly increasing (no duplicate or reversal); missing
                        between first and last <= 1 % (each gap listed)
  H8  timestamps        per eye device and host-synced timestamps strictly increasing;
                        device interval median 50 +- 1 ms; host timestamp never after the
                        host receipt; host-synced vs device timestamp consistent: the p99
                        |residual| of a linear fit host = a + b * device is <= 1 ms (no jumps;
                        clock drift allowed and reported in ppm; revised 6 Nov BEFORE the run,
                        after the dry run showed a fixed offset-spread limit cannot allow for
                        drift). Reported: interval p99/max, capture->receipt median/p95/max
  H9  bitstream         every AU has >= 1 slice; 1280 x 800 on every frame; no B frames;
                        IDR (recovery point) exactly every 20 frames between gaps; the
                        frame type reported by the encoder agrees with the slice type;
                        no FrameMeta in the raw encoder output. Reported: NAL layout,
                        SPS/PPS on every IDR, AUD presence, slices per AU, bitrate
  H10 L/R sync          >= 99 % of seqs present on both eyes; device-time |L - R| <= 1 ms
                        on every pair (pair monitor 0 violations)
  H11 decode/packaging  raw encoder output decodes on both eyes (one picture per
                        captured AU, 0 errors); the packaged MPEG-TS decodes and every
                        packet's FrameMeta seq matches sent.csv; frame-end SEI present;
                        pictures are not blank (luma std > 2) and left != right
  H12 clean shutdown    pipeline stopped, device closed, both senders joined, gateway
                        exit code 0, no gateway process left, no new DepthAI crash dump
  H13 bitrate (info)    per-eye mean bitrate reported against 8 Mbit/s (never gating)

Run: camera_gateway\\.venv\\Scripts\\python.exe -I camera_gateway\\tools\\analyse_stage1.py <gw_dir> [--runner <runner_dir>]
Writes <gw_dir>/stage1_analysis.json (never modifies the evidence).
"""
import argparse
import csv
import json
import pathlib
import statistics
import sys

sys.dont_write_bytecode = True
GW = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(GW), str(GW / "tools")]

import av  # noqa: E402
import numpy as np  # noqa: E402

import camera_gateway_a as cga  # noqa: E402
import gateway_core as gc  # noqa: E402
import standin_encoder as se  # noqa: E402
from gateway_core import pc  # noqa: E402

KEYINT, FPS = 20, 20.0


def V(ok, tested=True):
    return "NOT_TESTED" if not tested else ("PASS" if ok else "FAIL")


def pct(v, p):
    return float(np.percentile(v, p)) if len(v) else None


def decode_file(path, fmt=None):
    n, err, lumas, metas, eofs = 0, 0, [], [], []
    with av.open(str(path), format=fmt) as c:
        for pkt in c.demux(video=0):
            data = bytes(pkt)
            if not data:
                continue
            m, _ = pc.extract_meta(data)
            if m:
                metas.append(m.seq)
            eofs += pc.frame_end_markers(data)["eof_seq"]
            if not any(t in pc.VCL_TYPES for t, _, _ in pc.split_nals(data)):
                continue
            try:
                for f in pkt.decode():
                    n += 1
                    if n % 50 == 1:
                        lumas.append(se.y_plane(f))
            except av.error.InvalidDataError:
                err += 1
    return {"pictures": n, "errors": err, "sampled": lumas, "meta_seqs": metas, "eof_seqs": eofs}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("gw_dir")
    ap.add_argument("--runner")
    ap.add_argument("--seconds", type=float, default=30.0)
    a = ap.parse_args(argv)
    d = pathlib.Path(a.gw_dir)
    rep = json.loads((d / "report.json").read_text(encoding="utf-8"))
    def rows(name):                                   # an aborted run (refusal) has no stream files
        p_ = d / name
        return list(csv.DictReader(open(p_, encoding="utf-8"))) if p_.exists() else []
    cap, sent = rows("captured.csv"), rows("sent.csv")
    run = json.loads((pathlib.Path(a.runner) / "runner_status.json").read_text(encoding="utf-8-sig")) if a.runner else None
    C, M = {}, {}
    sel = rep.get("selection", {})
    C["H1_identity"] = V(sel.get("actual_device_id") == cga.CAMERA_A_ID and sel.get("actual_ip") == "169.254.1.222"
                         and "BOOTLOADER" in str(sel.get("preflight_seen_state")), bool(sel))
    post = rep.get("calibration_post_run") or {}
    bl = (rep.get("device_read_only") or {}).get("getBootloaderVersion")
    if bl is not None and bl != cga.EXPECTED_BOOTLOADER:
        C["H2_persistent_state"] = "FAIL"            # refused: not the validated bootloader
    else:
        C["H2_persistent_state"] = V(bl == cga.EXPECTED_BOOTLOADER and post.get("status") == "read_ok"
                                     and "BOOTLOADER" in str((post.get("last_precheck") or {}).get("seen_state")),
                                     bl is not None and bool(post))
    M["stop_reason"], M["errors"] = rep.get("stop_reason"), rep.get("errors")
    pre = rep.get("calibration_vs_baselines_before_start") or []
    C["H3_calibration"] = V(len(pre) == 2 and all(c["equal"] for c in pre)
                            and (rep.get("calibration_in_session") or {}).get("equal") is True
                            and post.get("equal") is True and len(post.get("baselines", [])) == 2
                            and rep.get("calibration_unchanged") is True, bool(pre))
    ir_ok = {"setIrLaserDotProjectorIntensity": True, "setIrFloodLightIntensity": True}
    C["H4_safety_settings"] = V("OFF" in str(rep.get("auto_calibration_mode")) and rep.get("ir_off_before_start") == ir_ok
                                and rep.get("ir_off_after_start") == ir_ok, "auto_calibration_mode" in rep)
    enc = (rep.get("pipeline") or {}).get("encoders") or {}
    au = rep.get("au_stats") or {}
    eyes = {e: [r for r in cap if r["eye"] == e] for e in gc.EYES}
    C["H5_encoder_support"] = V(rep.get("stop_reason") == "seconds_reached" and not rep.get("errors")
                                and all(len(eyes[e]) > 0 for e in gc.EYES)
                                and all("H264_BASELINE" in enc[e]["getProfile"] and "CBR" in enc[e]["getRateControlMode"]
                                        and enc[e]["getKeyframeFrequency"] == str(KEYINT) and enc[e]["getNumBFrames"] == "0" for e in enc)
                                and len(enc) == 2 and all(au[e].get("sps_profile_idc") == 66 for e in gc.EYES if e in au),
                                bool(enc) or bool(cap))
    expected = a.seconds * FPS
    M["frames_per_eye"] = {e: len(eyes[e]) for e in gc.EYES}
    C["H6_frame_counts"] = V(all(abs(len(eyes[e]) - expected) <= 0.05 * expected for e in gc.EYES)
                             and rep.get("capture_rate_fps") is not None and abs(rep["capture_rate_fps"] - FPS) <= 0.05 * FPS, bool(cap))
    seq_ok, gaps = True, {}
    for e in gc.EYES:
        s = [int(r["seq"]) for r in eyes[e]]
        seq_ok &= all(b > a_ for a_, b in zip(s, s[1:]))
        gaps[e] = [(a_, b - a_ - 1) for a_, b in zip(s, s[1:]) if b - a_ > 1]
        M.setdefault("missing", {})[e] = sum(g for _, g in gaps[e])
        M.setdefault("span", {})[e] = (s[-1] - s[0] + 1) if s else 0
    M["gaps"] = gaps
    C["H7_sequence"] = V(seq_ok and all(M["span"][e] and M["missing"][e] <= 0.01 * M["span"][e] for e in gc.EYES), bool(cap))
    ts_ok, ts = True, {}
    for e in gc.EYES:
        dv = [int(r["t_dev_ns"]) for r in eyes[e]]
        hs = [int(r["t_host_mono_ns"]) for r in eyes[e]]
        rx = [int(r["t_received_mono_ns"]) for r in eyes[e]]
        sq = [int(r["seq"]) for r in eyes[e]]
        iv = [(b - a_) / 1e6 / (sb - sa) for a_, b, sa, sb in zip(dv, dv[1:], sq, sq[1:]) if sb > sa]
        off = [(h - x) / 1e6 for h, x in zip(hs, dv)]
        lat = [(r_ - h) / 1e6 for r_, h in zip(rx, hs)]
        mono = all(b > a_ for a_, b in zip(dv, dv[1:])) and all(b > a_ for a_, b in zip(hs, hs[1:]))
        causal = all(x >= 0 for x in lat)
        spread = (pct(off, 99) - pct(off, 1)) if off else None
        resid_p99, drift_ppm = None, None
        if len(dv) > 2:
            x = (np.array(dv, dtype=np.float64) - dv[0]) / 1e9
            y = (np.array(hs, dtype=np.float64) - hs[0]) / 1e6          # ms
            b_, a0 = np.polyfit(x, y, 1)
            resid_p99 = float(np.percentile(np.abs(y - (a0 + b_ * x)), 99))
            drift_ppm = (b_ / 1000.0 - 1.0) * 1e6
        ts[e] = {"device_interval_ms": {"median": round(statistics.median(iv), 3) if iv else None, "p99": round(pct(iv, 99), 3) if iv else None,
                                        "max": round(max(iv), 3) if iv else None},
                 "host_minus_device_offset_spread_ms": round(spread, 3) if spread is not None else None,
                 "host_vs_device_fit_residual_p99_ms": round(resid_p99, 3) if resid_p99 is not None else None,
                 "device_clock_drift_vs_host_ppm": round(drift_ppm, 2) if drift_ppm is not None else None,
                 "capture_to_host_receipt_ms": {"median": round(statistics.median(lat), 2) if lat else None,
                                                "p95": round(pct(lat, 95), 2) if lat else None, "max": round(max(lat), 2) if lat else None},
                 "monotonic": mono, "host_ts_before_receipt": causal}
        ts_ok &= bool(mono and causal and iv and abs(statistics.median(iv) - 1000 / FPS) <= 1.0
                      and resid_p99 is not None and resid_p99 <= 1.0)
    M["timestamps"] = ts
    C["H8_timestamps"] = V(ts_ok, bool(cap))
    bs_ok, bs = True, {}
    for e in gc.EYES:
        rows = eyes[e]
        types = [r["nal_types"].split() for r in rows]
        idr = [i for i, r in enumerate(rows) if r["recovery_point"] == "1"]
        intervals = []
        for i, j in zip(idr, idr[1:]):
            s_i, s_j = int(rows[i]["seq"]), int(rows[j]["seq"])
            if not any(s_i < g[0] + 1 <= s_j for g in gaps[e]):          # skip intervals that span a gap
                intervals.append(s_j - s_i)
        ft_ok = all((r["frame_type"] == "I") == (r["recovery_point"] == "1") for r in rows)
        sps_on_idr = all(rows[i]["sps"] == "1" for i in idr)
        slices = [sum(1 for t in tt if int(t) in pc.VCL_TYPES) for tt in types]
        layouts = {}
        for tt in types[:200]:
            layouts[" ".join(tt)] = layouts.get(" ".join(tt), 0) + 1
        nbytes = sum(int(r["bytes"]) for r in rows)
        bs[e] = {"nal_layouts_first_200": dict(sorted(layouts.items(), key=lambda x: -x[1])[:6]), "sps_pps_on_every_idr": sps_on_idr,
                 "aud_frames": sum(r["aud"] == "1" for r in rows), "slices_per_au": sorted(set(slices)),
                 "idr_intervals": sorted(set(intervals)), "frame_types": dict(au.get(e, {}).get("frame_types", {})),
                 "encoder_frame_type_matches_slices": ft_ok, "mean_bitrate_mbit_s": round(nbytes * 8 / (len(rows) / FPS) / 1e6, 3) if rows else None}
        bs_ok &= (bool(rows) and min(slices) >= 1 and all(r["width"] == "1280" and r["height"] == "800" for r in rows)
                  and au.get(e, {}).get("frame_types", {}).get("B", 0) == 0 and intervals and set(intervals) == {KEYINT} and ft_ok)
    raw_meta = {e: (d / "camA_{}_raw.h264".format(e)).exists() and pc.extract_meta((d / "camA_{}_raw.h264".format(e)).read_bytes()[:2_000_000])[0] is None
                for e in gc.EYES}
    M["bitstream"] = bs
    C["H9_bitstream"] = V(bs_ok and all(raw_meta.values()), bool(cap))
    pm = rep.get("pairing") or {}
    sl, sr = {int(r["seq"]) for r in eyes["left"]}, {int(r["seq"]) for r in eyes["right"]}
    both = len(sl & sr) / max(1, len(sl | sr))
    M["pairing"] = dict(pm, seqs_on_both_eyes_fraction=round(both, 4))
    C["H10_lr_sync"] = V(both >= 0.99 and pm.get("pairs", 0) > 0 and pm.get("skew_violations", 1) == 0, bool(pm))
    dec, dec_ok = {}, True
    for e in gc.EYES:
        rawp = d / "camA_{}_raw.h264".format(e)
        r_ = decode_file(rawp, "h264") if rawp.exists() else None
        segs = sorted(d.glob("camA_{}_seg*.ts".format(e)))
        ts_res = [decode_file(p) for p in segs]
        sent_seqs = [int(r["seq"]) for r in sent if r["eye"] == e]
        meta_seqs = [s for t in ts_res for s in t["meta_seqs"]]
        eofs = [s for t in ts_res for s in t["eof_seqs"]]
        samp = (r_ or {}).get("sampled", [])
        stds = [float(np.frombuffer(y, np.uint8).std()) for y in samp]
        dec[e] = {"raw_pictures": r_ and r_["pictures"], "raw_errors": r_ and r_["errors"], "captured": len(eyes[e]),
                  "ts_segments": len(segs), "ts_pictures": sum(t["pictures"] for t in ts_res), "ts_errors": sum(t["errors"] for t in ts_res),
                  "sent": len(sent_seqs), "meta_seqs_match_sent": meta_seqs == sent_seqs, "frame_end_markers": len(eofs),
                  "luma_std_min": round(min(stds), 2) if stds else None, "_sample": samp[:1]}
        dec_ok &= (r_ is not None and r_["errors"] == 0 and r_["pictures"] == len(eyes[e]) and dec[e]["ts_errors"] == 0
                   and dec[e]["ts_pictures"] == len(sent_seqs) and meta_seqs == sent_seqs and len(eofs) >= len(sent_seqs) - 1
                   and stds and min(stds) > 2)
    lr_diff = None
    if dec["left"]["_sample"] and dec["right"]["_sample"]:
        lr_diff = float(np.mean(np.abs(np.frombuffer(dec["left"]["_sample"][0], np.uint8).astype(int)
                                       - np.frombuffer(dec["right"]["_sample"][0], np.uint8).astype(int))))
    for e in gc.EYES:
        dec[e].pop("_sample")
    M["decode"] = dict(dec, left_right_mean_abs_diff_first_sample=round(lr_diff, 2) if lr_diff is not None else None)
    C["H11_decode_packaging"] = V(dec_ok and lr_diff is not None and lr_diff > 1.0, bool(cap))
    snd = rep.get("senders") or {}
    def as_list(v):                                   # PowerShell JSON: [] -> null, [x] -> x
        return [] if v is None else (v if isinstance(v, list) else [v])
    runner_ok = run is None or (as_list(run.get("leftover_gateway_processes")) == []
                                and as_list(run.get("crash_dumps_after")) == as_list(run.get("crash_dumps_before")))
    C["H12_clean_shutdown"] = V(rep.get("pipeline_stopped") is True and rep.get("device_closed") is True
                                and all(s.get("joined") for s in snd.values()) and len(snd) == 2 and rep.get("exit_code") == 0
                                and runner_ok, bool(snd) and run is not None)
    M["runner"] = {k: run.get(k) for k in ("gateway_exit_code", "leftover_gateway_processes", "crash_dumps_before", "crash_dumps_after")} if run else None
    C["H13_bitrate_info"] = "INFO: " + ", ".join("{} {} Mbit/s".format(e, bs[e]["mean_bitrate_mbit_s"]) for e in gc.EYES if e in bs)
    gating = [v for k, v in C.items() if not k.startswith("H13")]
    out = {"criteria": C, "measurements": M, "hardware_checks_by_gateway": rep.get("hardware_checks"),
           "overall": "PASS" if all(v == "PASS" for v in gating) else ("FAIL" if "FAIL" in gating else "INCOMPLETE"),
           "gw_dir": str(d), "runner": a.runner}
    (d / "stage1_analysis.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    for k, v in C.items():
        print("{:24s} {}".format(k, v))
    print("OVERALL", out["overall"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

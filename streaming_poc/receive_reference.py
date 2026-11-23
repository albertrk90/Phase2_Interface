"""Task 04B reference receiver: local RTSP -> decode -> pair -> fresh latest-frame display.

The Python stand-in for the Unity IStereoVideoSource, used to settle the
behaviour before any Unity code exists. For one camera ID it opens the two
eye paths (cam<ID>_left, cam<ID>_right) over RTSP/TCP, one reader thread
each, and for every packet:

  * reads the FrameMeta SEI from the packet bytes (CRC-checked);
  * decodes it (single-threaded, so the decoder adds no frame delay); packets
    without a slice (a trailing end-of-frame NAL left at end of stream) are
    counted, not decoded;
  * reads the burned-in barcode from the decoded luma and compares it with
    the SEI (sequence, eye, camera) -- the picture/metadata consistency test.

A Presenter simulates a display at --display-hz. At each refresh it takes the
NEWEST sequence number for which both eyes have arrived (never an unmatched
pair) and, unless --freshness off, checks that pair before showing it:

  * RELATIVE DELAY (clock-offset independent). For every completed pair the
    delay d = (receiver UTC when the pair completed) - (sender UTC capture
    time) is recorded. d contains the unknown clock offset, but the offset
    cancels in d - min(d over the last --delay-window-s): the pair's EXCESS
    delay over the fastest recent pair. A pair whose excess exceeds
    --max-excess-ms was held somewhere (a backlog after a stall, a parser
    holdback) and is REJECTED, together with every older complete pair still
    queued (obsolete backlog). Rejected pairs are never shown later, so the
    displayed sequence stays strictly increasing; the last good image stays up
    and the freeze is logged.
  * ABSOLUTE AGE (only with a trusted clock: the sender is this host, so the
    shared monotonic clock is used, or --clock-uncertainty-ms is given for
    UTC). Optional hard limit --max-age-ms (age minus uncertainty), off by
    default.
  * LABEL. A displayed pair is "fresh" only when that is verified: the delay
    reference has --warmup-pairs pairs behind it since the last (re)connect,
    or the trusted-clock age plus uncertainty is within --fresh-age-ms.
    Otherwise it is shown as "unverified" -- never called fresh just because
    it is the newest pair received.
  * REBASELINE. If every pair has been rejected for --rebaseline-s while pairs
    keep arriving, the path's delay has genuinely changed; the reference is
    reset to the recent pairs (logged) instead of freezing indefinitely.
  * RECONNECT. A link (re)connect resets the delay reference and the warm-up.

It logs frame age at display, freezes (no new pair for longer than
--freeze-ms), skipped sequence numbers by cause, rejected pairs with reasons,
late/obsolete arrivals, integrity errors, link loss and reconnection.

--probe-raw adds a third, diagnostic-only RTSP reader on the left path with
FFmpeg parsing disabled (fflags noparse): it records when each depacketised
chunk reaches the demuxer output, before any H.264 parser, so the release
time after parsing can be compared with the time the bytes actually arrived.

LOCALHOST ONLY (poc_common.check_local_url). No camera, robot or COROL code.

Outputs (results/rx_<stamp>_<camera>_<label>/): events.jsonl, frames.csv
(one row per displayed pair), arrivals.csv (one row per decoded frame per
eye), probe.csv (with --probe-raw), summary.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
import threading
import time
from collections import OrderedDict, deque
from dataclasses import asdict, dataclass

import poc_common as pc
import synthetic_stereo as ss

HERE = pathlib.Path(__file__).resolve().parent
EYE_ORDER = ("left", "right")

FRAME_FIELDS = ["t_display_utc_ns", "t_display_mono_ns", "seq", "age_utc_ms_left",
                "age_utc_ms_right", "age_mono_ms", "arrival_skew_ms", "interval_ms",
                "skipped_superseded", "skipped_incomplete", "skipped_missing", "skipped_rejected",
                "burst", "barcode_ok", "eye_ok", "freshness", "delay_ms", "excess_ms",
                "ref_delay_ms", "abs_age_ms", "clock_trusted",
                # two separate measures (smoke test 3):
                "rel_status", "baseline_shift_ms", "pairs_since_reset",
                "abs_age_lo_ms", "abs_age_hi_ms", "abs_uncertainty_ms", "clock_source", "abs_status"]

# Combined display label (column "freshness"):
#   fresh             absolute capture->display age verified within --fresh-age-ms
#                     (upper bound, i.e. including the clock uncertainty)
#   late              absolute age verified OVER --fresh-age-ms (lower bound): shown
#                     because it is the newest acceptable pair, never called fresh
#   fresh_relative    absolute age unknown or straddling the threshold, but the
#                     pair is consistent with a reference of >= --warmup-pairs
#                     pairs that has not drifted up by more than --max-excess-ms
#   relative_adapted  as above, but the reference has risen (re-baselined) by more
#                     than --max-excess-ms since the last reset: consistent with a
#                     persistently delayed stream, NOT evidence of freshness
#   unverified        neither check available yet (warm-up, untrusted clock)
#   unchecked         --freshness off

ARRIVAL_FIELDS = ["eye", "sei", "seq", "camera", "meta_eye", "t_dev_ns", "t_host_mono_ns",
                  "t_utc_ns", "flags", "host", "session", "trial", "config_id",
                  "t_arrival_utc_ns", "t_arrival_mono_ns", "t_decoded_mono_ns",
                  "pkt_pts", "pkt_time_base", "keyframe", "bytes",
                  "barcode_seq", "barcode_eye", "barcode_camera", "aud", "eof_seq"]

PROBE_FIELDS = ["t_arrival_mono_ns", "t_arrival_utc_ns", "pkt_pts", "bytes", "nal_types",
                "meta_seq", "eof_seq", "aud"]


@dataclass
class FreshnessPolicy:
    enabled: bool = True
    max_excess_ms: float = 100.0
    window_s: float = 10.0
    warmup_pairs: int = 20
    rebaseline_s: float = 2.0
    max_age_ms: float = 0.0              # 0 = no absolute rejection
    fresh_age_ms: float = 150.0
    clock_uncertainty_ms: float | None = None   # None: trusted only for same-host senders
    # Same-host sender: both ends read the one QueryPerformanceCounter clock, so
    # the uncertainty is only the gap between the capture stamp and the moment
    # the frame is really captured / shown (stamping points), taken as 1 ms.
    same_host_uncertainty_ms: float = 1.0
    local_host: str = ""


class ArrivalLog:
    """One row per decoded frame per eye: what came out of the SEI (in-band),
    the packet's transport timestamp, and the receiver's own clock readings.
    Shared by both reader threads."""

    def __init__(self, path):
        self._lock = threading.Lock()
        self._fh = open(path, "w", newline="", encoding="utf-8")
        self._w = csv.DictWriter(self._fh, fieldnames=ARRIVAL_FIELDS)
        self._w.writeheader()

    def write(self, eye, meta, sei_status, t_arr_utc, t_arr_mono, t_dec, packet, data, code):
        marks = pc.frame_end_markers(data)
        row = {"eye": eye, "sei": sei_status, "t_arrival_utc_ns": t_arr_utc,
               "t_arrival_mono_ns": t_arr_mono, "t_decoded_mono_ns": t_dec,
               "pkt_pts": packet.pts, "pkt_time_base": str(packet.time_base),
               "keyframe": int(packet.is_keyframe), "bytes": len(data),
               "aud": marks["aud"], "eof_seq": " ".join(map(str, marks["eof_seq"]))}
        if meta is not None:
            row.update({"seq": meta.seq, "camera": meta.camera, "meta_eye": meta.eye,
                        "t_dev_ns": meta.t_dev_ns, "t_host_mono_ns": meta.t_host_mono_ns,
                        "t_utc_ns": meta.t_utc_ns, "flags": meta.flags, "host": meta.host,
                        "session": meta.session, "trial": meta.trial,
                        "config_id": meta.config_id})
        if code is not None:
            row.update({"barcode_seq": code[0], "barcode_eye": code[1], "barcode_camera": code[2]})
        with self._lock:
            self._w.writerow(row)

    def close(self):
        with self._lock:
            self._fh.close()


class Presenter:
    """Pairing, freshness check, latest-frame selection, freeze and gap accounting.

    Pure logic: arrivals and clock readings are passed in, so it can be tested
    without a network. Thread-safe for one display thread plus reader threads.
    """

    def __init__(self, camera, fps, freeze_ms, log=None, frame_sink=None, keep=256,
                 policy: FreshnessPolicy | None = None):
        self.camera = camera
        self.fps = fps
        self.period_ms = 1000.0 / fps
        self.freeze_ns = int(freeze_ms * 1e6)
        self.log = log
        self.sink = frame_sink
        self.keep = keep
        self.pol = policy or FreshnessPolicy(enabled=False)
        self._lock = threading.Lock()
        self.buf = {eye: OrderedDict() for eye in EYE_ORDER}
        self.pairs = OrderedDict()          # seq -> completion info, both eyes present
        self.hist = deque()                 # (t_complete_mono, delay_ms) of completed pairs
        self.pairs_since_reset = 0
        self.ref_floor = None               # lowest reference seen since the last reset
        self.last_seq = None                # last DISPLAYED seq
        self.floor_seq = None               # max(last displayed, last rejected)
        self.rejected = deque(maxlen=4096)
        self._rejected_set = set()
        self.streak_start = None            # first rejection of the current streak (mono ns)
        self.streak_pairs = 0
        self.last_new_mono = None
        self.in_freeze = False
        self.freeze_start_mono = None
        self.c = {"displayed": 0, "superseded": 0, "incomplete": 0, "missing": 0,
                  "late_discarded": 0, "obsolete_discarded": 0, "integrity_errors": 0,
                  "barcode_fail": 0, "eye_mismatch": 0, "camera_mismatch": 0, "freezes": 0,
                  "burst_displayed": 0, "rejected_excess_delay": 0, "rejected_absolute_age": 0,
                  "rejected_obsolete": 0, "fresh_displayed": 0, "unverified_displayed": 0,
                  "late_displayed": 0, "fresh_relative_displayed": 0,
                  "relative_adapted_displayed": 0,
                  "rebaselines": 0, "freshness_resets": 0, "skipped_rejected": 0}
        self.ages = []
        self.freeze_ms = []

    # -- helpers -----------------------------------------------------------

    def _event(self, type_, payload, t_utc=None, t_mono=None):
        if self.log is not None:
            self.log.emit(type_, payload, t_utc=t_utc, t_mono=t_mono)

    def _clock(self, meta):
        """(trusted, uncertainty_ms, use_mono) for absolute ages of this sender."""
        if meta.host and meta.host == self.pol.local_host:
            return True, float(self.pol.same_host_uncertainty_ms), True
        if self.pol.clock_uncertainty_ms is not None:
            return True, float(self.pol.clock_uncertainty_ms), False
        return False, None, False

    def _ref_delay(self, now_mono):
        cut = now_mono - int(self.pol.window_s * 1e9)
        while self.hist and self.hist[0][0] < cut:
            self.hist.popleft()
        return min(d for _t, d in self.hist) if self.hist else None

    def _purge_upto(self, seq):
        for b in (self.buf["left"], self.buf["right"]):
            for s in [s for s in b if s <= seq]:
                del b[s]
        for s in [s for s in self.pairs if s <= seq]:
            del self.pairs[s]

    def _mark_rejected(self, seq):
        if len(self.rejected) == self.rejected.maxlen:
            self._rejected_set.discard(self.rejected[0])
        self.rejected.append(seq)
        self._rejected_set.add(seq)

    # -- inputs ------------------------------------------------------------

    def on_link_reset(self, eye, now_mono=None, now_utc=None):
        """A reader (re)connected: the delay reference is no longer valid."""
        with self._lock:
            self.hist.clear()
            self.pairs_since_reset = 0
            self.ref_floor = None
            self.streak_start = None
            self.streak_pairs = 0
            self.c["freshness_resets"] += 1
        self._event("freshness_reset", {"camera": self.camera, "eye": eye},
                    t_utc=now_utc, t_mono=now_mono)

    def on_frame(self, eye, rec):
        """rec: {'meta': FrameMeta, 't_arrival_mono', 't_arrival_utc',
        't_decoded_mono', 'barcode': (seq, eye, cam) | None}"""
        seq = rec["meta"].seq
        with self._lock:
            if self.floor_seq is not None and seq <= self.floor_seq:
                key = ("late_discarded" if self.last_seq is not None and seq <= self.last_seq
                       else "obsolete_discarded")
                self.c[key] += 1
                return
            b = self.buf[eye]
            b[seq] = rec
            while len(b) > self.keep:
                b.popitem(last=False)
            other = self.buf["right" if eye == "left" else "left"].get(seq)
            if other is not None and seq not in self.pairs:
                l, r = (rec, other) if eye == "left" else (other, rec)
                t_cu = max(l["t_arrival_utc"], r["t_arrival_utc"])
                t_cm = max(l["t_arrival_mono"], r["t_arrival_mono"])
                cap = min(l["meta"].t_utc_ns, r["meta"].t_utc_ns)
                delay = (t_cu - cap) / 1e6
                self.pairs[seq] = {"t_complete_mono": t_cm, "t_complete_utc": t_cu, "delay_ms": delay}
                self.hist.append((t_cm, delay))
                self.pairs_since_reset += 1
                while len(self.pairs) > self.keep:
                    self.pairs.popitem(last=False)

    # -- display -----------------------------------------------------------

    def tick(self, now_mono, now_utc):
        """One display refresh. Returns the displayed row (dict) or None."""
        with self._lock:
            if not self.pairs:
                self._check_freeze(now_mono, now_utc)
                return None
            seq = max(self.pairs)
            pair = {"left": self.buf["left"][seq], "right": self.buf["right"][seq]}
            info = self.pairs[seq]
            ref = self._ref_delay(now_mono) if self.pol.enabled else None
            excess = info["delay_ms"] - ref if ref is not None else None
            trusted, unc, use_mono = self._clock(pair["left"]["meta"])
            if use_mono:
                abs_age = (now_mono - min(p["meta"].t_host_mono_ns for p in pair.values())) / 1e6
            elif trusted:
                abs_age = (now_utc - min(p["meta"].t_utc_ns for p in pair.values())) / 1e6
            else:
                abs_age = None

            reasons = []
            if self.pol.enabled:
                if excess is not None and excess > self.pol.max_excess_ms:
                    reasons.append("excess_delay")
                if trusted and self.pol.max_age_ms > 0 and abs_age - unc > self.pol.max_age_ms:
                    reasons.append("absolute_age")
            if reasons:
                return self._reject(seq, reasons, info, ref, excess, abs_age, trusted,
                                    now_mono, now_utc)
            self.streak_start, self.streak_pairs = None, 0

            # measure 1: relative freshness (clock-offset independent)
            if ref is not None:
                self.ref_floor = ref if self.ref_floor is None else min(self.ref_floor, ref)
            shift = (ref - self.ref_floor) if ref is not None and self.ref_floor is not None else None
            rel_verified = self.pairs_since_reset >= self.pol.warmup_pairs
            rel_status = ("off" if not self.pol.enabled else
                          "verified" if rel_verified else "warmup")
            # measure 2: estimated absolute capture->display age, with bounds
            if abs_age is None:
                abs_lo = abs_hi = None
                abs_status = "unknown"
            else:
                abs_lo, abs_hi = abs_age - unc, abs_age + unc
                abs_status = ("within" if abs_hi <= self.pol.fresh_age_ms else
                              "over" if abs_lo > self.pol.fresh_age_ms else "uncertain")
            if not self.pol.enabled:
                label = "unchecked"
            elif abs_status == "over":
                label = "late"
            elif abs_status == "within":
                label = "fresh"
            elif rel_verified and (shift is None or shift <= self.pol.max_excess_ms):
                label = "fresh_relative"
            elif rel_verified:
                label = "relative_adapted"
            else:
                label = "unverified"

            sup = inc = mis = rej = 0
            if self.last_seq is not None:
                left, right = self.buf["left"], self.buf["right"]
                for s in range(self.last_seq + 1, seq):
                    if s in self._rejected_set:
                        rej += 1
                    elif s in left and s in right:
                        sup += 1
                    elif s in left or s in right:
                        inc += 1
                    else:
                        mis += 1
            self._purge_upto(seq)
            interval_ms = ((now_mono - self.last_new_mono) / 1e6
                           if self.last_new_mono is not None else None)
            if self.in_freeze:
                dur = (now_mono - self.freeze_start_mono) / 1e6
                self.freeze_ms.append(dur)
                self._event("freeze_end", {"camera": self.camera, "duration_ms": round(dur, 1),
                                           "resumed_seq": seq, "last_seq": self.last_seq,
                                           "skipped": sup + inc + mis + rej},
                            t_utc=now_utc, t_mono=now_mono)
                self.in_freeze = False
            self.c["superseded"] += sup
            self.c["incomplete"] += inc
            self.c["missing"] += mis
            self.c["skipped_rejected"] += rej
            self.c["displayed"] += 1
            if label != "unchecked":
                self.c[label + "_displayed"] += 1
            pairs_since_reset = self.pairs_since_reset
            self.last_seq = seq
            self.floor_seq = seq if self.floor_seq is None else max(self.floor_seq, seq)
            self.last_new_mono = now_mono

        age_l = (now_utc - pair["left"]["meta"].t_utc_ns) / 1e6
        age_r = (now_utc - pair["right"]["meta"].t_utc_ns) / 1e6
        age_mono = (now_mono - min(p["meta"].t_host_mono_ns for p in pair.values())) / 1e6
        skew = (pair["right"]["t_arrival_mono"] - pair["left"]["t_arrival_mono"]) / 1e6
        burst = any(p["meta"].flags & pc.FLAG_BURST for p in pair.values())
        barcode_ok = all(p["barcode"] == (seq, pc.EYES[e], pc.CAMERAS[self.camera])
                         for e, p in pair.items())
        eye_ok = all(p["meta"].eye == e for e, p in pair.items())
        cam_ok = all(p["meta"].camera == self.camera for p in pair.values())
        self.ages.append(max(age_l, age_r))
        if burst:
            self.c["burst_displayed"] += 1
        if not (barcode_ok and eye_ok and cam_ok):
            self.c["integrity_errors"] += 1
            self.c["barcode_fail"] += 0 if barcode_ok else 1
            self.c["eye_mismatch"] += 0 if eye_ok else 1
            self.c["camera_mismatch"] += 0 if cam_ok else 1
            self._event("integrity_error", {"seq": seq, "barcode": {e: p["barcode"] for e, p in pair.items()},
                                            "meta_eye": {e: p["meta"].eye for e, p in pair.items()},
                                            "meta_camera": {e: p["meta"].camera for e, p in pair.items()}},
                        t_utc=now_utc, t_mono=now_mono)
        row = {"t_display_utc_ns": now_utc, "t_display_mono_ns": now_mono, "seq": seq,
               "age_utc_ms_left": round(age_l, 2), "age_utc_ms_right": round(age_r, 2),
               "age_mono_ms": round(age_mono, 2), "arrival_skew_ms": round(skew, 2),
               "interval_ms": round(interval_ms, 2) if interval_ms is not None else "",
               "skipped_superseded": sup, "skipped_incomplete": inc, "skipped_missing": mis,
               "skipped_rejected": rej, "burst": int(burst), "barcode_ok": int(barcode_ok),
               "eye_ok": int(eye_ok and cam_ok), "freshness": label,
               "delay_ms": round(info["delay_ms"], 2),
               "excess_ms": round(excess, 2) if excess is not None else "",
               "ref_delay_ms": round(ref, 2) if ref is not None else "",
               "abs_age_ms": round(abs_age, 2) if abs_age is not None else "",
               "clock_trusted": int(trusted),
               "rel_status": rel_status,
               "baseline_shift_ms": round(shift, 2) if shift is not None else "",
               "pairs_since_reset": pairs_since_reset,
               "abs_age_lo_ms": round(abs_lo, 2) if abs_lo is not None else "",
               "abs_age_hi_ms": round(abs_hi, 2) if abs_hi is not None else "",
               "abs_uncertainty_ms": unc if unc is not None else "",
               "clock_source": ("same_host_monotonic" if use_mono else
                                "utc_configured_uncertainty" if trusted else "untrusted"),
               "abs_status": abs_status}
        if self.sink is not None:
            self.sink(row)
        return row

    def _reject(self, seq, reasons, info, ref, excess, abs_age, trusted, now_mono, now_utc):
        """Reject `seq` and every older complete pair (obsolete backlog). Lock held."""
        older = [s for s in self.pairs if s < seq]
        for s in older:
            self._mark_rejected(s)
        self._mark_rejected(seq)
        self.c["rejected_obsolete"] += len(older)
        for r in reasons:
            self.c["rejected_" + r] += 1
        self._purge_upto(seq)
        self.floor_seq = seq if self.floor_seq is None else max(self.floor_seq, seq)
        if self.streak_start is None:
            self.streak_start = now_mono
        self.streak_pairs += 1 + len(older)
        self._event("pair_rejected", {"camera": self.camera, "seq": seq, "reasons": reasons,
                                      "delay_ms": round(info["delay_ms"], 2),
                                      "ref_delay_ms": round(ref, 2) if ref is not None else None,
                                      "excess_ms": round(excess, 2) if excess is not None else None,
                                      "abs_age_ms": round(abs_age, 2) if abs_age is not None else None,
                                      "clock_trusted": trusted, "obsolete_older": older,
                                      "threshold_ms": self.pol.max_excess_ms},
                    t_utc=now_utc, t_mono=now_mono)
        # A delay that has changed for good would otherwise freeze the display
        # until the window slides past the old minimum: re-baseline instead.
        need = max(3, int(0.5 * self.fps * self.pol.rebaseline_s))
        if (now_mono - self.streak_start >= self.pol.rebaseline_s * 1e9
                and self.streak_pairs >= need and "excess_delay" in reasons):
            cut = now_mono - int(self.pol.rebaseline_s * 1e9)
            old_ref = ref
            while self.hist and self.hist[0][0] < cut:
                self.hist.popleft()
            new_ref = min(d for _t, d in self.hist) if self.hist else None
            self.c["rebaselines"] += 1
            self.streak_start, self.streak_pairs = None, 0
            self._event("delay_rebaseline", {"camera": self.camera, "old_ref_ms": old_ref,
                                             "new_ref_ms": new_ref,
                                             "after_s": self.pol.rebaseline_s},
                        t_utc=now_utc, t_mono=now_mono)
        self._check_freeze(now_mono, now_utc)
        return None

    def _check_freeze(self, now_mono, now_utc):
        if self.last_new_mono is None or self.in_freeze:
            return
        if now_mono - self.last_new_mono > self.freeze_ns:
            self.in_freeze = True
            self.freeze_start_mono = self.last_new_mono
            self.c["freezes"] += 1
            self._event("freeze_start", {"camera": self.camera, "last_seq": self.last_seq,
                                         "since_last_new_ms": round((now_mono - self.last_new_mono) / 1e6, 1),
                                         "threshold_ms": self.freeze_ns / 1e6},
                        t_utc=now_utc, t_mono=now_mono)

    def summary(self):
        with self._lock:
            c = dict(self.c)
        return {"counts": c, "freshness_policy": asdict(self.pol),
                "age_ms": {"median": pc.percentile(self.ages, 50), "p95": pc.percentile(self.ages, 95),
                           "max": max(self.ages) if self.ages else None, "n": len(self.ages)},
                "freeze_ms": {"n": len(self.freeze_ms), "max": max(self.freeze_ms) if self.freeze_ms else None,
                              "total": sum(self.freeze_ms)}}


def _rx_options(a, extra_fflags=""):
    return {"rtsp_transport": "tcp", "fflags": "nobuffer" + extra_fflags, "flags": "low_delay",
            "max_delay": "0", "reorder_queue_size": "0",
            "probesize": str(a.probesize), "analyzeduration": str(a.analyzeduration)}


class EyeReader(threading.Thread):
    """Reads one eye path; reconnects with backoff; feeds the Presenter."""

    def __init__(self, eye, url, presenter, log, args, stop_evt, arrivals=None):
        super().__init__(name="rx-" + eye, daemon=True)
        self.eye, self.url = eye, pc.check_local_url(url)
        self.p, self.log, self.args, self.stop_evt = presenter, log, args, stop_evt
        self.arrivals = arrivals
        self.save_dir = None
        if args.save_every > 0:
            self.save_dir = pathlib.Path(args.out_dir) / "frames"
            self.save_dir.mkdir(exist_ok=True)
        self.c = {"packets": 0, "frames": 0, "no_sei": 0, "sei_errors": 0, "decode_errors": 0,
                  "decode_errors_before_sync": 0, "non_vcl_packets": 0, "connects": 0,
                  "link_downs": 0, "bytes": 0}
        self.backoff = pc.Backoff(lo=0.25, hi=args.reconnect_max_s, cur=0.25)

    def _save_pgm(self, frame, seq):
        """Decoded luma as an 8-bit PGM, for offline comparison with the
        regenerated synthetic frame (analysis only; never displayed)."""
        y = frame.planes[0]
        w, h, stride = frame.width, frame.height, y.line_size
        mv = memoryview(y)
        rows = b"".join(bytes(mv[r * stride:r * stride + w]) for r in range(h))
        (self.save_dir / "{}_{:06d}.pgm".format(self.eye, seq)).write_bytes(
            b"P5\n%d %d\n255\n" % (w, h) + rows)

    def run(self):
        import av
        a = self.args
        while not self.stop_evt.is_set():
            container = None
            try:
                container = av.open(self.url, options=_rx_options(a),
                                    timeout=(a.open_timeout, a.read_timeout))
                vs = container.streams.video[0]
                vs.thread_type = "SLICE"
                vs.codec_context.thread_count = 1
                self.c["connects"] += 1
                self.backoff.reset()
                self.log.emit("link_up", {"eye": self.eye, "url": self.url,
                                          "codec": vs.codec_context.name,
                                          "size": [vs.codec_context.width, vs.codec_context.height]})
                self.p.on_link_reset(self.eye)
                synced = False
                for packet in container.demux(vs):
                    if self.stop_evt.is_set():
                        break
                    if packet.size == 0:
                        continue
                    t_arr_mono, t_arr_utc = pc.mono_ns(), pc.utc_ns()
                    data = bytes(packet)
                    self.c["packets"] += 1
                    self.c["bytes"] += len(data)
                    if not any(t in pc.VCL_TYPES for t in pc.nal_types(data)):
                        # e.g. a trailing end-of-frame NAL flushed at end of stream
                        self.c["non_vcl_packets"] += 1
                        continue
                    meta, err = pc.extract_meta(data)
                    if packet.is_keyframe:
                        synced = True
                    if err:
                        self.c["sei_errors"] += 1
                        self.log.emit("sei_error", {"eye": self.eye, "error": err})
                    elif meta is None and synced:
                        self.c["no_sei"] += 1
                    try:
                        frames = packet.decode()
                    except Exception as e:           # noqa: BLE001
                        key = "decode_errors" if synced else "decode_errors_before_sync"
                        self.c[key] += 1
                        if synced:
                            self.log.emit("decode_error", {"eye": self.eye, "error": str(e)})
                        continue
                    for f in frames:
                        t_dec = pc.mono_ns()
                        self.c["frames"] += 1
                        y = f.planes[0]
                        code = ss.read_barcode(memoryview(y), y.line_size)
                        if (self.save_dir is not None and meta is not None
                                and meta.seq % a.save_every == 0):
                            self._save_pgm(f, meta.seq)
                        if self.arrivals is not None:
                            self.arrivals.write(self.eye, meta, "error" if err else ("ok" if meta else "missing"),
                                                t_arr_utc, t_arr_mono, t_dec, packet, data, code)
                        if meta is None:
                            continue
                        self.p.on_frame(self.eye, {"meta": meta, "t_arrival_mono": t_arr_mono,
                                                   "t_arrival_utc": t_arr_utc,
                                                   "t_decoded_mono": t_dec, "barcode": code})
                raise EOFError("stream ended")
            except Exception as e:                   # noqa: BLE001
                if self.stop_evt.is_set():
                    break
                self.c["link_downs"] += 1
                delay = self.backoff.next()
                self.log.emit("link_down", {"eye": self.eye, "error": "{}: {}".format(type(e).__name__, e),
                                            "retry_in_s": delay})
                self.stop_evt.wait(delay)
            finally:
                if container is not None:
                    try:
                        container.close()
                    except Exception:
                        pass


class RawProbe(threading.Thread):
    """Diagnostic only: the same path with FFmpeg's parser disabled, so each
    packet is a depacketised chunk exactly as it left the RTSP/RTP layer.
    Never decodes, never feeds the Presenter."""

    def __init__(self, url, log, args, stop_evt, path):
        super().__init__(name="rx-probe", daemon=True)
        self.url, self.log, self.args, self.stop_evt = pc.check_local_url(url), log, args, stop_evt
        self._fh = open(path, "w", newline="", encoding="utf-8")
        self._w = csv.DictWriter(self._fh, fieldnames=PROBE_FIELDS)
        self._w.writeheader()
        self.c = {"packets": 0, "connects": 0, "errors": 0}
        self.backoff = pc.Backoff(lo=0.25, hi=args.reconnect_max_s, cur=0.25)

    def run(self):
        import av
        a = self.args
        try:
            while not self.stop_evt.is_set():
                container = None
                try:
                    container = av.open(self.url, options=_rx_options(a, "+noparse+nofillin"),
                                        timeout=(a.open_timeout, a.read_timeout))
                    vs = container.streams.video[0]
                    self.c["connects"] += 1
                    self.backoff.reset()
                    self.log.emit("probe_link_up", {"url": self.url})
                    for packet in container.demux(vs):
                        if self.stop_evt.is_set():
                            break
                        if packet.size == 0:
                            continue
                        t_m, t_u = pc.mono_ns(), pc.utc_ns()
                        data = bytes(packet)
                        meta, _ = pc.extract_meta(data)
                        marks = pc.frame_end_markers(data)
                        self._w.writerow({"t_arrival_mono_ns": t_m, "t_arrival_utc_ns": t_u,
                                          "pkt_pts": packet.pts, "bytes": len(data),
                                          "nal_types": " ".join(map(str, pc.nal_types(data))),
                                          "meta_seq": meta.seq if meta else "",
                                          "eof_seq": " ".join(map(str, marks["eof_seq"])),
                                          "aud": marks["aud"]})
                        self.c["packets"] += 1
                    raise EOFError("stream ended")
                except Exception as e:               # noqa: BLE001
                    if self.stop_evt.is_set():
                        break
                    self.c["errors"] += 1
                    delay = self.backoff.next()
                    self.log.emit("probe_link_down", {"error": "{}: {}".format(type(e).__name__, e),
                                                      "retry_in_s": delay})
                    self.stop_evt.wait(delay)
                finally:
                    if container is not None:
                        try:
                            container.close()
                        except Exception:
                            pass
        finally:
            self._fh.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--camera", choices=("A", "B"), required=True)
    ap.add_argument("--server", default="rtsp://127.0.0.1:8554")
    ap.add_argument("--fps", type=int, default=20, help="expected source rate")
    ap.add_argument("--display-hz", type=float, default=60.0)
    ap.add_argument("--freeze-ms", type=float, default=125.0,
                    help="no new pair for longer than this is a freeze (default 2.5 frame periods)")
    ap.add_argument("--freshness", choices=("on", "off"), default="on")
    ap.add_argument("--max-excess-ms", type=float, default=100.0)
    ap.add_argument("--delay-window-s", type=float, default=10.0)
    ap.add_argument("--warmup-pairs", type=int, default=20)
    ap.add_argument("--rebaseline-s", type=float, default=2.0)
    ap.add_argument("--max-age-ms", type=float, default=0.0, help="absolute limit; 0 = off")
    ap.add_argument("--fresh-age-ms", type=float, default=150.0)
    ap.add_argument("--clock-uncertainty-ms", type=float, default=None,
                    help="trust UTC capture times from other hosts to within this; "
                         "unset = absolute ages only for same-host senders")
    ap.add_argument("--probe-raw", action="store_true",
                    help="diagnostic: also read the left path with FFmpeg parsing disabled")
    ap.add_argument("--seconds", type=float, default=60.0,
                    help="run time; with --done-flag, the maximum run time")
    ap.add_argument("--done-flag", default=None,
                    help="stop --drain-s after this file appears (written by the publisher "
                         "when it has sent its last frame), instead of after --seconds")
    ap.add_argument("--drain-s", type=float, default=3.0)
    ap.add_argument("--reconnect-max-s", type=float, default=1.0,
                    help="cap of the reconnect backoff (0.25 s doubling)")
    ap.add_argument("--open-timeout", type=float, default=3.0)
    ap.add_argument("--read-timeout", type=float, default=3.0)
    ap.add_argument("--probesize", type=int, default=500000)
    ap.add_argument("--analyzeduration", type=int, default=500000)
    ap.add_argument("--session", default="poc")
    ap.add_argument("--trial", default="")
    ap.add_argument("--label", default="run")
    ap.add_argument("--save-every", type=int, default=0,
                    help="save the decoded luma of every Nth sequence number as PGM (0 = off)")
    ap.add_argument("--out", default=str(HERE / "results"))
    args = ap.parse_args(argv)

    urls = {eye: pc.check_local_url("{}/cam{}_{}".format(args.server.rstrip("/"), args.camera, eye))
            for eye in EYE_ORDER}
    out_dir = pathlib.Path(args.out) / "rx_{}_{}_{}".format(pc.stamp(), args.camera, args.label)
    out_dir.mkdir(parents=True, exist_ok=False)
    args.out_dir = str(out_dir)
    log = pc.EventLog(out_dir / "events.jsonl", "receiver_" + args.camera,
                      args.session, args.trial or args.label)
    fh = open(out_dir / "frames.csv", "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=FRAME_FIELDS)
    writer.writeheader()
    policy = FreshnessPolicy(enabled=args.freshness == "on", max_excess_ms=args.max_excess_ms,
                             window_s=args.delay_window_s, warmup_pairs=args.warmup_pairs,
                             rebaseline_s=args.rebaseline_s, max_age_ms=args.max_age_ms,
                             fresh_age_ms=args.fresh_age_ms,
                             clock_uncertainty_ms=args.clock_uncertainty_ms,
                             local_host=pc.host_id())
    presenter = Presenter(args.camera, args.fps, args.freeze_ms, log, writer.writerow, policy=policy)
    stop = threading.Event()
    arrivals = ArrivalLog(out_dir / "arrivals.csv")
    readers = [EyeReader(eye, urls[eye], presenter, log, args, stop, arrivals) for eye in EYE_ORDER]
    probe = RawProbe(urls["left"], log, args, stop, out_dir / "probe.csv") if args.probe_raw else None
    log.emit("run_start", {"argv": sys.argv[1:], "urls": urls, "display_hz": args.display_hz,
                           "freeze_ms": args.freeze_ms, "freshness": asdict(policy),
                           "probe_raw": bool(probe)})
    print("[rx {}] reading {}{}".format(args.camera, ", ".join(urls.values()),
                                        " (+raw probe on left)" if probe else ""))
    for r in readers + ([probe] if probe else []):
        r.start()

    period = 1.0 / args.display_hz
    t_end = time.monotonic() + args.seconds
    next_t = time.monotonic()
    late_ticks = 0
    done_flag = pathlib.Path(args.done_flag) if args.done_flag else None
    done_seen = None
    stop_reason = "max_seconds" if done_flag else "seconds"
    try:
        while time.monotonic() < t_end:
            if done_flag is not None:
                if done_seen is None and done_flag.exists():
                    done_seen = time.monotonic()
                    log.emit("publisher_done_seen", {"flag": str(done_flag), "drain_s": args.drain_s})
                if done_seen is not None and time.monotonic() - done_seen >= args.drain_s:
                    stop_reason = "publisher_done_and_drained"
                    break
            next_t += period
            presenter.tick(pc.mono_ns(), pc.utc_ns())
            wait = next_t - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            else:
                late_ticks += 1
                next_t = time.monotonic()
    except KeyboardInterrupt:
        log.emit("interrupted", {})
    finally:
        stop.set()
        for r in readers + ([probe] if probe else []):
            r.join(timeout=args.read_timeout + 1)
        summary = {"camera": args.camera, "label": args.label, "seconds": args.seconds,
                   "stop_reason": stop_reason,
                   "elapsed_s": round(time.monotonic() - (t_end - args.seconds), 2),
                   "presenter": presenter.summary(),
                   "readers": {r.eye: r.c for r in readers},
                   "probe": probe.c if probe else None,
                   "late_display_ticks": late_ticks, "out_dir": str(out_dir)}
        log.emit("run_end", summary)
        log.close()
        fh.close()
        arrivals.close()
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("[rx {}] done: {}".format(args.camera, json.dumps(summary["presenter"]["counts"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())

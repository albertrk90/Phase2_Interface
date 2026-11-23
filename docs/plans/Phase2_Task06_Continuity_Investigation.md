# Task 06 follow-up: video continuity investigation (6 Nov 2026; offline only)

**Scope:** read-only analysis of the Stage 1 and Stage 2 evidence; offline simulation; opt-in code paths with regression tests.
- **Not done:** no camera, MediaMTX, COROL or robot access; no packet capture; no OS setting changed.
- **Live configuration:** the validated live defaults are unchanged (keyint 20, `resync`, 150 ms send-age guard).

## 1. Recommendation (smallest justified change)

**For the next live preview, run Camera A with an H.264 keyframe interval of 10 instead of 20.**
- **Unchanged:** 20 fps, 1280 × 800, CBR 8 Mbit/s, rectification, calibration, the gateway logic, the 150 ms guard and the receiver policy.
- **How:** one existing parameter: `run_stage2.ps1 -Keyint 10`, which passes `--keyint 10`. The default stays 20 until you approve.

| Effect | Evidence |
|---|---|
| Freezes from the same transport stalls are about 30 % shorter: median 874 → 624 ms, worst 1348 → 849 ms (20 stalls of 315 ms, one per GOP phase) | Calibrated simulation (§5) |
| Right-eye frames lost per stall about 36 % fewer | Same simulation |
| **What is displayed is unchanged:** every pair fresh, at most 94 ms old; no stale display; L/R intact; decodable | Same simulation; `tests/test_continuity.py` |
| **Cost:** at a fixed 8 Mbit/s, about 20 % fewer bits per P-frame. IDR frames (209 kB, 5× a P-frame) come twice a second. Stand-in estimate on real Camera A imagery: −0.9 dB median PSNR. Each IDR adds 1.6–2.9 ms capture-to-host latency | Stage 1/2 OAK frame sizes; libx264 stand-in (not the OAK encoder) |

**It does not remove the stalls.** It shortens the freeze each stall causes. The OAK's real quality at keyint 10 must be checked in the next live preview (hardware checks: recovery interval 10, bitrate, a visual check).

**Not recommended yet:** raising the age limit to 400 ms, or the new catch-up policy. They shorten freezes further (to about 366 ms), but they display catch-up pairs up to 138–153 ms old (§4). That weakens the no-stale-display property unless the receiver also gets an absolute-age limit, which is a further change to a validated setting.

## 2. Transport delays: best evidence (bounded; cause not proven)

**Stage 2, six events, all on the right-eye gateway → MediaMTX TCP connection:**

| Onset frame | Delivery held | Blocked write | Frame |
|---|---|---|---|
| 261 | 321 ms | seq 263, 215 ms | P, 42 kB |
| 314 | 314 | seq 315, 263 | P, 44 kB |
| 696 | 310 | seq 698, 210 | P, 48 kB |
| 760 | 316 | seq 760, 316 | IDR, 208 kB |
| 961 | 322 | seq 963, 221 | P, 41 kB |
| 1326 | 318 | seq 1328, 213 | P, 36 kB |

The intervals between events were 2.6, 19.1, 3.2, 10.1 and 18.2 s.

**Pattern:**
1. Frames written normally stopped being delivered for a near-constant **310–322 ms**.
2. Writes continued until about 100 kB (two P-frames) was buffered; the next write blocked until the hold ended.
3. Every other write on both eyes took ≤ 15 ms.
4. The left-eye connection was unaffected each time.

**Ruled out by the evidence:**
- **Camera:** capture → host was normal, with 0 sequence gaps.
- **Gateway capture loop and CPU:** left-eye writes in the same windows took 1–9 ms.
- **Frame type or size:** 5 P-frames and 1 IDR, all typical sizes.
- **MediaMTX warnings:** its log has none at those times. It does note "RTP packets too big (1460 > 1440), remuxing", but that applies from the start, to both paths.
- **Unity:** the oracle replay is exact.

**Earlier observations:**
- **Similar ~300 ms episodes occurred** with the synthetic libx264 publisher → MediaMTX (G1, about 15 per minute in T4).
- **None occurred** in the G1 rerun, or in Stage 1, which had no network.

**Hypotheses, most to least consistent:**
1. **A lost segment on the loopback TCP connection, recovered by the retransmission timeout.** The near-constant ~315 ms matches Windows' documented default minimum RTO of 300 ms. The active value cannot be read without admin rights (`Get-NetTCPSetting` shows it blank). Loopback runs in "inline" mode with 5 workers.
2. **Nagle/delayed-ACK interaction:** typically about 200 ms on Windows, which is less consistent with a constant 310–322 ms.
3. **MediaMTX pausing its reads:** would not explain one connection only, and nothing is logged.

**Why only the right eye** in this run is not established.

**Stopping here, as instructed.** A next step without privileges or drivers would be to record `netstat -s -p tcp` "Segments Retransmitted" immediately before and after a run, with Wi-Fi off and the host quiet. An increase of about the number of stalls would support hypothesis 1. It was not run.

## 3. GOP-drop logic and keyframe requests

- **More frames are discarded than strictly necessary.** In Stage 2, **80 of the 107 dropped right-eye frames (75 %) reached the host after the stall had ended.** They were fresh, but undecodable because the chain before them had been cut.
  - The validated `resync` policy waits for the next IDR, up to 19 frames at keyint 20. This is the price of never sending a broken chain without a keyframe request.
- **No runtime keyframe request** exists in the installed DepthAI 3.11.0. `VideoEncoder` has one frame input and no control or config input; `keyframeFrequency` is a pipeline-build property. Forcing an IDR would mean rebuilding the pipeline, which is not acceptable mid-session.
  - A web search found no DepthAI documentation of a keyframe request, only other vendors' APIs ([GStreamer](https://gitlab.freedesktop.org/gstreamer/gst-plugins-base/-/merge_requests/883), [QNX](https://www.qnx.com/developers/docs/7.1/com.qnx.doc.camera/topic/camera_force_video_keyframe.html), [NVIDIA Jetson](https://docs.nvidia.com/jetson/archives/r34.1/ApiReference/group__V4L2Enc.html), [Microsoft](https://learn.microsoft.com/en-us/windows/win32/medfound/forcedkeyframeinsertion)).
  - Whether newer DepthAI versions add one is not established; upgrading is out of scope.
- **So the keyframe interval is the only encoder-side lever** on the cost of a drop: the worst wait falls from 950 ms to 450 ms.

## 4. Raising the send-age guard to 400 ms: analysis (default unchanged)

- **Encoded-frame dependencies:** frames delayed by a stall shorter than 400 ms are sent late instead of dropped, so the chain stays intact and decodable. A stall longer than 400 ms, or a full queue (10 frames = 500 ms), still resyncs.
- **Decoder recovery:** immediate once the backlog drains (a few frames in a burst), with no wait for an IDR.
- **Backlog:** bounded by the 10-frame queue. After a stall about six late right frames are sent back to back. The left eye is unaffected, so pairs re-form as the right backlog arrives.
- **Freshness protection:** pairs older than the relative limit (excess > 100 ms) are rejected by the validated receiver safeguard. But the **catch-up pairs that pass that rule are displayed up to 138–153 ms old** (one labelled "late" in the keyint 10 + catch-up case), against at most 94 ms with `resync`.
  - The receiver's absolute-age rejection is off in the validated configuration (`max_age_ms` 0).
  - So this option trades about 0.5 s less freeze for older images just after each stall.
- **The opt-in `catchup` policy** (prepared, not default) behaves like the 400 ms limit, but jumps straight to a newer IDR when one is already queued, and stops at a 500 ms hard limit. It has the same freshness trade-off.

## 5. Simulation (`camera_gateway/tools/continuity_sim.py`; results `camera_gateway/results/continuity_sim_20261106.json`)

**What it is:** a discrete-event model using the real `GopQueue` and stale policy, real stand-in access units, the timing measured in Stage 2, and the validated Python presenter with the exact Stage 2 freshness policy.

**Calibration against the six real Stage 2 events:**

| | Event 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Observed freeze (ms) | 1015 | 1365 | 1281 | 1065 | 998 | 765 |
| Simulated freeze (ms) | 998 | 1348 | 1248 | 1048 | 998 | 749 |

Each simulated freeze is within 33 ms of the observed one.

**Sweep, 20 stalls of 315 ms:**

| Configuration | Median freeze | Worst | Total | Right frames not sent | Oldest displayed pair | Stale display |
|---|---|---|---|---|---|---|
| A: keyint 20, resync, 150 ms (validated) | 874 ms | 1348 | 17.5 s | 276 | 94 ms | none |
| **B: keyint 10, resync, 150 ms** | **624** | **849** | **12.5 s** | **178** | **94 ms** | **none** |
| C: keyint 20, 400 ms limit | 366 | 383 | 7.4 s | 0 | 150 ms | none by the relative rule |
| D: keyint 20, catchup | 366 | 383 | 7.4 s | 8 | 149 ms | none by the relative rule |
| E: keyint 10, catchup | 366 | 383 | 7.4 s | 14 | 153 ms (1 "late") | none by the relative rule |

**Stalls of 600 ms:**
- A: median freeze 1173 ms;
- **B: 924 ms;**
- C: the same as A, because the stall exceeds 400 ms;
- D/E: 832 / 666 ms.

**Limits:** this is a model. It cannot show the OAK's behaviour at keyint 10 or the real network.

## 6. Code and tests (all offline; live defaults unchanged)

**Code:**
- **`gateway_core.on_stale`, `GopQueue.jump_to_recovery`:** the stale handling is factored out. `resync` is the default and identical to the validated behaviour; `catchup` is opt-in.
- **`EyeSender`, CLI and runner:**
  - the gateway gains `--stale-policy` (default `resync`) and `--hard-max-age-ms`;
  - the runner `run_stage2.ps1` gains `-Keyint 10|20` (default 20).

**Tests:**
- `tests/test_continuity.py` 20/20: policy behaviour, decodability under a real 300 ms blocked write, simulator calibration and properties, defaults unchanged, runner `-Keyint`.
- Unchanged and still passing: `test_gateway.py` 74/74, `test_stage2_analysis.py` 23/23.

**Evidence:** Stage 1, Stage 2, Task 04B and Task 05 evidence is unmodified (checked by modification time).

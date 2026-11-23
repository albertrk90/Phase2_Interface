# Task 06: real Camera A to Unity preview (offline preparation; review gate)

**Status (6 Nov 2026): offline preparation complete.**
- **Not done:** no live camera session, no hardware encoder test, no MediaMTX launch, no network change.
- **Not touched:** COROL and the robots.
- **Before this task:** Task 05 M1 was closed as **CONDITIONALLY VALIDATED** (§1).

## 1. Starting point: Task 05 M1 closure (researcher decision, 6 Nov 2026)

| Item | Result |
|---|---|
| Original T4, criteria v1 | **FAIL, 7/10** (the recorded result; unchanged) |
| Supplementary post-hoc T4, criteria v2 | **PASS, 10/10** |
| Receiver correctness | Supported (oracle replay exact; pixel-exact display; clean shutdown) |
| Unscheduled freezes | **Unresolved performance issue** (93 in 360 s in both receivers; the ~300 ms transport-delay issue) |

## 2. Is on-device stereo H.264 encoding feasible? Yes on paper; NOT verified on hardware

| Question | Finding | Source | Verified? |
|---|---|---|---|
| Encoder input format | "Only NV12 or GRAY8 (which gets converted to NV12)". StereoDepth `rectifiedLeft` / `rectifiedRight` are GRAY8 | Luxonis VideoEncoder documentation (v3) | Documented only |
| Encoder resources | Limit 248 Mpixel/s for H.26x (shared with JPEG). Two eyes at 1280 × 800 and 20 fps = **41 Mpixel/s (16.5 %)** | Same | Documented only |
| Size constraint | Width must be a multiple of 32: 1280 = 40 × 32. Height 800 = 50 macroblocks | Same | Documented only |
| Profile and rate control | `H264_BASELINE`, CBR, `setKeyframeFrequency`, `setNumBFrames(0)`, `setBitrateKbps` all exist in 3.11.0 | Offline introspection (`results/depthai_api_20261106_112155.json`) | API present |
| Metadata preserved | `EncodedFrame` has `getSequenceNum`, `getTimestamp` (host-synced), `getTimestampDevice`, `getFrameType` (I/P/B), exposure and lens data. That it carries the input frame's data strongly suggests the seq and times are copied from the input | Offline introspection | **Unverified until the first physical test** |
| Left/right synchronisation | The rectified pair shares one sequence number (Stage E grouped all four streams by equal seq); the raw pairs had \|L−R\| ≤ 0.03 ms (Stage D). The gateway's pair monitor flags a device-time skew over 1 ms | Camera checkpoint §9, §11 | Raw pairs yes; encoded pairs unverified |
| Frame rate | OV9282 native 1280 × 800 MONO supports 20 fps; the gateway's `check_sensor_modes` refuses otherwise | camera_validation | Verified for raw capture |
| Host clock | `dai.Clock.now()` against `time.monotonic_ns()`: median −0.45 µs (range −0.9 to +0.1 µs). The same QPC clock as Unity | Offline measurement | Yes (host side) |
| XLink load | About 16 Mbit/s encoded, against about 330 Mbit/s for two raw streams at 20 fps | Arithmetic | — |

**Host-encoding fallback (documented; not implemented).** If the encoder rejects the rectified GRAY8 input, drops the metadata, or adds too much latency:
- **Pipeline:** stream `rectifiedLeft` / `rectifiedRight` raw (GRAY8) to the host. Pair them by equal seq, as Stage E did. Encode on the host with the validated Task 04B encoder path (`publish_synthetic.EyeOutput.encode(luma, meta)`: libx264 Baseline, zerolatency, keyint, no B-frames). Then publish exactly as now.
- **Costs:** about 330 Mbit/s of raw XLink traffic per camera, where Stage D's delivery stalls were observed (about 2.7 per minute), plus host CPU.
- **Benefit:** the raw-frame latest-frame queue of Task 04B applies unchanged.
- **Approval:** a separate decision; no uncontrolled workaround is to be introduced.

## 3. Gateway (new `camera_gateway/`; see its README)

**Pipeline (rectification as approved E1):**
1. CAM_B and CAM_C, GRAY8 1280 × 800 at 20 fps, `enableUndistortion=False`.
2. StereoDepth: rectification on, distortion correction ON, alpha unset, edge fill 0, no spec translation.
3. Two VideoEncoders: H.264 Baseline, CBR 8 Mbit/s, keyframe every 20, 0 B-frames.
4. Non-blocking device queues (8).

**Carrying the identity and timing:**
- the FrameMeta v1 SEI before the first slice: camera A, eye, device seq, `t_dev`, host-synced capture time, UTC, flags 0, `config_id` 6001;
- the end-of-frame SEI after the last slice (Task 04B S7 fix);
- the stream parameters from the camera's own first IDR (template muxer; no encoder opened).

**Flow control:**
- **Latest-frame policy, GOP-aware.** The bounded queue holds at most 10 frames per eye. Any discontinuity (device gap or reversal, overflow, stale frame over 150 ms, reconnect) resumes only at the next recovery point, so the stream stays decodable.
- **Capture is independent of the network.** The capture loop is on the main thread, with one sender thread per eye.
- **Senders:** connect first, then start at a recovery point; capped reconnect backoff.

**Safeguards:** these reuse the validated camera_validation code, read-only and SHA-256 pinned; details in the gateway README.
- Camera A identity only.
- Sensor-mode check.
- Calibration compared with the baselines **before start**, and verified in session and after the run.
- IR off acknowledged before and after start.
- AutoCalibration OFF confirmed.
- No device writes.
- The live mode needs `--live`; without it the gateway only prints the plan.

**Dependencies:** a separate `camera_gateway/.venv` with depthai 3.11.0, numpy 2.4.6 and av 19.0.2. These are the exact builds of the existing venvs (RECORD hashes match). Neither existing venv was altered.

## 4. Unity receiver: real-camera mode

- **Switch:** `-m1Source synthetic|camera`; the default is `synthetic`, unchanged.
- **Camera mode** (`StereoPresenter.RequireBarcode = false`, `ReceiverCore.ReadBarcode = false`):
  - **Removed for camera imagery only:** the synthetic barcode check, logged as `barcode_ok = "na"`.
  - **Added:** both eyes' SEI must have FLAG_SYNTHETIC clear, otherwise a `source_mismatch` integrity error.
  - **Unchanged:** SEI eye and camera identity, equal-seq pairing, absolute and relative freshness, event logging, the left-eye main display and right-eye developer inset, the crop and the render checks.
  - **Source PSNR:** runs only when reference frames exist (file replay).
- **Synthetic mode is not weakened.** The same barcode-less frames remain integrity errors; tested in both directions (§6).
- **Logs:** `summary.unity.source`, plus a `run_start` source field.
- **Camera-mode presenter summary:** `counts.source_mismatch` and `integrity_checks`.
- **Verifier:** `Tools/verify_unity_run.py` handles a camera source (oracle semantics mapped) and has `scenario_camera()` for the recorded real-imagery input.

### 4.1 Camera A crop reconciliation

| Item | Finding |
|---|---|
| Code | `DisplayRig.CameraACrop = RectInt(39, 6, 1238, 770)` gives x 39–1276 and y 6–775 **inclusive**: 1238 × 770, i.e. `img[6:776, 39:1277]`. The shader maps it with a top-left origin. **Correct** |
| Applied when | Whenever `camera == "A"`, in both sources. It was **already applied in M1**: T3, T4 and all replays displayed the crop, and T4's render check verified 953,260 = 1238 × 770 pixels pixel-exact |
| **Discrepancy (documents)** | Plan Task 05 §4.3 says the crop is "present but set to the full frame" for M1, and Task 05 §17.3 asks to "apply" it. **Both are wrong.** Erratum added; no code change |
| Minor | With bilinear filtering at non-1:1 window scales, the outermost displayed pixels blend at most half a texel from outside the crop (rows 5 and 776, columns 38 and 1277). Negligible; not changed |
| Validity | The crop belongs to the E1 rectification (distortion correction on, alpha unset). The gateway fixes that configuration (`config_id` 6001); any change requires re-deriving the crop |

## 5. Offline input from real imagery

`camera_gateway/tools/make_recorded_camera_input.py` writes `unity/Phase2Client/test_results/inputs/camera_E1_A`:
- **Input:** the five real rectified Camera A pairs of E1, cycled for 20 s at 20 fps.
- **Encoder:** the libx264 stand-in (**not** the OAK encoder), with the requested settings.
- **Path:** through the actual gateway `stream()`, GopQueue, senders, packaging and template muxer, into files.
- **Injected device gap at seq 125–127:** resynchronised, resuming at IDR 140.
- **Injected link loss after 200 writes:** reconnect, with segment 2 starting at a recovery point.
- **Result:** 380 pairs sent; stand-in quality against the source 40.0–41.1 dB.

## 6. Tests (all offline)

| Suite | Result |
|---|---|
| `camera_gateway/tests/test_gateway.py` | **69/69 PASS.** Covers AU inspection and the recovery rule (including non-IDR I, AUD, multi-slice and CBR filler). It shows that packaging never changes a picture: the stream decodes bit-identically to the unpackaged AUs, and the metadata survive MPEG-TS. Also: no encoder opened; extradata = the camera's SPS/PPS; a P-start control fails to decode; the GOP queue (gap, reversal, overflow, align, and a 600-frame threaded stress run); the pair monitor; the sender (connect failures, link loss to segment 2, age guard); the full safety sequence on a fake device with every refusal path and no forbidden call; the hash pin; argument refusals |
| Unity EditMode | 37/38. **New `CameraSourceTests` 8/8.** Failure: the existing compatibility check C09 compares today's QPC offset with the offset recorded in the 5 Nov `synthetic_A` input. The laptop rebooted at 09:45:51 today, so they differ by 87,634.96 s. Unity and Python agree to under 0.01 ms today. Environment artefact; the input was not regenerated |
| Unity PlayMode | 1/1 |
| Player: camera-mode replay of `camera_E1_A` | **PASS twice.** Oracle replay exact; the 8 camera scenario checks pass. Display bit-exact, 14 references at 99 dB; render check left and right max diff 0 at crop 1238 × 770; gap and GOP-dropped frames never shown; reconnect resumed; 0 integrity errors, 0 source mismatches |
| Player: synthetic regression (`replay_A`) | **First run: FAIL on `freezes_logged`** (3 freezes, not 4). A transient player main-loop stall of about 0.5 s coincided with the 300 ms drop, so the freeze was never sampled. Oracle exact; the other 10 checks PASS. **Rerun: 11/11 PASS**, no stall. All four first runs of today's rebuilt player had such 0.5 s stalls, with no event and not caused by the render checks. Yesterday's runs and today's reruns had none. Cause not established |
| Designed to fail | Real imagery in **synthetic** mode: 372/372 pairs fail the barcode check. Synthetic input in **camera** mode: 172/172 pairs are `source_mismatch` |
| Verifier regression | The modified verifier reproduces the recorded verdicts of T3, T4 and the pre-T4 replay; their reports are untouched |
| Invariants | camera_validation: all 437 files hash-identical. Nothing in `camera_validation/.venv`, `streaming_poc/.venv` or `streaming_poc` was modified |

## 7. Proposed 60-second live Camera A preview (needs approval; nothing below has been run)

Two stages: hardware alone first, then the full chain. The laptop is on isolated Ethernet, so Claude Code is offline and the researcher runs the commands. All commands are from `C:\Users\a1920234\Documents\Phase2_Interface`.

### Stage 0: on Wi-Fi, before connecting anything

```powershell
camera_gateway\.venv\Scripts\python.exe -I camera_gateway\tests\test_gateway.py          # expect 69 checks, 0 failed
$R = "camera_validation\results"
$A = "--expect","169.254.1.222=19443010B14C872F00","--baseline-user","$R\calibration_user_19443010B14C872F00_20261103_182445.json","--baseline-factory","$R\calibration_factory_19443010B14C872F00_20261103_182445.json"
camera_gateway\.venv\Scripts\python.exe -I camera_gateway\camera_gateway_a.py @A          # PLAN ONLY; touches nothing
Get-FileHash streaming_poc\config\mediamtx_localhost.yml                                   # compare with the value recorded in streaming_poc
Get-ChildItem $env:LOCALAPPDATA\depthai\cache\crashdumps -Recurse | Measure-Object        # crash-dump count before
```

### Stage 1: Ethernet, Camera A to files, 30 s, no MediaMTX

This verifies the on-device encoder by itself.

```powershell
camera_gateway\.venv\Scripts\python.exe -I camera_gateway\camera_gateway_a.py @A --live --sink file --seconds 30 --label hw1
```

**Continue only if all of the following hold:**
- `RESULT: PASS`, with the stop at `seconds_reached`;
- `calibration_unchanged: true` in the report (in session and post-run);
- `report.json` → `hardware_checks` all PASS: profile 66, 1280 × 800, no B-frames, IDR every 20, every AU has a slice, pairs with equal seq and skew ≤ 1 ms, rate within 5 %;
- `au_stats`: record the real bitstream layout (AUD, SPS repetition);
- no new crash dump.

**If the encoder is refused or a check fails:** stop and report. The host-encoding fallback (§2) is a separate decision.

### Stage 2: Ethernet, 60 s preview (three terminals)

```powershell
# T1  MediaMTX (localhost-only config; Ctrl+C to stop after the run)
cd streaming_poc; tools\mediamtx_v1.21.3\bin\mediamtx.exe config\mediamtx_localhost.yml
# T2  check the listener, then start the gateway
Get-NetTCPConnection -LocalPort 8554 -State Listen | Select-Object LocalAddress            # must be 127.0.0.1 only
camera_gateway\.venv\Scripts\python.exe -I camera_gateway\camera_gateway_a.py @A --live --sink rtsp --seconds 60 --label preview1
# T3  within about 3 s of T2: the Unity player in camera mode (first frame after about 8 s)
cd unity\Phase2Client; $O = "test_results\camA_preview_$(Get-Date -Format yyyyMMdd_HHmmss)"; New-Item -ItemType Directory $O | Out-Null
Builds\M1\Phase2M1.exe -m1Mode rtsp -m1Server rtsp://127.0.0.1:8554 -m1Source camera -m1Seconds 62 -m1Label camA_preview -m1Quit -m1Out $O -m1SaveEvery 200 -logFile "$O\unity_player.log" -screen-fullscreen 0 -screen-width 1280 -screen-height 800
```

**Afterwards:**
1. Wait for the gateway's `RESULT` line, which includes the post-run calibration verification (≤ 60 s).
2. Stop MediaMTX with Ctrl+C in T1.
3. Confirm that no `mediamtx`, test Python or `Phase2M1` process is left, and that port 8554 is not listening.
4. Count crash dumps again.
5. Back on Wi-Fi, run `Tools\verify_unity_run.py <unity_rx_dir>` for the oracle replay with camera semantics.

**Observations to record (informational; no formal pass/fail):**
- **Gateway:** RESULT, `calibration_unchanged`, `hardware_checks`, `au_stats`, GOP-queue resyncs and device gaps, sender link events.
- **Unity:** display throughout; 0 integrity errors and 0 source mismatches; 0 decode/SEI errors; render check left and right pass; absolute and relative age (median, p95); freezes and unscheduled freezes; frame-time p99; clean shutdown.
- **Visual:** a short note on the left-eye image and the right-eye inset (orientation, crop, sharpness, blocking).

## 8. Hardware and safety checks before connecting the camera

1. **Approval** recorded separately for Stage 1 and for Stage 2 (Stage 2 includes the MediaMTX launch).
2. **Network:**
   - The laptop is on the isolated camera Ethernet only, with Wi-Fi off; the gateway refuses non-link-local host addresses.
   - No change to Windows network or firewall settings.
   - No 192.168.1.x address present; COROL and the robots not running.
3. **Camera A:** at 169.254.1.222, ID `19443010B14C872F00`, powered by the PoE switch (the post-swap port arrangement). In bootloader state, with no other DepthAI process running (close any camera_validation preview). Camera B is not targeted.
4. **Baseline calibration files** present; the gateway compares the device with them **before start** and refuses on any difference.
5. **Physical:** camera mounted, lens unobstructed, no people in view. IR stays off; it is acknowledged before and after start.
6. **Firmware:** decline any firmware or bootloader update prompt. Nothing in the gateway calls one, and 0.0.29 stays unapplied.
7. **Unity player:** the rebuilt 6 Nov player (assemblies 11:42). `My project` and the Side Quest projects are not opened.
8. **Power:** each run is short (≤ 60 s). Modern Standby froze G1 at about 10 min idle, so keep the laptop active.
9. **Abort:** Ctrl+C in the gateway shuts down cleanly and still verifies the calibration. Unplugging PoE is the last resort, and must be recorded.
10. **Evidence:** every run writes new folders; nothing is overwritten.

## 9. Known risks for the first physical test

- **Encoder:** it may refuse the rectified GRAY8 input or the 2-encoder plus StereoDepth load (documented as supported). Then use the fallback (§2).
- **Metadata:** `EncodedFrame` may not carry the input seq or timestamps. The pair monitor and hardware checks would show it, and Unity would display nothing (no matching seqs).
- **Device stalls:** delivery stalls (Stage D, about 2.7 per minute on raw streams, cause unknown) appear as device gaps. Each costs up to one GOP (≤ 1 s at keyint 20); keyint 10 halves that at a small bitrate cost.
- **Delays:** the unresolved ~300 ms delay episodes may recur; they are logged as freezes.
- **Age definition:** the absolute age now runs from the device capture time (mapped to the host by DepthAI) to display. It is not comparable with the synthetic M1.3.
- **Player stalls:** the transient ~0.5 s player stalls seen today (§6) would show as display hitches.

## 10. Stage 0 and Stage 1 results (6 Nov 2026)

- **Before hardware:** the stale Unity clock fixture (C09) was fixed with a boot-session reference; EditMode 43/43. Stage 0 PASS (`camera_gateway/results/stage0_20261106_120607`). Connection procedure verified: bootloader state, no persistent change. Checkpoint §13.17.
- **Stage 1 (12:28–12:29): PASS on H1–H12.** On-device H.264 encoding of both rectified eyes is verified on hardware. Details: [STAGE1_RESULTS.md](../../camera_gateway/results/stage1_review_20261106/STAGE1_RESULTS.md); checkpoint §13.18.
- **Facts for Stage 2:**
  - capture to host receipt is a fixed ~73 ms (p95 ~77 ms), so the expected Unity capture-to-display age is ~85–95 ms;
  - a start-up stall within the first ~5 s; GOPs are dropped by the 150 ms age guard (by design);
  - AUD on every AU and SPS/PPS on every IDR;
  - the crop excludes all rectification border.
- **Still untested live:** the RTSP sink (pre-encoded stream through MediaMTX) and Unity camera mode on a live stream.

## 11. Stage 2 runner: prepared and dry-run offline (6 Nov 2026; live session NOT approved)

**Chain:** Camera A, then the gateway (on-device H.264), then localhost MediaMTX, then the Unity Phase2M1 player in camera mode, for 60 s. Camera A only; no robot, no COROL.

**Runner:** `camera_gateway/tools/run_stage2.ps1`. Its order and timeouts are in its header:
1. **Pre-checks:** no camera, gateway, Unity or MediaMTX process; port 8554 free (TCP and UDP); MediaMTX config SHA-256 equal to the verified localhost-only config; `mediamtx.exe` equal to the binary in the checksum-verified v1.21.3 zip; no stale MediaMTX log; Unity player present.
2. **Keep-awake.**
3. **Network wait:** isolated network (link-local only, Wi-Fi off, stable 45 s, up to 60 min). It is monitored throughout the run, and any other network configuration aborts the run.
4. **MediaMTX:** must listen within 5 s, with sockets exactly TCP 127.0.0.1:8554.
5. **Gateway:** Stage 1 safeguards, `--sink rtsp --seconds 120 --stop-file`. The runner waits until both eyes are published (≤ 90 s).
6. **Unity:** launched only after that (`-m1Source camera -m1Seconds 60 -m1Quit`; ≤ 105 s).
7. **Gateway stop file:** normal shutdown and post-run calibration verification (≤ 180 s).
8. **MediaMTX stopped**, and its log moved into the evidence folder.
9. **Final check:** recorded before any leftover is stopped.
10. **Analysis:** `tools/analyse_stage2.py`.

**Abort and failures:** the file `camera_gateway/results/STAGE2_ABORT`, a network change or any failure triggers the same orderly shutdown.

**Analysis.** Integrity criteria S1–S11, fixed before any live run:
- the Stage 1 safety items;
- the MediaMTX sockets;
- Unity display, render checks and crop;
- frame identity and metadata against what the gateway sent;
- stereo pairing, with `barcode_ok "na"` and no synthetic checks;
- no stale replay;
- the oracle replay;
- cleanup.

It also reports stage latencies separately (median, p95 and max for capture→host, host→send, send→Unity arrival, arrival→selection, host→selection and capture→selection). Stalls, freezes, gaps, GOP drops, reconnects and freshness states are listed individually.

**Offline verification (6 Nov; no camera, no MediaMTX, no Unity launched).** The dry runs used a fake device, a fake loopback listener and a fake Unity stand-in. They are kept under `camera_gateway/results/stage2_runner_*`.

| Run | Result |
|---|---|
| Plan-only (`..._124510_planonly`) | All pre-checks pass; nothing launched |
| Success, detached through WMI (`..._124607_dryrun_none`) | Completed in 93 s: listener TCP 127.0.0.1:8554 only; gateway streaming after 2.8 s; Unity exit 0 after 63.7 s; stop file; clean final check. S1–S9 and S11 PASS; S10 NOT_TESTED (the fake player writes no presenter trace) |
| First success attempt (`..._124528_dryrun_none`) | **FAILED SAFELY** on a runner bug: the socket list was wrapped twice, so the exact-socket check refused. Fixed; the shutdown was clean |
| Gateway refusal, bootloader 0.0.29 (`..._dryrun_gateway_abort`) | **Unity never launched**; listener stopped; clean |
| Unity hang (`..._dryrun_unity_hang`) | Stopped at 65 s (deviation); gateway stop file; clean |
| Unity crash, exit 3 (`..._dryrun_unity_crash`) | Orderly shutdown; clean |
| Operator abort mid-preview, detached through WMI (`..._125042_dryrun_none`) | Unity stopped; gateway `stop_file` with calibration verified; clean |

**Suites:** gateway 74/74 (adds `--stop-file`); Stage 2 analysis 23/23, every criterion with a designed-to-fail case.

**Refinements made after the dry runs, before any live run:**
- S11 judges cleanup, and requires Unity's exit code only if Unity was launched; it also requires no deviation.
- The outcome is `completed_with_deviations` when Unity did not exit 0.
- The earlier dry-run analysis files were left as written.

### 11.1 Commands for the live Stage 2 session (only after approval)

From `C:\Users\a1920234\Documents\Phase2_Interface`, on Wi-Fi first:

```powershell
# 1. plan-only check (nothing launched)
powershell -NoProfile -ExecutionPolicy Bypass -File camera_gateway\tools\run_stage2.ps1 -PlanOnly
# 2a. EITHER run it in your own PowerShell window (stays visible; no Claude Code needed):
powershell -NoProfile -ExecutionPolicy Bypass -File camera_gateway\tools\run_stage2.ps1 -WaitMinutes 60
# 2b. OR arm it detached (as Stage 1):
$script = (Resolve-Path camera_gateway\tools\run_stage2.ps1).Path
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -WaitMinutes 60"; CurrentDirectory = (Get-Location).Path }
# 3. connect Camera A (PoE), turn Wi-Fi off; the run starts 45 s after the network is isolated
#    (about 2.5-3 min in total). Do not close the Unity window; it quits by itself after 60 s.
# abort at any time:   New-Item -ItemType File camera_gateway\results\STAGE2_ABORT     (delete it afterwards)
```

**Outputs:**
- `camera_gateway\results\stage2_runner_<stamp>\`: `runner.log`, `runner_status.json`, gateway, MediaMTX and Unity logs, `mediamtx.log`, `unity_rx_<stamp>_win64player_A_camA_preview\`, `stage2_analysis.json`, `analysis_stdout.txt`.
- `camera_gateway\results\gw_<stamp>_A_stage2\`: the gateway's own evidence.

**Done** when `runner.log` ends with `STEP done`.

## 12. Stage 2 result (6 Nov 2026, 12:55–12:58; approved, run once)

**Integrity PASS on S1–S11, including the oracle replay.** Live Camera A imagery was displayed in Unity.

**Latency, capture → selection:** median 90.7 ms, p95 99.4 ms, max 121.3 ms. Of this, on-device 73.8 ms and host chain 17.0 ms.

**The researcher's apparent dropped frames are 6 freezes of 0.77–1.36 s.** Each one followed a 210–316 ms blocked write on the right-eye RTSP connection to MediaMTX (the unresolved ~300 ms localhost transport delay). Unity rejected the late pairs, and the gateway's 150 ms age guard dropped the rest of the GOP.

**Details:** [STAGE2_RESULTS.md](../../camera_gateway/results/stage2_review_20261106/STAGE2_RESULTS.md); checkpoint §13.19. **Mitigation options** (age guard, keyint, loopback investigation) await review; nothing changed.

## 13. Continuity investigation (6 Nov 2026, offline; approved)

Report: [Phase2_Task06_Continuity_Investigation.md](Phase2_Task06_Continuity_Investigation.md).

**Recommended smallest change:** keyint 10 (runner `-Keyint 10`; default still 20).
- In a simulation calibrated on the six Stage 2 events, it gives about 30 % shorter freezes, with displayed freshness unchanged.

**Not recommended yet:** the 400 ms age limit or catch-up policy.
- They give shorter freezes, but display catch-up pairs up to about 150 ms old.

**The transport stalls:** a near-constant ~315 ms delivery hold on one loopback TCP connection. The best hypothesis is the retransmission timeout; it is not proven.

**Next:** the AI2 interface plan is in [Phase2_Task07_AI2_Supervisory_Interface_Plan.md](Phase2_Task07_AI2_Supervisory_Interface_Plan.md).

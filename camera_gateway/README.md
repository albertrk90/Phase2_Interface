# camera_gateway: Camera A to Unity (Task 06)

**Status (6 Nov 2026): prepared and tested offline only.**
- **Not yet done:** no live camera session, no hardware encoder test, no MediaMTX launch.
- **Unverified:** nothing here establishes that the OAK encoder works; that needs a physical test (see "Live preview").
- **Plan and results:** [docs/plans/Phase2_Task06_CameraA_Unity_Preview_Plan.md](../docs/plans/Phase2_Task06_CameraA_Unity_Preview_Plan.md).

**What it does.** The gateway takes Camera A (OAK-D Pro PoE AF, `19443010B14C872F00`) and moves its images to Unity:

1. StereoDepth rectification, using the approved Stage E E1 configuration: distortion correction on, alpha unset.
2. Two on-device H.264 Baseline encoders, one per eye.
3. On the host, a FrameMeta v1 SEI (the format Unity already parses) and an end-of-frame SEI added to each frame.
4. Delivery to localhost MediaMTX paths `camA_left` and `camA_right`, or to MPEG-TS files.

## Environment (separate; nothing else changed)

| Package | Version | Why | Matches |
|---|---|---|---|
| depthai | 3.11.0 | camera pipeline and safeguards | `camera_validation/.venv`, same wheel (RECORD hashes of `depthai.cp313-win_amd64.pyd` and `depthaicore-50581win.dll` identical) |
| numpy | 2.4.6 | depthai requires numpy < 3 | `camera_validation/.venv` |
| av | 19.0.2 | muxing of pre-encoded H.264 (RTSP and MPEG-TS) | `streaming_poc/.venv`, same build |

**Python:** 3.13.17 (the same interpreter as the two existing venvs).

**Files:** `requirements.txt` (pins) and `requirements.lock.txt` (`pip freeze`).

```powershell
C:\Users\a1920234\AppData\Local\Programs\Python\Python313\python.exe -m venv camera_gateway\.venv
camera_gateway\.venv\Scripts\python.exe -m pip install -r camera_gateway\requirements.txt
```

## Files

| File | Role |
|---|---|
| `gateway_core.py` | Access-unit inspection (recovery point = IDR, or SPS + PPS + I-slice), SEI and frame-end packaging, the GOP-aware latest-frame queue, the stereo pair monitor. Pure logic |
| `gateway_output.py` | Muxing of pre-encoded AUs. The stream comes from a template demuxed from the camera's own first IDR, so no encoder is opened. One independent sender thread per eye (connect first, start at a recovery point, age guard, reconnect with backoff) |
| `camera_gateway_a.py` | Entry point: safeguards, DepthAI pipeline, capture loop, report. **Plan-only unless `--live`** |
| `tools/inspect_depthai_api.py` | Offline API inspection; no device. Output in `results/depthai_api_*.json` |
| `tools/standin_encoder.py` | libx264 stand-in for the OAK encoder's output (tests only), plus the real E1 imagery loader |
| `tools/make_recorded_camera_input.py` | Real Camera A imagery through the actual gateway code, written as Unity file-replay input (`unity/Phase2Client/test_results/inputs/camera_E1_A`) |
| `tests/test_gateway.py` | 69 offline checks |

## Why the synthetic publisher is not reused directly

1. **Dropping frames.** The synthetic publisher queues raw frames and encodes after dequeuing them, so dropping one is harmless. On-device encoding delivers already-encoded P-frames, and dropping one corrupts decoding until the next IDR. The gateway's queue therefore resynchronises to the next recovery point after any discontinuity: a device gap, an overflow, a stale frame, or a (re)connection.
2. **Stream parameters.** The synthetic publisher's RTSP stream takes SPS/PPS from its own libx264 encoder. Here they come from the camera's first IDR. With PyAV 19.0.2, the template codec context is never opened and its extradata survives the header write; this was verified offline.
3. **Sequence numbers and times** come from `EncodedFrame` (`getSequenceNum`, `getTimestamp`, `getTimestampDevice`).
   - `dai.Clock` is the same QPC clock as `time.monotonic_ns` and Unity's `Clocks.MonoNs`: the median difference is −0.45 µs.

**Metadata per frame:**
- camera `A`, the eye, and the device seq (shared by the rectified pair);
- `t_dev_ns`, `t_host_mono_ns` and `t_utc_ns` (= host-mono + UTC−mono offset);
- flags `0` (FLAG_SYNTHETIC clear);
- `config_id` 6001.

## Safeguards (validated code, imported read-only and SHA-256 pinned; no bytecode written)

The gateway imports `discover_cameras.py`, `calibration_check.py` and `capture_stereo.py` from camera_validation. It refuses to start if their hashes have changed.

- **Identity:** Camera A only (`--expect` must name `19443010B14C872F00`). It uses `connect_verified`, which does a broadcast pre-check, requires bootloader state, verifies the ID and IP after connecting, and refuses if the host has non-link-local addresses.
- **Sensors:** `check_sensor_modes` confirms OV9282 at 1280 × 800 MONO and the requested fps.
- **Calibration:** read before start and compared with the baseline files **before start**, refusing on any difference. It is re-read in session, then verified after shutdown with a fresh connection.
- **IR:** the dot projector and flood light are set to 0 and acknowledged before and after start.
- **Auto-calibration:** AutoCalibrationMode OFF, confirmed by the getter.
- **No device writes:** there is no calibration, firmware, bootloader, IP or device-setting call. The offline fake device refuses and records any other call.
- **Shutdown:** the pipeline is stopped and the device closed in every exit path.

## Offline verification (6 Nov 2026)

| Suite | Result |
|---|---|
| `tests/test_gateway.py` | **69/69** |
| Unity EditMode | 37/38. The new `CameraSourceTests` pass 8/8. The one failure is the existing compatibility check C09, which compares today's clock offset with a 5 Nov input after this morning's reboot; Unity and Python agree today |
| Unity PlayMode | 1/1 |
| Player, camera-mode replay of real imagery (`verify_unity_run.py`) | oracle PASS, 8/8 scenario checks; twice |
| Player, synthetic regression | First run FAIL on `freezes_logged` (a transient ~0.5 s player stall hid the 300 ms drop's freeze); rerun 11/11 PASS |

The tests do not establish the OAK encoder's behaviour.

## Live preview

Not approved yet; the exact steps are in the plan document. Plan-only check (touches nothing):

```powershell
$R = "camera_validation\results"
camera_gateway\.venv\Scripts\python.exe -I camera_gateway\camera_gateway_a.py --expect 169.254.1.222=19443010B14C872F00 --baseline-user $R\calibration_user_19443010B14C872F00_20261103_182445.json --baseline-factory $R\calibration_factory_19443010B14C872F00_20261103_182445.json
```

## Concurrent Wi-Fi + Ethernet: `ethernet_scoped` mode (12 Nov 2026, researcher-approved opt-in)

The university now allows Wi-Fi and wired Ethernet at the same time (policy `fMinimizeConnections = 0`; checkpoint §13.24). The validated default is unchanged: `--network-scope isolated` / `-NetworkScope Isolated` refuses to run while Wi-Fi has an address.

The opt-in mode is `camera_gateway_a.py --network-scope ethernet_scoped` and `tools/run_stage2.ps1 -NetworkScope EthernetScoped`. It works as follows:
- **Before anything is contacted,** `network_scope.py` must pass, and it is re-checked during the run. It requires:
  - the camera route uses one wired interface that carries only a link-local address and has no default route;
  - no other interface offers the link-local network, and no subnet overlaps it;
  - ARP shows the recorded Camera A MAC.
- **No broadcast discovery,** which would also go out on the Wi-Fi network. The gateway connects by unicast, then runs the same ID, IP and bootloader checks, the calibration checks before, during and after the run, IR off, and AutoCalibration OFF.
- **During streaming,** the scope is re-checked every 5 s by the gateway and the runner; any change stops the run.
- **Wi-Fi probe:** the runner logs an HTTPS request to the university site every 5 s to `wifi_probe.csv`.
- **Unchanged:** the stream settings (keyint 20, `resync`, 150 ms age guard), the Camera A crop and the Stage 2 criteria. The only exception is S1, which uses a labelled `ethernet_scoped` variant: there is no broadcast bootloader-state pre-check, so the ARP check and the verified unicast connect take its place.

```powershell
powershell -ExecutionPolicy Bypass -File camera_gateway\tools\run_stage2.ps1 -NetworkScope EthernetScoped -PreviewSeconds 60
```

**Tests:** `tests/test_network_scope.py` (31 checks); the existing suites pass unchanged (gateway 74, Stage 2 analysis 23, continuity 20). Dry and plan-only runs were OK.

**First live run, 12 Nov 18:37:** `results/stage2_runner_20261112_183708/`. S1–S11 PASS; Wi-Fi probe 19/19 HTTPS 200 during streaming. Details are in checkpoint §13.24.

**Pre-change copies:** `results/*.pre_scope_20261112.bak`.

## S4.1 Site Window live smoke test: `-Player S4Smoke` (13 Nov 2026, approved)

- **What it runs:** `tools/run_stage2.ps1 -NetworkScope EthernetScoped -Player S4Smoke -PreviewSeconds 85` launches `Builds\S4\SiteWindowSession.exe -s4LiveSmoke`. That is the separate development definition `phase2_s41_live_smoke.json`, with **live Camera A**, Camera B the synthetic recording, and the robot simulated.
- **What it keeps:** the gateway's unchanged 120 s limit; `-PreviewSeconds` above 85 is refused.
- **Analysis:** `analyse_stage2.py --player s4` (a labelled S6 Site Window variant; S1–S5 and S7–S11 unchanged).
- **Unchanged:** M1 is still the default player.
- **First run:** `results/stage2_runner_20261113_123525/`, S1–S11 PASS (checkpoint §13.26).
- **Hardware:** connect only Camera A to the switch for live tests.
- **Pre-change copies:** `results/*.pre_s4smoke_20261113.bak`.

## Full interactive S4.1 walkthrough: `-Player S4Demo -ExtendedTest` (13 Nov 2026, approved opt-in; uncommitted)

- **Command:** `tools/run_stage2.ps1 -NetworkScope EthernetScoped -Player S4Demo -ExtendedTest -GatewaySeconds 600 -PreviewSeconds 525`.
- **What it runs:** the unchanged `phase2_s41_interactive_demo.json`, with live Camera A, synthetic Camera B, a simulated robot and a person as the participant. The player ends on window close (Alt+F4) or at the deadline.
- **Duration limits:**
  - `--extended-test` raises the gateway's limit to a **hard 600 s**. Without it, 120 s applies exactly as before.
  - The runner refuses `S4Demo` without `-ExtendedTest`, `-ExtendedTest` for M1 or S4Smoke, `-GatewaySeconds` above 120 without the flag or outside 120–600, and `-PreviewSeconds > GatewaySeconds − 75`.
  - At player launch it re-checks that `PreviewSeconds + 45` s of gateway time remain.
- **Analysis:**
  - `analyse_stage2.py --player s4demo --out stage2_analysis_<receiver>.json`, once per live Camera A receiver (one per trial reset);
  - `tools/summarise_live_walkthrough.py --runner <run>` writes `walkthrough_summary.json` and `.md`: visible stalls (planned restart waits vs unexpected), receiver freezes labelled by what was on screen, render hitches, SAGAT hide/restore, Camera B selections, freshness, latency, Wi-Fi and shutdown.
- **Dry-run-only fault:** `-Fault late_player` checks the launch-time refusal.
- **Offline evidence:** `results/extended_offline_checks_20261113/` (checkpoint §13.27).
- **Pre-change copies:** `results/*.pre_extended_20261113.bak`.
- **Hardware:** only Camera A connected. The dual-camera MAC anomaly is unresolved, and the guard stays on.
- **First live run (13 Nov 2026, 15:06; checkpoint §13.28):**
  - completed, with 3/3 analyses PASS and a clean shutdown;
  - 11 unexpected visible freezes, caused by per-eye RTSP write stalls of about 300 ms that trip the age guard and resync;
  - diagnostics in `results/walkthrough_diagnostics_20261113/`.

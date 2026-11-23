# Task 04B: offline streaming proof of concept (localhost only)

**Status (5 Nov 2026): two 60 s localhost smoke tests run (both approved).**
- **Smoke 1:** S7 FAIL, a one-frame holdback ([results](results/smoke_20261105_113138/SMOKE_RESULTS.md)).
- **Smoke 2:** the holdback is located in FFmpeg's H.264 parser.
  - Fixed with `--frame-end sei`: frame-boundary latency PASS.
  - The receiver freshness safeguard: stale-frame rejection PASS.
  - Overall FAIL only on S4, because the receiver's window closed before the publisher's ([results](results/smoke_20261105_115058/SMOKE_RESULTS.md)).
- **Smoke 3** (stall + MediaMTX restart): **ABORTED** at the restart point by an orchestrator-script bug (now fixed and self-tested).
  - The restart was not performed. Partial pre-abort data is consistent with the fixes.
  - [Results](results/smoke_20261105_120546/SMOKE_RESULTS.md). No pop-ups (operator confirmed).
- **Smoke 3 re-run** (approved): **all criteria PASS on both streams**, including S4, S7a, S7b, R1–R5 and F1–F3. F3b (live persistent delay) is NOT_TESTED, as declared.
  - **Deviation:** the restart was late (issued at t = 40.85 s, not 38 s), giving about 6 s of downtime and about 18 s of post-restart streaming.
  - **Found:** the publisher logs `link_up` before a real connection, and reconnects block its capture loop.
  - [Results](results/smoke_20261105_121101/SMOKE_RESULTS.md).
- **Full G1 run** (approved; 5 Nov 12:27): **G1.1–G1.7 PASS on both cameras.**
  - **Interrupted:** Windows Modern Standby (idle timeout) froze every process at t ≈ 615 s, so the planned last 45 s did not run in real time.
  - **Extended checks:** S8, S7b and P2 FAIL, and S7a FAIL on camera B.
  - **Found:** a recurring ~300 ms localhost transport delay (cause unverified).
  - **Not measured:** Python CPU and memory.
  - [G1 results](results/smoke_20261105_122716/G1_RESULTS.md). **Review gate:** accept or repeat.
- **G1 rerun preparation** (5 Nov, offline only; nothing launched): the four approved corrections are implemented and tested offline (keep-awake request; no stale frame at reconnect; interpreter and system-wide resource sampling; bounded exit wait before cleanup). A read-only review of the ~300 ms delays is in [delay_coincidence.txt](results/smoke_20261105_122716/delay_coincidence.txt). **The rerun itself needs approval** (commands below).
- **G1 rerun** (approved; 5 Nov 15:11–15:22, uninterrupted): **G1.1–G1.7 PASS on both cameras over the full 660 s.**
  - P2 (fresh frame after reconnection, 99–110 ms), S8, S7a and the Python and system resource measurements are all now PASS or measured.
  - **Overall smoke verdict FAIL on S7b only:** its "rejections after every stall" sub-rule cannot be met by a drop stall. Not re-scored; the researcher decides.
  - The ~300 ms delays did not recur.
  - [Rerun results](results/smoke_20261105_151122/G1R_RESULTS.md).
- **Task 04B closed (researcher, 5 Nov) at the G1 gate.**
  - S7b stays FAIL as recorded; a v2 is proposed for future tests only (below).
  - F3b stays NOT_TESTED; the ~300 ms delays stay an unresolved observation.
  - All evidence is preserved.

**Purpose:**
- Exercise the proposed media path (H.264 Constrained Baseline per eye, per-frame SEI metadata, MediaMTX relay, RTSP over TCP, decoding, sequence-number pairing, latest-frame display) on this laptop alone.
- Test it against gate G1 of the [Task 04A audit](../docs/audits/Phase2_Task04A_Streaming_Architecture_Audit.md) §7.

**Scope limits:**
- No cameras, no robot, no COROL code, no Unity.
- Synthetic frames only. The E1–E5 captures contain an identifiable person, so they are not used.

## Safeguards

| Safeguard | How |
|---|---|
| Localhost only | MediaMTX has a single listener, RTSP on `127.0.0.1:8554`, TCP only. RTMP, HLS, WebRTC, SRT, MoQ, the API, metrics, pprof and playback are all off, and every address is bound to 127.0.0.1 ([config](config/mediamtx_localhost.yml)). Publish and read are allowed only from 127.0.0.1/::1 and only on the four paths `cam{A,B}_{left,right}` |
| URL guard | `poc_common.check_local_url()` refuses any non-loopback host and COROL's ports 8080/8081, before any folder or connection is created |
| Separate environment | `streaming_poc\.venv` (PyAV 19.0.2 only). `camera_validation\.venv` is untouched |
| Untrusted download kept apart | MediaMTX v1.21.3 zip in `tools\mediamtx_v1.21.3\download\`, SHA-256 checked against the release's `checksums.sha256` (`b2f5246b…bdbaf2`, match); extracted to `tools\mediamtx_v1.21.3\bin\`. **The exe is not Authenticode-signed**; Windows Defender / AppLocker may block it [unverified] |
| Firewall | Binding to 127.0.0.1 only should not need an inbound firewall rule. **Observed:** no Windows Security, Defender or Firewall pop-up appeared during either smoke test on 5 Nov 2026 (operator confirmation by the researcher); the Defender log shows one informational cloud lookup at the first launch, and AppLocker shows no events. **If Windows ever shows a firewall prompt, choose Cancel / do not allow** and report it; no firewall setting is to be changed |
| Validated code | Nothing in `camera_validation/`, COROL or the Side Quest projects is modified or imported |

## Files

| File | Role |
|---|---|
| [config/mediamtx_localhost.yml](config/mediamtx_localhost.yml) | Localhost-only MediaMTX configuration (derived from the v1.21.3 default file) |
| [poc_common.py](poc_common.py) | `FrameMeta` and the SEI (`user_data_unregistered` with a fixed UUID; CRC-32); Annex B helpers; event log (JSONL, COROL addendum §9 format); URL guard |
| [synthetic_stereo.py](synthetic_stereo.py) | 1280 × 800 synthetic left/right frames: barcode (sequence/eye/camera), eye markers, known disparities, moving bar |
| [publish_synthetic.py](publish_synthetic.py) | Gateway stand-in: libx264 Constrained Baseline, no B-frames, 1 s keyframe interval, 8 Mbit/s per eye, CBR; SEI before the first slice; two RTSP paths per camera; stall/drop injection; reconnect with backoff |
| [receive_reference.py](receive_reference.py) | Reference receiver: two reader threads, SEI and barcode checks, sequence-number pairing, latest-frame-wins display at 60 Hz, freeze/gap/age logging, reconnect |
| [analyse_poc.py](analyse_poc.py) | G1 verdict per criterion (PASS / FAIL / NOT_TESTED) from one publisher folder and one receiver folder |
| [smoke_check.py](smoke_check.py) | Smoke-test verdicts S1–S8 from the publisher, receiver and evidence folders (adds `sent.csv` against `arrivals.csv` metadata comparison and PSNR of saved frames) |
| [tests/holdback_check.py](tests/holdback_check.py) | Offline timing analysis: arrival against own and next frame's send time |
| [tests/trace_frame_release.py](tests/trace_frame_release.py) | Offline stage-by-stage trace (RTP packetiser, H.264 parser, decoder) for frame-end modes none/aud/sei |
| [tests/test_freshness.py](tests/test_freshness.py) | 34 offline checks: frame-end release, freshness safeguard, the 700 ms stall regression (synthetic and replay of the recorded run) |
| [tests/missing_check.py](tests/missing_check.py) | Offline: where never-received frames fall relative to the receiver window |
| [tests/partial_check.py](tests/partial_check.py) | Offline: summary of a run that ended abnormally (flushed per-frame files only) |
| [tests/test_publisher_nonblocking.py](tests/test_publisher_nonblocking.py) | 21 offline checks, run on the real publisher through a simulated 1 s outage on an in-memory sink. Covers: generation stays on schedule; queue ≤ 2 pairs; `link_up` only after a successful write; no stale backlog after recovery; the burst stall keeps its 14/6-frame meaning; full frame accounting |
| [tests/test_publisher_reconnect.py](tests/test_publisher_reconnect.py) | 19 offline checks for G1 failure P2: a reconnection that blocks during an outage and then succeeds (FLV in-memory sink, a global-header muxer like RTSP). A control run with the old lazy connect reproduces the stale frame; the fixed publisher passes P2 as scored by `smoke_check`'s own code; age-guard checks |
| [tests/test_rerun_prep.py](tests/test_rerun_prep.py) | 10 offline checks: interpreter and system-wide resource summary; S8 stays strict with the new cleanup fields; the unchanged criterion code still scores the preserved G1 evidence as before, without modifying it |
| [tests/delay_coincidence.py](tests/delay_coincidence.py) | Offline, read-only: ~300 ms delay episodes per publish connection and their coincidence across connections |
| [tests/gil_release_check.py](tests/gil_release_check.py) | Offline: PyAV releases the GIL while FFmpeg is blocked writing (to a local named pipe), so a sender thread keeps generation running |

**Publisher structure (final Task 04B fixes, 5 Nov):**
- **Generation** runs on the main thread and never blocks.
- A **bounded latest-frame queue** (`--queue-pairs 2`) discards the oldest pair when full; every discard is counted and attributed to "link down" or "link up".
- A **sender thread** does all encoding, (re)connection and muxing.
- **Connect before taking a frame** (G1 rerun fix for P2): the sender writes the container header, which for RTSP *is* the connection, before it takes a pair from the queue, so no frame is in hand while a connection attempt blocks. `link_connected` is logged when the header is written.
- **Age guard:** a pair older than `--max-send-age-ms` (default (queue + 1) frame periods = 150 ms) when taken is discarded before encoding and counted as `skipped_stale`; burst-stall frames are exempt.
- **`link_up`** is logged only after the first successful frame write on a connection. A failed connection or first write is `link_connect_failed`; a later failure is `link_down`.
- **Fault injection** is keyed on capture time and applied in the sender, below the queue.
- **`generated.csv`** records every generated pair.

**Orchestrator ([run_smoke_restart.ps1](run_smoke_restart.ps1)):**
- It is parameterised for the full G1 plan.
- It stops and restarts MediaMTX on the scheduled clock. The safety checks use the fast .NET listener tables, and any lateness is logged as `RESTART LATE`.
- It samples CPU and memory of MediaMTX and the four Python **interpreter** processes (the venv launcher's child, recorded in `pids.json`) to `resources.csv`, and system-wide CPU and memory to `system.csv`.
- **Keep-awake:** it holds a per-process `SetThreadExecutionState` request (system + display required) for the run and releases it in `finally` (`keepawake.json`). No power setting or policy is changed. Lid close, power button or screen lock can still suspend the machine. Kernel-Power standby events during the run are recorded (read-only) in `cleanup.json`.
- **End of run:** it waits up to `-ExitWaitSeconds` (default 60) for every publisher and receiver (launcher and interpreter) to exit, then runs the cleanup check; anything still running is recorded first and only then stopped (`stopped_after_check`), so S8 is not masked.
| [run_smoke_restart.ps1](run_smoke_restart.ps1) | Orchestrator for one bounded 60 s run. Order: MediaMTX, then publishers, then receivers (done-flag stop); 700 ms stall at t = 15 s; MediaMTX restart at t = 35 s. `-SelfTest` launches nothing |

**Per-frame metadata (SEI):**
- camera, eye, sequence number;
- device time, host monotonic time and **UTC wall-clock** capture time;
- **host ID**;
- session and trial IDs, configuration ID;
- flags (synthetic, burst-held).

**Receiver events:** `link_up`/`link_down`, `freeze_start`/`freeze_end` (with duration), `integrity_error`, `sei_error`, `decode_error`.

**Frame-age columns in `frames.csv`:** UTC capture → display per eye; monotonic capture → display.

## Offline checks done (no network, no server)

41/41 passed on 5 Nov 2026 ([tests/test_streaming_poc.py](tests/test_streaming_poc.py); run it with `.venv\Scripts\python.exe -I tests\test_streaming_poc.py`, which writes only to a temporary folder). They cover:
- emulation prevention;
- the SEI round-trip, CRC rejection and foreign-UUID filtering;
- insertion before the first VCL NAL;
- the barcode on raw frames;
- **libx264 output is Baseline (profile_idc 66) with no B-frames**, one decoded frame per packet, and SEI and barcode intact through an MPEG-TS file round-trip;
- presenter pairing, latest-frame-wins after a burst, freeze start/end, late-frame discard, exact missing counts, integrity and eye-mapping errors;
- the URL guard;
- the event-record fields;
- the config file (listeners off, loopback only);
- the analyser verdicts.

**Not yet exercised:** the RTSP publish/read code paths against a live MediaMTX, timing under real load, reconnection, and Windows firewall/Defender behaviour.

## G1 rerun (prepared; needs approval)

Same plan and acceptance criteria as the 12:27 run. From `streaming_poc`, with the laptop on AC power, lid open and screen unlocked:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_smoke_restart.ps1 -SelfTest -SelfTestDir $env:TEMP
powershell -ExecutionPolicy Bypass -File .\run_smoke_restart.ps1 -Seconds 660 -Stall 120:300:burst,240:700:burst,360:700:drop -Drop 480:5 -RestartAt 540 -DownSeconds 5 -Label g1
# then, per camera, and once for both:
.venv\Scripts\python.exe analyse_poc.py --pub results\pub_<stamp>_A_g1_A --rx results\rx_<stamp>_A_g1_A
.venv\Scripts\python.exe smoke_check.py --evidence results\smoke_<stamp> --stream results\pub_<stamp>_A_g1_A results\rx_<stamp>_A_g1_A --stream results\pub_<stamp>_B_g1_B results\rx_<stamp>_B_g1_B
```

## Original manual G1 procedure (superseded by the orchestrator)

Run each command in its own terminal, from `C:\Users\a1920234\Documents\Phase2_Interface\streaming_poc`.

```powershell
# 1. server (stop it with Ctrl+C)
tools\mediamtx_v1.21.3\bin\mediamtx.exe config\mediamtx_localhost.yml

# 2. receiver for camera A (start before the publisher; 11.5 min)
.venv\Scripts\python.exe receive_reference.py --camera A --seconds 690 --label g1a

# 3. publisher for camera A: 11 min, with two burst stalls (300 / 700 ms, as in Stage D),
#    one 700 ms drop stall and a 5-frame drop
.venv\Scripts\python.exe publish_synthetic.py --camera A --seconds 660 --label g1a `
    --stall 120:300:burst --stall 240:700:burst --stall 360:700:drop --drop 480:5

# 4. server restart test (G1.6): at about 9 min, Ctrl+C the server, wait about 5 s, start it again

# 5. verdict
.venv\Scripts\python.exe analyse_poc.py --pub results\pub_<stamp>_A_g1a --rx results\rx_<stamp>_A_g1a
```

Camera B can be run at the same time with `--camera B` (one receiver and one publisher each). A short 60 s smoke test, without faults, is advisable before the full run.

## Orchestrator v2 (5 Nov, approved for Task 05 T3; defaults unchanged)

`run_smoke_restart.ps1` gained four options:

| Option | Effect |
|---|---|
| `-Cameras A` | Starts only camera A's publisher and receiver (default `A,B`) |
| `-NoRestart` | Skips only the planned MediaMTX restart |
| `-ExternalProcess <name>` | MediaMTX is held until a hand-started process (e.g. the Unity player `Phase2M1`) exits, bounded by `-ExitWaitSeconds`; recorded in `cleanup.json` |
| `-PlanOnly` | Prints the exact launch plan and exits without launching anything |

**Unchanged by these options:** preflight, the listener check, keep-awake, supervision, resource sampling and cleanup.

**Regression:** `-PlanOnly` with the G1 rerun parameters reproduces exactly the arguments the G1 rerun processes recorded; the self-test covers the new parsing. Version 1 (used for the G1 rerun) is archived with the T3 evidence.

## Orchestrator v3 (5 Nov, Task 05 T4 preparation)

- **`-ExternalProcess` now samples the hand-started process** (CPU and memory in `resources.csv`, role `ext_<name>`) and records its start and exit times and exit code (`cleanup.json`, `external_process.tracked`).
- **Cleanup's `external_process_running` serialises as `[]`** (it was `{}` in T3); cleanup behaviour is unchanged.
- **Tests:** `-SelfTest` and `tests/test_orchestrator_plans.py`.

## Criteria versions

Recorded verdicts are never re-scored. A changed criterion gets a new version and a new key in `smoke_check.py`, and the old key is kept so that historical reports stay reproducible.

**S7b v1 (in force for all Task 04B runs; unchanged):**
- no displayed pair over the excess-delay threshold;
- no "fresh" label without verification;
- the display is strictly increasing;
- **for every stall:**
  - at most 2 held frames shown;
  - first-frame recovery is 0 frames;
  - `rejection_events > 0`, counted cumulatively from the stall start to the end of the run.

**S7b v2 (adopted by the researcher on 5 Nov for future tests only; implemented 5 Nov as `smoke_check.s7b_v2`, key `S7b_v2_stale_frame_rejection`, tested by `tests/test_s7b_v2.py`).** The S7b v1 historical FAILs (12:27 and 15:11 runs) are preserved. The same global conditions, and the same "at most 2 held frames shown" and "0-frame recovery" for every stall. The rejection requirement changes in two ways:
1. **Applicability.** A stall requires a rejection only if at least one of its held frames actually *arrived* at the receiver after the stall start (from `arrivals.csv`). A drop stall, where no held frame arrives, is reported as "rejection: not applicable". Its other conditions still apply.
2. **Bounded window.** Rejections count only within the stall's window, from stall start to stall end + 2 s, and only when they reject a held frame or its obsolete backlog. This way, unrelated later rejections (such as G1's ~300 ms delays) cannot satisfy it.

It would be reported as a new key, `S7b_v2_stale_frame_rejection`, next to the unchanged `S7b_stale_frame_rejection`.

**S7b v3 (approved 6 Nov 2026, POST-HOC after the Task 05 T4 v1 FAIL; for future use).**
- **Where:** `smoke_check.s7b_v3_check`, key `S7b_v3_stale_frame_rejection`; tested by `tests/test_s7b_v3.py`.
- **Reported only when requested** (`--s7b-v3`, or `stream_analysis(..., s7b_v3=True)`). Runs without the flag reproduce the v1 and v2 keys and every earlier report exactly.
- **Changes from v2:**
  1. **No per-stall recovery rule.** v1 and v2's "0-frame recovery" contradicted M1.4 and G1.4's "≤ 2 frames", which stays authoritative.
  2. **Pre-stall frame.** `seq_first − 1` is in the held set only when it is **transport-held**: its send→receipt time exceeds 50 ms (S7a's limit) for either eye. Otherwise the held set is the publisher's stall frames only.
- **Reported separately per stall:** transport delay (capture→send and send→receipt of the pre-stall frame), freshness (displays in the stall window) and held-frame display (gating).
- **Otherwise unchanged from v2.**

Task 05's `score_m1` uses v3 under M1 criteria v2 (see `unity/Phase2Client/Tools/score_m1.py`).

## Not decided here

- The production encoder: the OAK on-device `VideoEncoder`. libx264 only mirrors its settings.
- The Unity receiver implementation: kept flexible (FFmpeg-based on Windows; MediaCodec-based on Quest).
- Bitrate, keyframe interval and the freeze threshold: these defaults are placeholders, to be revisited after G1.

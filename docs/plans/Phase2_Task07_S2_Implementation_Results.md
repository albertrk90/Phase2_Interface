# Task 07 S2: two-camera supervisory video (implementation and results)

**Status: S2 implemented (6 Nov 2026), awaiting review before S3.** Offline only:
- recorded or generated video through the validated M1 receivers;
- the in-process simulated backend;
- no COROL, robots, MediaMTX or physical cameras;
- nothing changed in `camera_validation`, `camera_gateway`, `streaming_poc` or any historical evidence.

**Basis:**
- [S1 results](Phase2_Task07_S1_Implementation_Results.md) (accepted);
- [design proposal rev. 2](Phase2_Task07_AI2_Interface_Design_Proposal.md);
- the researcher's S2 decisions (6 Nov 2026): the opt-in `createDisplay` flag; synthetic Camera B; the C09 investigation; the provisional nudge semantics retained.

> Simulation only: all backend acknowledgements and timings are placeholders. Simulated commanded-offset limits are not approved physical robot limits. The S2 screen is a **developer harness**, not the participant interface (S3).

---

## 1. Implemented

| Item | Where | Notes |
|---|---|---|
| **Opt-in `createDisplay` flag** (decision 1) | `Assets/Phase2/Video/Unity/StereoReceiverBehaviour.cs` | Default `true` = M1 behaviour. Every statement on that path runs as before; the additions only set two counters (`PairsCopied`, `LastCopiedRow`) and record size and crop. `false`: no `DisplayRig`; the selected pair stays available read-only (`LeftLuma`, `RightLuma`, `PairsCopied`, `LastCopiedRow`, `ImageWidth/Height`, `DisplayCrop`); `run_start.display` reads "external view (createDisplay=false)". The **only** edit to existing validated code |
| **One receiver per camera**, both continuous | `Experiment/Unity/CameraFeeds.cs` (`CameraFeed`) | Each camera keeps its own backend threads, `StereoPresenter` (pairing, absolute/relative freshness, SEI/eye/camera identity, barcode for synthetic), logs and output folder. A feed uploads that receiver's selected **left-eye** luma (2D condition) into its own R8 texture |
| **Supervisory video view** | `CameraFeeds.cs` (`SupervisoryVideoView`) | One quad with the **unchanged** `LumaUnlit` shader. Zoom and pan = its `_Crop` sub-rectangle via the pure `ViewMapping.CropUv`; no shader change. Built-in 1× render check (same criteria as M1) |
| **Decision-time frame data** | `FeedDisplayInfo` (implements S1's `IDisplayInfo`) | Every client event and request carries the displayed frame of **both** cameras: seq, display UTC, SEI capture UTC, freshness label, and age (null when the clock is untrusted, as in replay). Video state = no fresh pair for > 500 ms on the on-screen camera |
| **Session driver + developer harness** | `Experiment/Unity/S2Session.cs`, scene `Assets/Phase2/Scenes/S2_TwoCamera.unity`, `Editor/S2Build.cs` | Runs the S1 `SimHarness` on the **real QPC clock** (a virtual clock advanced to `Clocks.MonoNs` each frame). The plate is applied in `LateUpdate`, so state changes show the same frame. The **simulated trial starts only after both cameras display pairs** (`video_ready`): no decision point opens without video. Plain IMGUI panel, mouse zoom at a point and drag to pan, keyboard shortcuts. Logs: `client_events.jsonl`, `backend_events.jsonl`, `wire.jsonl`, `view_frames.csv` (every frame: camera, zoom, rectangle, crop UV, shown seq, both cameras' seqs, video state), `s2_summary.json`. Optional scripted verification run (`-s2Script`) recording 33 named checks; `-s2Shots` saves screenshots |
| **Synthetic Camera B** (decision 2) | `Tools/make_synthetic_camera_b.py` → `test_results/inputs/synthetic_B_s2/` | Task 04B synthetic frames with the **camera-B** barcode code and SEI camera B with FLAG_SYNTHETIC set, 40 s, 20 fps. A hatched inset frame plus large **"SIMULATED CAMERA B / SYNTHETIC TEST FEED - NOT A REAL CAMERA / OVERVIEW CAMERA STAND-IN"**, placed clear of the barcode, eye markers and stereo targets. References are the **decoded** luma (bit-exact expected). No camera session |
| **S1 additions** (additive, defaults unchanged) | `Experiment/Core/ViewState.cs`, `Experiment/Sim/*` | `ViewMapping` (crop UV, plate to source); richer `DisplayedFrame` (display time, freshness, age availability); `SimHarness` optional clock, display and file-sink injection; `TeeSink` |
| **Demo scenario** | `Experiment/Scenarios/s2_demo.json` | 4 elements, short placements. Primary camera **A by default**; B for two elements to exercise restoration to the protocol-defined primary; balanced across hidden conditions (the validator is clean) |
| **Offline verifier** | `Tools/verify_s2_run.py` | Imports `verify_unity_run.py` **read-only and unchanged**. Per camera: oracle replay plus scenario checks. Camera A's `display_bit_exact_and_crop` re-evaluated with the same criteria from the S2 view's render check (no M1 rig exists with `createDisplay=false`; labelled as a substitution). Camera B checks. S2 view rules over `view_frames.csv` and the client log (outside Inspect always primary at 1×; commits carry context; no decision before both cameras are live) |

### 1.1 Rules as implemented (S1 logic, presentation in S2)

| Rule | How it is implemented and verified |
|---|---|
| Camera A is the default primary | The prescribed primary comes from the scenario (protocol) per decision point |
| Camera switching and zoom only in Inspect | Refused and logged otherwise |
| Inspect stays active while Intervene and nudges are used; Allow and Retry can be committed from the inspected view | The camera and zoom are **unchanged until the decision point closes**, then reset to the primary at 1× |
| A camera switch implies no robot movement or approval | It is local view state plus `view` telemetry: never a request, never acknowledged, no backend effect. Tested in EditMode and PlayMode |

---

## 2. C09 investigation (decision 3)

Evidence: [`unity/Phase2Client/test_results/c09_investigation_20261106/NOTE.md`](../../unity/Phase2Client/test_results/c09_investigation_20261106/NOTE.md).

- **Cause:** a legitimate wall-clock adjustment. The Windows Time service (NtpClient, `time.windows.com`) stepped UTC by **−2488 ms at 15:58:17 local**:
  - Kernel-General event 1 and Time-Service event 35;
  - read-only `Get-WinEvent` queries;
  - this was after the reference was made (11:58) and before the S1 run (16:56).
- **The clocks themselves agree:** a fresh read-only measurement gave −2489.221 ms, the same boot session (boot estimate shifted −2.488 s). QPC is unchanged; Unity and Python agree.
- **Action:** the original failures and the superseded reference were preserved; the reference was regenerated with `Tools/make_clock_reference.py`.
- **Rerun:** **6/6 PASS, C09 offset difference 0.00 ms.** No threshold, time or sync setting was changed. Every EditMode run since then has included C09 and passed.

---

## 3. Test results

**Unity 6000.3.28f1.** Evidence is in `unity/Phase2Client/test_results/ai2_s2/` plus the run folders named below (git-ignored).

| Suite | Final result | Notes |
|---|---|---|
| **EditMode, all assemblies** | **102 / 102 PASS** | 43 existing receiver/compatibility (C01–C09, presenter oracle traces, camera source); 51 S1; **8 new S2**: crop mapping, zoom boundaries over all levels and points, camera switch never a request, restoration to each element's primary across a full trial with retry, view persistence through arm/cancel, pause, nudges and failed Retry, decision-time log with both cameras' frames |
| **PlayMode: M1 replay** (unchanged test) | **PASS** in all 4 runs today | |
| **PlayMode: S2 two-camera session** (new) | **FAIL in the final run**; PASS in runs 2 and 3; run 1 FAIL | Final run: Camera B `display_image_missing = 1` (pre-existing race R2, §4); all 33 scripted checks passed. Run 1: my script sampled the plate in the same frame it changed the view (fixed: plate applied in `LateUpdate`, script waits for the view to settle) |
| **M1 PlayMode runs, `verify_unity_run.py` (unchanged)** | **3 PASS, 1 FAIL** of 4 | The FAIL (`unity_rx_20261106_173556_editor_A_playmode`) is the oracle's event-order comparison only: two simultaneous `freshness_reset` events with swapped eyes (pre-existing race R1, §4). Every displayed row and counter matched, and all 11 scenario checks passed |
| **M1 player regression** (rebuilt with `M1Build.BuildPlayer`) | **PASS** | `replay_A` (synthetic): oracle + 11 scenario checks. `camera_E1_A` (camera mode): oracle + 8 checks, including the **M1 rig's pixel-exact render check** |
| **S2 PlayMode sessions, `verify_s2_run.py`** | Run 3 (`ai2_s2_20261106_173512_editor`) **PASS**; final run (`…174409_editor`) **FAIL** | The final run's failures are R1 on both cameras (oracle event order) and R2 on Camera B (`b_clean_run`). Every other check passed |
| **S2 Windows player, scripted** (final build) | Run 1 (`ai2_s2_20261106_174659_win64player`): **33/33 checks**; verify FAIL on R1 only (Camera B oracle event order). Run 2 (`…174748_win64player`): **OVERALL PASS** | Video ready after 0.54 s and 0.19 s; 0 missing images. Frame time p99 17.1–18.7 ms at 60 Hz with both receivers and the harness (indicative; M1.8 bound 25 ms). An earlier player build (`…174017`) passed every check, but saw an **18 s FFmpeg start-up delay** on its first launch (not recurring; cause unverified) and exposed that the trial could open a decision before video existed (fixed: `video_ready` gating) |

**Pixel exactness of the S2 view at 1×:** max |diff| **0** in every run:
- Camera A: 953,260 px of the rectification crop;
- Camera B: 1,024,000 px.

**Synthetic B display** is bit-exact against the decoded references (99 dB). The first S2 runs used pre-encode references (39.5–42 dB, encoder loss on the label). The input was regenerated with decoded references; the superseded input is kept as `test_results/inputs/_superseded_synthetic_B_s2_preencode_refs_20261106/`.

---

## 4. Unresolved technical issues

Two are pre-existing in the validated M1 receiver code, which S2 does not touch. I did not fix either, because both need your approval and an M1 regression.

| # | Issue | Evidence | Effect | Proposed fix (not applied) |
|---|---|---|---|---|
| **R1** | **`freshness_reset` event order race.** `StereoPresenter.OnLinkReset` records its op inside the presenter lock but emits the event **outside** it. When both eyes (re)connect within microseconds, the two events can be written in the opposite order to the ops | `ops.csv` `r,right` then `r,left`; `events.jsonl` left then right, with the right event's timestamp 1.4 µs **earlier**. Seen in 4 of 18 verified receiver runs today (M1 editor 1/4; S2 editor 2/6; S2 player 1/6); none in the M1 player runs | **Logging order only.** Displayed rows, counters and freshness decisions all match the validated Python presenter. The oracle's strict event-order comparison fails | Emit the event inside the lock (or derive it from the traced op), then rerun the M1 differential and oracle regression |
| **R2** | **Luma availability race.** `ReceiverCore.OnFrame` calls `Presenter.OnFrame` (the pair becomes selectable) **before** `Lumas.Put` (its luma is stored). A display tick in between selects a pair whose second eye's luma is not yet stored | `display_image_missing` (seq 299, left) once, Camera B, final S2 editor run (batch-mode editor ticking at about 2,700 Hz). Never seen in player runs (60 Hz) | That pair's image is not uploaded; the plate keeps the previous picture for one pair interval (about 50 ms). Logged | Store the luma before notifying the presenter (release it if the frame proves late or obsolete), then rerun the M1 regression |
| R3 | **FFmpeg start-up delay** of 18 s, once, on the first launch of a freshly built S2 player | `backend_started` 18.06 s after `run_start`; later launches 0.2–0.5 s | None now that the trial waits for video | Watch for it in S3 and S4 sessions. Hypothesis (unverified): first-load scanning of newly copied DLLs |
| R4 | **Camera A replay is about 20 s** (`camera_E1_A`); Camera B is 40 s | — | After about 20 s the harness shows Camera A "video: interrupted" (correctly) | A longer offline A input for S3 demos (generated or recorded; your choice) |

**Also by design:** the S2 Camera A run cannot produce the M1 `DisplayRig` render check. `verify_s2_run.py` substitutes the S2 view's own 1× render check, using the same criteria, and reports both verdicts.

---

## 5. Demonstration procedure (offline)

Run from `unity/Phase2Client`.

**1. Inputs** (once). `camera_E1_A` already exists. Generate synthetic Camera B:

```powershell
..\..\streaming_poc\.venv\Scripts\python.exe -I Tools\make_synthetic_camera_b.py
```

**2. Build the S2 player** (or open `Assets/Phase2/Scenes/S2_TwoCamera.unity` in the Editor and press Play):

```powershell
$U = "C:\Program Files\Unity\Hub\Editor\6000.3.28f1\Editor\Unity.exe"
& $U -batchmode -quit -projectPath . -buildTarget Win64 -executeMethod Phase2.EditorTools.S2Build.BuildPlayer -logFile test_results\logs\s2_build.log
```

**3. Interactive demo** (about 45 s of video):

```powershell
Builds\S2\Phase2S2.exe -screen-fullscreen 0 -screen-width 1600 -screen-height 900
```

Things to try:
- The first decision opens once both cameras are live, on the wrist camera at 1×. Camera, zoom and pan are refused outside Inspect.
- **Inspect** (I), then **Cam B** (B) shows *SIMULATED CAMERA B*. Click the plate to zoom at a point (2× then 3×); drag to pan.
- **Intervene** (V), then nudge with the arrows: the view stays as it is while each nudge goes received → accepted → started → completed → ready.
- **Allow** then **Confirm** (Enter) from the inspected view: nothing resets until the decision closes, then the view returns to the primary camera at 1×.
- Elements 3 and 4 open on their prescribed primary, Camera B.

**4. Scripted demo and verification:**

```powershell
Builds\S2\Phase2S2.exe -s2Script -s2Shots -s2Quit -screen-fullscreen 0 -screen-width 1600 -screen-height 900
..\..\streaming_poc\.venv\Scripts\python.exe -I Tools\verify_s2_run.py test_results\ai2_s2_<stamp>_win64player
```

Screenshots `screen_*.png` are written into that run folder.

---

## 6. Readiness for S3 (Windows participant interface)

**Ready:**
- the two-camera video path (both validated receivers, each with its own safeguards);
- the view model and shader mapping (pixel-exact at 1×);
- decision-time logging with both cameras' frames;
- the S1 state machine and simulated backend driven on real time;
- `video_ready` gating;
- a verifier for whole sessions.

S3 replaces the IMGUI developer panel with the Site Window UI (uGUI + TextMeshPro: View and Adjust wings, Desk, string table) on top of `S2Session`'s feeds, view and harness.

**Before or with S3, your decisions are needed on:**
1. **R1 and R2 fixes** in the validated receiver (small, targeted; each followed by the full M1 regression). Recommended before any pilot, because R2 can drop one displayed update and R1 makes the oracle check intermittently fail.
2. **A longer Camera A offline input** for S3 demos and pilots (R4).
3. **Font download** (IBM Plex, D11) for the S3 UI, if still wanted.

# Task 07 S3: Site Window Windows participant interface (implementation and results)

**Status: S3 accepted by the researcher as the functional baseline (12 Nov 2026) and committed: `e418f620663e5cf7c84fa37127758d12bf11a02d` (local `master`, no remote).** Superseded in the workflow by [S3.1](Phase2_Task07_S3_1_Implementation_Results.md) (released-element recovery and correction); the S3 held-element workflow remains as a regression. S4 has not been started.

Offline only:
- recorded or generated video through the validated M1 receivers;
- the in-process simulated backend;
- no camera, MediaMTX, COROL, robot, network or university settings were touched;
- nothing in `camera_validation`, `camera_gateway`, `streaming_poc` or any historical evidence was changed.

**Basis:**
- [Site Window proposal, revision 2](Phase2_Task07_AI2_Interface_Design_Proposal.md), with the researcher decisions recorded in [S1 results §1](Phase2_Task07_S1_Implementation_Results.md);
- [S2 results](Phase2_Task07_S2_Implementation_Results.md) and [Part A receiver race fixes](Phase2_Task07_S2_PartA_Receiver_Race_Fixes.md);
- the S3 brief of 11 Nov 2026.

> **Simulation only.** All acknowledgements, timings and results come from the simulated backend. Receipt does not imply motion. The step sizes (1, 2, 5 mm) and limits (±15 mm per axis, 12 nudges per decision point) are provisional simulation settings, not approved robot limits. Camera B is SYNTHETIC. The recorded video does not respond to nudges or Retry.

---

## 1. How to try it

**The build:** `unity/Phase2Client/Builds/S3/SiteWindow.exe` (Windows x64, Mono, 208 MB folder, git-ignored). It needs the existing offline inputs `test_results/inputs/camera_E1_A` and `synthetic_B_s2`; both are present.

| Goal | Command (from `unity/Phase2Client`) |
|---|---|
| Try it, full screen on the main display | Double-click `Builds\S3\SiteWindow.exe`, or `powershell -ExecutionPolicy Bypass -File Tools\run_site_window.ps1` |
| Full screen on the 1920 × 1080 monitor (pixel-exact plate) | `... Tools\run_site_window.ps1 -Monitor 2` (monitor numbering is Unity's; try 1, 2, 3) |
| In a 1600 × 900 window | `... Tools\run_site_window.ps1 -Windowed` |
| With developer tools (fault injection, pause, video freeze; F2 hides) | add `-Dev` |
| The scripted verification run, with screenshots | `... Tools\run_site_window.ps1 -Script -Monitor 2`, then `..\..\streaming_poc\.venv\Scripts\python.exe -I Tools\verify_s3_run.py <run folder>` |

- **Close it with Alt+F4.** The participant interface ignores the keyboard by design; only `-Dev` adds a key (F2).
- **Mouse only:** click controls; in Inspect, click the image to zoom in at that point and drag to pan.
- **Each launch writes evidence** to `test_results/ai2_s3_<stamp>_win64player/` (client and backend event logs, wire transcript, per-frame view log, summary, the participant texts that were shown) plus one `unity_rx_*` receiver folder per camera.
- **First launch after a fresh build** may sit on "Waiting for video" for up to about 18 s while Windows first loads the new FFmpeg DLLs (the known R3 effect; see §8). The trial starts only once both cameras show images.

**The walkthrough** (`s3_walkthrough.json`): four decision points, primary camera A for elements 1–2 and B for 3–4, no scripted faults.
1. **Begin.** The start screen names the trial; Begin starts both receivers. The first decision point opens about 2.5 s after both cameras are live.
2. **At a decision point,** the three keys light up: Allow · Inspect · Intervene. Wings are folded, the wrist camera is at 1×, and the status reads *Holding for your decision*.
3. **Inspect** opens the View wing (left): Wrist / Overview camera, 1× 2× 3×, Reset view, a map of the visible area, End inspection. Click the image to zoom at a point; drag to pan. Repeat Inspect as often as you like.
4. **Intervene** (Inspect may stay open) opens the Adjust wing (right): step 1, 2 or 5 mm; four arrows around a plan diagram; the nudge lifecycle (*Sent · Received · Accepted · Moving · Done*); the commanded offset; nudges remaining; and, below a rule, *Retry placement…*.
5. **Nudges:** each click sends one nudge. The pad locks until the site permits the next. Extra clicks are ignored and logged. The offset changes only when a nudge completes.
6. **Allow or Retry** opens a confirmation row on the Desk that names your current view ("You are viewing: overview camera (simulated), 2×."). Cancel returns to the keys.
7. **After about 20 s** Camera A's recording ends. The caption turns amber (*Video interrupted · n s*), then *Video unavailable*, and the last image is shown dimmed with a note. It is never looped. Camera B runs about 40 s.
8. With **`-Dev`**, the panel at the top right arms the simulated backend's own faults for the next request (reject, fail during motion, delayed receipt, failed Retry, rejected Allow). It can also pause or resume as the experimenter, freeze A or B for 3 s, or drop and restore the link.

**Rebuild** (batch mode, about 2 minutes):
```powershell
$U = "C:\Program Files\Unity\Hub\Editor\6000.3.28f1\Editor\Unity.exe"
& $U -batchmode -quit -projectPath . -buildTarget Win64 -executeMethod Phase2.EditorTools.S3Build.BuildPlayer -logFile test_results\logs\s3_build.log
```
The build applies borderless full screen at native resolution and the product name "SiteWindow" for this build only, then restores the project's player settings (verified: `ProjectSettings/` unchanged).

---

## 2. What was built

All S3 code is new, under `unity/Phase2Client/Assets/Phase2/SiteWindow/`. **The only edit to existing code** is one additive field in S2's video view (first row below).

| Item | Where | Notes |
|---|---|---|
| **`SupervisoryVideoView.FitMargin`** (S2 code, additive) | `Experiment/Unity/CameraFeeds.cs` | The fit margin was a constant 1.08. It is now a field whose default 1.08 keeps S2 byte-for-byte unchanged in behaviour. S3 sets 1 and places the view camera's viewport exactly on the plate. The validated `LumaUnlit` shader, the `_Crop` zoom and the receivers are untouched |
| **Participant model** (pure C#, no engine references, reusable for Quest 3) | `SiteWindow/Model/ParticipantStrings.cs`, `SiteWindowModel.cs` (`Phase2.SiteWindow.Model`) | **One string table** for every participant-visible text. `SiteWindowModel.Build(machine, videoInputs)` projects the S1 `SupervisorMachine` plus each camera's video state into a `SiteWindowState`: status line, caption, keys, Desk mode, confirmation, step card, record, wings, lifecycle, offset. It decides nothing |
| **Interface** (uGUI + TextMeshPro, built in code) | `SiteWindow/Unity/SiteWindowUi.cs`, `SwTheme.cs`, `SwShape.cs`, `SwButton.cs`, `SwHitArea.cs`, `PlateInput.cs` (`Phase2.SiteWindow.Unity`) | Layout, rendering and click reporting only. **`SwButton` always forwards its click:** a control shown unavailable still sends the click to the machine, which refuses it and logs `input_ignored`. Availability is never enforced in the UI |
| **Session** | `SiteWindow/Unity/S3Session.cs` | Start screen; Begin starts both receivers (`createDisplay = false`), the S2 feeds and view, and the S1 `SimHarness` on the real QPC clock. Also: per-camera video state; interface logging; cursor; developer tools (`-s3Dev` only) |
| **Scripted verification** | `SiteWindow/Unity/S3Script.cs` | 63 named checks, driven through the **real** EventSystem raycast at each control's on-screen position, with screenshots and an on-screen pixel check (§6.2) |
| **Thumbnail shader** | `SiteWindow/Shaders/LumaUI.shader` | R8 luma → grey for the View wing's location map only (mirrors `LumaUnlit`'s maths for a RawImage). The plate keeps `LumaUnlit` |
| **Scenarios** | `Experiment/Scenarios/s3_walkthrough.json`, `s3_script.json` | Both balanced across hidden conditions (validator clean). The script scenario adds deterministic backend faults (§6.2) |
| **Scene, build, launcher** | `Scenes/S3_SiteWindow.unity`, `Editor/S3Build.cs`, `Tools/run_site_window.ps1` | The scene holds one `S3Session` that references the shaders and fonts, so the player includes them |
| **Tests** | `SiteWindow/Tests/Editor/SiteWindowModelTests.cs` (17), `SiteWindow/Tests/PlayMode/S3SiteWindowPlayModeTests.cs` (1) | §6.1 |
| **Offline verifier** | `Tools/verify_s3_run.py` | Imports `verify_s2_run.py` read-only (which imports `verify_unity_run.py` read-only): oracle replay of both receivers, the S2 view rules, plus S3 log-integrity rules (§6.3) |
| **Fonts** | `SiteWindow/Fonts/` | IBM Plex Sans 1.1.0 (Regular, Medium, SemiBold) and Plex Mono 2.5.0 (Regular, Medium), from IBM's official GitHub releases, SIL OFL 1.1; licence files kept beside them. Provenance and hashes: `ThirdParty/README.md` |
| **TextMesh Pro essentials** | `Assets/TextMesh Pro/` | Extracted from the `TMP Essential Resources.unitypackage` inside the installed `com.unity.ugui` 2.0.0 (nothing downloaded); Shader Graph variants left out |

**Separation kept:**

| Layer | Implemented by |
|---|---|
| Experimental logic | S1 machine and backend, unchanged |
| Backend communication | in-process link, unchanged |
| Video | receivers, feeds and view, unchanged apart from the one field above |
| Participant UI | model → UI |
| Logging | the existing `EventLog` files plus `view_frames.csv` |

---

## 3. Design: how Site Window was translated into Unity

**Geometry (1920 × 1080 stage, scaled uniformly to the screen):**

| Element | Position and size (stage px) |
|---|---|
| Strip | 0–50 |
| Caption | 50–84 |
| Plate | x 341, y 84, **1238 × 770** |
| Wings | 301 × 770 at x 20 and x 1599 |
| Desk | from y 868 |

- **At a 1920 × 1080 screen the scale is exactly 1.** Camera A then shows 1 source pixel per screen pixel at 1×, verified on screen (§6.2).
- **Camera B is fitted by height** (scale 0.9625, 1232 × 770, centred).
- **The plate never moves,** whatever is open, so the image and the three keys stay spatially stable.

**Visual language:** as approved.
- **Palette:** warm graphite and paper-coloured type, hairline rules, a title-block step card.
- **Two non-evaluative hues only:** lens blue = inspecting; amber = a system condition (video interrupted or unavailable, not accepted, not completed, no confirmation).
- **No green or red,** no scores, timers or counters of inspections.

**Typography:** IBM Plex Sans for text, Plex Mono for the offset values and the video readout (tabular figures); 12.5 px minimum (caps labels and lifecycle labels), 15–19 px body, 28 px keys.

**Where S3 departs from the browser mock-up** (no change to interactions or information):

| Change | Reason |
|---|---|
| Strip 50 px and caption 34 px (mock-up 56 and 34); Desk starts 14 px below the plate (mock-up: touching) | The plate's inspect outline and registration marks no longer collide with the Desk rule |
| Lifecycle labels sized to their text, bars aligned under each label | Fixed equal cells made "Received / Accepted / Moving" overlap at 12 px (first build) |
| Camera buttons have three lines (name · letter and role · video state) | The role and simulated-feed note plus a video warning overflowed one line |
| "Video unavailable": the last image dimmed, with an opaque card ("No new images are arriving from this camera. The last image received is shown dimmed. This does not indicate the robot's status.") | Text over a busy image was unreadable. The card states the separation between video and robot state |
| A start screen with Begin | The brief asks for "starting or entering a trial". It also keeps Camera A's 20 s recording from being used up before the participant is ready |
| Confirm and Cancel share one raised style (Confirm has a 2 px paper border); the same structure for Allow and Retry | The mock-up's bright paper Confirm button made confirming visually dominant over cancelling |
| Arrows drawn as geometry, not glyphs | Avoids any font-coverage dependency (the glyph check found none missing anyway) |
| Interrupted video: amber plate outline and caption counter, image not covered | Transparent, but nothing over the image while frames may still be arriving |

**Restrained motion:**
- the wings fade and slide 8 px in 140 ms;
- unavailable controls fade to their dimmed state in 150 ms;
- the current lifecycle stage pulses gently while waiting;
- the commanded target ring pulses while a nudge is "moving".

There are no sounds or haptics.

---

## 4. Interaction rules as implemented

Rules are enforced by the S1 machine and backend; the UI only shows them.

| Requirement | Implementation |
|---|---|
| **Allow** from the normal view or from Inspect; confirmation; selection and confirmation logged separately | `choice` (selection), `arm_cancel` (Cancel) and `commit` (confirmation) are separate client events. The commit carries the inspection state, camera, zoom, visible rectangle, both cameras' displayed frames (seq, display time, freshness), video state and the commanded offset |
| **Inspect:** camera, zoom and pan only during Inspect; repeated Inspect; outside Inspect the primary camera at 1× | The View wing exists only while inspecting. Plate clicks or drags outside Inspect reach the machine and are refused (`input_ignored: not_inspecting`); nothing is sent to the backend |
| **Intervene does not close Inspect;** decisions are made from the inspected view; reset only when the decision point closes | Both wings open together. The view is restored (`view_restore`, cause `decision_close`) only at closure; verified frame by frame (§6.2) |
| **Nudges:** one independent request at a time; immediate acknowledgement; receipt is not motion | The pad locks in the click's frame and *Sent* shows at once. *Received* is worded as receipt only. *Moving* appears only on the backend's `started`. *Done* or *Not completed* comes on its result, and the pad unlocks on `ready`. Clicks while locked are logged and never queued |
| **Backend authority over limits;** rejected nudges do not use the allowance; accepted ones do even if they fail; failures are not achieved displacement | The arrows grey out at the guidance limit, but the backend validates. Shown: *Not accepted: …* (amber, allowance unchanged); *Movement not completed. The commanded offset is unchanged.* (allowance used) |
| **Offset = accepted cumulative commanded correction** | "Commanded offset … Sum of accepted, completed nudges. Not a measured position." It is updated only from the backend's reported value |
| **Retry:** confirmation; reset only when the new attempt has begun; a failed or rejected Retry resets nothing | Retry is below a rule in the Adjust wing, with the Desk confirmation. A failed Retry shows *Retry did not start. The nudges and the commanded offset are unchanged.* The reset is logged after `request_started` |
| **Video separate from robot and task state** | Task status (strip) and nudge lifecycle (Adjust wing) come only from backend messages. The video state (caption, plate frame and veil) comes only from the receivers. A frozen or ended video never changes the status line (tested) |
| **No participant timeouts, scores or correctness cues** | None. Only system timeouts (receipt, acceptance, start, execution, ready) appear, as *No confirmation from the site. Please wait for the experimenter.* |

---

## 5. Logging added (the existing event model is unchanged)

All new records go into the **same** `client_events.jsonl` through the existing `EventLog`, on the simulation clock, each with the machine's full context (`ctx`).

| Event | Content |
|---|---|
| `ui_click` | Every click: control id, and whether it was shown as available |
| `ui_hover` | Begin and end for every control |
| `ui_plate_click` | Plate-normalised point (then the machine's `view_zoom` or refusal) |
| `ui_state` | **What the participant could see, logged on every change:** status and tone, Desk mode, hint or message, key states, confirmation text, wings, caption, plate condition, lifecycle cells and message, offset and allowance shown, arrow availability, top record line, step card. This allows an audit of the presentation independent of the layout |
| `video_state` | Per-camera transitions (waiting / live / interrupted / unavailable), with time since the last image, whether the receiver has finished, and whether the camera was on screen |
| `session_begin`, `s3_start`, `s3_end` | Session framing; fonts, screen and scale; developer mode |
| `dev_*` | Developer tool actions (fault armed, pause, freeze, link); `-s3Dev` only |
| `view_frames.csv` | S2's per-frame columns, plus each camera's video state, stage scale and plate pixel rectangle |
| `participant_texts.txt` | Every distinct participant-visible string shown in the session (for review and lint) |

---

## 6. Verification

### 6.1 Automated tests (Unity 6000.3.28f1, batch mode)

| Suite | Result | Notes |
|---|---|---|
| **EditMode, all assemblies** | **126 / 126** (final run 11 Nov) | 50 compatibility and receiver (C01–C09, oracle traces, race tests); 59 S1/S2; **17 new S3 model tests** |
| **PlayMode, all** | **3 / 3** in each of the last three runs | `FullReceiver_ReplayScenario` (M1), `TwoCamera_ScriptedSession` (S2) and **`SiteWindow_ScriptedSession`** (S3, all 63 checks plus receiver cleanliness). The S3 test failed in the first two Editor runs (`MissingComponentException`, §8 item 3); fixed |

**The 17 S3 model tests cover:**
- monitoring;
- the initial decision screen;
- view controls only in Inspect, and repeated Inspect;
- Inspect and Intervene together;
- the full nudge lifecycle with exact stage presentation;
- rejection (fault and backend out-of-bounds with client guidance off);
- failure during motion and before start;
- arrows at the limits;
- receipt timeout and recovery;
- Allow and Retry confirmations sharing one structure and naming the view;
- failed and successful Retry;
- experimenter pause;
- video states never changing the task status;
- the **participant-text lint** over a full faulted trial;
- the **presentation leak test:** the complete sequence of presented states with their virtual times is identical across five hidden-condition permutations;
- a **sensitivity test** (a deliberate 100 ms hidden-condition delay is detected);
- string formatting.

### 6.2 Scripted session in the Windows player (1920 × 1080, stage scale 1)

**Final release build:** `test_results/ai2_s3_20261111_162443_win64player`, **63 / 63 checks**, plus an earlier four runs of the same script, all passing after the fixes in §8.

**The script follows the brief's list end to end:**
1. start screen;
2. initial decision screen;
3. refusals outside Inspect;
4. two Inspect episodes switching cameras;
5. click-zoom at a point, drag-pan and the zoom buttons;
6. Intervene with Inspect kept;
7. seven nudges;
8. Allow from Overview 2× with Cancel, then confirm;
9. element 2: a nudge, a Retry that fails, then a Retry that starts a new attempt;
10. element 3 (primary B): an injected video freeze, Allow during the interruption, then recovery;
11. element 4: Camera A's recording has ended; Allow; trial complete.

**Scenario faults:**
- nudge 2 rejected;
- nudge 3 fails during motion;
- nudge 6's receipt is delayed 1.5 s, beyond the 1 s receipt timeout, so the request goes Unconfirmed and then completes late without being re-sent;
- Retry 1 fails before start.

| Check group | Result |
|---|---|
| **On-screen pixel exactness** of the plate at 1× (Camera A, in the decision view and in Inspect): the captured screen inside the plate against the receiver's source luma | **953,260 px, max |diff| 0, no non-grey pixel**, both checks, every 1080p player run. The full interface was drawn around the plate |
| 1× render checks (M1/S2 criteria) | Camera A 0 and Camera B 0 (max |diff|) |
| Nudge lifecycle | Immediate *Sent*; click while busy ignored; *Moving* only after `started`; offset unchanged until `completed`; stage events in exact order; rejection uses no allowance; failure uses allowance but does not change the offset; guidance limit logged and nothing sent; Unconfirmed then late recovery, sent once |
| Decisions | Confirmation names "overview camera (simulated), 2×"; Cancel logged; 2 choices and 1 commit for Allow; commit context complete; view unchanged until close, then primary at 1× with the wings folded |
| Retry | Failed Retry resets nothing; reset only after `request_started`; new attempt with a fresh origin (*Attempt 2*, 0 mm, 12 of 12) |
| Video | Interruption shown in amber while task status and keys are unaffected; decision during the interruption logs `video_state: interrupted`; recovery logged; exhausted Camera A shown as unavailable, not looped |
| Integrity | 7 nudges, each with exactly one terminal stage; never two requests in flight; 5 decision points, each closed once (6 commits = 5 + the Retry that failed to start); no protocol problems; every click logged |
| Presentation | IBM Plex loaded; all participant glyphs render (none missing from Plex); participant-text lint clean; AI2 keys equal in size and in fixed order |

**Frame time** (from `view_frames.csv`, final run, both receivers and the full UI at 60 Hz):
- median 16.7 ms, p99 20.2 ms;
- the few frames over 25 ms coincide with scripted measurement steps (screen capture, render checks, screenshots, the glyph check) or the session-start frame (receiver start-up).

This is indicative, not a formal M1.8 evaluation.

### 6.3 Offline verification (`Tools/verify_s3_run.py`)

**OVERALL PASS** for every S3 run folder listed below:
- per camera: oracle replay against the validated Python presenter, and the camera scenario checks;
- the S2 view rules: outside Inspect always primary at 1×; commits carry context; no decision before both cameras are live;
- the S3 rules:
  - one request in flight;
  - no nudge before the previous ready;
  - every nudge has one terminal stage;
  - **the offset shown always equals the last backend report** (checked on every `ui_state`);
  - Retry resets only after started;
  - view changes only while inspecting;
  - commits carry view, video state and frames;
  - choice and commit logged separately;
  - clicks and video states logged;
  - participant-text lint;
  - on-screen pixel checks.

| Run | Oracle A / B | Overall |
|---|---|---|
| `ai2_s3_20261111_162443_win64player` (final release build) | PASS 2129 ops / PASS 4169 ops | PASS |
| `ai2_s3_20261111_162532_win64player` (same build, `-s3Dev`) | PASS / PASS | PASS |
| `ai2_s3_20261111_154848`, `160630`, `160719`, `160944`, `161532`, `161622` `_win64player` | PASS / PASS | PASS |
| `ai2_s3_20261111_160044_editor`, `161151_editor`, `162755_editor` (PlayMode; the last on the final code) | PASS / PASS | PASS (no on-screen check in batch mode) |

### 6.4 Regression of S1, S2 and M1 (nothing they validate was changed)

| Suite | Result |
|---|---|
| S1 + S2 EditMode (`Phase2.Experiment.Tests`) | 59 / 59 |
| Receiver and compatibility EditMode (`Phase2.Compat.Tests`), including R1/R2 race tests | 50 / 50 (after regenerating the per-boot C09 clock reference, §8 item 8) |
| M1 PlayMode replay + `verify_unity_run.py` | PASS in every run (oracle 55,490–58,119 ops) |
| S2 PlayMode two-camera session + `verify_s2_run.py` | PASS in every run since the fix (both oracles) |
| **M1 Windows player** (rebuilt): `replay_A` and `camera_E1_A` (camera mode) | **2 / 2 PASS**, including the M1 rig's pixel-exact `display_bit_exact_and_crop` |
| **S2 Windows player** (rebuilt; exercises `FitMargin`'s default) | **2 / 2 PASS** (oracle A and B, every scenario and view rule) |

No acceptance threshold was changed. No historical evidence was overwritten: superseded fixtures are preserved beside their replacements.

---

## 7. Screenshots (final release build, 1920 × 1080)

In [`Phase2_Task07_S3_screenshots/`](Phase2_Task07_S3_screenshots/):

| Requested view | File |
|---|---|
| Main decision view | `screen_01_decision_view.png` |
| Inspect mode (Overview, 2×) | `screen_02_inspect_overview_2x.png` |
| Inspect + Intervene | `screen_03_inspect_and_intervene.png` |
| Nudge movement in progress | `screen_04_nudge_moving.png` |
| Allow confirmation (from Inspect, 2×) | `screen_07_allow_confirm.png` |
| Video interruption | `screen_09_video_interrupted.png` |
| Also | `00_start`, `05_nudge_rejected`, `06_no_confirmation` (receipt timeout), `08_retry_confirm`, `10_video_unavailable` (exhausted recording), `11_trial_complete`, `03b_developer_tools` (`-s3Dev` only) |

---

## 8. Problems found and fixed during S3

1. **Fonts fell back to Liberation Sans in the first player run.** Runtime-created TMP font assets have a null fallback list, and my code dereferenced it. Fixed; the scripted check `fonts_ibm_plex_loaded` guards it.
2. **Trial start stamped in the past after a main-thread stall** (first player run, with the 18 s first-launch FFmpeg load, R3).
   - **What happened:** `Harness.Start()` ran before the simulation clock was advanced. `trial_start` and the first `decision_open` were therefore stamped 18 s early, and the first placement wait was skipped. The check `no_decision_before_both_cameras_live` caught it.
   - **Fix (S3 only):** advance the clock before starting the trial.
   - **Not changed:** `S2Session` has the same ordering (a latent defect in the developer harness). I left it alone because S2 was not to be refactored; fix it if the S2 harness stays in use.
3. **Editor-only `MissingComponentException`** (PlayMode runs 1–2).
   - **Cause:** the Editor resolves `RequireComponent` through a MonoBehaviour's script file, and `SwShape`, `SwButton`, `PlateInput` and `SwHitArea` shared one file.
   - **Fix:** one file per MonoBehaviour, and CanvasRenderers added explicitly. The player was never affected.
4. **Lifecycle labels overlapped** (first screenshots). Fixed with text-sized cells.
5. **The lint caught a bare "offset"** ("The nudges and offset are unchanged"). "offset" is also a hidden-condition label, so the string now reads "the commanded offset" everywhere.
6. **The developer panel covered the plate's right edge.** The on-screen pixel check found it (max |diff| 218). The panel now always sits right of the plate, on an opaque backing that absorbs clicks, so a developer click can never also reach the participant control underneath.
7. **A scripted wait loop without a timeout** hung one developer-mode run. It is now bounded. The first `view_frames.csv` row could also be stamped 0; fixed.
8. **C09 (environmental, pre-existing check):** the laptop rebooted on 10 Nov, so the per-boot clock reference was stale ("made in another boot session"). The old reference is preserved and it was regenerated with the established `Tools/make_clock_reference.py`; C09 passes. Evidence: `unity/Phase2Client/test_results/c09_boot_session_20261111/`.
9. **R3 recurred once:** about 18 s of FFmpeg start-up on the first launch of a freshly built player, consistent with first-load scanning of new DLLs. It has not been seen on later launches. The start screen and `video_ready` gating mean it delays the session start only.

**Also noted (my error):** while trying to screenshot the developer panel, an operating-system screen grab captured the user's desktop instead of the application. The image was deleted at once. It was never sent anywhere or used, and the documented screenshots are all the application's own in-process captures.

---

## 9. Known limitations and unresolved decisions

**Limitations:**
1. **The video does not react to nudges or Retry.** Camera A is a fixed recording and Camera B is synthetic. Movement feedback is only the lifecycle, status line, plan diagram and offset. In the real cell, participants would see the element move. This matters for any pilot that measures correction behaviour.
2. **Camera A runs only about 20 s** (R4, accepted for S3). Most of a session shows Camera A as *Video unavailable*. Camera B runs about 40 s, then is also unavailable.
3. **Pixel-exact only at 1920 × 1080.** At other screen sizes the whole stage scales uniformly, so the plate is resampled. Camera B is always fitted at 0.9625.
4. **An Unconfirmed request with a lost original stays Unconfirmed** until a snapshot or decision close (S1 interpretation 6). There is no experimenter resolution tool yet; a `drop` fault would leave the participant waiting. The developer panel deliberately offers only delayed receipt.
5. **The developer panel is IMGUI,** for development only. It is not an experimenter console.
6. **`verify_s3_run.py` verifies S3 runs.** It is not the S4 log checker; there are no corrupted-log negative tests.
7. **The participant-text lint is a pattern list,** not a semantic review. The participant texts of each run are saved for human review (`participant_texts.txt`).
8. **Frame-time figures are indicative** (60 Hz, one laptop, two replays), not a formal M1.8 run.
9. **Hover is logged for every control,** not only the AI2 keys, which adds log volume.
10. **The model is engine-free and ready for XR reuse,** but the uGUI layout is screen-space only. No world-space or Quest work has been done.

**Decisions for you:**

| # | Decision | My recommendation |
|---|---|---|
| S3-1 | Keep the participant **Begin** screen, or let the experimenter start the trial? | Keep it for the prototype. For the study, an experimenter start from the console |
| S3-2 | The **"SIMULATION · RECORDED VIDEO"** tag in the strip (`-s3NoSimTag` hides it) | Keep it for all simulated sessions, including pilots |
| S3-3 | **Video that reflects simulated corrections** (for example a synthetic Camera A scene whose element moves with the commanded offset), and/or a longer real Camera A recording (R4) | Needed before any pilot of nudging behaviour |
| S3-4 | Video thresholds: interrupted after 500 ms without a new image (D8, as approved); "unavailable" once the receiver has ended | Confirm. For live streams, "unavailable" would need a time rule (for example 5 s) |
| S3-5 | Hover logging scope | Keep it for all controls during development; restrict it later if the volume matters |
| S3-6 | Participant display: 1920 × 1080 at 100 % scaling, for pixel-exact Camera A | Confirm the lab monitor. This links to D6 (angular size against resolution) |
| S3-7 | The S2 harness timing defect (§8 item 2) | Fix it in the harness when convenient. It is not used in sessions |

**Still open from earlier stages:** D6, D7, D9, D13 and D14–D17 (AIML/CRATER commissioning: what a nudge physically moves, real latencies, achieved against commanded, per-nudge release). The draft AIML questions remain unsent. There is also the university licensing review before any distribution.

---

## 10. Changed files and suggested checkpoint

**`unity/Phase2Client` (committed 12 Nov 2026 as `e418f62`):**
- **Modified:**
  - `Assets/Phase2/Experiment/Unity/CameraFeeds.cs` (the additive `FitMargin` field);
  - `ThirdParty/README.md` (font and TMP provenance).
- **New:**
  - `Assets/Phase2/SiteWindow/**`: model, UI, session, script, shader, fonts with licences, tests;
  - `Assets/TextMesh Pro/**`: TMP essentials;
  - `Assets/Phase2/Scenes/S3_SiteWindow.unity`;
  - `Assets/Phase2/Editor/S3Build.cs`;
  - `Assets/Phase2/Experiment/Scenarios/s3_walkthrough.json` and `s3_script.json`;
  - `Tools/run_site_window.ps1` and `Tools/verify_s3_run.py`;
  - `.meta` files for each.
- **Restored, not changed:** `M1_WindowsReception.unity` and `S2_TwoCamera.unity`. The M1 and S2 build scripts regenerate them with new object IDs; they were reset to the committed versions.
- **Unity README** updated (S3 section).

**Workspace (not in Git):**
- this report and `docs/plans/Phase2_Task07_S3_screenshots/`;
- the root `README.md`;
- the camera checkpoint §13.21 and its START HERE pointer.

**Suggested checkpoint after your review:**
```
git add -A
git commit -m "Task 07 S3: Site Window Windows participant interface (uGUI/TMP, IBM Plex); scripted verification; regression baseline"
```

---

## 11. Next steps (each needs your approval)

1. **Your review of the prototype** (§1). Interface changes would be addressed as S3 revisions.
2. Decisions S3-1 to S3-7.
3. **S4** (not started): session runner and the log checker with corrupted-log tests.
4. Later, separately: the Quest 3 translation, and commissioning with CRATER/AIML.

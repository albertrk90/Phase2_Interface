# Task 07 S3.1: revised placement, recovery and correction workflow (implementation and results)

**Status: S3.1 accepted by the researcher as the functional baseline (12 Nov 2026) and committed: `b5722b82ef79bfb0748a6d29a4fde30a7a381f24` (`b5722b8`, local `master`, no remote; 25 files).** Provisional decisions C1–C7 are in §7. S4, Quest, digital twin, machine vision and robot integration have not been started.

Offline only. Simulated backend, recorded or synthetic video, no hardware, cameras, MediaMTX, COROL or network.

**Basis:**
- the S3.1 brief (12 Nov 2026);
- the accepted S3 baseline, committed as **`e418f620663e5cf7c84fa37127758d12bf11a02d`**;
- the specification written first: [Revised CONOPS and state-machine changes](Phase2_Task07_S3_1_Revised_CONOPS.md).

> **Simulation only.** Recovery, facilitator involvement, nudges, placement, release, settling and every timing are simulated placeholders.
> - **Not approved values:** steps, limits (±15 mm, ±5°, 12 nudges, 3 recoveries) and the rotational axis are not approved physical values.
> - **Video:** the recorded video does not show any of these operations.
> - **`development_override`:** accepts motion requests without live video, so the short recordings can be used. It is a development facility, **not a permission for blind physical corrections**.

---

## 1. Git checkpoint of S3

| Item | Value |
|---|---|
| Commit | `e418f620663e5cf7c84fa37127758d12bf11a02d` (`e418f62`) on `master`; local only, no remote |
| Message | Task 07 S3: Site Window Windows participant interface; scripted verification; regression baseline |
| Content | 143 files: S3 source, scenarios, tests, launcher, verifier, IBM Plex fonts with their OFL licences, TMP essential resources |
| Excluded by the existing `.gitignore` | `Builds/`, `test_results/` (raw evidence), `Library/`, FFmpeg binaries. No personal data |

---

## 2. How to try S3.1

**The build:** `unity/Phase2Client/Builds/S3/SiteWindow.exe` (rebuilt 12 Nov). Launch from `unity/Phase2Client`.

| Goal | Command |
|---|---|
| The revised workflow (the default) | Double-click the exe, or `powershell -ExecutionPolicy Bypass -File Tools\run_site_window.ps1` (add `-Monitor 2` for the 1080p monitor, `-Windowed` for a window) |
| With developer tools | add `-Dev`. The released-workflow buttons arm the next request's outcome: facilitator review, assistance or rejection; failed recovery; failed or uncertain placement. The panel also has pause, video freeze and link loss. F2 hides it |
| S3.1 scripted verification, with screenshots | `... run_site_window.ps1 -Script31 -Monitor 2`, then `..\..\streaming_poc\.venv\Scripts\python.exe -I Tools\verify_s3_run.py <run folder>` |
| The S3 (held-element) verification, kept as a regression | `... run_site_window.ps1 -Script -Monitor 2` |

**What to try** (`s31_walkthrough.json`: four elements, primary camera A, A, B, B):
1. **Begin.** The robot places, releases and retreats. The status reads *Element released · holding for your decision*; Allow, Inspect and Intervene are available.
2. **Inspect, then Intervene.** The Adjust wing shows *Element released* and **Recover element…**. The nudge pad and rotation are greyed out: "Nudges are available once the element is held at the adjustment position."
3. **Recover element…** asks for a confirmation that names your view. The lifecycle then shows *Sent · Received · Accepted · Recovering · Held*. The 2nd recovery of the session is reviewed by the simulated facilitator: *Waiting for the facilitator*, then a *Review* stage.
4. **Held for adjustment.** Allow is shown locked ("Allow becomes available after Place and release."). Nudge along or across the rail (1, 2 or 5 mm) and rotate (0.5, 1 or 2°), one request at a time.
5. **Place and release…** (confirmed) shows *Placing* and then *Released*. The step card reads *Attempt 1 · placement 2*. You reassess the result, and may Allow, Inspect or Intervene again.
6. **Retry placement…** (held element only, confirmed) discards your adjustments and repeats the standard placement as a new attempt.

---

## 3. What changed

**Architecture:** the S1–S3 workflow is kept intact as `held_element_v1`, the default for old scenarios. The revised workflow `released_recovery_v1` is selected by the scenario, and the interactive build defaults to it. Every S1, S2 and S3 test therefore remains a valid regression.

| Layer | Change |
|---|---|
| **Schema v1.2** (`Experiment/Core/Messages.cs`) | New kinds `recover`, `place_release` and `repeat_placement`; stages `facilitator_review` and `facilitator_assist`; axis `rotation` (`step_deg`; `cumulative_commanded_deg`); a new **`element_state`** message; optional `workflow`, `max_recoveries`, `motion_video_policy`, `recoveries_remaining` and snapshot fields. **Strict allow-listing is kept; all additions are optional,** so old-workflow messages are unchanged apart from the version string |
| **Client machine** (`SupervisorMachine.cs`) | Gating on the backend's element state: Allow only when `released`; Recover only when `released` and within the allowance; nudges, Place and release, and Retry only when `held`; nothing while `uncertain`. Also: confirmations for the new kinds; rotation nudges and steps; the `require_live` motion guidance; facilitator timeouts (120 s). New records: `element_state`, `secure_grasp_confirmed`, `reassessment_begin`, `reassessment_first_action`, `choice{intervene}` and **`cdp_summary`** (§5) |
| **Simulated backend** (`SimulatedBackend.cs`, `SimInfrastructure.cs`) | One construction decision point per element: placement → release → `element_state: released` (cycle 1). Recovery with an optional facilitator review, approval or rejection, and assistance; secure grasp and lift; translation and rotation nudges validated against the commanded cumulative; Place and release; Retry from held (reset only once the new attempt has started); uncertain outcomes resolved by the simulated facilitator; backend checks of the element-state prerequisites and the video policy. **Hidden ground truth** (prescribed variation, architecture settle model, re-grasp error, resulting pose error) is logged only in the backend (`placement_result`, `recovery_result`, `nudge_result`) |
| **Participant model** (`SiteWindowModelReleased.cs`, `ParticipantStrings.cs`) | Applied after the S3 presentation, overriding only what differs: status vocabulary; Allow shown locked unless released; the Adjust wing for each element state; lifecycles for recovery (with *Review* / *Assist* when the facilitator is involved) and placement; neutral failure wording; *Attempt n · placement c*. **The old-workflow presentation is untouched** |
| **Interface** (`SiteWindowUi.cs`, `S3Session.cs`) | A minimally revised Adjust wing: element-state title, **Recover element…** / **Place and release…**, rotation step and *Rotate −/+*, a 2 × 2 offset block (along, across, rotation, nudges left), Retry with its own description. Developer tools for the facilitator and failures. Visual polish is deferred, as agreed |
| **Scenarios** | `s31_walkthrough.json` (interactive default) and `s31_script.json` (deterministic outcomes). Both have balanced primaries and a clean validator |
| **Verification tools** | `S31Script.cs` (39 checks in the player; 38 in batch mode, without the on-screen check); a new PlayMode test; `verify_s3_run.py` gains released-workflow rules (Allow only when released; nudges and placement only when held; recovery only when released; one `cdp_summary` per closure with the time partition summing exactly; secure grasp logged) |

**Retry, as proposed and implemented (CONOPS §6, option B):** Retry exists only for a held element. It discards the commanded adjustments and repeats the programmed placement as attempt + 1. Whether that repeats the prescribed variation is a scenario setting (`retry_variation`, default `same`). This needs your decision (C1).

---

## 4. Verification

### 4.1 Automated tests (Unity 6000.3.28f1)

| Suite | Result |
|---|---|
| **EditMode, all** | **146 / 146**: compatibility and receiver 50/50; S1/S2 59/59 plus **13 new released-workflow tests**; Site Window 17/17 plus **7 new released-presentation tests** |
| **PlayMode, all** | **4 / 4**: M1 replay, S2 two-camera, S3 scripted session (held-element) and **S3.1 scripted session** (released) |

**The 13 released-workflow tests (`ReleasedWorkflowTests`) cover:**
- the initial release (and that old scenarios have no workflow key and no recovery);
- the gating, **enforced by the backend for raw requests that bypass the client**;
- the full sequence (Inspect → recover → translation and rotation → Place and release → reassessment → repeated intervention → Allow), with the view kept throughout;
- facilitator review, assistance and rejection, with separate durations;
- unsuccessful recovery; uncertain state and its resolution; a placement that does not complete;
- Retry from held (a failed Retry resets nothing; a reset only when the new attempt starts);
- rotation bounds (guidance and backend) and offered steps only;
- the video policy (`require_live` refuses motion while Allow stays available; the override logs);
- link loss during recovery (the snapshot restores the state); pause during placement;
- a **leak test** over hidden conditions, prescribed variations, architecture and settling: the client stream and its timing are identical;
- the **firewall** and determinism.

**The 7 presentation tests** cover the released and held screens, confirmations sharing one structure, the facilitator lifecycle, the uncertain state, the video-required presentation, and a presentation-level leak test with the participant-text lint.

### 4.2 Scripted sessions in the Windows player (1920 × 1080)

| Run | Workflow | Checks | `verify_s3_run.py` |
|---|---|---|---|
| `ai2_s3_20261112_133732_win64player` | **released (S3.1)** | **39 / 39** | **OVERALL PASS**: oracle replay of both receivers; all view, S3 and S3.1 rules |
| `ai2_s3_20261112_133821_win64player` | held (S3 regression) | 63 / 63 | OVERALL PASS |
| `ai2_s3_20261112_134044_editor` / `134128_editor` (PlayMode) | released / held | all | OVERALL PASS |

- **On-screen pixel check:** 953,260 px, max |diff| 0 at 1× in the released workflow too.

**The S3.1 script follows the brief's sequence:**
1. initial placement and release;
2. inspection (Overview camera at 2×);
3. Intervene with Inspect kept; a nudge refused before the secure grasp;
4. recovery confirmation naming the view; facilitator review; recovery; facilitator assistance; secure grasp; adjustment enabled; Allow refused while held;
5. a translation nudge and a rotation nudge (*Moving: +1° rotation*);
6. Place and release, then reassessment in the same decision point (*placement 2*, the view kept);
7. an unsuccessful recovery (neutral wording), then a successful one (allowance exhausted);
8. Place and release not completed (still held), then completed (*placement 3*);
9. final Allow from the inspected view (commit context `element_state: released`), then primary at 1×;
10. element 2: a Retry that fails (nothing reset), then a Retry with a new attempt and a fresh origin;
11. element 3: an uncertain placement that locks Allow and motion, resolved by the facilitator;
12. element 4: Allow directly; trial complete.

**Per-decision-point time accounting** (`cdp_summary`, from the player run). The four parts sum exactly to the duration:

| CDP | Duration | Participant decision | Technical execution | Facilitator | Cycles | Requests |
|---|---|---|---|---|---|---|
| 1 | 21.8 s | 1.9 s | 15.9 s | 4.0 s | 3 | 3 recover (2 completed), 3 place (2 completed), 2 translation + 1 rotation nudge |
| 2 | 6.9 s | 0.6 s | 6.3 s | 0 | 2 | 1 recover, 2 repeat placement |
| 3 | 7.0 s | 0.3 s | 4.2 s | 2.5 s (uncertain state) | 2 | 1 recover, 1 place (uncertain) |

### 4.3 Regression (nothing validated was changed)

| Suite | Result |
|---|---|
| M1 PlayMode replay + `verify_unity_run.py` | PASS (oracle 62,212 ops) |
| S2 PlayMode two-camera + `verify_s2_run.py` | PASS |
| **M1 Windows player** (rebuilt): `replay_A`; `camera_E1_A` | **2 / 2 PASS**, including the pixel-exact `display_bit_exact_and_crop` |
| **S2 Windows player** (rebuilt; uses the changed S1 core) | **2 / 2 OVERALL PASS** |
| S3 scripted session (held-element workflow) | 63 / 63; verify PASS |

- **Thresholds:** no acceptance threshold was changed.
- **C09:** the laptop rebooted again overnight. The per-boot clock reference was preserved and regenerated with the established tool: `test_results/c09_boot_session_20261112/`.
- **Regenerated scenes:** the scene files that the build scripts regenerate (`M1_WindowsReception`, `S2_TwoCamera`, `S3_SiteWindow`) were restored to their committed versions.

---

## 5. Logging (brief §8 mapping)

| Requirement | Records |
|---|---|
| Initial AI2 choice; confirmed intervention request | `choice{inspect\|intervene\|allow\|recover\|place_release\|repeat_placement}` then `commit{…}`; `cdp_summary.first_action` and `first_action_latency_ms` |
| Recovery request and acknowledgement; facilitator involvement; execution and outcome | `request_sent / _received / _facilitator_review / _accepted / _rejected / _started / _facilitator_assist / _completed / _failed / _ready`; `request_summary.durations.facilitator_review_ms / facilitator_assist_ms / execution_ms`. The backend also logs `facilitator_action` |
| Secure grasp | `element_state{held, cause: secure_grasp_confirmed}` and `secure_grasp_confirmed` |
| Translation and rotation nudges; commanded against achieved | Nudge events with axis and `step_mm` or `step_deg`; reported cumulative mm and deg. **Backend only:** `nudge_result` (commanded and achieved), `placement_result` (programmed variation, commanded correction, in-hand error, placed error, seated, released pose error), `recovery_result` |
| Place and release; reassessment | `request_*` for `place_release`; `element_state{released}`; `reassessment_begin{cycle}`; `reassessment_first_action{latency_ms}` |
| Closure; separated times | `decision_close` plus `cdp_summary` (participant decision, technical execution, facilitator and paused time; cycles; requests by kind and axis) |

**Traceability:** every client record carries the CDP token, `cycle`, `attempt`, `element_state`, the view and both displayed frames, so all cycles of a decision point stay traceable to it. `cdp_summary` is also emitted in the held-element workflow (additive; that workflow's other records are unchanged).

---

## 6. Screenshots (final build, 1920 × 1080)

In [`Phase2_Task07_S3_1_screenshots/`](Phase2_Task07_S3_1_screenshots/):

| # | State |
|---|---|
| `31_01` | Initial placement released: the decision view |
| `31_02` | Inspect + Intervene: element released, recovery offered, pad unavailable |
| `31_03` | Recovery confirmation (names the view) |
| `31_04` | Facilitator review |
| `31_05` | Facilitator assisting recovery |
| `31_06` | Held for adjustment: Allow locked, nudges and rotation available |
| `31_07` | Rotation nudge moving |
| `31_08` | Place and release in progress |
| `31_09` | Reassessment (placement 2) |
| `31_10` | Recovery not completed (neutral) |
| `31_11` | Retry confirmation (held element) |
| `31_12` | Element state uncertain (desk locked, facilitator resolving) |
| `31_13` | Trial complete |

---

## 7. Known limitations and open decisions

**Limitations:**
1. **The video shows none of the simulated operations** (fixed recording; synthetic Camera B). Camera A ends after about 20 s.
2. **The settle model is a placeholder** (capture tolerance and slide fraction). It exists only to make hidden ground truth loggable; it is not physics and not a model of either architecture.
3. **One rotational axis** (`rotation`, a convention-neutral label). Multiple rotational axes would need a schema extension.
4. **The facilitator is simulated** by scenario rules and developer buttons. There is no facilitator console or backend control mechanism yet (beyond S3.1).
5. **The client's video state stands in for the backend's video health** in the `require_live` check. The live backend must use its own source.
6. **The Adjust wing is dense.** The recovery lifecycle labels shrink to about 11 px when the facilitator is involved. Visual polish is deferred, as agreed.
7. **The facilitator-assist duration includes the predefined lift,** which follows assistance before completion. This is documented in the tests.
8. **Unconfirmed requests with a lost original** still have no resolution tool (S1 interpretation 6).

**Researcher decisions (12 Nov 2026; provisional).** S3.1 is accepted as the functional baseline. Full wording is in [CONOPS §11](Phase2_Task07_S3_1_Revised_CONOPS.md).

| # | Decision | Implementation |
|---|---|---|
| C1 | Retry stays available after recovery; it repeats the original programmed placement, **including its prescribed variation**, and discards adjustments | As implemented (`retry_variation: same`) |
| C2 | Corrections stay relative to the programmed placement pose. Commissioning must establish the repeatability of the recovered tool-to-element relationship before real operation | As implemented; commissioning item |
| C3 | Rotational axes, signs, steps and bounds stay provisional | Unchanged |
| C4 | Facilitator-assisted recovery is the baseline physical recovery strategy | Modelled |
| C5 | Three recoveries per decision point, configurable, not fixed in code | `max_recoveries` (scenario; default 3) |
| C6 | Real operation needs agreed visual-access, backend-state and safety prerequisites; the development override is **not** permission for blind physical operation | Override remains simulation-only |
| C7 | Preserve placement (cycle) and attempt identifiers in the logs; participant presentation may be simplified later | Logged on every record |

**Leak-test scope (clarified 12 Nov 2026).** The hidden-condition leak tests apply to **unintended interface cues and supplementary information**: system-generated messages, wording, availability and timing. Legitimate differences in the **observed physical construction state** are the essential experimental stimuli and are not information leaks. The simulation tests can be strict only because the recorded video does not change with the hidden state.

**UI refinements deferred** (not implemented, by instruction):
- confirmation text overlap in the recovery and Retry confirmations;
- the dense Adjust panel;
- small stage labels;
- progressive disclosure of the recovery, adjustment and placement controls;
- possible simplification of the participant-visible action history.

---

## 8. Changed files

**`unity/Phase2Client` (committed 12 Nov 2026 as `b5722b8`):**
- **Modified:**
  - `Experiment/Core/Messages.cs` and `SupervisorMachine.cs`;
  - `Experiment/Sim/SimInfrastructure.cs` and `SimulatedBackend.cs`;
  - `SiteWindow/Model/ParticipantStrings.cs` and `SiteWindowModel.cs` (partial; `RecordLine` reused);
  - `SiteWindow/Unity/SiteWindowUi.cs`, `S3Session.cs` and `S3Script.cs` (lint pattern);
  - `SiteWindow/Tests/PlayMode/S3SiteWindowPlayModeTests.cs`;
  - `Tools/run_site_window.ps1` and `Tools/verify_s3_run.py`;
  - `README.md`.
- **New:**
  - `Experiment/Scenarios/s31_walkthrough.json` and `s31_script.json`;
  - `Experiment/Tests/Editor/ReleasedWorkflowTests.cs`;
  - `SiteWindow/Model/SiteWindowModelReleased.cs`;
  - `SiteWindow/Tests/Editor/SiteWindowReleasedModelTests.cs`;
  - `SiteWindow/Unity/S31Script.cs`;
  - their `.meta` files.

**Workspace (not in Git):**
- this report and the screenshots;
- [the CONOPS](Phase2_Task07_S3_1_Revised_CONOPS.md);
- S3 report §10 (commit recorded);
- the root README;
- checkpoint §13.21 (S3 commit) and §13.22, with the START HERE pointer.

**Checkpoint:** committed as `b5722b82ef79bfb0748a6d29a4fde30a7a381f24` with the message "Task 07 S3.1: released-element workflow (recovery, facilitator, rotation, place and release); schema v1.2; regression baseline". Builds, `test_results/`, FFmpeg binaries, `Library/`, `Logs/`, `UserSettings/` and Python caches are excluded by the existing `.gitignore`. Nothing was pushed.

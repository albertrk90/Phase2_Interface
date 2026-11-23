# Task 07 S4.1: experimental configuration and session orchestration, implementation results

**Status (12 Nov 2026):** implemented and verified; simulated backend and offline video only, no hardware.

**Accepted** by the researcher after manual review as the **simulated functional baseline**, and **committed as `6c7e33c9b4ddeb920a9a056a3d169155c4cc40eb`** (local `master`, not pushed; §9).
- **Deferred:** minor UI design issues, to the later polish stage.
- **Still open:** the methodological questions (specification §7, D1–D10), the demonstration parameters and the commissioning limitations (§8).
- **S4.2 has not started.**

**Specification:** [S4.1 experimental development specification](Phase2_Task07_S4_1_Experimental_Development_Specification.md). It records:
- the agreed design, the provisional parameters, the commissioning items and the instrument or scoring items;
- the discrepancies D1–D10, including the **V17 methodology corrections** from the researcher's message of 12 Nov.

**Starting point:** S3.1 `b5722b82ef79bfb0748a6d29a4fde30a7a381f24` on `master`; the working tree was clean before work began.

---

## 1. What was built

All S4.1 code lives in `unity/Phase2Client/`.

| Area | Where | Summary |
|---|---|---|
| **Experiment definition** | `Assets/Phase2/Experiment/Protocols/phase2_protocol_demo.json` (reference 4 × 3 structure), `phase2_s41_interactive_demo.json` (short demonstration); `Experiment/Session/ExperimentDefinition.cs` | Versioned JSON (`ai2-experiment-v1`), editable without recompiling. Carries the validation rules (spec §2), a SHA-256 content ID and the deterministic session plan. **All physical, timing and instrument values are labelled demonstration placeholders** |
| **Allocation** | `SessionStore.cs` (`AllocationRegister`) | Balanced cyclic allocation by enrolment ordinal over W1–W4, saved before the measured session and never regenerated. Tested at N = 8, 6, **20 (5 per sequence)** and **24 (6 per sequence)**; no maximum |
| **Records** | `SessionStore.cs` | One directory per session, never overwritten. It holds the manifest, the effective definition, `session_events.jsonl` (append-only, all linkage IDs on every record), the researcher-only `ground_truth.jsonl`, an atomic `checkpoint.json`, and `runs/run_NN/<trial>/` raw client, backend and wire logs |
| **Session runner** | `SessionRunner.cs` | The full lifecycle (spec §3.3) with role-scoped requirements, facilitator actions, interruptions, validity, replacement, discontinuation, restart reconciliation, closure integrity checks and the participant-safe `ParticipantPhase` |
| **Trial runtime** | `TrialRuntime.cs` | A fresh backend per trial (the common baseline); the formal-CDP sequence of observation, SAGAT freeze and restore, and decision-ready; the first-commitment lock and confidence; unscheduled and merged episodes; pathway capture; the per-trial wire leak scan |
| **Facilitator authority** | `SessionStore.cs` (`Authority`) | Role permissions for Facilitator A (CRATER), Facilitator B (North Terrace) and both (spec §3.16). They do not depend on the console that presents them |
| **Backend (simulated)** | `Experiment/Sim/SimulatedBackendS4.cs` (new partial) and hooks in `SimulatedBackend.cs` | Autonomous construction with hidden CDP roles; `supervise` holding at the next safe state; the formal-CDP hold; console facilitator control (review, grasp, uncertain state); **scoped adjustment-episode authorisation with expiry**; construction-state carry-over (demonstration); researcher-only ground-truth records |
| **Schema v1.3** | `Experiment/Core/Messages.cs` | Optional additions only: the `supervise` request (with `mode`, no token); `decision_open.origin` and `supervision_cmd_id`; `element_state.adjustment`; snapshot fields |
| **Client machine** | `Experiment/Core/SupervisorMachine.cs` | Opt-in hooks: an assessment hold; the `Committed` lock with `ReleaseCommit` and `CancelCommit`; unscheduled requests; the assessment and confidence time buckets |
| **Simulation support** | `Experiment/Session/SessionSimulation.cs` | The simulated trial host, automatic facilitators, a scripted participant that never reads hidden state, and `RunFull`, the accelerated full session |
| **Participant presentation** | `SiteWindow/Model/SessionStrings.cs`, `SiteWindowModelSession.cs`; `SiteWindow/Unity/SiteWindowUiSession.cs` | Session screens; hold keys; the observation lock; "held at your request"; the probe screen (plate camera disabled); the confidence prompt over the Desk; the waiting-for-authorisation pad; the practice tag; the XR-substitution label |
| **Unity host and console** | `SiteWindow/Unity/S4SessionMode.cs` (a partial of `S3Session`) | The Unity trial host (receivers restarted at every trial reset), session screens, the docked **facilitator console** (IMGUI, roles A and B, automatic facilitators toggled per role; F9 hides it), resume, and the accelerated run |
| **Build and launcher** | `Editor/S4Build.cs`, scene `Scenes/S4_Session.unity`, `Tools/run_session.ps1` | A separate player, `Builds/S4/SiteWindowSession.exe`, so the S3 build is unchanged |
| **Verification** | `Experiment/Session/Tests/Editor/` (34 tests), `SiteWindow/Tests/Editor/SessionScreenTests.cs`, `SiteWindow/Unity/S41Script.cs` plus the PlayMode test, `Tools/verify_s4_session.py` | §5 |

**Edits to existing validated code** are all additive and opt-in:
- `SimHarness` accepts a shared scheduler;
- `SiteWindowUi` became partial, with session overlays and a reserved console width;
- the S3 frame-render body became `RenderSiteWindow()`;
- session-mode branches in `S3Session`, active only with `-s4`.

The M1 receivers, S2 feeds and video view, and every acceptance threshold are unchanged.

---

## 2. Launch and review

```powershell
cd C:\Users\a1920234\Documents\Phase2_Interface\unity\Phase2Client
$U = "C:\Program Files\Unity\Hub\Editor\6000.3.28f1\Editor\Unity.exe"
# build (batch, ~2 min)
& $U -batchmode -quit -projectPath . -buildTarget Win64 -executeMethod Phase2.EditorTools.S4Build.BuildPlayer -logFile test_results\logs\s4_build.log
```

| Mode | Command | What it is |
|---|---|---|
| **Interactive demonstration** (about 5 min) | `powershell -ExecutionPolicy Bypass -File Tools\run_session.ps1` | 1920 × 1080 window with the facilitator console on the right. Automatic facilitators are on (1.5 s delay); switch them off per role in the console. The participant uses only Continue and the Site Window |
| Manual facilitators | `… run_session.ps1 -Manual` | Every Facilitator A and B action goes through the console buttons |
| Resume an interrupted session | `… run_session.ps1 -Resume -Participant P9NN` | Reopens the saved session; Reconciliation comes first |
| Full protocol, interactive | `… run_session.ps1 -Full` | The 4 × 3 reference structure (long) |
| **Scripted UI verification** | `… run_session.ps1 -Script` | The whole demonstration through real clicks; exit 0 means every check passed; then the verifier runs |
| **Accelerated full session** | `… run_session.ps1 -Accelerated` | The reference protocol in virtual time (about 8 s wall-clock), then `verify_s4_session.py --full`. Batch alternative: `-executeMethod Phase2.EditorTools.S4Build.RunAccelerated` |

**Things to look at in the interactive demonstration:**
1. **The session screens:** welcome, introduction, training, the 2D practice trial, the XR briefing (labelled as a development substitute), the practical check, and the block intro.
2. **During autonomous construction:** Inspect and Intervene read *"Ask the robot to hold…"*. Clicking one gives *"Hold requested · the robot will stop at the next safe point"*, then *"held at your request"*.
3. **At a formal decision point:** *"Decision point · observe the placement"*, with the keys locked. At the probe decision point, the question screen replaces the Site Window (no imagery); afterwards the view returns.
4. **Confirming Allow or Recover** brings up the confidence prompt over the Desk. Nothing is sent until you answer.
5. **The adjustment flow:**
   1. Request recovery.
   2. Facilitator A reviews it, confirms the secure grasp and authorises the adjustment (automatically, or with the console buttons). Until then the pad reads *"Nudges become available once the facilitator has authorised this adjustment"*.
   3. Nudge, then Place and release, then reassess, then Allow.
6. **Console:**
   - pending requirements by role;
   - Facilitator A's tasks;
   - pause, technical failure, terminate, cancel commitment, revoke adjustment, discontinue;
   - interruption readiness (A and B) and resume;
   - the current episode's hidden location, role and probe flag, which are shown only here.

**Evidence:**
- sessions: `test_results\s4_sessions_demo\S4-P9NN-01\`;
- presentation log: `test_results\ai2_s4_<stamp>_win64player\`;
- check any session with `..\..\streaming_poc\.venv\Scripts\python.exe -I Tools\verify_s4_session.py <session_dir>`.

**Video note:** both receivers restart at each trial reset. Camera A's recording is about 20 s and is never looped within a trial, so later placements in a trial may show *Video unavailable*. Motion is still allowed under `development_override`, which is simulation-only.

---

## 3. Design choices made within the brief

| Topic | Choice | Reason |
|---|---|---|
| Where the schedule lives | The session runner (researcher side) holds the plan. The backend holds the hidden per-element roles. The participant presentation receives only `ParticipantPhase` codes and the machine state | Keeps the separation in brief §5; the lint and leak tests check it |
| Decision-ready at non-probe CDPs | The end of the same observation interval used at probe CDPs | No timing or wording difference reveals which CDP carries the probe (spec D2) |
| Overlap with a scheduled CDP | Merged into one formal episode; the probe proceeds | Brief §11, so there is no duplicate episode; both identities are kept (spec D3) |
| Unscheduled request modes | Inspect starts inspection at the hold; Intervene opens the Adjust panel | The request expresses the participant's intent; both are logged with their cause |
| Restoration after the probe | The Site Window itself is shown, locked (*Restoring the view*), until the plate is verified to show the primary camera at 1× | First implemented as a full-stage screen, which deadlocked with the verification (found by the independent verifier, §6) |
| Adjustment authorisation scope | Nudges only. Place and release, and Retry, need the secure grasp (held state) as in S3.1 | They are predefined placements, not participant-directed adjustments; commissioning may change this [C] |
| Facilitator presentation | An IMGUI console docked in a reserved right strip of one window, with the stage fitted into the rest | No new processes or network; the permissions are independent of it (brief §14). Not a safety-rated control system |
| Replacement assignment | Automatic by rule when eligible (technical or procedural category, within the limits), or by Facilitator B | Never for participant performance; the original records are always kept |

---

## 4. Accelerated full session (reference protocol, virtual time)

**Run:** player `-s4Accelerated`. Session `test_results/s4_accelerated/20261112_165832_win64player/S4-P01-01`, participant P01, sequence W1 (A B D C).
- **Time:** 7.5 s wall-clock for about 10.9 virtual minutes. The simulation timings are placeholders, so a physical session will be much longer.
- **Integrity:** the runner's checks pass, and `verify_s4_session.py --full` passes 26/26.

**What the scripted session exercises:**
- **Training:** additional practice (the first competency outcome was "additional practice"), then competent; 2D and XR practice; refreshers.
- **Facilitator cancellation:** a locked commitment cancelled during training.
- **Unscheduled requests:**
  - an Intervene merged into the B1-T1 early probe CDP;
  - an Inspect that reaches the **inactive** early location of B1-T2;
  - an Inspect at an ordinary placement (B1-T3);
  - an Intervene at B3-T1.
- **Interruptions:**
  - a technical interruption **after** a commitment (B2-T1), resumed with flags;
  - a wellbeing pause during autonomous construction (B2-T2);
  - a backend failure **before** the commitment at B3-T2's second CDP: the trial is terminated, and replacement **B3-T2-R1** uses the equivalent scenario.
- **Restart:** a **simulated application crash** mid-B4-T1, then a reload from the saved records. Facilitator A reconciles the physical state and Facilitator B confirms readiness. B4-T1 becomes `terminated_restart` and replacement **B4-T1-R1** runs in `run_02`; B4-T1 is not replayed.

| Measure (completed measured trials) | Planned | Realised |
|---|---|---|
| Completed trial slots | 12 | 12 (10 original + 2 replacements) |
| Formal CDPs | 24 | 24 |
| Inactive locations | 12 | 12 (11 autonomous + 1 reached by an unscheduled hold, identity kept) |
| SAGAT probes (3 responses each) | 12 | 12 (per-architecture placeholder banks) |
| First-commitment confidence ratings | 24 | 24 |

Totals include the training trials and the partial, preserved records of the two terminated trials:
- 36 formal CDPs and 3 unscheduled episodes;
- 14 probe freezes;
- 37 first commitments and 33 confidence responses;
- 4 interruptions;
- 165 facilitator actions, with 0 refused.

**Example time partition** (a formal CDP, client clock):

| Part | Time |
|---|---|
| Duration | 5,240 ms |
| Participant decision | 592 ms |
| Technical execution | 48 ms |
| Assessment hold (observation) | 4,000 ms |
| Confidence | 600 ms |

The parts sum exactly to the duration. Decision-ready → first commitment was 616 ms.

---

## 5. Verification

### 5.1 Automated tests

| Suite | Result |
|---|---|
| **EditMode, all** | **181/181**: 146 existing plus 35 new. The new ones are 34 in `Phase2.Session.Tests` and 1 participant-presentation lint |
| **PlayMode, all** | **5/5**: M1 replay, S2 two-camera, S3, S3.1, and **S4.1 scripted demonstration** (24 named checks) |

The 24 verification items in the brief are each covered by at least one test:

| # | Item | Test(s) |
|---|---|---|
| 1 | Valid and invalid definitions | `Definitions_BothShippedProtocolsAreValid…`, `ContentId…`, `Invalid_…` (×2), `V17_…` (×2) |
| 2 | Williams sequences | `Williams_W1toW4_AreLatinAndCarryoverBalanced…` (also rejects a cyclic Latin square) |
| 3 | Stable allocation | `Allocation_BalancedCyclic…`, `V17_Allocation_FivePerSequenceAt20_SixAt24` |
| 4–7 | 4 × 3 structure; 2 active and 1 inactive; probe at an active CDP; balance | `Plan_FourBlocksOfThreeTrials…` (all four sequences), `T04_PlannedStructureRealised` |
| 8 | Training and competency first | `T08_…` |
| 9 | Baseline reset and readiness | `T09_…`, `Reset_WaitsForEachReadiness_AndRejectsTheWrongBaseline` |
| 10–11 | Persistence within a trial; no carry-over between trials | `T10_…` |
| 12 | Unscheduled Inspect and Intervene | `T12_…`, the S4.1 PlayMode hold checks |
| 13 | Scheduled/unscheduled overlap | `T13_OverlapMergedIntoFormalCdp_ProbeNotCancelled` |
| 14 | Recovery and adjustment workflow | `T14_…`, the PlayMode adjustment checks |
| 15 | Facilitator authority | `Authority_RolesAreScoped`, `Authority_WrongRoleRefusedAndLogged` |
| 16 | Authorisation and revocation | `FormalCdp_HoldProbeConfidence_AuthorisationScopedAndRevoked` (client and backend refusal; revoke; pause; release) |
| 17 | Probe hiding and restoration | `T17_…`, the focused test, the PlayMode `s41_probe_hides_imagery` / `s41_view_restored_after_probe` / `s41_view_restoration_verified_no_timeout` |
| 18 | Confidence before execution | `T18_…`, the focused test, PlayMode `s41_confidence_after_locked_commitment` |
| 19 | Distinct timing | `T19_TimingKeptSeparate` (complete, non-overlapping partition) |
| 20 | Interruptions, termination, replacement | `T20_…` |
| 21 | Partial and measure-level validity | `T21_…`, `Discontinuation_PreservesRecords_ClosesSession` |
| 22 | Persistence and restart | `T22_…`, `SessionStore_RefusesToOverwrite_ResumeUsesSavedDefinition` |
| 23 | Event linkage | `T23_EveryRecordLinked`, `T25_…` |
| 24 | No ground-truth leakage | `T24_…` (client logs and wire, both runs), `InactiveLocation_SameParticipantStreamAsOrdinaryPlacement` (identical messages **and** timing), `SessionPresentation_Lint…` |

### 5.2 Windows players

| Run | Result |
|---|---|
| **S4 player, scripted demonstration** (`ai2_s4_20261112_165954_win64player`, session `S4-P906-01`) | **24/24 checks**, exit 0; `verify_s4_session.py` **23/23**. 1920 × 1080, stage scale 1, 77 s |
| **S4 player, accelerated full session** | Completed; integrity pass; `verify_s4_session.py --full` **26/26** (§4) |
| S3 player, scripted (held-element workflow, rebuilt) | **63/63**; `verify_s3_run.py` OVERALL PASS (on-screen pixel checks pass) |
| S3.1 player, scripted (rebuilt) | **39/39**; `verify_s3_run.py` OVERALL PASS |
| S2 player, scripted ×2 (rebuilt; uses the changed S1 core) | **2/2 OVERALL PASS** |
| M1 player (rebuilt): `replay_A`, `camera_E1_A` | **2/2 OVERALL PASS** |

**Housekeeping:**
- No acceptance threshold was changed.
- The scenes that the build scripts regenerate (M1, S2, S3) were restored to their committed versions.
- `S4_Session.unity` is new.

Screenshots of the S4 player run are in [Phase2_Task07_S4_1_screenshots](Phase2_Task07_S4_1_screenshots/): welcome, onboarding, block intro, hold requested, held at request, XR substitution, observation, probe, confidence, and complete.

---

## 6. Problems found and fixed during S4.1

| Problem | Found by | Fix |
|---|---|---|
| `File.Replace` failed intermittently when the checkpoint was rewritten quickly | EditMode | `SessionStore.AtomicWrite`: retry, then an overwriting copy (the target always holds a complete file) |
| Supervise status messages carried no token, so the client rejected them and the request timed out as "unconfirmed" | Full-session test (missing acknowledgement times) | `StatusMsg` token optional for `supervise`; test T25 now also asserts no protocol errors or timeouts in any client log |
| Auto-facilitator actions scheduled before auto mode was switched off still fired; reconciliation could not progress with the restart interruption open | Focused tests | Role checked at fire time; reconciliation allowed with an open restart interruption |
| Ground-truth references from before a restart could not be verified | T25 | Reloaded from `ground_truth.jsonl` on resume |
| The block-intro screen took its interface from the previous (practice) trial, so the XR label was missing | PlayMode | The interface comes from the pending trial only during reset or the trial |
| **Probe restoration deadlock:** the full-stage "restoring" screen kept the plate hidden, so the view was never verified and every probe timed out (flagged) after 5 s | **`verify_s4_session.py`** on the scripted run | The restoring phase shows the locked Site Window; the new PlayMode check `s41_view_restoration_verified_no_timeout` |
| The pad showed nudges as available before Facilitator A's authorisation (refused by the machine and backend) | PlayMode | Pad disabled, with *"Nudges become available once the facilitator has authorised this adjustment"* |
| A failing S4.1 PlayMode test left its session screen over the next test (S3 "Begin" obstructed) | PlayMode | Tests clean up before asserting |
| Participant text: "hidden" in the probe note; placeholder SAGAT items named the architecture | Presentation lint | Reworded |

---

## 7. Methodology V17 corrections (researcher message, 12 Nov)

Applied in the definitions, the code and the tests:
- **Sample:** 20 analysable participants, up to 24 recruited; the reference allocation is 5 per sequence at N = 20 and 6 at N = 24; the 6–8 figure is superseded.
- **Survey B** is the single block-end instrument (8 items: 1 × 7-point depth and alignment access, 6 × Raw NASA-TLX, 1 × 7-point overall decision confidence). No other subjective SA or uncertainty instrument is configured.
- **Architecture-specific SAGAT banks** are supported and used per trial, with placeholder content only. No scoring.
- **The five architectural-state categories** (converging, tolerable residual, unresolved or ambiguous, consequential, obstructed or failed) are the ground-truth classification scheme. Physical acceptability and participant evidence availability are separate attributes; scenario labels are refused as classifications.
- **H2:** the first substantive Allow or Intervene commitment is the primary event, with correction and final acceptance recorded separately. Scoring is left to S4.2.
- **Input method:** V17 specifies speech recognition. The development implementation's manual controls do **not** resolve this; it is recorded as `input_method.formal_status: under_review`, and the validator warns.

---

## 8. Known limitations and outstanding decisions

**Limitations:**
- **Simulation only.** All physical values, tolerances, timings, scenarios, the settle and carry-over models, and the facilitator delays are demonstration placeholders. The physical safe-state model, assisted recovery, grasp verification, video prerequisites, baselines and resets, and clock alignment all need commissioning (spec §5).
- **XR is not implemented.** XR blocks run as a labelled Windows development substitution, flagged and never counted as XR exposure.
- **Placeholder instruments.** SAGAT banks, the confidence item and the competency item texts are placeholders. External instruments are completion records only; there is no survey platform.
- **Offline video is short.** Camera A is about 20 s per trial reset, so later placements in a trial show *Video unavailable* under `development_override`.
- **The facilitator console** is a single-machine demonstration panel (IMGUI), not a distributed administration tool. The participant and facilitators share one screen in the demonstration.
- **`inspect_during_observation`** is parsed but only the agreed default (`false`) is implemented (spec D2).
- **The content ID** uses the C# canonical JSON; the Python verifier does not recompute it.
- **Deferred:** the UI refinements from S3.1 (CONOPS §11) were not undertaken, as instructed.

**Outstanding decisions:** spec §7, D1–D10. In particular:
- D2: passive observation before the probe;
- D3: merging a hold request into a probe CDP;
- D5: the input method;
- D9: a cancelled first commitment.

---

## 9. Files changed (uncommitted) and recommended checkpoint

**In the Unity repository** (`git status`: 13 modified, 24 untracked entries, including `.meta` files and new folders).

**Modified:**
- Core and simulation: `Experiment/Core/Messages.cs`, `SupervisorMachine.cs`; `Experiment/Sim/SimInfrastructure.cs`, `SimulatedBackend.cs`;
- Site Window: `SiteWindow/Model/SiteWindowModel.cs`; `SiteWindow/Unity/S3Session.cs`, `SiteWindowUi.cs`;
- tests: `SiteWindow/Tests/PlayMode/S3SiteWindowPlayModeTests.cs`;
- four SiteWindow `.asmdef` files.

**New:**
- `Experiment/Session/`: definition, store, runner, trial runtime, simulation, the `.asmdef`, and tests (`Tests/Editor/`, 3 files plus the `.asmdef`);
- `Experiment/Protocols/`: the two definitions;
- `Experiment/Sim/SimulatedBackendS4.cs`;
- Site Window: `SiteWindow/Model/SessionStrings.cs`, `SiteWindowModelSession.cs`; `SiteWindow/Unity/S4SessionMode.cs`, `S41Script.cs`, `SiteWindowUiSession.cs`; `SiteWindow/Tests/Editor/SessionScreenTests.cs`;
- build: `Editor/S4Build.cs`, `Scenes/S4_Session.unity`;
- tools: `Tools/run_session.ps1`, `Tools/verify_s4_session.py`.

Also edited: the Unity `README.md`.

**Outside the repository:** this report and the specification, the screenshots folder, checkpoint §13.23, the START HERE pointer, and the root README.

**Excluded by the existing `.gitignore`:** `Builds/` (including `Builds/S4/`) and `test_results/`, which holds every session, accelerated run, scripted run and log.

**Recommended checkpoint, after review:**
```
Task 07 S4.1: experiment definition and session runner (Williams allocation, CDP scheduling, unscheduled supervision, facilitator roles, SAGAT/confidence hooks, interruptions, persistence); schema v1.3; regression baseline
```
**Committed (12 Nov 2026, after the researcher's acceptance) as `6c7e33c9b4ddeb920a9a056a3d169155c4cc40eb`**, with this message, on local `master` (not pushed).
- **The commit holds** 61 files: the S4.1 source, protocols, tests, scene, tools and the Unity README.
- **Excluded:** `Builds/`, `test_results/` and the downloaded binaries, as before.
- **After the commit:** the working tree is clean.
- **Not in the commit** (outside the nested repository): this report, the specification, the screenshots folder, the checkpoint and the root README.

S4.2 has not started.

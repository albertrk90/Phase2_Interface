# Task 07 S1: AI2 core state machine and simulated backend (implementation and results)

**Status: S1 complete (6 Nov 2026), awaiting approval for S2.** Offline only: simulated backend; no COROL, robot, network, camera or streaming activity. No Unity UI.

**Basis:**
- [Site Window design proposal, revision 2](Phase2_Task07_AI2_Interface_Design_Proposal.md), approved by the researcher on 6 Nov 2026;
- the researcher's additional decisions of the same day (§1).

> **Simulation only.** All acknowledgements, timings and results come from the in-process simulated backend. Receipt acknowledgement does not imply immediate physical motion. Real execution must be commissioned and validated separately with CRATER/AIML. The step sizes (1, 2 and 5 mm) and limits (±15 mm per axis, 12 nudges per decision point) are provisional simulation settings, not approved robot movement limits.

---

## 1. Researcher decisions (6 Nov 2026) and how S1 implements them

| # | Decision | Implementation | Verified by |
|---|---|---|---|
| 1 | For simulation, corrections occur while the robot **still holds** the element; provisional pending CRATER/AIML; no physical movement | `correction_model: "held_element_provisional"` in the nudge spec, the scenario and every backend `nudge_result`. "Motion" is a number on a virtual clock. AIML question 28 added | Scenario test; backend log fields |
| 2 | Show the **accepted cumulative commanded** correction (labelled commanded); never the measured achieved position; log commanded and achieved separately | Client messages carry only `cumulative_commanded_mm`. The backend logs `commanded_mm`, `achieved_mm`, `cumulative_commanded_mm` and `cumulative_achieved_mm` (`achieved_source: simulated`). The strict per-type key allow-list makes an "achieved" field unparseable on the client | `BackendParse_RejectsAnyUnlistedKey…`, `EveryClientBoundMessage_IsAllowListed…`, `Nudge_FailsDuringMotion…` |
| 3 | Retry = fresh attempt; reset the correction **only after the backend reports that the new attempt has begun**; a rejected or failed Retry resets nothing | The Retry lifecycle is *received → accepted → started* (started = the new attempt has begun, with `new_attempt`). The client resets on *started* only, then logs `correction_reset` | `Retry_ResetsCorrectionOnlyWhenNewAttemptStarted`, `Retry_Rejected_StateUnchanged`, `Retry_FailedBeforeStart_StateUnchanged` |
| 4 | Participant-selectable step sizes from a backend-defined set (provisionally 1, 2, 5 mm) | `decision_open.nudge.step_sizes_mm`. The client refuses sizes not offered (`step_not_offered`); the backend rejects them (`bad_step`) | `StepSizes_OnlyBackendOffered`, `Backend_RejectsStepAxis…` |
| 5 | Limits configurable and **backend-enforced** (±15 mm, 12 nudges: provisional) | Scenario/config values. Backend validation checks the per-axis bound on the commanded cumulative and the nudges per decision point. Client guidance (greyed-out arrows) can be switched off, and the backend still enforces | `Backend_PerAxisLimit…` (guidance off), `Backend_NudgeCountLimit`, `ClientGuidance_RefusesBeyondLimit…` |
| 6 | Each nudge independent: own ID, validation, acknowledgement, execution state and result; **no batching or queueing** | One request in flight per session. The client refuses input while busy (logged `input_ignored`). The backend rejects a second concurrent request (`busy`) and duplicate IDs (`duplicate`). Nothing is ever re-sent | `OneAtATime_FurtherClicksIgnored…`, `Backend_OneInFlight…`, `DroppedRequest_StaysUnconfirmed_NoSilentRetry` |
| 7 | Log receipt, acceptance, motion start, motion completion and next-command-ready **separately** | Separate client events `request_received`, `_accepted`, `_started`, `_completed` / `_failed`, `_ready`, each with backend and client times. A `request_summary` holds all stage times and durations. The backend logs every message it sends | `Nudge_FullLifecycle_EachStageLoggedSeparately…` (exact stage intervals) |
| 8 | Inspect may stay active throughout nudging; Allow or Intervene from the inspected view **without** resetting camera or zoom | Inspection is an orthogonal region. Camera and zoom stay free during a nudge. The view is restored only on ending inspection or on decision close. Every commit and request carries `inspecting`, camera, zoom, the viewport rectangle and the displayed frames of both cameras | `Allow_FromInspect_KeepsViewAndLogsDecisionContext`, `Nudge_WhileInspecting_ViewFreeDuringMotion…`, `Retry_FromInspect…`, full-trial integrity |
| 9 | Add the held/released, facilitator-approval and intervention-safety questions to the AIML draft; **do not send** | [`docs/coordination/CRATER_AIML_Questions_DRAFT.md`](../coordination/CRATER_AIML_Questions_DRAFT.md) §A4, questions 28–34 (also: retry semantics, link loss mid-nudge). Background bullets updated. Still marked DRAFT, NOT SENT | — |

---

## 2. What was built

All files are new, under `unity/Phase2Client/Assets/Phase2/Experiment/`. No existing file was edited.

| Assembly / folder | Files | Contents |
|---|---|---|
| `Phase2.Experiment.Core` (pure C#, `noEngineReferences`; references `Phase2.Video.Core` only) | `Json.cs`, `Messages.cs`, `ViewState.cs`, `SupervisorMachine.cs` | JSON reader (the writer is the existing `MiniJson`); **schema v1.1** messages with strict per-type allow-list parsing; millimetres on the wire and integer micrometres inside; stage-order table; `IClock` (`SystemClock` = the validated QPC/UTC clocks, `VirtualClock`); `ViewState` (camera, zoom 1/2/3, pan clamped, source-pixel rectangle); `IDisplayInfo`; **`SupervisorMachine`** (client) |
| `Phase2.Experiment.Sim` (pure C#) | `SimInfrastructure.cs`, `SimulatedBackend.cs` | Virtual-time `Scheduler`; `InProcessLink` (latency, link loss, full wire transcript); `MemorySink`; `Scenario` (JSON) + `ScenarioValidator`; deterministic fault injection (reject, delay receipt, drop, fail before start, fail during motion); **`SimulatedBackend`**; `SimHarness` |
| `Scenarios/` | `s1_reference.json` | 8 elements, mixed hidden conditions, provisional nudge settings, held-element model |
| `Tests/Editor` (`Phase2.Experiment.Tests`) | `TestUtil.cs`, `SchemaAndViewTests.cs`, `LifecycleTests.cs`, `SessionTests.cs` | 51 EditMode tests |

### 2.1 Request lifecycle (schema v1.1)

- **One request in flight per session.** Every request carries its own `client_cmd_id` and passes through its own stages. The backend frees the slot with `ready`, or with `decision_close` when the decision point ends.

| Kind | Stages | Terminal | Then |
|---|---|---|---|
| `inspect_begin` / `inspect_end` | received → accepted / rejected | accepted / rejected | `ready` |
| `allow` | received → accepted / rejected | accepted | `decision_close` (task continues) |
| `retry` | received → accepted → **started** (new attempt began; reset) / failed; or rejected | started / failed / rejected | `decision_close` after started; `ready` otherwise |
| `nudge` | received → accepted → started → completed / failed; or rejected | completed / failed / rejected | `ready` after a configurable settle |

- **`received` is receipt only:** it says nothing about when, or whether, motion starts.
- **Timeouts:** receipt, acceptance, start, execution and ready each have their own client timeout. A timeout moves the client to *Unconfirmed*, a system fault: it never re-sends, and late statuses are still accepted and logged as `late_status`.
- **Pause:** a nudge already moving completes, and the backend refuses new requests (`paused`).
- **Link loss:** messages in flight are lost. On reconnection the backend sends a `snapshot`, which resolves the client's outstanding request as completed (`request_resolved_by_snapshot`), still in flight, or lost (`request_lost`). Nothing is re-sent.

### 2.2 Simulated timings (placeholders)

| Setting | Value |
|---|---|
| Link latency | 2 ms |
| Validation | 20 ms |
| Nudge start delay | 250 ms |
| Nudge motion | 700 ms |
| Settle | 300 ms |
| Retry start | 400 ms |
| Placement | 3 s |

**Client timeouts:** receipt 1 s, acceptance 1 s, start 5 s, execution 10 s, ready 5 s. All are configurable.

---

## 3. Test results

**Authoritative run:** Unity 6000.3.28f1, batch mode, EditMode, 6 Nov 2026 16:56 (local). Evidence: `unity/Phase2Client/test_results/ai2_s1/editmode_all.xml` and `editmode_all.log`. The folder is git-ignored.

| Assembly | Total | Passed | Failed |
|---|---|---|---|
| **`Phase2.Experiment.Tests` (new, S1)** | **51** | **51** | **0** |
| `Phase2.Compat.Tests` (existing receiver and compatibility suite, run as a regression check) | 43 | 41 | **2** |
| All EditMode | 94 | 92 | 2 |

**The two existing-suite failures** are one pre-existing environmental check, **C09**, reported by two tests: `ClockReferenceTests.CurrentReferenceFile_IsFromThisBootSession` and `FfmpegCompatibilityTests.AllCompatibilityChecks_PassInEditor`.
- **What it compares:** the stored boot-session clock reference (`test_results/inputs/clock_reference.json`, made this morning) against the current QPC-to-UTC offset.
- **What it found:** a difference of **−2489 ms**. It is the same boot epoch (different epochs differ by hours), so the most likely cause is a Windows UTC time-sync step since the reference was taken. **Unverified.**
- **Not caused by S1:** S1 changed no clock code and no fixture. C01–C08 all passed in the same run.
- **Not regenerated:** I left the fixture as it is (preserve validation evidence). It can be regenerated with `Tools/make_clock_reference.py` on your approval, and C09's 50 ms threshold may deserve a note about time-sync steps.

**Pre-check:** the same 51 tests were compiled with Unity's Roslyn and run with a scratch reflection runner on Unity's bundled .NET 6. The first run gave 49/51 (§5, items 1–2); after the fixes, 51/51.

### 3.1 What the 51 tests cover

| Group | Tests | Key assertions |
|---|---|---|
| Schema and JSON | 7 | Exact round trip of all 14 backend and 2 client message shapes. **Any unlisted key rejected** (including nested `achieved` / `hidden_condition`). Wrong schema version, malformed requests and unknown types rejected. Stage-order table. Strict JSON reader. Exact micrometre arithmetic |
| View state | 4 | 1× full image; zoom-at-point clamped at edges; pan clamped (none at 1×); camera switch resets zoom; unknown camera or zoom refused |
| Startup and Inspect | 5 | Primary at 1× on open. Camera and zoom refused outside Inspect (and not sent as telemetry). 3 Inspect episodes on one token, each restoring the view. **Allow from Inspect at overview 3×:** view unchanged by choice and commit; commit and backend records carry inspection state, camera, zoom, rectangle and displayed frames; view restored only at decision close. Decision close closes the Adjust panel and ends Inspect |
| Nudges | 9 | Full lifecycle with **exact backend intervals** (validate 20 ms, start 250, motion 700, settle 300) and separate events. Cumulative updated only on completion, equal to the backend report. **One at a time:** 8 extra inputs ignored and 1 request reached the backend. View free during motion. Offered step sizes only. Adjust panel required. Client guidance at ±15 mm. Rejected nudge changes nothing and uses no allowance. Failed nudge leaves the commanded offset unchanged; achieved recorded only in the backend log |
| Backend enforcement (raw requests, client bypassed) | 4 | Per-axis bound (`out_of_bounds`), count limit (`limit_reached`), `bad_step`, `bad_axis`, `stale_token`, `not_available`, `paused`, `busy`, `duplicate`. No rejected request changes state |
| Retry | 5 | Reset only at *started* (not at accepted), logged after the stage event. Rejected and failed-before-start Retry leave token, attempt and offset unchanged. Retry from Inspect keeps the view until close. Arm/cancel sends nothing |
| Faults, timeouts, pause, link | 9 | Delayed receipt → Unconfirmed → late completion, never re-sent. Dropped request stays Unconfirmed for 30 s with no retry. Execution timeout. Pause mid-nudge completes the movement and blocks new input. Pause keeps the inspect view. Pause defers the next decision point. Link loss during Inspect restored by snapshot. Link loss after receipt resolved by snapshot. Link loss before arrival → `request_lost`, not re-sent |
| Whole session | 7 | **Information firewall** over a faulted full trial (pause, link loss, snapshot, every fault type): every client-bound message parses strictly, with no forbidden key and no hidden-condition value. **Leak test:** four permutations of hidden conditions give byte-identical client-bound streams (content and virtual timing) and client logs, while the backend logs differ. **Leak-test sensitivity:** a deliberate 100 ms hidden-condition delay (test hook) is detected. **Determinism:** two faulted runs are byte-identical (wire, client log, backend log). **Full-trial integrity:** 9 decision points (one retry); one commit and one close each; outside Inspect always primary at 1×; never more than one request in flight; every request summarised once; legal stage order; shown cumulative = reported; 18 nudges with distinct IDs and full lifecycles. The scenario file loads, validates and equals the built-in reference. The validator flags primary camera correlated with hidden condition. Client events through the existing `EventLog` have the standard schema |

---

## 4. Interpretations to confirm

1. **Failed nudge and the displayed offset.** A nudge that was accepted but **failed** does not add to the displayed *commanded* cumulative. Only completed nudges count, and the backend logs whatever the simulation "achieved". In the real cell a partly executed nudge could leave the element somewhere the commanded offset does not describe. This needs AIML input (Q30, Q32).
2. **Allowance accounting.** Rejected nudges do not use the 12-nudge allowance. Accepted nudges do, even if they later fail.
3. **What the limits check.** Limits are checked against the **commanded** cumulative only. In the real system they may also need to consider measured position (AIML Q29, Q32).
4. **Inspect is acknowledged.** `inspect_begin` and `inspect_end` go through the same acknowledged lifecycle (they hold or release the task). View changes are telemetry only, with no acknowledgement.
5. **Correction model visible to the client.** The correction model label (`held_element_provisional`) is part of the nudge spec the client receives. It is not shown and carries no correctness information.
6. **Unconfirmed requests have no resolution tool yet.** An *Unconfirmed* request whose original was lost stays unconfirmed until a snapshot or decision close. Experimenter tooling to resolve it belongs with the experimenter console (later).

---

## 5. Deviations and fixes during S1

1. **Test fix:** a wire-order test used `<` where the second nudge legitimately leaves in the same virtual instant its predecessor's `ready` arrives. It now uses `≤`. The test was too strict; behaviour was unchanged.
2. **Log-order fix:** the client logged `correction_reset` before `request_started` for the same Retry status. The state change was correct; the log now records the stage first, then the reset it caused.
3. **Side effects of the Unity run (expected, not changes):**
   - Unity re-saved `ProjectSettings/ShaderGraphSettings.asset` with its default values at editor exit (created 5 Nov; content is defaults).
   - The existing compatibility test wrote its usual new report, `test_results/compat/editor_compat_20261106_165634.json`.
   - `.meta` files were generated for the new folder.

---

## 6. Not done in S1 (by design)

- No Unity scene or UI.
- No change to `StereoReceiverBehaviour`, `DisplayRig` or any video, camera or streaming code.
- No Python log checker (S4).
- No real backend, network or authentication.
- No experimenter console.

---

## 7. Next stage (S2), awaiting approval

**S2, two-camera supervisory video:**
- **Viewport:** a `WindowView` that renders Camera A or B, with digital zoom through the existing `LumaUnlit` `_Crop` sub-rectangle (no shader change).
- **Video source for the state machine:** `IDisplayInfo` fed by the real receivers.
- **Regression:** the full M1 regression re-run.

**Approvals needed for S2:**
- **D12, the one change to existing code:** an opt-in `createDisplay` flag (default unchanged) on `StereoReceiverBehaviour`, gated on an unchanged M1 regression.
- **D10, Camera B offline input:** either a short new empty-scene recording (a live camera session) or synthetic B input. The existing E2/E4 Camera B recordings show an identifiable person and will not be used.
- **Optional:** regenerate the C09 clock reference so that the existing suite is green again before S2's regression run.

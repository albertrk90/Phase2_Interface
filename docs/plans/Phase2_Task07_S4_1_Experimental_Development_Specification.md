# Task 07 S4.1: experimental development specification (configuration, session orchestration, facilitator coordination)

**Status:** development specification for the simulated session runner, 12 Nov 2026. It consolidates:
- the researcher's S4.1 brief;
- the methodology correction of the same day, following review of formal methodology **V17** and its appendices.

**It is not an ethics approval and not the formal protocol.** Where it and the formal methodology or ethics documents differ, the formal documents govern. §7 lists the known differences.

**Scope.** S4.1 covers experimental configuration, session orchestration and facilitator coordination only. It does not cover:
- final questionnaires, SAGAT items, scoring, or analysis datasets (these are S4.2);
- Quest 3, a digital twin, machine vision, or physical robot integration.

Everything runs against the simulated backend and offline video.

**Implementation:** `unity/Phase2Client/Assets/Phase2/Experiment/Session/` (pure C#) and the Site Window session mode. Results are in [S4.1 implementation results](Phase2_Task07_S4_1_Implementation_Results.md).

Each requirement below is labelled:
- **[A]**: agreed experimental design (researcher decision);
- **[P]**: provisional demonstration parameter (configurable; not a final value);
- **[C]**: physical commissioning requirement (CRATER/AIML);
- **[I]**: final instrument or scoring requirement (S4.2 / methodology);
- **[D]**: discrepancy or open methodological question (§7).

---

## 1. Technical plan

### 1.1 Reused components

**Reused unchanged in behaviour:**
- M1 receivers, S2 feeds, and the video view;
- the S1 `SupervisorMachine` (still the client authority) and the `SimulatedBackend` (still the backend authority);
- the S3 Site Window;
- the S3.1 released-element workflow: recovery, secure grasp, translation and rotation nudges, Place and release, Retry as a repeated standard placement, and reassessment.

**What changed in existing code:** every addition is opt-in, so the S1–S3.1 scenarios and tests behave exactly as before.

### 1.2 New components

**Pure C# (`Phase2.Experiment.Session`):**
- `ExperimentDefinition`: the versioned definition, its validation rules, a content ID and the deterministic plan.
- `AllocationRegister`: saved participant-to-sequence allocations.
- `SessionStore`: append-only records, an atomic checkpoint, and per-run raw logs.
- `Authority`: the role permissions.
- `SessionRunner`: the lifecycle, requirements, facilitator actions, interruptions, validity, replacement, restart reconciliation, closure integrity checks and the participant-safe phase.
- `TrialRuntime`: one trial; observation, probe, restoration and decision-ready; the confidence lock; pathway capture.
- `SessionSimulation`: the simulated host, automatic facilitators, a scripted participant and the accelerated full run.

**Unity:**
- `S4SessionMode` (a partial of `S3Session`): the session host, the per-trial receiver restart, participant screens and the facilitator console.
- `S41Script`: the scripted UI verification.
- `S4Build`, plus the `Tools/run_session.ps1` launcher.

**Tools:** `Tools/verify_s4_session.py`, an independent offline verifier of a session directory.

### 1.3 Changes to the AI2 machines and backend (schema `ai2-v1.3`; all optional)

**Backend (simulated):**
- Each element carries a hidden potential-CDP role: active, inactive or none.
- Only **active** elements open a formal CDP (`decision_open{origin: scheduled}`). Inactive locations and ordinary placements continue autonomously, with identical messages and timing.
- **`supervise`**: a request during autonomous construction is acknowledged at once. The robot then holds at the **next safe state**:
  - the release of the element being placed; or
  - immediately, if an element has just been released.
- **Formal-CDP hold:** requests are rejected with `decision_not_ready` until the session runner enables the decision opportunity.
- **Facilitator-console mode:** recovery review, secure-grasp confirmation, uncertain-state resolution, and a **scoped adjustment-episode authorisation**, which is required before any nudge.
- **Construction-state persistence** within a trial, using a demonstration carry-over model **[P]**.
- **Researcher-only ground-truth records.**

**Client (`SupervisorMachine`):**
- an assessment hold;
- the first-commitment lock (`Committed`), with `ReleaseCommit` and `CancelCommit`;
- unscheduled requests from the Inspect or Intervene keys;
- new time buckets: assessment hold and confidence.

### 1.4 Facilitator permission model

See §4. It is implemented in `Authority`; every action goes through `SessionRunner.Act(role, action, args)`, which logs it, and refusals are logged too. The permissions do not depend on the console that presents them.

### 1.5 Testing strategy

- **Deterministic EditMode tests** for the definition and for all 24 verification items. One accelerated full session in virtual time is shared by the tests, plus focused tests.
- **A participant-presentation lint** over a whole demonstration session.
- **A PlayMode scripted UI session** through real EventSystem raycasts.
- **The offline Python verifier.**
- **The existing M1, S1, S2, S3 and S3.1 regressions.**

---

## 2. Experiment definition (`ai2-experiment-v1`)

The definition is a readable, version-controlled JSON file in `Assets/Phase2/Experiment/Protocols/`. It can be edited without recompiling.

| File | Purpose |
|---|---|
| `phase2_protocol_demo.json` | **Reference structure:** 4 blocks × 3 trials, W1–W4, full lifecycle. All physical and timing values are demonstration values **[P]** |
| `phase2_s41_interactive_demo.json` | A short interactive demonstration: 2 blocks × 1 trial, 4 placements per trial. The validator flags the deliberately incomplete counterbalancing as a warning |

**Identity.** Each definition has:
- experiment, protocol and version identifiers;
- a status (`demonstration`; anything other than `approved` produces a warning);
- a **content ID**: `sha256:` over the canonical JSON (parsed and re-written, so whitespace does not affect it).

Every session saves the exact definition text, `effective_definition.json`. On resume the **saved** definition is used, never the current file.

**Contents:**
- conditions;
- sequences;
- the allocation procedure;
- recruitment;
- structure;
- CDP allocation patterns and per-block trial order;
- architectures: baseline, placement sequence and element IDs, potential CDP locations, demonstration settle model and carry-over;
- scenario families and scenarios: prescribed position and rotation variation per placement, expected outcome, evidence availability, equivalent replacement;
- trial scenarios by condition;
- training phases, competency checklist, additional practice and refreshers;
- observation interval;
- SAGAT, as a placeholder instrument with architecture-specific placeholder banks;
- confidence, as a placeholder;
- external assessments;
- ground-truth categories;
- interruption and replacement rules;
- simulation settings and facilitation settings;
- the input-method status.

**Validation rules (an error makes a definition unusable; warnings are recorded with every session):**
- **Design:**
  - the 2 × 2 factorial;
  - each sequence is a permutation of the conditions, the sequences form a Latin square, and they are **first-order carry-over balanced** (Williams);
  - a known allocation procedure.
- **Trial structure:**
  - blocks ≤ conditions (fewer gives a warning);
  - three distinct potential locations;
  - active + inactive = 3;
  - one probe per trial, **always at an active CDP**;
  - **probe and inactive locations balanced across a block**: each location carries the probe once and is inactive once.
- **Architectures and scenarios:**
  - every location maps to a placement;
  - every measured architecture has a baseline;
  - each scenario names a known architecture and family, with known placements and outcome or evidence values;
  - each condition's scenarios match its architecture;
  - **2D and XR blocks of an architecture use the same scenario set**.
- **Training:** both interfaces must be familiarised, and training scenarios must be training-only.
- **Assessments:**
  - question counts per probe and per architecture bank;
  - a confidence scale of at least two points;
  - known assessment timings.
- **Replacement:** categories must be known; **participant performance can never be eligible**.
- **V17 corrections:**
  - max recruited ≥ the target;
  - architectural-state categories present and kept apart from the acceptability values;
  - the input-method status is stated.

---

## 3. Agreed design as implemented

### 3.1 Factors, conditions, Williams sequences **[A]**

| Condition | Architecture | Interface |
|---|---|---|
| A | Lunar Lantern | 2D |
| B | Lunar Lantern | XR |
| C | RegoLight | 2D |
| D | RegoLight | XR |

| Sequence | Order |
|---|---|
| W1 | A B D C |
| W2 | B C A D |
| W3 | C D B A |
| W4 | D A C B |

**Allocation:**
- **Procedure:** `cyclic_by_enrolment_ordinal`, so participant n receives sequence `W[(n−1) mod 4]`. An explicit pre-assignment variant is supported.
- **When it is saved:** in `allocation_register.json` when the session is created, before anything measured. It is never regenerated: not on start, not on resume, and not after a definition edit.
- **No upper limit** is imposed by the software.

**Sample (V17 correction).**
- The target is **20 analysable participants**, with **up to 24 eligible participants recruited**, supported by the simulation-based power analysis for H1 and H2.
- The reference allocation is **5 per sequence at N = 20** and **6 per sequence at N = 24** (both tested).
- Actual allocation and attrition may differ.
- The 6–8 participants given in the S4.1 brief is superseded.

Condition ordering is kept separate from scenario ordering and from the CDP and SAGAT allocation.

### 3.2 Participant-level structure **[A]**

- Four blocks, three measured trials each: **12 measured trials**.
- Three potential CDP locations per trial (early, middle, late): **two active formal CDPs and one inactive location**.
- **One three-item SAGAT probe** per trial, at an active CDP.
- **One first-commitment confidence rating** at each active CDP: up to 24.
- The resulting planned totals are 24 CDPs, 12 inactive locations, 12 probes and 24 ratings.
- These quantities live in the definition, not in code.
- **Default allocation pattern** (P1, per the brief):

  | Trial | Early | Middle | Late |
  |---|---|---|---|
  | 1 | active, probe | active | inactive |
  | 2 | inactive | active, probe | active |
  | 3 | active | inactive | active, probe |

- A second balanced pattern (P2) and a per-block trial order show that both are configurable.

### 3.3 Session lifecycle **[A]**

1. Pre-session: instruments recorded, eligibility recorded, then Facilitator B starts the session.
2. Onboarding.
3. Training phases: general, then 2D practice, then XR practice, each with dedicated training scenarios.
4. Competency check.
5. Additional practice, then the competency check again (within the allowance).
6. Training complete.
7. For each assigned block:
   1. block intro (the condition transition);
   2. refresher;
   3. for each trial: **trial reset**, then the trial;
   4. block assessment;
   5. break.
8. Post-session interview recorded.
9. Closure, with integrity checks.
10. Closed.

How the runner handles this:
- Each stage completes when its role-scoped requirements are met.
- The participant only ever sees *Continue* buttons and the AI2 interface; the participant never needs developer controls.
- **Training and measured data stay distinguishable:** every record carries `purpose` and `measured`.
- Incomplete or discontinued sessions are supported (§5).

### 3.4 Training **[A]**, with durations and allowance **[P]**

- Hybrid familiarisation, plus a **facilitator-administered competency checklist** covering:
  - Allow;
  - Inspect and view tools;
  - deciding from the inspected view;
  - recovery;
  - nudges;
  - Place and release;
  - Retry;
  - unscheduled requests;
  - the question screens.
  The checklist item texts are **[P]**.
- **What is recorded:**
  - phase IDs, order and duration;
  - per-item results (`demonstrated`, `needs_practice` or `not_assessed`), plus assistance;
  - the attempt number;
  - the outcome: `competent`, `additional_practice` or `training_incomplete`;
  - additional practice used against the allowance;
  - Facilitator B's confirmation.
- Competency concerns operational understanding, not error detection.
- Background questionnaires and eligibility rules are **not** built; there are hooks and completion records only.

### 3.5 Baselines and trial reset **[A]**; physical baselines **[C]**

- Every trial starts from its architecture's common predefined baseline. Each trial is a fresh backend instance, so no construction deviation is carried over (tested).
- Construction state **persists within a trial**: in the demonstration, a later placement inherits part of the earlier resulting error (`carryover_fraction`) **[P]**.
- **Trial reset requires all of:**
  - Facilitator A confirms the baseline, with the matching baseline ID (a wrong ID is refused);
  - Facilitator A confirms robot readiness;
  - Facilitator B confirms participant readiness;
  - the video and backend prerequisites are met (in Unity, both receivers are restarted and showing images).
- Reset duration is recorded separately. Physical reset trajectories are not implemented.

### 3.6 Active and inactive CDPs **[A]**

**Active CDP sequence:**
1. Release, retreat and settle.
2. The CDP opens with the decision **held**.
3. The **observation interval** runs (`formal_cdp_observation_ms`, 4 s demonstration **[P]**).
4. If this CDP carries the probe, the SAGAT sequence runs (§3.8).
5. **Decision-ready**, recorded as the `decision_ready` event.

At non-probe CDPs, decision-ready is the end of that same observation interval. Every formal CDP therefore looks and times identically up to the point where the probe would start **[D2]**.

**Inactive location:**
- No prompt is shown, and construction continues.
- The location, its placement and its ground-truth reference are recorded (`inactive_location`).
- The participant stream is **identical** to an ordinary placement, in both messages and timing (tested).
- Faults are never assumed to be present.

### 3.7 Continuous supervision and unscheduled actions **[A]**

During autonomous construction:
- **Inspect and Intervene request a hold**; Allow is dormant.
- The acknowledgement comes at once.
- The robot holds at the **next safe state** (the next release), and the participant's mode is applied: Inspect starts inspection, Intervene opens the Adjust panel.
- **Recorded separately:**
  - request time;
  - acknowledgement time;
  - safe-state (episode-open) time;
  - episode start;
  - actions;
  - resolution;
  - the placement at the time of the request.

**Overlap rules** (no duplicate episodes):
- **The safe state is a formal CDP.** The request is **merged**: one formal episode, keeping both the request ID and the CDP identity. The formal sequence takes precedence, so **the probe is not cancelled or moved**.
- **The safe state is an inactive location.** An unscheduled episode opens there, and its researcher-only records keep the inactive identity.
- **A click during the observation interval or probe of an open CDP.** It is refused (`decision_not_ready`) and counted as an early action attempt.

Unscheduled episodes have no probe and no confidence prompt. The physical robot is **not** assumed able to stop at arbitrary moments **[C]**.

### 3.8 SAGAT hooks **[A]**; items and scoring **[I]**

**Sequence:**
1. Observation interval.
2. **Freeze:** the backend is held, and a ground-truth snapshot is taken and referenced by the probe record.
3. The plate camera is disabled and the Site Window is replaced by the probe screen. Construction imagery and operational information are hidden; the receivers keep running.
4. Three items are shown, with no feedback. Each response and its timing is recorded.
5. The latest valid view is restored: the primary camera at 1×.
6. Restoration is verified (`view_restored`). If it times out, the measures are flagged.
7. Decision-ready.

**What is not final:**
- The questions are **visibly marked development placeholders**.
- The definition supports **architecture-specific question banks**, as V17 has, and each trial uses its architecture's bank. The bank contents remain placeholders until S4.2.
- **No scoring is implemented.**

### 3.9 First-commitment confidence **[A]**; wording and scale **[I]**

- **What counts as the first substantive commitment:**
  - confirming Allow;
  - confirming the recovery request (the Intervene commitment). Opening the Intervene panel is not a commitment.
- **What happens:**
  - The commitment is **recorded and locked**: the request is not sent, and a ground-truth snapshot is taken.
  - The confidence prompt appears over the Desk; the view stays visible.
  - When the participant answers, the commitment is released and executes.
- **What the participant cannot do:** revise the locked commitment.
- **What a facilitator can do:** cancel it for safety, withdrawal or technical reasons. The commitment record is kept, and the confidence measure is set to `not_collected`.
- **What is recorded:** confidence time is kept separately, and so is whether the probe preceded the commitment.
- **Where it does not appear:** after nudges or later commitments, or at unscheduled episodes. The scale is a placeholder.

### 3.10 External assessments **[A]**; instruments **[I]**

- **Recorded for each instrument:** instrument ID and version, scope (session or block), start and completion, status (`completed`, `incomplete`, `skipped` or `unavailable`), an optional external reference, and Facilitator B's confirmation.
- **V17 instrument set:**

  | Timing | Instrument |
  |---|---|
  | Pre-session | Participant background; eligibility and stereoacuity |
  | Block end | **Survey B**: 8 items (one 7-point perceived depth and alignment-access rating, six Raw NASA-TLX items, one 7-point overall decision-confidence rating) |
  | Post-session | Interview |

- The competency checklist is recorded through the training stage.
- No other subjective SA or uncertainty instruments are established in V17, so none are configured; they can be added to the definition.
- No survey platform is built.

### 3.11 Ground truth and information separation **[A]**; verification method **[C]**

**Researcher-only records (`ground_truth.jsonl`):**
- programmed variation;
- initial released state;
- state at the SAGAT freeze;
- state at first commitment;
- post-correction state;
- final acceptance.

**What each record carries:**
- the simulated pose error and the construction state;
- a *preliminary* classification, from the placeholder settle model;
- the **expected outcome**, labelled as the scenario design and "not verified";
- evidence availability;
- physical acceptability;
- verification status, method, evidence references and who verified it;
- the final classification;
- notes.

**V17 classification scheme:** the five architectural-state categories are **converging**, **tolerable residual**, **unresolved or ambiguous**, **consequential**, and **obstructed or failed**.
- Facilitator A's `record_ground_truth` accepts only these categories; scenario labels are refused.
- **Physical acceptability** and **participant evidence availability** are separate attributes. Their value sets are provisional **[P]**.
- Expected scenario labels never determine decision-quality scores.

**Leak-test principle (S3.1 scope):**
- **What the tests look for:** unintended interface cues and supplementary information, such as metadata, wording, recommendations and timing.
- **Never shown to the participant:**
  - ground truth;
  - CDP roles or schedule;
  - probe placement;
  - scenario or baseline identifiers;
  - session or participant codes.
- **Not a leak:** legitimate differences in the construction imagery. These are the stimuli.

### 3.12 Decision quality and the supervisory pathway **[A]**; scoring **[I]**

- **The primary observation per formal CDP** is the first substantive commitment (`first_commitment`, locked).
- **V17 refinement:** H2 moves from the final supervisory decision to the first substantive Allow or Intervene commitment, with later correction and final acceptance retained separately. The event structure supports this; the scoring rules are left to S4.2.
- **The full pathway** is captured in the session record (`pathway`, linked to the episode) and is also preserved raw in the per-trial client log. It includes:
  - the initial AI2 choice;
  - inspection and view changes;
  - commitments, the confidence rating and recovery;
  - facilitator stages, nudges, place-and-release and reassessment;
  - later commitments and final acceptance, with physical outcome references.
- An Intervene → correction → Allow pathway stays one episode with several commitments. Corrections never become extra primary observations.

### 3.13 Timing **[A]**

- **Clock domains:** raw monotonic and UTC nanoseconds on every record. The session and participant-client records share one clock, while the backend log keeps its own; no synchronisation between future remote sites is assumed **[C]**.
- **Per-episode raw intervals:**
  - observation;
  - probe;
  - view restoration;
  - open → decision-ready;
  - decision-ready → first action;
  - decision-ready → first commitment (formal decision time starts at decision-ready);
  - confidence;
  - commitment → release;
  - close;
  - supervision request → acknowledgement and → safe state.
- **The client's CDP time partition:** participant, technical, facilitator, paused, **assessment hold** and **confidence**. It is complete and non-overlapping (tested).
- **Also recorded:** reset, training stages, assessments, breaks and interruptions.

### 3.14 Interruptions, validity and replacement **[A]**; thresholds and exclusions **[P]/[I]**

**Interruption categories:**
- technical execution failure;
- video loss;
- backend failure;
- application restart;
- facilitator pause;
- participant wellbeing;
- procedural;
- withdrawal.

**What an interruption record holds:** its ID, category, start and end, the IDs it affects, the affected episode and phase, and whether it came before or after the commitment. It also holds the facilitator response, the resolution and the validity implication.

**Resuming** requires Facilitator A's physical readiness and Facilitator B's participant readiness.

**What happens to observations:**
- An interruption **after** a valid commitment keeps the commitment, and flags the execution.
- An interruption before the commitment flags the decision timing.
- Termination preserves the unaffected observations.

**Validity** is recorded at session, block, trial, episode and measure level. The measure-level entries are first commitment, confidence, probe and decision timing, each `valid`, `flagged` or `not_collected`.
- XR blocks run on Windows are **flagged as a development substitution and never recorded as XR exposure**.

**Replacement trials:**
- assigned automatically by rule, or by Facilitator B;
- each has a unique ID (`…-R1`), is linked to the original, keeps the original's records, and uses the same CDP allocation and the predefined **equivalent scenario**;
- allowed only for technical or procedural categories, never participant performance;
- limited per block and per session **[P]**.

**Discontinuation** of a block or the session preserves records; the remaining trials are marked not run.

### 3.15 Persistence and recovery **[A]**

- **What is saved:**
  - an append-only, never-overwritten event stream with stable IDs that continue across runs;
  - an atomic checkpoint after every state-changing event;
  - per-run raw trial logs.
- **On restart:**
  1. The session reopens from its saved definition, allocation, plan and checkpoint.
  2. `application_restart` is recorded and an interruption is opened.
  3. **Nothing is replayed.**
  4. **Reconciliation:** Facilitator A records the physical state (`baseline_restored` or `state_unknown`) and Facilitator B confirms the participant is ready.
  5. A measured trial interrupted mid-run is terminated, its records are kept, and an eligible replacement follows. A trial interrupted during reset is reset again.

### 3.16 Facilitators **[A]**; execution model **[C]**

This is **experiment control, not a safety-rated robot control system**; the physical execution model is subject to CRATER/AIML commissioning.

| Role | Actions |
|---|---|
| **Facilitator A (CRATER)** | Baseline; robot readiness; recovery review (approve or decline); assistance and **secure-grasp confirmation**; **adjustment-episode authorisation** and revocation; uncertain-state resolution; preliminary ground truth; technical failures; physical reconciliation; physical readiness to resume |
| **Facilitator B (North Terrace)** | Session start and progression; participant readiness; assessments; competency; condition transitions; wellbeing; procedural interruptions; discontinuation; replacement assignment; participant readiness to resume |
| **Both** | Pause; cancel a locked commitment; terminate a trial; resolve an interruption; resume |

**The adjustment authorisation:**
- It is scoped to the current CDP token and placement cycle.
- Individual nudges are then validated by the backend without per-nudge approval.
- It **expires** on release, episode close, revocation, pause, link loss or an uncertain state.
- Without it, both the client and the backend refuse nudges (tested).

### 3.17 Presentation

**Participant:**
- session screens for:
  - welcome, onboarding and training;
  - competency and additional practice;
  - block intro, with the XR substitution label;
  - refresher, trial readiness and the probe;
  - restoration, the questionnaire handover, break, interview, and completion or ended;
- the hold keys;
- the observation lock;
- "held at your request";
- the confidence prompt over the Desk.

**Facilitator console:** a researcher-facing IMGUI panel, docked on the right; F9 hides it. It shows:
- session identifiers;
- pending requirements by role;
- Facilitator A's tasks;
- role-specific actions;
- interruption handling;
- the current episode, with its location, role and probe;
- recent events.

Automatic facilitators are optional and can be switched per role. No major visual redesign was attempted.

---

## 4. Provisional demonstration parameters **[P]** (all in the definition files)

- **Placements:** six per architecture (four in the interactive demonstration), with element and target IDs.
  - CDP locations: P2, P4 and P6.
  - Primary cameras: A for P1–P3, B for P4–P6.
- **Settle model:**
  - Lunar Lantern: 2 mm / 1° capture, slide 1.0;
  - RegoLight: 5 mm / 3°, slide 0.6;
  - carry-over 0.25.
- **Scenario variations and expected outcomes:**
  - Family 1, matched: LL-M1/M2 and RG-M1/M2, with the same programmed values but different expected accommodation;
  - Family 2, calibrated: LL-C1 and RG-C1;
  - "limited" evidence-availability examples;
  - `…R` equivalent replacements.
- **Timings:**
  - placement 3 s;
  - autonomous gap 0.6 s;
  - observation 4 s;
  - S3.1 motion timings.
- **Facilitator delays:** simulation only.
- **S3.1 limits:** recoveries 3; nudges 12; ±15 mm; ±5°; steps 1/2/5 mm and 0.5/1/2°.
- **Training content and allowance:** checklist items; additional practice ×1; refresher scenarios.
- **Replacement limits:** 1 per block, 2 per session.
- **Placeholder instruments:** SAGAT, the per-architecture banks, and the confidence scale (1–5).
- **Value sets:** physical acceptability (`acceptable`, `not_acceptable`, `not_determined`) and evidence availability (`full`, `limited`).

---

## 5. Physical commissioning requirements **[C]**

- **Safe-state model:** where the robot can actually stop when a hold is requested, and how long it takes to get there. Arbitrary stops are not assumed.
- **Recovery:** the assisted-recovery procedure, how the secure grasp is verified, and the repeatability of the recovered tool-to-element relationship (S3.1 C2).
- **Adjustment episodes:** how the authorisation is executed physically, and the revocation triggers, including live video and backend-health loss (C6).
- **Placement:** rotational axes, signs, steps and bounds (C3), and the real settle and accommodation behaviour.
- **Video prerequisites:** these must replace `development_override`.
- **Baselines:** the physical baseline definitions and reset procedure, with their durations.
- **Ground truth:** the verification method (by a human or an instrument) and the evidence references.
- **Clocks:** time alignment between CRATER and North Terrace.

## 6. Final instrument and scoring requirements **[I]** (S4.2 and the methodology)

- the architecture-specific SAGAT bank and scoring protocol (from V17);
- the confidence item wording and scale;
- the Survey B items;
- the background and eligibility instruments, and the interview guide;
- the scoring rubric for decision quality (H2: first substantive commitment, with correction and final acceptance kept separate);
- analysis-ready tables;
- exclusion rules, and thresholds for interruptions and replacements.

## 7. Discrepancies and open methodological questions **[D]**

| # | Item | Treatment in S4.1 |
|---|---|---|
| D1 | **No formal methodology or ethics documents are in the workspace.** The V17 corrections come from the researcher's 12 Nov message, so no direct cross-check was possible | Recorded. The definition is labelled `demonstration`; nothing here implies ethics approval |
| D2 | Is Inspect available during the pre-probe observation interval? | Implemented as **passive observation, identical at every formal CDP** (`inspect_during_observation: false`, configurable in the definition but not yet in behaviour). This avoids a cue that a probe is coming; to be confirmed |
| D3 | An unscheduled request whose safe state is a formal CDP | Merged into that CDP. The formal sequence (including the probe) takes precedence, and the request is recorded. A participant who requested a hold may experience the probe sooner than expected; confirm this is acceptable |
| D4 | An unscheduled episode just before a probe CDP gives extra inspection opportunity before the freeze | Not prevented; recorded, so the analysis can account for it |
| D5 | **Input method:** V17 specifies speech recognition as the principal input; the Windows implementation uses manual pointer controls | **Unresolved.** The definition records `formal_status: under_review`, and the development implementation does not decide the formal choice |
| D6 | Sample size: the brief's 6–8 against V17's 20 analysable (up to 24 recruited) | Corrected to V17 (§3.1) |
| D7 | The brief named block-level confidence or uncertainty and "other subjective SA" instruments; V17 has only Survey B (8 items) | Corrected: Survey B only, configurable |
| D8 | The earlier Task 07 proposal assumed a familiarisation trial per condition and per-decision-point primary cameras; S3 had every element as a CDP | Superseded by hybrid training, primary cameras per placement and the 2-of-3 CDP structure |
| D9 | Facilitator cancellation of a locked commitment: is the next commitment the primary observation, or the cancelled one? | The cancelled first commitment stays recorded as the first commitment, and confidence is `not_collected`. The S4.2 scoring decides |
| D10 | The XR condition is not implemented | XR blocks run as a labelled Windows development substitution, flagged and never recorded as XR exposure |

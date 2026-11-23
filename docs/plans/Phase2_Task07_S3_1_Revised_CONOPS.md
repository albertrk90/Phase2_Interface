# Task 07 S3.1: revised placement, recovery and correction CONOPS, and the state-machine changes

**Status (12 Nov 2026):** specification for S3.1, written before implementation. **Implemented the same day and accepted by the researcher as the functional baseline** (decisions in §11) (simulation defaults as marked [P]); results in [S3.1 results](Phase2_Task07_S3_1_Implementation_Results.md). All operations are **simulated**. Nothing here is an approved physical procedure, limit or coordinate convention.

**Basis:**
- the researcher's S3.1 brief (12 Nov 2026);
- the accepted S3 baseline: commit `e418f620663e5cf7c84fa37127758d12bf11a02d`;
- [S1 results](Phase2_Task07_S1_Implementation_Results.md) and [S3 results](Phase2_Task07_S3_Implementation_Results.md).

**Labels:** **[R]** researcher statement; **[P]** my proposal, implemented as a configurable simulation default; **[D]** decision or commissioning question still open.

---

## 1. What changes, and what is kept

| Topic | S1–S3 (provisional) | S3.1 |
|---|---|---|
| Element at the decision point | Still held by the robot | **Released**, with the robot retreated; the element has settled freely [R] |
| Intervene | Opens nudges on the held element | Opens **recovery**; nudges only after a confirmed secure grasp at the adjustment position [R] |
| Corrections | Translations along / across the rail | Translations **and a bounded rotation**, each an individual request [R] |
| Completing a correction | None (Allow placed the held element) | **Place and release**: controlled placement, release, retreat, then reassessment [R] |
| Retry | A fresh attempt from the decision point | Only for a **held** element (after recovery); see §6 [P] |
| Facilitator | Not modelled | May review, assist or reject a recovery; can resolve an uncertain state [R] |
| Decision-point scope | One token per placement attempt | **One construction decision point (CDP) per element**, from the first release to the final Allow. Every recovery, correction, placement and retry stays inside it, numbered by `cycle` and `attempt` [P] |

**Kept unchanged:**
- one request in flight; no batching or queueing; no silent retries;
- every nudge acknowledged at once, then validated, executed and reported;
- the backend is the authority on limits and states;
- the viewing rules: camera, zoom and pan only in Inspect; Inspect and Intervene can coexist; decisions can be made from Inspect; the view is restored when the CDP closes;
- the information firewall (strict allow-listed messages); the leak test;
- the separation of video state from robot state.

**Two workflows, one codebase.** The S1–S3 "held element" workflow stays available, unchanged, as `workflow: held_element_v1`, the default for old scenarios. This keeps every existing S1, S2 and S3 test meaningful as a regression. The revised workflow is `workflow: released_recovery_v1`, selected by the scenario. The participant build uses the revised workflow by default.

---

## 2. Revised construction sequence (one element, one CDP)

```
 robot (predefined)                            participant                    facilitator (CRATER)
 ───────────────────────────────────────────  ─────────────────────────────  ─────────────────────
 1 pick → 2 place with prescribed variation
 → 3 release → 4 retreat → 5 element settles
                         ── element_state: released (cycle 1) ──►  6 observe / Inspect
                                                                   7 Allow ─────────────────────► CDP closes, next element
                                                                     Intervene → Recover element… (confirm)
 recovery request ◄────────────────────────────────────────────── recover
   [facilitator review: approve / reject] ◄──────────────────────────────────────────────────── may approve / reject
   recover, confirm secure grasp, lift to the adjustment position
   [facilitator assistance] ◄──────────────────────────────────────────────────────────────── may assist / execute
                         ── element_state: held ──►                nudges: translation / rotation (one at a time)
                                                                   Place and release… (confirm)
 controlled place → release → retreat → settle
                         ── element_state: released (cycle n+1) ──► reassess: Allow / Inspect / Intervene again
```

- **Recovery and lifting** are predefined, supervised backend operations. The participant only requests them.
- **The participant never commands a trajectory.** The only participant-commanded motion is a bounded nudge of the held element at the approved adjustment position.
- **Approach, lowering, release and retreat** are part of Place and release.

---

## 3. Element state (new; backend-authoritative)

| State | Meaning | Participant may |
|---|---|---|
| `released` | Placed and released; the robot has retreated; the element is free | Allow · Inspect · Intervene → **Recover** |
| `recovering` | A recovery operation is in progress (including facilitator stages) | Inspect (view only) |
| `held` | Secure grasp confirmed; the element is at the approved adjustment position | Nudges · **Place and release** · Retry · Inspect. **Not Allow** |
| `placing` | Controlled placement, release and retreat in progress | Inspect (view only) |
| `uncertain` | The backend cannot confirm the element's state (for example an uncertain recovery or placement outcome) | Inspect (view only). **No Allow and no motion** until the facilitator or backend resolves it |

**Rules:**
- **Allow is accepted only when** `released`, no request is in flight, nothing is armed, and the state is not `uncertain`. Both the client and the backend enforce this; the backend reason is `element_not_released`.
- **Nudges, Place and release, and Retry** require `held` (backend reason `element_not_held`).
- **Recover** requires `released` and an unused recovery allowance (`max_recoveries` per CDP, provisional: 3).
- **Every change is a separate `element_state` message:** `{token, state, cycle, attempt, cause}`. Its causes come from a closed set: `initial_release`, `recovery_started`, `secure_grasp_confirmed`, `recovery_unsuccessful`, `placement_started`, `released`, `placement_not_completed`, `state_uncertain`, `facilitator_resolved`. **No cause or field carries alignment, error or correctness.**

---

## 4. Requests and lifecycles (schema v1.2)

`received` is still receipt only. Each request ends in exactly one terminal stage, then `ready` (or the CDP closes).

| Kind (new kinds in bold) | Stages | Element state effect |
|---|---|---|
| `inspect_begin` / `inspect_end` | unchanged | none |
| `allow` | received → accepted / rejected | CDP closes; next element |
| **`recover`** | received → [**`facilitator_review`**] → accepted / rejected → started → [**`facilitator_assist`**] → **completed** / failed | started: `recovering`; completed: `held` (secure grasp confirmed); failed: `released` or `uncertain` |
| `nudge` (translation **or rotation**) | received → accepted / rejected → started → completed / failed | none (the element stays `held`) |
| **`place_release`** | received → accepted / rejected → started → **completed** / failed | started: `placing`; completed: `released` (cycle + 1); failed: `held` (not completed) or `uncertain` |
| **`repeat_placement`** (Retry in this workflow) | received → accepted / rejected → started (the new attempt has begun: corrections reset) → **completed** / failed | started: `placing`; completed: `released` (cycle + 1, attempt + 1) |
| `retry` (old workflow only) | unchanged | not available in `released_recovery_v1` |

**Facilitator stages:**
- `facilitator_review` = waiting for the facilitator's approval;
- `facilitator_assist` = the facilitator is assisting or executing the recovery.

They have their own long client timeout (provisional 120 s, a system fault, not a participant limit), because they depend on a person.

**A rejected or failed recovery is not a participant error.** It is shown neutrally ("Recovery not completed"), is not counted against the participant, and the element simply stays released, or becomes uncertain.

---

## 5. Bounded corrections, including rotation

- **Translation is unchanged:** `along_rail` and `across`; steps 1, 2, 5 mm; ±15 mm per axis.
- **Rotation (new):** one rotational axis, id `rotation`. It is a **convention-neutral label**. Its physical definition (which axis, sign and origin) must match the placement geometry and the coordinate convention agreed with CRATER/AIML [D].
- **Rotation settings (provisional simulation values, not approved limits):** steps 0.5, 1 and 2°; ±5°; selectable like the millimetre steps.
- **Wire format:** a rotation nudge carries `step_deg` instead of `step_mm`. Cumulative values are reported as `cumulative_commanded_mm {along_rail, across}` plus `cumulative_commanded_deg {rotation}`. Inside the code they are integer micrometres and millidegrees.
- **One allowance** `max_nudges` (provisional 12) per attempt covers both kinds. Rejected nudges use none. Accepted nudges use one even if they fail.
- **Reference frame [P, D]:** the commanded correction is the **accepted cumulative commanded offset relative to the attempt's programmed placement pose**.
  - It is not reset by a recovery; corrections accumulate across recovery cycles in the same attempt.
  - It is reset only when a Retry's new attempt has begun.
  - Whether the real cell places relative to the programmed pose, the nominal target or the re-grasped in-hand pose is a commissioning question. The re-grasp capture range of the tapered recesses also matters.
- **Displayed** is the commanded value only ("not a measured position"). The simulator also logs a hidden "achieved" value. The internal pose models (§8) are backend-only.

---

## 6. Retry, recovery and fresh attempts

**The problem:** a released element cannot simply be "retried". The robot is not holding it.

**Options:**

| Option | Meaning | Assessment |
|---|---|---|
| A. Remove Retry | Corrections only | Loses the "let the robot redo it" choice, which the AI2 framework used |
| **B. Retry from the held state [P, implemented]** | After a recovery, *Retry placement…* discards the commanded corrections and repeats the programmed placement as attempt + 1, with release, retreat and settling | Distinct from adjustment; needs no extra robot capability; the participant's two exits from `held` are "place with my corrections" and "repeat the standard placement" |
| C. Compound Retry from `released` | One request = recover + repeat placement | Hides a recovery inside a "retry"; recovery outcomes and facilitator involvement become ambiguous to log and to the participant |

**Open questions [D]:**
- whether a retried attempt repeats the same prescribed variation (a systematic robot error) or none. This is configurable per scenario as `retry_variation: same | none`; the simulation default is `same`;
- whether a fresh attempt should also re-pick from the supply.

---

## 7. Video and visibility

- **Viewing rules are unchanged** (§1).
- **Robot and task state** come only from backend messages; **video state** comes only from the receivers.
- **Proposal [P, D]: motion needs live video.** `motion_video_policy` controls what happens to motion requests (recover, nudge, place_release, repeat_placement) when the on-screen camera is not live:
  - `require_live`: refused. The client greys the controls out ("Movement requests need live video"). The backend refuses independently (`video_unavailable`).
  - `development_override`: accepted, and every override is logged by the backend (`video_policy_override`). It exists **only** so that simulated workflows can be tested with the short offline recordings. **It is not a permission for blind physical corrections.** The live backend must use its own video-health source, not the client's report, and must enforce the agreed prerequisites.
- **Allow and Inspect stay available** during interrupted video, as before (D8). They are logged with the video state.
- **Simulation note:** the recorded video does not show recovery, adjustment or placement. Feedback comes from status, lifecycle and element state only.

---

## 8. Hidden ground truth (backend only; never sent to the client)

| Item | Simulation model (placeholder, no physics) |
|---|---|
| Prescribed placement variation per element | `variation {along_rail mm, across mm, rotation deg}` |
| Architecture condition | `architecture {name: lunar_lantern \| regolight, capture_mm, capture_deg, slide_fraction}` |
| Re-grasp error after recovery | `regrasp_error` |
| Resulting released pose error | placed = programmed variation + commanded correction + re-grasp error. If every component is within the capture tolerance the element **seats** (error 0); otherwise it stays misaligned, scaled by `slide_fraction` |

- These are logged as `placement_result`, `nudge_result` and `recovery_result` in the backend log, with commanded and achieved values.
- The leak test extends to them: the client stream and its timing must be identical whatever the hidden variation, architecture or settling outcome.
- **Scope of the leak test (researcher clarification, 12 Nov 2026).** The leak tests guard against **unintended interface cues and supplementary information**: messages, wording, availability, timing or any other system-generated content that could reveal a hidden condition, the prescribed variation, the settling outcome or placement correctness.
  - **Not leaks:** legitimate differences in the **observed physical construction state**, meaning what the cameras show of the placed element. These are the essential experimental stimuli and must not be treated as information leaks.
  - **Why the simulation tests are strict:** the recorded video does not change with the hidden state, so no visual difference exists there. In the real cell, the video of the resulting placement is expected to differ by condition, and that is the point of the experiment.

---

## 9. Logging (client log, existing `EventLog` schema)

| Requirement | Records |
|---|---|
| Initial AI2 choice | `choice` (allow, inspect, **intervene**; the last is new in this workflow); `cdp_summary.first_choice` and `first_action_latency_ms` |
| Confirmed intervention request | `choice{recover}` then `commit{recover}` (the confirmation); the same for `place_release` and `repeat_placement` |
| Recovery request and acknowledgement; facilitator involvement; execution and outcome | `request_sent` / `_received` / `_facilitator_review` / `_accepted` / `_rejected` / `_started` / `_facilitator_assist` / `_completed` / `_failed`; `request_summary` with facilitator durations |
| Secure-grasp confirmation | `element_state{held, cause: secure_grasp_confirmed}` plus `secure_grasp_confirmed` |
| Translational and rotational nudges | nudge events with axis, direction and `step_mm` or `step_deg`; reported cumulative mm and deg |
| Commanded against achieved | backend only: `nudge_result`, `placement_result`, `recovery_result` |
| Place and release, and reassessment | `request_*` for `place_release`; `element_state{released}`; `reassessment_begin{cycle}` |
| Closure | `decision_close` plus **`cdp_summary`**: cycles, attempts, recoveries, nudges by axis, placements, and **participant decision time** separated from **technical execution time**, **facilitator time** and **paused time** |

Every record carries the CDP token, `cycle`, `attempt`, `element_state` and the existing view and displayed-frame context, so all corrections remain traceable to one CDP.

---

## 10. Failure handling

| Situation | Behaviour |
|---|---|
| Recovery rejected (by the backend or the facilitator) | Element stays `released`; neutral message; Allow and Intervene are available again |
| Recovery unsuccessful | `failed: recovery_unsuccessful`; the element stays `released`; the participant may Allow, Inspect or request recovery again (within the allowance) |
| Recovery or placement uncertain | `failed: state_uncertain`; element `uncertain`; everything except viewing is locked; the facilitator resolves it (simulated after `uncertain_resolve_ms`) → `released` |
| Place and release not completed | `failed: placement_not_completed`; the element stays `held`; the participant may nudge, place again or retry |
| No receipt or completion | the existing *Unconfirmed* system fault; never re-sent |
| Experimenter pause | an operation already started completes; new requests are refused (`paused`); Allow is refused while paused |
| Link loss | messages lost; on reconnection the snapshot carries `element_state`, `cycle`, `attempt`, both cumulative values and the recovery count; the client resolves its outstanding request (completed, in flight or lost) and adopts the backend state |

---

## 11. Researcher decisions on S3.1 (12 Nov 2026; provisional)

S3.1 is accepted as the functional baseline: the released-element workflow, facilitator-assisted recovery, the secure-grasp requirement, individual translational and rotational nudges, controlled Place and release, and reassessment.

| # | Decision | Implementation status |
|---|---|---|
| C1 | **Retry remains available after recovery** and repeats the original programmed placement, **including its prescribed experimental variation**; it discards participant adjustments | As implemented: option B, `retry_variation: same` |
| C2 | **Corrections remain relative to the programmed placement pose.** Physical commissioning must establish the repeatability of the recovered tool-to-element relationship before this is accepted for real robot operations | As implemented; commissioning item |
| C3 | Rotational axes, signs, step sizes and bounds **remain provisional** pending physical commissioning | Unchanged (one axis; 0.5, 1, 2°; ±5°) |
| C4 | **Facilitator-assisted recovery is the baseline physical recovery strategy** | Modelled (review, assist, reject; uncertain states resolved by the facilitator) |
| C5 | Provisional allowance of **three recoveries per decision point**, configurable rather than fixed in code | As implemented: `max_recoveries` in the scenario (default 3) |
| C6 | Real robot operations require **agreed visual-access, backend-state and safety prerequisites**. The development override for unavailable video is **not** permission for blind physical operation | `development_override` stays simulation-only; the live prerequisites are to be agreed |
| C7 | **Preserve placement (cycle) and attempt identifiers in experimental logs**; their participant-facing presentation may be simplified later | Logged on every record (`cycle`, `attempt`); presentation unchanged for now |

**Known UI refinements for later (not implemented, by the researcher's instruction):**
- confirmation text overlap in the recovery and Retry confirmations;
- the dense Adjust panel;
- small stage labels;
- progressive disclosure of the recovery, adjustment and placement controls;
- possible simplification of the participant-visible action history.

## 12. Decisions originally requested (superseded by §11)

| # | Question |
|---|---|
| C1 | Retry semantics: option B (implemented), A or C; and the retried variation (`same` or `none`) |
| C2 | The correction reference frame and whether corrections persist across recoveries (implemented: relative to the attempt's programmed pose, persisting until Retry) |
| C3 | The rotational axis, sign convention, step sizes and limits (simulated: one axis, 0.5 / 1 / 2°, ±5°) |
| C4 | The facilitator procedure: when review or assistance happens, the physical recovery method, and who resolves uncertain states |
| C5 | `max_recoveries` per CDP (simulated: 3) and whether recovery attempts are limited at all |
| C6 | The visibility prerequisites for motion in the live system (`require_live` proposed) |
| C7 | Whether participants see the placement cycle number ("placement 2") |

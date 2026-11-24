# Manual trial walkthrough — change notes (24 Nov 2026)

Run: `twin_link/start_twin_trial.ps1` (nominal taught protocol, web consoles). Notes are collected during the run; nothing is implemented until the list is agreed.

## A. Participant ID screen (first screen)
- A1. Centre all elements. Show ONLY: (1) "Enter Participant ID", (2) the text box, (3) the Start session button, (4) "Lunar Architecture Research Group" with the LARG logo at the bottom (`design/LARG SAL LOGO on black.png`).

## B. Facilitator A go-ahead points
- B1. Facilitator A is asked for the go-ahead ONLY:
  1. before the onboarding video starts;
  2. once before the practice sessions start;
  3. once before each of the 12 trials.
- B2. Keep the competency outcome gate (Competent / More practice), but remove the "Done" click that currently comes before it.

## C. Session flow
- C1. Remove the refreshers. Flow: onboarding video → two training tasks (one on screen / 2D, one in VR / XR) → straight to trial 1.

## D. General layout
- D1. Centre all text throughout the interface, including the confidence rating screen.

## E. Decisions (24 Nov, after the run)
- E1. Facilitator A gives all three go-aheads (before onboarding video, before practice, before each of the 12 trials).
- E2. Before each trial: ONE A click replaces A "baseline", A "robot ready" and B "participant ready" (system still waits for video + twin).
- E3. Drop all other facilitator steps: block intro/condition change, break, Survey B, post-session questionnaire, closure (questionnaires recorded outside the system). B keeps the competency outcome and wellbeing/withdrawal buttons.
- E4. Practice runs = short twin task (about 4 RegoLight placements, one CDP + one SAGAT probe), once 2D, once "XR" (on Windows); not analysed.

## F. Implemented 24 Nov (UNCOMMITTED; Unity tree)
- Protocol flag `facilitation.gates: "facilitator_a_minimal"` (new; default "standard" keeps every other protocol and the e2e quickcheck unchanged). Manual protocol `phase2_s41_corol_regolight_nominal_taught.json` → 0.2.0: gates minimal, `refreshers` removed, phases `practice_2d` / `practice_xr` (scenario `RG-PRACTICE`: architecture `regolight_practice` = RG-P01..P04 from the RegoLight baseline, CDP + SAGAT at P03, familiarisation text in the briefing), additional practice 1 run (provisional).
- New A action `go_ahead` (console buttons "Start video" / "Start practice" / "Start trial N"); B only Competent / More practice; practice runs send no trial identity (twin runs them nominal).
- ID screen: centred prompt, field, Start session; LARG logo + "Lunar Architecture Research Group" at the bottom (logo copied to `Assets/Phase2/SiteWindow/Resources/LARG_logo.png`); black background.
- Session screens and confidence prompt centred (text, Continue button, scale row); long briefings push Continue down.
- Tests: new `MinimalFlowTests` 4/4; EditMode 261/263 (2 = C09 clock check after today's +1 h system clock step; environmental). S4 player rebuilt; not yet run by hand; e2e regression not yet rerun.
- Not done: Site Window panels (status band, View/Adjust wings) are not re-centred — to confirm.

## G. Second manual run (P912) feedback, implemented 24 Nov evening (UNCOMMITTED)
- G1. Go-aheads before the onboarding video and the practice runs → Facilitator B; A keeps the per-trial go-ahead.
- G2. Inspect outside a decision point no longer holds the robot: it opens the view controls (camera/zoom/pan) while construction continues (`simulation.inspect_without_hold`); ends by itself when a decision point opens (primary view). Intervene still asks for a hold.
- G3. Practice = 2 placements: P01 nominal, P02 decision point + SAGAT.
- G4. "Stuck after practice" = P912's first block was Lunar Lantern; the twin refused its baseline (no LL geometry). Researcher chose: LL blocks run the RegoLight trial as a logged development substitution (`development_substitutions.architectures`).
- Protocol 0.3.0; MinimalFlowTests 5/5; EditMode 262/264 (C09 clock only). S4 player rebuilt; relaunched for a manual run.

## H. Third manual run feedback, implemented 24 Nov night (UNCOMMITTED; Unity + twin repo)
- H1. Before EACH practice run (desktop, headset, any additional practice) BOTH facilitators give a go-ahead: B (participant ready) and A (site reset, robot ready). Video: B only; trials: A only.
- H2. Confidence overlay: "Please answer the question below" instead of "PAUSED".
- H3. Status band: fixed labels ROBOT STATUS / VIDEO STATUS; changing text shortened (Placing, Live, Delayed …). Presentation only; logged status strings unchanged.
- H4. Video plate corners rounded (radius 10, concentric with the outline, now radius 16).
- H5. Hold before the descent (researcher: hover over the target; continue or adjust, then place): Intervene during a NON-CDP placement → twin host POST /api/hold → place_pNN stops at the hover above the receiving pose and lowers to the hold height (120 mm; same hold record as after recovery) → decision opens with the brick HELD → Intervene pad (nudges) → Place and release (no nudges = normal placement) → Allow. Too late (descent started) = as before (released, then held). Formal CDP placements always complete first (observation/SAGAT design unchanged). Protocol flag `simulation.hold_before_place` (manual protocol 0.4.0 only).
- Found/fixed: the client rejected element_state causes `recovery_not_started` / `placement_not_started` (sent by the twin backend when a motion is refused before moving) as protocol errors; now accepted.
- Tests: EditMode 264/266 (C09 clock only); new MinimalFlowTests 7/7; twin `twin_link/twin_hold_check.py` 7/7 (hold before descent, nudge 10.01 mm realised, late hold = normal, refusals).

- C2. SAGAT familiarisation is no longer a separate phase: it is folded into the two interface practice runs (2D and XR).

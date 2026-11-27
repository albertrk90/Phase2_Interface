# Placement variations (both architectures), SAGAT ideas, onboarding video contents (27 Nov 2026)

Source: `Albert/phase2/variation_schedule.py` (v2.1), `trial_plan.py`, `lantern_plan.py` and `docs/lunar_lantern/README.md`. Simulation (digital twin) only.

## 1. How the variations are introduced

### Common to both architectures
- **Trial:** about 16 placements. There are 3 potential critical decision points (CDPs): early, middle and late, at placements P05, P10 and P14.
- **Active CDPs:** in each trial, 2 of the 3 are active (the participant decides Allow or Intervene); the third is inactive and runs nominally.
- **SAGAT freeze:** exactly one per trial, at one of the two active CDPs.
- **Over a participant's 6 trials on one architecture** (2 blocks × 3):
  - each (active pair, SAGAT location) combination occurs once;
  - each active pair occurs once per block.
- **Errors appear only at active CDPs.** Every other placement is nominal, including the inactive CDP.
  - Per participant and architecture: 12 active-CDP slots, made up of 8 errors and 4 nominal.
  - Every trial has at least one error, and so a trial can contain one nominal active CDP. This means "the robot stopped for a decision" does not mean "something is wrong".
- **Error sizes:**
  - three bands: small, medium and large;
  - each participant gets a 3/3/2 split over their 8 errors, and the band that occurs twice rotates over participants;
  - each block contains all three bands.
- **Repetition:** no participant meets the same (placement, offset) twice.
- **The error is in where the robot releases the element, not in the element itself.** The robot follows its programmed path to a release pose that has been shifted, lets go 10 mm short, and the element settles where it lands. The participant sees the result while the robot hovers above it, wrist camera looking down at the element just placed.
- **No rotational errors in either architecture.** Every error is a pure translation; the element's orientation is always the nominal one.
  - RegoLight once had an 8° rotation case in development, but it is not in the schedule; the schedule notes rotation as a "nice to have later".
  - The interface can show rotation nudges, but only when the backend offers them.
- **No other kinds of error either:** no dropped or broken elements, no wrong element, no missed pick, no robot fault, and no change in the image (the cameras show the true state).

### RegoLight (brick wall on a 30° slope)
- **Error:** the release pose is shifted horizontally by whole centimetres in 2D, both along the rail and across it (away from or towards the rail).
- **Bands by distance from the nominal seat:** small 2–3 cm, medium more than 3 up to 5 cm, large more than 5 up to 8 cm.
- **What it looks like:** the brick is lifted just enough to clear what is there, so it **rests on its neighbours or the formwork**, displaced and raised, not seated. Contact is scripted, not physics.
- **Correctable exactly:** the ideal seat is a whole number of 10 mm nudges away, at least 2 cm inside the 10 cm nudge limit.
- **Uniqueness:**
  - medium and large (placement, offset) errors are unique across the whole study;
  - each small one is used at most 3 times, because only 20 small offsets exist per location.

### Lunar Lantern (plates set into tilted pockets on a curved formwork; 12 rows)
- **Error:** the plate's line of descent is shifted **along the row only** (1D: + is away from the rail side) by 10, 20 or 30 mm (small, medium, large), with the sign drawn.
- **What it looks like:** the plate comes down its own axis and stops at first contact, **perched up its axis** instead of sitting in its pocket: about 21, 45 and 65 mm up for 10, 20 and 30 mm.
  - At these decision points the robot holds at the hover above the plate.
  - Whether a real plate stays perched or slides into its pocket is open until commissioning.
- **Few offsets:** only 6 per location (±10, ±20, ±30). Study-wide uniqueness is therefore impossible.
  - Per participant: no repeats, and signs balanced (4 + / 4 −).
  - Across the study: the least-used offset is preferred.
- **Adjust panel:** shows only "Away from rail" / "Towards rail". There is no along-rail control and no rotation control.
- **Rows tilt from 57° (row 1) to 8° (row 12).** The trial uses rows 5–7, so error severity also reads differently by row.

### Interventions (the participant's options at a CDP)
- **Allow:** the error, if any, stays and the trial goes on.
- **Intervene:**
  1. Recovery: Facilitator A takes the element out and stands it in the recovery stand, and the robot picks it up again.
  2. Hold: the robot holds the element on the original, erroneous line.
  3. Nudges: the participant makes 10 mm adjustments, one at a time, with the stage of each shown.
  4. Then either "Place and release" or "Retry". Retry repeats the programmed placement, error included; the adjustments are discarded.
- A decided element is settled into its pocket or seat at the start of the next placement.

## 2. What kinds of SAGAT questions this supports (ideas)
SA levels follow Endsley: L1 perception, L2 comprehension, L3 projection. The freeze happens at an active CDP, either before the decision or partway through an intervention.

**L1: perception (what is there)**
- Has the element just placed reached its intended position? (Yes / No / Can't tell)
- Which direction is it displaced?
  - RegoLight: along the rail / across / both.
  - Lantern: away from the rail / towards the rail / none.
- Roughly how far? (none / about 1 cm / about 2 cm / 3 cm or more)
- Is the element seated, resting on neighbours, or perched?
- Lantern only: is the plate's tip inside its pocket?
- What is the robot doing right now? (holding above / descending / retreating / waiting for a decision)
- Which placement number or row is it working on? How many remain in this trial?
- Which camera view were you just looking at? Is the video live or interrupted?

**L2: comprehension (what it means)**
- Is the current state acceptable as is? (Tolerable / needs adjustment / unclear)
- Use the ground-truth categories in the methodology: converging, tolerable residual, unresolved or ambiguous, consequential, obstructed or failed.
- Would the next element be affected if this one stayed as it is? (RegoLight: the neighbouring brick or course; Lantern: the next plate in the row or the plate above.)
- Is there enough visual evidence to judge? Which view would settle it?
- After nudges (a freeze mid-intervention): how far has the element been moved in total, and which way? Is the element now closer to or further from the target?
- What did the last nudge request do: accepted, rejected or still moving?

**L3: projection (what happens next)**
- If you Allow now, what happens to the next placement?
- Lantern: will the next plate in this row fit?
- RegoLight: will the next brick sit properly?
- How many more nudges of 10 mm are needed to reach the target? (0 / 1 / 2 / 3+)
- If you press Retry, where will the element end up? This tests the trap: the error is repeated, because Retry discards the adjustments.
- If Place and release is pressed now, will the element seat?
- What will the robot do after this decision?

**Tips for the bank**
- Keep parallel wording across architectures, and change only the nouns and directions: brick / plate; along rail + across / along row. That way the answers can be compared.
- Include nominal-CDP freezes, where the correct answer is "on target / no action needed". These check for a "stopped means wrong" bias.
- Give every question a ground truth computable from the twin log: offset sign, size, band, robot stage, cumulative commanded offset, placement number. Avoid questions only a human rater could score.
- Do not ask about rotation, and keep "both axes" questions to RegoLight only, since lantern errors are 1D.
- Add "Can't tell" as an option where evidence may genuinely be missing (occlusion at P01, P06 and P12 from the site camera on the lantern).
- Keep each architecture's bank long enough for a different item mix per freeze: 6 trials, so 6 freezes per architecture per participant.

## 3. Onboarding video: what it could include
Target length: about 4–6 minutes. Show the real interface and the robot in the twin, not slides.

1. **Purpose and roles (30 s):** the participant supervises a construction robot remotely. Facilitator A is the on-site helper; Facilitator B runs the session. Say that it is simulation-backed and that nothing they do is unsafe.
2. **The two architectures (45 s):**
   - RegoLight: bricks laid on a sloped wall.
   - Lunar Lantern: plates set into tilted pockets row by row.
   - Show one nominal placement of each, and what a good final seat looks like.
3. **The screen (60 s):**
   - video area with the wrist and site cameras;
   - the View wing (Inspect: change camera, zoom);
   - the Adjust wing;
   - the decision keys (Allow / Intervene);
   - the status strip: Live / "Video interrupted", the robot stage, the trial counter.
   - The same tour in XR, for the XR blocks.
4. **A decision point (45 s):** the robot stops above the element it just placed and waits. Inspect, then choose:
   - Allow if the placement is acceptable;
   - Intervene if not.
   - Some stops are fine as they are; a stop does not mean something is wrong.
5. **Intervening (90 s), one worked example per architecture:**
   - recovery by Facilitator A and the re-pick;
   - nudges one at a time, watching each go sent → accepted → moving → done;
   - the RegoLight controls (along rail / across), against the Lantern controls (Away from / Towards rail);
   - the nudge limits;
   - then Place and release, against Retry. Retry repeats the original placement and does not keep the adjustments.
6. **SAGAT freezes (30 s):** the screen may blank and questions appear. Answer from what you knew just before. There's no penalty for "don't know", and the trial resumes where it stopped.
7. **Session flow (30 s):**
   - 4 blocks (architecture × interface), 3 trials each;
   - the "Trial x of 12 complete" screen;
   - surveys after trials 3, 6, 9 and 12;
   - a practice run before the first block of each architecture.
8. **What to expect from video (15 s):** the image may briefly freeze or show "Video interrupted"; keep supervising as normal.
9. **Closing (15 s):** there are no trick buttons. Take the time you need, but decide as you would on a real site. Ask the facilitator if anything is unclear.

**Recording notes:**
- Record from the S4 player with a development id (P9xx) so nothing touches participant data.
- Use the same captions in 2D and XR.
- Avoid showing any real participant's schedule, and avoid any SAGAT question from the real bank.

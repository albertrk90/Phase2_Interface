# Phase 2: status and next steps (end of 26 Nov 2026)

This is the resume point for the next session. Everything below is simulation only.

## Where things stand
Both architectures now have errors and interventions in the twin.
- **RegoLight:** unchanged.
- **Lunar Lantern:** errors along the row and every intervention (recovery stand, along-row nudges, place-and-release, Retry, hold before the descent). Details: `docs/lunar_lantern/README.md`, "Update (26 Nov 2026)".

## Done today
1. **Housekeeping:** committed the 25 Nov status doc; refreshed the OneDrive Unity bundle (`Phase2Client_unity_20261126_1017.bundle`, master `7ef85c7`).
2. **Recovery stand:** your corrected model is merged into the twin scene (22.5 mm slot). The robot picks from rail 8473 mm.
3. **Lantern errors, schedule v2.1:**
   - Line of descent shifted along the row by 10, 20 or 30 mm; the plate rests at first contact, perched about 21, 45 and 65 mm up its axis.
   - CDP allocations and RegoLight entries unchanged (the Unity export changed only its version and hash; re-embedded in the protocol).
   - Bands re-dealt for P19, P21–P23.
4. **Lantern interventions in the trial host**, planned on 11 lines per placement (−50 to +50 mm).
5. **Interface:**
   - Lantern nudge: "Along row +/−" only.
   - One practice run per architecture: practice 1 follows block 1; practice 2 is the other architecture on the other interface.
   - Protocol `0.8.0-lantern-interventions-dev`. S4 player rebuilt.

## Verification (26 Nov)
- Lantern check 14/14.
- Schedule check 8/8 (288 trials match).
- HOME 6/6.
- Hold 7/7.
- RegoLight e2e 15/15 (also with the rebuilt player).
- Unity EditMode 280/282: the 2 failures are the C09 clock reference after a reboot (regenerate with `Tools/make_clock_reference.py`).

## Afternoon and evening: two manual runs (P03) and fixes
**After the first manual run:**
- **Decision view:** at the decision points (CDPs only), the lantern stops at the hover up the plate axis, so the wrist camera sees the plate just placed. RegoLight already ended at its hover.
- **Lantern speed:** the approach moves near the formwork were too fast (up to about 258°/s at one joint). Each straight-line move now has its own speed, keeping every joint at or below 28.6°/s.
- **Clearance after the stand pick (mm):** the gripper stays 105 mm or more from the formwork, and the arm 52 mm or more. The held plate comes within 41 mm of the placed plates and 34 mm of the formwork, both on the final approach to the hold.
- **Nudge buttons:** relabelled "Away from rail" / "Towards rail".
- **After each trial:** a "Trial x of 12 complete" screen, with a go-ahead needed from both A and B. After trials 3, 6, 9 and 12, the participant is told to do the survey with the facilitator.
- **Block screen:** names the condition, e.g. "Block 1 of 4 · Lunar Lantern on the 2D screen". Both facilitators see the current and next block.

**After the second manual run:**
- **"Link lost" at the end:** this was the S4 build's own 2-hour limit (`maxSeconds` 7200), which ended P03 partway through block 4. The limit is now 12 hours, in both the build and `start_twin_trial.ps1`.
- **Lantern after an intervention:** place_release and Retry now also wait at the hover over the re-placed plate for the next decision.
- **Block title:** kept on one line (shrinks to fit); the "Viewing: …" line was dropped.
- **SAGAT data:** questions from the lantern bank and the generic practice items were logged as RG-2. They are now logged as `placeholder_<bank>`.
- **Facilitator web pages, status panel:**
  - fixed boxes: Situation on top, then Participant, Robot (twin) and Stage;
  - below them, the block cards with three trial bars each and a "Trial n of 12" counter;
  - practice runs count as training;
  - the role box no longer lists past button presses.

**Verification:** lantern check 14/14 (it now also checks the pause after release and Retry), RegoLight e2e 15/15, relay 9/9, EditMode 281/283 (C09).

## Next, in priority order
1. **SAGAT questions for both architectures** (decided 26 Nov): rewrite the RegoLight questions and write the Lunar Lantern ones together. The lantern bank is still three development placeholders.
2. **Physical realism of lantern errors** (decided: twin only for now). At commissioning: does a real plate stay perched, or slide into its pocket?
3. **CDP ranges** (early, middle and late as ranges rather than P05, P10 and P14). Note P16's + lines can't be entered directly: a CDP at P16 would need its errors on the − side, or a replan.
4. **Onboarding video:** the real clip.
5. **The small changes from the 25 Nov P01 run** (deferred; you didn't remember them).

### Loose ends
- Mohsi's feedback on the 24 Nov videos.
- Physically: 90 lantern plates and the recovery stand.
- The planner takes about 30 min (11 lines × 16 placements); re-run it after any change to the scene or the grasp.

## How to run things
As on 25 Nov (`docs/plans/2026-11-25_status_and_next_steps.md`), plus:
- **Lantern check:** `twin_link\twin_lantern_check.py` (14 checks; about 8 min).
- **Planner:** `..\..\..\.venv\Scripts\python.exe lantern_plan.py`, from `Albert\phase2`.
- **Schedule:** `variation_schedule.py --v2 [--check] [--export-unity PATH]`, then `Tools/embed_participant_schedule.py`.
- **S4 player:** `Unity.exe -batchmode -quit -projectPath <Phase2Client> -executeMethod Phase2.EditorTools.S4Build.BuildPlayer`.

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

## Next, in priority order
1. **Your manual run with a Lunar Lantern block** (P01, block 1 = A). Look at the errors, the stand recovery and the "Along row" panel. Also the small changes from the 25 Nov P01 run, if you remember them.
2. **Physical realism of lantern errors** (decided: twin only for now). At commissioning: does a real plate stay perched, or slide into its pocket?
3. **CDP ranges** (early, middle and late as ranges rather than P05, P10 and P14). Note P16's + lines can't be entered directly: a CDP at P16 would need its errors on the − side, or a replan.
4. **SAGAT question bank** rewrite (root-level bank file plus embed tool).
5. **Onboarding video:** the real clip.

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

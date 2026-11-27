# Phase 2: status and next steps (end of 27 Nov 2026)

This is the resume point for the next session. Everything below is simulation only.

## Where things stand
- **SAGAT:** the researcher's question bank v2 runs in the live protocol as a draft, with a counterbalanced set per freeze.
- **Facilitator B** can end a session and get the system ready for the next participant.
- **Pilot IDs P901–P924** run exactly the plans of P01–P24.
- **Restarts** (trial, block, session) are built but **not working properly live**; testing is deferred.
- **All earlier participant data was deleted** at the researcher's request.

## Done today
1. **Briefs for the researcher:**
   - how placement variations work in both architectures, with SAGAT question ideas and onboarding contents: `docs/plans/2026-11-27_variations_brief_for_SAGAT_and_onboarding.md`;
   - the onboarding video script, draft v0.1: `docs/plans/2026-11-27_onboarding_video_script_draft.md`.
2. **SAGAT bank v2** (`docs/sagat/sagat_question_bank_v2.csv`, draft). Details in `docs/sagat/README.md`.
   - **Import:** `Tools/import_sagat_bank.py` copies only the text, options and SA level into the protocol. Answer rules and notes stay in the CSV, which is pinned by its sha256.
   - **Sets 5 and 6:** pending validation. They are allocated, but each freeze that uses them is flagged.
   - **Allocation v2** (`Tools/sagat_set_allocation.py`): one complete set per measured freeze. Each set is used exactly:
     - 12 times in 2D and 12 in XR;
     - 8 times each at early, middle and late;
     - 12 times in the participant's first block of the architecture and 12 in the second;
     - 8 times each at trial position T1, T2 and T3.

     Block order is read from the schedule, never changed. Unity refuses the allocation if a participant's Williams sequence differs.
   - **Practice probes:** the generic items. Development IDs get sets 1–3, then 4–6.
   - **Logged:** item IDs, bank version, the assigned set, presented options and responses. The freeze state is labelled simulated, and responses are unscored.
   - **Protocol:** `0.9.0-sagat-bank-v2-dev`.
3. **Facilitator consoles:**
   - the block cards are on top;
   - participant and session moved into the Situation box, and the separate "trial n of 12" line is gone;
   - the Participant / Robot / Stage boxes have a fixed height, so nothing jumps;
   - on the participant ID screen the pages stay connected ("waiting for a participant ID").
4. **End session / next participant (B):**
   - **Ready for next participant** after a normal close, or **End session and get ready for the next participant** (under More) at any time.
   - What happens: the session closes, the robot goes HOME, and the participant app restarts on the ID screen. The twin, host, renderers and relay keep running.
   - Fixed after the P901 run: a session ended during practice now closes at once (before, it waited out a 3-minute limit).
5. **Pilot mirrors:**
   - P901–P924 run P01–P24's plan (sequence, CDP allocations, the twin's errors, SAGAT sets), recorded under the pilot ID.
   - P900 and P925–P999 stay development IDs.
   - Unity names the mirror and the twin checks it.
6. **Restart dropdown (B):** restart trial, block or session, each needing a second click; A's go-ahead comes before anything moves. **The researcher found it not working properly in the live run.** The live protocol's replacement limits are now 1 per block and 2 per session (they were 0 and 0).
7. **Data:** deleted all session folders, the allocation register, archived session folders, relay logs, and the twin host's ledger and run directories. Kept: automated check evidence, taught poses, scene state.
8. **Scripted demo check fixed:** 24/24 again. The script now waits while the training-media placeholder plays; for four days that overlay had blocked every click.

## Verification (27 Nov)
- Unity EditMode 293/295. The 2 failures are the C09 clock reference after a reboot; regenerate with `Tools/make_clock_reference.py`.
- New tests: SagatQuestionSetTests 7/7, RestartTests 3/3, plus pilot-mirror and discontinue-during-practice tests.
- Tool tests pass. Twin `test_variation_schedule` 16/16. Twin schedule check 10/10, including S8/S9 for pilot mirrors.
- Relay console check 9/9.
- Scripted S4 player 24/24; session verifier 23/23.
- End-session live test without the twin passed (old app out in 2 s, new app on the ID screen). With the twin it worked after the practice fix, apart from the wait for an in-flight placement.

## Commits (all pushed)
- **Unity:**
  - `6a7082d` SAGAT bank v2;
  - `e00a5e7` allocation v2;
  - `0135606` console layout;
  - `79befde` end session, pilot mirrors and restarts;
  - `980485a` scripted check fix.
- **Twin:** `259b2ed` pilot mirrors.
- **Root:** `b0b1240`, `67db5f8`, `51c0897`, and this doc.
- **OneDrive bundle:** `Phase2Client_unity_20261127_1600.bundle`.

## Next, in priority order
1. **XR (Quest 3) interface:** starts Monday (researcher). Android build support is installed; no XR packages yet (installing them needs approval).
2. **Restarts:** triaged in `docs/plans/2026-11-27_restart_triage.md`. Root cause: after a trial stops mid-placement, the new trial's twin baseline is rejected as "busy" and never re-sent, so the reset hangs. Fixes 1–6 are listed there. Also delete the test session S4-P01-01 and P01's allocation entry before the real P01.
3. **Onboarding video:** the researcher reviews the script draft (open points at its end), then records it with ID P950.
4. **SAGAT before pilots:**
   - check the five-option question screen on screen;
   - decide on sets 5 and 6 (keep them, or swap them out until validated);
   - scoring comes later, keeping simulated keys apart from physically verified ones.

### Deferred
- Physical realism of lantern errors (after Mohsi's go-ahead for the real robot).
- CDP ranges.

### Loose ends
- Mohsi's feedback on the 24 Nov videos.
- Physically: 90 lantern plates and the recovery stand.
- **Observation interval:** settled. 1 s look-only, then no time limit on the decision; the protocol note is corrected. SAGAT set 6 needs a longer interpretable interval before it can be validated.
- **Onboarding script:** answers recorded. Survey B at block end, breaks any time, synthesised narration.

## How to run things
As on 26 Nov (`docs/plans/2026-11-26_status_and_next_steps.md`), plus:
- **Participant IDs:** P01–P24 study; P901–P924 pilot of P01–P24; P900 and P925–P999 development.
- **SAGAT bank:**
  ```
  python -I Tools/import_sagat_bank.py --csv ../../docs/sagat/<bank>.csv <protocol>
  python -I Tools/sagat_set_allocation.py --protocol <protocol> --embed <protocol>
  ```
  From `unity/Phase2Client`, using the twin venv. The allocator takes about 80 s.
- **Scripted player check:** `powershell -ExecutionPolicy Bypass -File Tools\run_session.ps1 -Script`

# Phase 2: status and next steps (end of 25 Nov 2026)

This is the resume point for the next session. Everything below is simulation only.

## Where things stand
Both architectures run end to end in the twin with the participant interface (S4 player, trial host and facilitator relay).
- **RegoLight:** the mature path. It has the variation schedule's errors at the CDPs, every intervention (recover via the recovery slot, nudges, place-and-release, Retry) and hold before the descent.
- **Lunar Lantern:** placement runs nominally on the twin with the taught grasp. It has no errors yet, and its interventions are refused before any motion.

### Repos (all in sync with their remotes, 25 Nov evening)

| Repo | Remote | Head |
|---|---|---|
| Twin `lab_digital_twin`, branch `albert-phase2-alpha` | GitLab (Mohsi) | `86cbe49` |
| Unity `Phase2Client` | GitHub `albertrk90/Phase2Client` (private) | `7ef85c7` |
| Root `Phase2_Interface` | GitHub `albertrk90/Phase2_Interface` (private) | `b60f0dd` |

The OneDrive Unity bundle has **not** been refreshed since `c6b4574`.

### Done in this round (24–25 Nov)
1. **Repos:** explained the three repos; moved Unity and root to private GitHub; archived `backups/` and `_archive/` to OneDrive, then deleted them locally.
2. **Study CDP allocation:** P01–P24, Williams sequences by ID, P9xx = development IDs. This is variation schedule v2, and all 288 Unity allocations are accepted by the twin.
3. **Interface polish:**
   - The onboarding video: play, pause and replay; Continue only appears at the end; Facilitator B can skip it; a stand-in clip plays until the real one exists.
   - The SAGAT familiarisation moved into that video.
   - Smaller changes: "waiting for facilitator(s)" lines, recovery notices, the logo aspect, the TopPad layout, rounded video corners, and sample practice questions.
4. **Lunar Lantern:** see the next section.
5. **HOME:** the arm upright at the middle screen, rail 4030 (also the new divider). Every trial starts there and returns there at the end (`trial_home`). This applies to both architectures.
6. **Release 10 mm short:** every release, in both architectures, happens 10 mm short of the rest pose; the brick then settles the last 10 mm (a scripted settle).

### Lunar Lantern as built (details in `docs/lunar_lantern/README.md`)
- **Layout:** your 25 Nov export. Screen Mid moved 600 mm. The lantern pick tray is now at rail ~4740–5940; the formwork is at ~7630–8030, facing the rail end.
- **Placements:** 16, in rows 5–7. Rows 5 and 7 use columns 2–6; row 6 uses columns 1–6, because its column 7 is out of reach. Order: bottom row first, nearest the rail first. CDPs are at P05, P10 and P14.
- **Filled pockets:** every other pocket is filled at the start of a trial. That's 74: 32 relocated tray plates plus 42 fixed plates kept from the built layout. The tray then holds exactly the 16 to pick. **Physically the lab needs 90 plates.**
- **Taught grasp:** the custom fingers go through the plate's tip hole (taught 25 Nov).
- **Motion:**
  - the rail only moves with the arm tucked in a travel pose;
  - each pocket is approached through a point 150 mm out in front of it;
  - the plate goes down its own axis and is released 10 mm short.
- **Collision checks:** run in the planner and by a watcher during runs. Result: 16/16 placements, no contacts.
- **Recovery slot:** defined (build tray, far corner, rail ~8160), but not used yet.
- **Site camera:** `site_lantern`, on your lantern tripod. Its framing is still to be checked.

### Verification at the end of the day
- RegoLight end-to-end: 15/15.
- HOME check: 6/6.
- Lantern host check: 6/6.
- Unity EditMode tests: 280/280.
- Your manual P01 run, with a Lunar Lantern block: "went ok; small changes needed".

## Next, in priority order
1. **Your small changes from the P01 lantern run** (not yet listed). Start here.
2. **Lantern camera framing:** check `site_lantern` in the interface; move the tripod if needed.
3. **Lantern interventions:** recover, nudges, place-and-release, Retry and hold before the descent are refused now. They need a design for tilted pockets:
   - nudge axes on the slope (in the plate's plane?);
   - the recovery slot holder;
   - where the hold height sits along the plate axis.
4. **Lantern errors:** the schedule's lantern entries are still stand-ins planned on RegoLight geometry, and are not applied. Decide how errors are defined on the tilted pockets, then regenerate the lantern entries on the real geometry.
5. **Practice runs:** both are RegoLight now. You were leaning towards one per architecture.
6. **CDP ranges:** early, middle and late as ranges (for example 4–5, 9–11, 14–16) rather than the fixed P05, P10 and P14.
7. **SAGAT question bank:** rewrite it (no rotation variations any more); make it a root-level bank file with an embed tool; Unity samples from it.
8. **Onboarding video:** produce the real clip (`intro_to_study.mp4` in the media folder); a stand-in plays for now.

### Loose ends
- Refresh the OneDrive Unity bundle.
- Optional: the 0.5 mm planning margin for the participant's place-and-release (the contact search).
- Mohsi's feedback on the videos you sent on 24 Nov.

### Further out (physical; not started)
- **Lab hardware:** 90 lantern plates and the recovery-slot holder.
- **Real robot:** CRATER risk assessment and commissioning (robot control is on hold over COROL's lack of authentication).
- **Camera streaming:** the open live-streaming issues (O1 continuity, O2 shutdown, O3 dual-camera MAC).

## How to run things
- **Manual trial** (twin, host, renderers, relay, player): `powershell -ExecutionPolicy Bypass -File twin_link\start_twin_trial.ps1`. Enter **P01** to get Lunar Lantern as block 1 (P9xx start with RegoLight). The participant window can take over a minute to appear.
- **Twin on its own:** double-click `Albert\START_PHASE2_TWIN.bat`.
- **Lantern nominal run** (from `digital_twin`, with Remote mode ON): `..\.venv\Scripts\python.exe Albert\phase2_lantern_nominal_sim.py --watch`.
- **Checks:**
  - `twin_link\twin_trial_e2e.py`
  - `twin_link\twin_home_check.py`
  - `twin_link\twin_lantern_check.py`
  - `twin_link\twin_schedule_check.py`

  Run each with the twin venv: `..\Phase 2_COROL\lab_digital_twin\.venv\Scripts\python.exe -I <script>`.
- **PowerShell 5.1:** separate commands with `;`, not `&&`.

# Phase 2 development report: 20 November 2026

The reader is an assistant (ChatGPT) helping with this PhD project, which has not seen today's work.

**The project.** Phase 2 of a PhD experiment: participants remotely supervise a robot (UR20 arm on a linear rail, Robotiq 2F-140 gripper with custom fingers) building a structure from bricks ("RegoLight" layout, 16 placements). At decision points they Allow, Inspect or Intervene.

**Two codebases:**
- `Phase2_Interface`: the Unity participant interface (`unity/Phase2Client`, git, local only) and its launch scripts (`twin_link`).
- `lab_digital_twin`: a colleague's (Mohsi's) COROL digital twin. It is a FastAPI server, `digital_twin/server.py`, with a three.js viewer and a robot simulator. Our work is on branch `albert-phase2-alpha`.

**Everything is SIMULATION ONLY.** No physical robot, rail or gripper commands. Servers are bound to 127.0.0.1. All commits are local; pushing is planned later, together with the researcher.

---

## 1. Interventions on the digital twin (twin repo)

**A trial host, `Albert/phase2/trial_host.py`** (HTTP on 127.0.0.1:8095), runs one named step per request on the twin:
- `trial_baseline`, then `place_p01` … `place_p16`;
- interventions: `recover_pNN`, nudges, `place_release` and `retry_pNN`.

**The request ledger** separates "refused before motion" (nothing moved) from "unknown outcome". An unknown outcome blocks the host until an operator resolves it. Nothing is ever re-run automatically.

**Trial structure.** 16 bricks per trial. There are three potential decision points (CDPs) at P05, P10 and P14. Two are active (supervisory decision) and one is inactive. A SAGAT situation-awareness freeze probe is held at one of the active CDPs.

**Precision fix.**
- **Problem:** the simulator's straight-line moves stop up to 0.5 mm short. Its IK keyframes in `sim.py` are accepted at 0.5 mm, and moves under 1 mm were skipped entirely.
- **Fix:** nudges and small corrections now go to IK joints solved with the simulator's own kinematics, then one joint move. Mohsi's simulator was not changed.
- **Result:** nudges land exactly.

**Hold height after Recover:** 120 mm (the researcher's choice).

## 2. Nudges and placement errors (config v5)

**Nudges:**
- One fixed step: 10 mm along the rail or across it.
- Rotation nudges are dropped for now (a nice-to-have later).
- The held brick must stay inside a 100 mm circle around where Recover lifted it. A nudge that would leave the circle is refused before motion, and the interface greys out that button.

**Placement errors.**
- **What they are:** whole-centimetre position offsets of 2–8 cm, so 10 mm nudges can always reach the ideal drop exactly, at least 2 cm inside the circle.
- **Where they go:** only at the trial's two active CDPs. Some active CDPs stay nominal, and the inactive CDP is always nominal.
- **Difficulty bands:**

  | Band | Offset | Distinct offsets |
  |---|---|---|
  | Small | 2–3 cm | 20 |
  | Medium | >3–5 cm | 52 |
  | Large | >5–8 cm | 116 |

- **Lift to clear:** the twin has no contact physics, so a misplaced brick is lifted just enough to clear its neighbours (0–90 mm).

**Variation schedule** (`Albert/phase2/variation_schedule.py` writes `data/regolight_variation_schedule_v1.json`; seed 20261120; deterministic):
- **Study design:** 20 participants × 4 blocks (Lunar Lantern / RegoLight × 2D / XR) × 3 trials.
- **What is scheduled:** the 120 RegoLight trials.
- **Per participant (RegoLight):** 8 errors and 4 nominal active CDPs; every trial has at least one error.
- **Bands:** balanced across the study (53 / 54 / 53).
- **No repeats:** no (placement, offset) repeats anywhere in the study, and no participant sees the same offset twice.
- **CDP patterns:** each participant meets all six (active pair, SAGAT location) combinations once. These patterns are provisional.
- **Development / pilot IDs** (P900–P999) get fixed `DEV` entries.

**Rules set by the researcher:**
- Retry repeats the same error.
- Once the participant's decision about a brick is over (whether they left the error in place or placed the brick themselves), the twin "settles" the brick to its nominal seat when the next placement starts, so construction can continue. The participant's pose stays on record.

**Interface side.**
- The trial baseline sends the trial identity (participant, architecture, interface, trial id, CDP allocation).
- The twin refuses the baseline if its schedule's CDP allocation disagrees with the interface's.

**Verification:** the full end-to-end participant trial (the real Unity player, scripted participant, twin server, trial host and rendered views) passes 12/12 checks.

## 3. Participant interface (Unity)

- **Participant identification screen** before the session (facilitator enters the ID). Accepted IDs: P01–P20 for the study, P900–P999 for pilots. An existing session can be resumed.
- **Accurate numbering:** the manual trial protocol has the study structure (4 blocks × 3 trials), so screens say "Block 1 of 4" and "Trial 4 of 12". Trials are numbered across the session. A one-trial copy of the protocol is used for the automated check.
- **Training media placeholders:** 16:9 "Video / Image · Placeholder" boxes on the introduction, training, checklist, refresher and block screens.
- **Tests:** EditMode tests 259/259.

## 4. Teaching tool inside the twin viewer's sim jog panel

**Starting it.** With Remote mode off and **Jog sim ON**, the Jog panel has a **Teach** section under the jog rows, so jogging keeps working while teaching. It is shown only for the UR20.

**What it does:**
- Record named poses: joints, TCP, rail, gripper opening and, if a brick is held, how it sits in the gripper.
- **Go** back to a pose (arm and rail together); Rename / Delete (delete needs two clicks).
- **Grip nearest** (attach the closest brick) and **Release**.
- The list shows the newest pose first. A new pose is highlighted and opened, and clicking a name shows its details.
- The fingers are moved with the viewer's own gripper box.

**Saving:**
- The working list is saved instantly to `runs/phase2/taught_items.json` (not versioned).
- **Export…** writes a dated, never-overwritten pose set to `Albert/phase2/data/poses/` (versioned).
- **Load** restores a set into the list.

**Teaching lock.**
- It follows Jog sim and is refused while the trial host is running a step.
- While teaching, Remote mode and the trial's object moves are refused.
- It lapses 20 s after the page goes quiet.

**Double-click launchers:** `Albert/START_PHASE2_TWIN.bat` starts the server on 127.0.0.1:8080 and opens the viewer with the Phase 2 scene already loaded (`?config=client_config_phase2_experiment.json`). `Albert/RESET_PHASE2_TWIN.bat` resets the scene.

**UI polish:**
- The panel never covers the view buttons, can be dragged by its top bar, and hides the long help text while teaching.
- The orange status banner in the viewer is hidden by default (opt-in: `#p2banner=1`).

## 5. Housekeeping

- **Renderer leak fixed.** The headless Edge browsers used to render the participant's camera views were left running after test runs, which slowed the live views to ~2.4 fps. They are now tied to their Python process with a Windows job object, so they die with it.
- **Phase2_Interface trimmed from ~21 GB to ~4.5 GB:**
  - **Deleted (13.7 GB):** a stray Unity test project, old builds, old test evidence, and three 2.9 GB crash logs (one kept as a first/last 5 MB excerpt in its backup).
  - **Archived:** `corol_sim` and `corol_link` (superseded by the twin repo) moved to `_archive/2026-11-20/`.
  - **Log:** `_archive/2026-11-20/TRIM_LOG.txt`.
  - **Checks afterwards:** the tests and the end-to-end check still pass.

**Commits (local, not pushed):**
- twin repo `albert-phase2-alpha`: `69d6ec6` … `4f50482`
- Unity `master`: `4136722`, `237da40`, `e27b243`

---

## Next task (the researcher's request)

**Pick order: take tray bricks far from the rail first.**

**Why:** safety margin against the arm colliding with the rail.

**Current state.**
- The 16 placements pick, in order, the tray bricks *closest* to the rail.
- P01–P05 take the column at 0.63 m from the rail, P06–P10 the column at 0.76 m, P11–P15 the column at 0.90 m, and P16 one brick at 1.04 m (world X = across the rail).
- The tray holds 20 bricks, out to 1.60 m from the rail.
- The assignment is the manifest's `tray_after_baseline` order, used by `Albert/phase2/trial_plan.py`.

**Wanted:** start with the farthest bricks.

**Points to check:**
1. **Reach:** the UR20's reach (about 1.75 m) to the farthest columns. Choose which 16 of the 20 bricks to use.
2. **Grasp:** the taught grasp was taught on the nearest brick (brick.001) and is applied to every brick. Check that it is valid and collision-free at the far columns, using the twin's per-part gripper colliders.
3. **Rail stations:** pick positions along the rail per brick.
4. **Regeneration and tests:**
   - regenerate the nominal pose file;
   - bump the config version (v6), keeping the interface protocol's `config_version` in step;
   - rerun the nominal 16-placement run and the 12-check end-to-end trial.

## Still parked

- Small interface changes noted during the manual run.
- The interface's CDP allocation for real participants (P01–P20) must come from the variation schedule. Until then, use pilot IDs.
- Lunar Lantern on the twin (no geometry yet).
- Rotation errors.
- Notes for Mohsi on the simulator quirks: short `movel` moves stop up to 0.5 mm short, and a very short move can finish between `robot_sim`'s status polls.
- Pushing both repos, together with the researcher.

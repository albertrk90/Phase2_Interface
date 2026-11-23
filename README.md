# Phase 2 Interface: remote supervision of robotic lunar construction

Development workspace for Phase 2 of a PhD experiment on **human supervision of robotic lunar construction**. Participants remotely supervise a robot performing a construction task and respond at decision points. They see the worksite through live camera imagery, and the experiment compares how they perform under two viewing conditions.

**Workspace layout (20 November 2026, after the clean-up; see `_archive/2026-11-20/TRIM_LOG.txt`):**

| Folder | What it is |
|---|---|
| `unity/Phase2Client` | the participant interface (Unity; git, local). Current player: `Builds/S4`. Trial protocols in `Assets/Phase2/Experiment/Protocols` |
| `twin_link` | runs a participant trial against the digital twin repo: `start_twin_trial.ps1` (manual), `twin_trial_e2e.py` (automated check) |
| `streaming_poc`, `camera_gateway` | the live-camera path (MediaMTX, Camera A gateway) and the Python environment the Unity tools use |
| `camera_validation` | the running camera / development checkpoint log `CAMERA_DISCOVERY_2026-11-03.md` |
| `docs`, `design`, `backups` | plans and audits, the UI mock-up, dated checkpoints |
| `_archive/2026-11-20` | `corol_sim` and `corol_link`, superseded by the digital twin repo (`lab_digital_twin`, branch `albert-phase2-alpha`: `digital_twin/Albert/phase2`) |

The robot side of a trial (trial host, placement errors, views, teaching) now lives in the digital twin repo; see its `digital_twin/README.md`, section "Phase 2 participant trials".

**Current status (12 November 2026):** the Unity participant client is in progress (Task 07).
- **Task 07 S1 complete:** the AI2 state machine and simulated backend.
- **Task 07 S2 complete:** two-camera supervisory video (real Camera A replay, SIMULATED Camera B).
- **R1/R2 fixed:** the two receiver races are fixed, and the full M1 and S2 regression passed.
- **Task 07 S3 accepted** as the functional baseline: the **Site Window Windows participant interface**, committed as `e418f62` ([S3 report](docs/plans/Phase2_Task07_S3_Implementation_Results.md)).
- **Task 07 S3.1 accepted** as the functional baseline and committed as `b5722b8` (12 Nov), with provisional decisions C1–C7 ([CONOPS §11](docs/plans/Phase2_Task07_S3_1_Revised_CONOPS.md)): the revised CONOPS.
  - **The revised sequence:** the robot places with a prescribed variation, releases and retreats; the participant reassesses; Intervene → recovery (the facilitator may review or assist) → secure grasp → bounded translation and **rotation** nudges → **Place and release** → reassessment.
  - **The S3 workflow is kept** as a selectable mode.
  - **Results:** EditMode 146/146, PlayMode 4/4, S3.1 player session 39/39, M1 and S2 player regression PASS.
  - **Documents:** [CONOPS](docs/plans/Phase2_Task07_S3_1_Revised_CONOPS.md) and [S3.1 report](docs/plans/Phase2_Task07_S3_1_Implementation_Results.md).
- **Task 07 S4.1 accepted** as the simulated functional baseline (after manual review; minor UI issues deferred) and **committed as `6c7e33c`** (12 Nov): experimental configuration and session orchestration ([specification](docs/plans/Phase2_Task07_S4_1_Experimental_Development_Specification.md), [S4.1 report](docs/plans/Phase2_Task07_S4_1_Implementation_Results.md)).
  - **What it adds:** a versioned experiment definition; the Williams W1–W4 allocation (reference 5 per sequence at N = 20, 6 at N = 24, methodology V17); the full session lifecycle; two active and one inactive CDP per trial; unscheduled supervision; facilitator roles A and B with a console; placeholder SAGAT and confidence lifecycles; interruptions, validity, replacement and restart reconciliation.
  - **Results:** EditMode 181/181, PlayMode 5/5, S4 player scripted demonstration 24/24, accelerated full session `verify_s4_session.py --full` 26/26; S3, S3.1, S2 and M1 player regressions PASS.
  - **Simulation only:** every physical and instrument value is a demonstration placeholder; XR blocks are a labelled Windows substitution.
- **Concurrent Wi-Fi and Ethernet works (12 Nov):** the policy is now `fMinimizeConnections = 0`; the cameras route via Ethernet and the internet via Wi-Fi in the same period.
  - **Live preview:** the first live Camera A preview with Wi-Fi up, in the approved opt-in `ethernet_scoped` gateway mode, passed S1–S11, with Wi-Fi probes 19/19 during streaming.
  - **Freezes:** one 1.1 s freeze, the known RTSP write-stall / GOP-loss pattern.
  - **Site Window:** the Camera A live-source option is prepared (uncommitted).
  - **Details:** checkpoint §13.24.
- **Development checkpoint `ca5c803`:** the Camera A live-source option.
- **Live S4.1 smoke test PASS (13 Nov):** live Camera A in the Site Window, inside the unchanged 120 s gateway limit; S1–S11, 16/16 smoke checks, no freezes, Wi-Fi 10/10. The S4-compatible runner changes are uncommitted, for review ([checkpoint §13.26](camera_validation/CAMERA_DISCOVERY_2026-11-03.md)).
- **Next:** an S4-compatible live runner and a decision about test duration (approval needed). Restart point: [checkpoint §13.25](camera_validation/CAMERA_DISCOVERY_2026-11-03.md). Recheck the C09 clock reference after any reboot. The open methodological questions, demonstration parameters and commissioning limitations remain. S4.2, Quest 3, digital twin, machine vision and robot integration have **not** been started; each needs approval. Deferred UI refinements are listed in CONOPS §11.
- **Git checkpoint:** the last commit is S4.1 (`6c7e33c`; S3.1 is `b5722b8`, S3 is `e418f62`) in [`unity/Phase2Client`](unity/Phase2Client/README.md) (local only, no remote); see [checkpoint §13.22–§13.23](camera_validation/CAMERA_DISCOVERY_2026-11-03.md).
- **Not used:** no camera, MediaMTX, COROL or robot in Task 07.

Earlier status record (kept for history):

Status as of **4 November 2026 (end of day)**: camera validation (Task 03) is in progress.
- **Complete:** Stages A–D, and Stage E tests E1–E5.
- **Next:** the Stage E second-scene tests E6–E9 are prepared but not run.
- **5 Nov:**
  - Task 04A and the COROL addendum are reviewed.
  - The provisional architecture is approved; robot control is on hold.
  - Task 04B (the offline streaming PoC) is **prepared but not run**, waiting at the review gate. See [streaming_poc/README.md](streaming_poc/README.md).
- **Not built:** only camera-validation tooling exists in this workspace. **No participant interface, administration interface, streaming gateway, robot integration or Unity build has been implemented yet.**

To resume, see [camera checkpoint: NEXT SESSION: START HERE](camera_validation/CAMERA_DISCOVERY_2026-11-03.md#next-session-start-here).

---

## 1. Experimental conditions

| Condition | Display | Imagery |
|---|---|---|
| A: Conventional 2D | Desktop monitor (monoscopic) | One image from the camera source |
| B: Stereoscopic XR | Meta Quest 3 | Separate left/right images, one per eye |

Design intent (from the [Task 01 audit](docs/audits/SideQuest_Phase2_Technical_Audit.md), §8.2; not yet implemented or confirmed): both conditions use the same camera source, encoding and receiver code. Condition A shows the left image of the same stereo pair, so stereopsis is the only intended difference. The choice of monocular source for Condition A is still an open researcher decision.

## 2. Hardware and intended roles

| Hardware | Intended use | Status |
|---|---|---|
| Universal Robots UR20 | Performs the construction task under supervision | No integration work started |
| Robotiq gripper | End effector on the UR20 | Model and integration not yet documented |
| Camera A: Luxonis OAK-D Pro PoE AF | Robot wrist camera (provisional) | Discovery, stereo capture, synchronisation and rectification (E1/E3/E5) validated 3–4 Nov 2026; provisional framing 75.5° × 51.5° with a common crop |
| Camera B: Luxonis OAK-D Pro W PoE (wide-angle) | Overview tripod camera (provisional) | Same stages validated 3–4 Nov 2026 (E2/E4); provisional framing 97.1° × 70.6°; residual vertical offset under investigation; CRATER coverage untested |
| Meta Quest 3 | Condition B display | Not yet used in Phase 2 |
| Dobot Magician E6 | Robot used in the original Side Quest system | **Not used in Phase 2 camera work; must not be operated** |

Both OAK cameras carry a stereo pair of OV9282 monochrome global-shutter sensors plus a central IMX378 colour sensor (verified, see [camera checkpoint](camera_validation/CAMERA_DISCOVERY_2026-11-03.md)). They also have IR dot-projector/flood hardware, which must stay off.

## 3. Participant interfaces vs administration interface

- **Participant interfaces** (Conditions A and B): show the camera imagery and the controls a participant needs at decision points. They must **not** show placement-correctness cues (such as the Side Quest GREEN/YELLOW/RED zone indicator or zone-specific sounds) and should avoid gamification. Both conditions should present equivalent information.
- **Experiment administration / facilitator interface**: used by the researcher to run sessions. It is separate from the participant views and may show information participants must not see (session and robot state, system health, logging status). Its functions have not yet been specified.

Neither interface has been designed or implemented yet.

## 4. Recovered Side Quest code

Phase 2 builds on an earlier system called **Side Quest**. It used Luxonis DepthAI cameras, a Python stereo video sender, a Dobot robot, and a Unity app that showed separate left/right images in a Quest 3. Both original repositories are **read-only references**; do not modify them.

| Repository | Location | Contents |
|---|---|---|
| Unity project (UVCS workspace `SideQuestXR_Unity`) | `C:\Users\a1920234\Documents\SideQuest_Recovery` | Unity 6000.3.4f1, URP, OpenXR / Quest 3, stereo receiver and UI |
| Robotics / Python | `C:\Users\a1920234\Documents\Side_Quest_Robotics\SIDE_QUEST_ROBOTICS` | Includes the camera sender `Robotics/motion/camera_streamer.py`, plus robot-control code (do not run) |

**Likely reusable** (per the [Task 01 audit](docs/audits/SideQuest_Phase2_Technical_Audit.md), §6; none of this has been tested in Phase 2):
- URP + OpenXR + Quest 3 configuration, the XRI 3.3 rig and world-space UI.
- The per-eye stereo material `Mat_HardwareStereo.mat` / `DualSourceStereo.shadergraph`.
- The `TogglableReceiver` threading pattern (needs reconnect, clean shutdown and frame IDs).
- The framed `'L'|len|JPEG`, `'R'|len|JPEG` TCP protocol (adequate for a first LAN milestone; needs sequence/timestamp fields).
- The ACK/NACK and decision-token pattern from `RobotCommandPipe` / `XRUIStateManager`.
- The lunar environment assets.

**Unsuitable for Phase 2:** zone/correctness indicators, boost/combo/music gamification, direct nudge and gripper controls for participants, and hard-coded `169.254.1.10` addressing.

**Camera sender (`camera_streamer.py`):** full findings are in the [Task 02 audit](docs/audits/Phase2_Task02_Camera_Sender_Audit.md). Key points:
- It is only ever launched from `task_controller.py`, which initialises the gripper and opens the robot-arming command server, so it must not be run as-is. The module itself imports only `robot_config`.
- Its DepthAI v2 path pairs left/right MJPEG frames through a `Sync` node (50 ms threshold) at 1280 × 720, 20 fps.
- Its v3 path reads the left and right queues one after the other with **no pairing**.
- Its `requirements.txt` does not pin DepthAI.
- It serves one client per port, sends unrectified images with no frame IDs or timestamps, and fails silently on camera loss.
- The camera IDs and IPs in the old `robot_config` (INSPECTOR `19443010B14C872F00` / `169.254.1.222`, SITE_MANAGER `194430108183F12E00` / `169.254.1.223`) match the devices discovered on 3 Nov 2026.
- Phase 2 uses new code instead (see [camera_validation/](camera_validation/)).

## 5. Milestones

| Milestone | Status |
|---|---|
| Task 01: Audit recovered Unity project | Completed; report archived in `docs/audits/` |
| Task 02: Audit original Side Quest camera sender | Completed; report archived in `docs/audits/` |
| Task 03 Stage A: Python and DepthAI environment preparation | Completed |
| Task 03 Stage B: Individual camera discovery (both cameras) | Completed |
| Task 03 Stage B: Both cameras on one network | **Completed 4 Nov.** Both cameras were connected one after the other, and then held open together for 10 s with verified device IDs (`RESULT: PASS`). Earlier address-resolution failures cleared after a switch-port swap; their root cause is unknown. See the [camera checkpoint](camera_validation/CAMERA_DISCOVERY_2026-11-03.md) §6. |
| Task 03 Stage C: Stereo image acquisition | **Initial functional validation complete for both cameras (4 Nov):** 200 synchronised native 1280 × 800 pairs each, calibration unchanged. Loss-free continuity is **not** established: Camera A missed frames in 2 of 3 runs, Camera B had none missing in 1 run. See [checkpoint §7.8–7.9](camera_validation/CAMERA_DISCOVERY_2026-11-03.md). |
| Task 03 Stage D: Synchronisation and frame continuity | **Completed 4 Nov (7 runs, all PASS).** Synchronisation verified (\|L–R\| ≤ 0.03 ms). Delivery stalls of 0.1–0.7 s occur about 2.7 times per minute on the local link; frames are lost only in the longest (13 of 8,413), on both cameras. Root cause not established; it does not block Stage E. See [checkpoint §9](camera_validation/CAMERA_DISCOVERY_2026-11-03.md). |
| Task 03 Stage E: Rectification and visual checks | **E1–E5 complete and analysed.** Provisional configuration **approved**: Camera A 75.5° × 51.5° with a common crop; Camera B 97.1° × 70.6°, pending the CRATER coverage check. **Second-scene tests E6–E9 prepared, not run.** They use `--setup-preview`, which passed 38 offline checks but is **untested with a physical camera or real OpenCV window**. Quest 3 comfort untested. See [checkpoint §11–12 and the handover](camera_validation/CAMERA_DISCOVERY_2026-11-03.md#handover-status-end-of-4-november-2026). |
| Task 03 Stage F: Image-quality assessment | Pending |
| Task 03 Stage G: Camera-validation report | Pending |
| Task 04A: Open-source streaming and architecture audit | **Completed 5 Nov (research only); awaiting review.** Proposes one Unity codebase (Windows + Quest 3) fed by on-device H.264 → MediaMTX → RTSP/TCP, with a JPEG/TCP fallback. Unity WebRTC is not adopted (deprecated). See the [Task 04A audit](docs/audits/Phase2_Task04A_Streaming_Architecture_Audit.md) and [checkpoint §13](camera_validation/CAMERA_DISCOVERY_2026-11-03.md). |
| Task 04A addendum: COROL integration audit | **Completed 5 Nov (source inspection only); awaiting review.** COROL (`lab_digital_twin`, `albert-phase2`) provides a digital twin, a UR20/rail/gripper control library and a gripper daemon. The Phase 2 task is simulation-only, with placeholder poses. A new task orchestrator and experiment backend are needed; Task 04B is unaffected. See the [COROL audit](docs/audits/Phase2_Task04A_Addendum_COROL_Integration_Audit.md). |
| Provisional architecture | **Approved 5 Nov as the planning baseline.** Orchestrator, backend, video and Unity are kept separate; one Unity codebase with a flexible receiver back-end; **robot control on hold** pending AIML review of the network-isolation and access-control requirements. See [docs/architecture/Phase2_Provisional_Architecture.md](docs/architecture/Phase2_Provisional_Architecture.md) |
| Task 04B: Offline streaming proof of concept | **Two 60 s localhost smoke tests, 5 Nov.**<br>**Smoke 1:** stale frames after a stall (S7 FAIL).<br>**Smoke 2:** the holdback was traced to FFmpeg's H.264 parser.<br>• Fixed with an end-of-frame SEI: frame-boundary latency **PASS**; median frame age 18 ms.<br>• Receiver freshness safeguard: stale-frame rejection **PASS**.<br>• Overall FAIL only on S4, a receiver-window artefact.<br>**Smoke 3** (stall + server restart): the first attempt aborted on an orchestrator bug (fixed).<br>**Smoke 3 re-run:** **all criteria PASS on both streams**, including reconnection R1–R5. Restart timing deviated (issued at t = 40.85 s, not 38 s); a publisher logging flaw was found ([results](streaming_poc/results/smoke_20261105_121101/SMOKE_RESULTS.md)).<br>**Full G1 run (5 Nov 12:27):** G1.1–G1.7 **PASS**, but interrupted by Windows standby at t ≈ 615 s ([G1 results](streaming_poc/results/smoke_20261105_122716/G1_RESULTS.md)).<br>**G1 rerun (5 Nov 15:11, uninterrupted):** G1.1–G1.7 **PASS** on both cameras; P2 and S8 fixed; S7b FAIL on a drop-stall sub-rule ([rerun results](streaming_poc/results/smoke_20261105_151122/G1R_RESULTS.md)).<br>**Closed 5 Nov at the G1 gate** (checkpoint §13.10) |
| Task 04: Standalone stereo camera gateway | Not started; follows Task 04B |
| Unity Editor installation | **Unity 6.3 LTS 6000.3.28f1 installed** (5 Nov). A URP test project (`My project`, disposable; deleted 20 Nov 2026) opens and Play Mode works. Android Build Support and Quest deployment **not verified**. The recovered Side Quest project (6000.3.4f1) stays read-only |
| Task 05: Unity Windows reception | **Compatibility milestone PASS (5 Nov, offline):** new project [`unity/Phase2Client`](unity/Phase2Client/README.md). The FFmpeg route was verified in the Editor and a standalone player. **M1 offline receiver implemented and verified** (Editor and Windows player; checkpoint §13.12). **T3 live 60 s smoke PASS** (checkpoint §13.13); **T4 run 5 Nov: formal M1 FAIL on M1.4–M1.6** (definition and scorer issues; §13.15; the recorded result). **6 Nov: supplementary post-hoc re-score under M1 criteria v2 PASS 10/10**; **M1 closed 6 Nov as CONDITIONALLY VALIDATED** (v1 FAIL 7/10 recorded; v2 PASS 10/10; unscheduled freezes unresolved) ([RESCORE_RESULTS](unity/Phase2Client/test_results/m1_t4_rescore_v2_20261106/RESCORE_RESULTS.md); §13.16) ([plan](docs/plans/Phase2_Task05_Unity_Windows_Reception_Plan.md)) |
| Task 06: real Camera A to Unity preview | Offline preparation complete (6 Nov). New [`camera_gateway/`](camera_gateway/README.md) and the Unity `-m1Source camera` mode. **Stage 0 PASS; Stage 1 PASS (6 Nov 12:28): on-device H.264 of both rectified Camera A eyes verified on hardware**, 601 frames per eye, 0 gaps, L/R skew ≤ 0.034 ms, calibration and bootloader unchanged ([results](camera_gateway/results/stage1_review_20261106/STAGE1_RESULTS.md)). **Stage 2 live preview PASS on integrity S1–S11 (6 Nov 12:56)**: live Camera A displayed in Unity; capture → Unity median 90.7 ms (p95 99.4); 6 freezes of about 1 s traced to right-eye loopback transport stalls ([results](camera_gateway/results/stage2_review_20261106/STAGE2_RESULTS.md)) ([plan](docs/plans/Phase2_Task06_CameraA_Unity_Preview_Plan.md)). **Continuity investigation (6 Nov, offline):** keyint 10 recommended for the next preview ([report](docs/plans/Phase2_Task06_Continuity_Investigation.md)) |
| Task 07: AI2 supervisory interface (Windows) | **S1 complete (6 Nov):** AI2 state machine, simulated backend, schema v1.1 ([S1](docs/plans/Phase2_Task07_S1_Implementation_Results.md)).<br>**S2 complete (6–7 Nov):** two-camera supervisory video, SIMULATED Camera B ([S2](docs/plans/Phase2_Task07_S2_Implementation_Results.md)).<br>**R1/R2 receiver races fixed;** regression passed: EditMode 109/109, PlayMode 12/12, M1 player 4/4, S2 player 2/2 ([Part A](docs/plans/Phase2_Task07_S2_PartA_Receiver_Race_Fixes.md)).<br>Design: [Site Window rev. 2](docs/plans/Phase2_Task07_AI2_Interface_Design_Proposal.md).<br>**S3 implemented and verified (11 Nov), awaiting review:** Site Window Windows participant interface (uGUI/TMP, IBM Plex) and a simulated session. Scripted session 63/63; EditMode 126/126; PlayMode 3/3; M1 and S2 player regression PASS ([S3](docs/plans/Phase2_Task07_S3_Implementation_Results.md)). Accepted and committed as `e418f62` (12 Nov).<br>**S3.1 implemented and verified (12 Nov), awaiting review:** released-element workflow (recovery, facilitator, rotation, Place and release), schema v1.2; EditMode 146/146, PlayMode 4/4, player session 39/39 ([CONOPS](docs/plans/Phase2_Task07_S3_1_Revised_CONOPS.md), [S3.1](docs/plans/Phase2_Task07_S3_1_Implementation_Results.md)). Accepted and committed as `b5722b8` (12 Nov).<br>**S4.1 accepted and committed as `6c7e33c` (12 Nov):** experiment definition and session runner (Williams allocation, training and competency, active/inactive CDPs, unscheduled supervision, facilitator roles A/B with console, SAGAT and confidence placeholder lifecycles, interruptions, validity, replacement, persistence and restart), schema v1.3; EditMode 181/181, PlayMode 5/5, S4 player 24/24, accelerated full session 26/26 ([spec](docs/plans/Phase2_Task07_S4_1_Experimental_Development_Specification.md), [S4.1](docs/plans/Phase2_Task07_S4_1_Implementation_Results.md)) |
| Participant interfaces (2D desktop, Quest 3 XR) | Not started |
| Administration / facilitator interface | Not started |
| Experiment-control backend, UR20 / Robotiq integration, event logging | Not started |

## 6. Development environment

- Windows 11 Enterprise laptop `AU-350998`, VS Code with Claude Code.
- Python 3.13.17, installed per-user at `%LOCALAPPDATA%\Programs\Python\Python313` (not on PATH).
- Project virtual environment `camera_validation\.venv`, containing only the [pinned packages](camera_validation/requirements.txt): `depthai==3.11.0` (DepthAI **v3** API), `opencv-python==4.14.0.94`, `numpy==2.4.6`.
- Camera network: laptop `Ethernet 4` (`169.254.80.246/16`) → isolated PoE switch → cameras at `169.254.1.222` (A) and `169.254.1.223` (B).
- **Networking constraint:** university Wi-Fi appears to disconnect when Ethernet is active (cause unconfirmed; IT request in progress). Prepare code and dependencies on Wi-Fi, then switch to Ethernet to run camera tests locally. No university network, firewall or adapter settings have been changed.
- Unity is not installed.

## 7. Documentation and audit reports

| Document | Location | Notes |
|---|---|---|
| Camera runbook | [camera_validation/README.md](camera_validation/README.md) | Setup and commands |
| Camera validation checkpoint (3–4 Nov 2026) | [camera_validation/CAMERA_DISCOVERY_2026-11-03.md](camera_validation/CAMERA_DISCOVERY_2026-11-03.md) | Chronological record of Stages A–E, evidence, handover status, **NEXT SESSION: START HERE** |
| Task 01 Unity audit | [docs/audits/SideQuest_Phase2_Technical_Audit.md](docs/audits/SideQuest_Phase2_Technical_Audit.md) | **Archived**; byte-identical to the original audit output (SHA-256 `f1af2b2f…7f682`) |
| Task 02 camera-sender audit | [docs/audits/Phase2_Task02_Camera_Sender_Audit.md](docs/audits/Phase2_Task02_Camera_Sender_Audit.md) | **Archived**; verified complete (sections 1–7) and well-formed Markdown |
| Task 04A streaming and architecture audit | [docs/audits/Phase2_Task04A_Streaming_Architecture_Audit.md](docs/audits/Phase2_Task04A_Streaming_Architecture_Audit.md) | 5 Nov 2026; comparison matrix, architecture, primary and fallback stacks, proof-of-concept plan, gates, open decisions; **awaiting review** |
| Task 04A addendum: COROL integration audit | [docs/audits/Phase2_Task04A_Addendum_COROL_Integration_Audit.md](docs/audits/Phase2_Task04A_Addendum_COROL_Integration_Audit.md) | 5 Nov 2026; COROL components, protocols, AI2 mapping, safe intent handling, event log, updated three-path architecture; reviewed |
| Provisional architecture | [docs/architecture/Phase2_Provisional_Architecture.md](docs/architecture/Phase2_Provisional_Architecture.md) | Approved decisions D1–D7, components, three communication paths, **network-isolation and access-control requirements (for AIML/IT review)**, assumptions register |
| Questions for the CRATER/AIML team | [docs/coordination/CRATER_AIML_Questions_DRAFT.md](docs/coordination/CRATER_AIML_Questions_DRAFT.md) | **Draft, not sent.** Part A needed now; Part B for hardware integration |
| Streaming PoC runbook | [streaming_poc/README.md](streaming_poc/README.md) | Task 04B safeguards, files, offline checks, proposed G1 commands |

The Task 02 file begins with a "Written for:" line and ends with an offer to publish it. Both are carried over from the original session reply and do not affect the content.

## 8. How to resume safely

1. Read [camera_validation/CAMERA_DISCOVERY_2026-11-03.md](camera_validation/CAMERA_DISCOVERY_2026-11-03.md): **Handover status** and **NEXT SESSION: START HERE** (at the end). The next step is a single Camera B setup-preview run (E6), checked before E7–E9.
2. On Wi-Fi, run `camera_validation\.venv\Scripts\python.exe camera_validation\env_check.py` to confirm the environment.
3. Prepare scripts on Wi-Fi. Run camera tests only on the isolated Ethernet network. Review `camera_validation/results/` afterwards.

Standing rules for this project:
- Do **not** modify `SideQuest_Recovery` or `Side_Quest_Robotics`.
- Do **not** run or import `task_controller.py`, robot-control, gripper or robot-communication code, and do not initiate robot motion.
- Do **not** flash camera firmware, update bootloaders (0.0.29 is available but deliberately not applied), change camera IPs, or write EEPROM/calibration.
- Keep the IR dot projector and flood illuminator **off**.
- Never start a DepthAI pipeline without `pipeline.setAutoCalibrationMode(OFF)` confirmed. DepthAI ≥ 3.6 defaults to `ON_START`, which can flash new user calibration to the camera.
- Do **not** change Windows network, firewall, routing, antivirus or university IT settings without explicit approval, and do not run broad network scans.
- Install Python packages only into the project venv, and only with approval.

## 9. Workspace layout

```
Phase2_Interface/
  README.md                         this file
  docs/
    audits/
      SideQuest_Phase2_Technical_Audit.md    Task 01: recovered Unity project
      Phase2_Task02_Camera_Sender_Audit.md   Task 02: original camera sender
      Phase2_Task04A_Streaming_Architecture_Audit.md   Task 04A: streaming and architecture audit
      Phase2_Task04A_Addendum_COROL_Integration_Audit.md   Task 04A addendum: COROL robot-control integration
    architecture/
      Phase2_Provisional_Architecture.md     approved provisional architecture and requirements
    coordination/
      CRATER_AIML_Questions_DRAFT.md         draft questions for the AIML team (not sent)
  streaming_poc/                    Task 04B offline streaming PoC (localhost only)
    README.md                       runbook and review gate
    config/mediamtx_localhost.yml   localhost-only MediaMTX config (not yet launched)
    poc_common.py, synthetic_stereo.py, publish_synthetic.py, receive_reference.py, analyse_poc.py
    tests/test_streaming_poc.py     offline checks (no network)
    tools/mediamtx_v1.21.3/         official release zip + extracted binary (not run)
    results/                        run outputs (empty)
    .venv/                          separate venv (av==19.0.2)
  camera_validation/
    README.md                       camera runbook
    CAMERA_DISCOVERY_2026-11-03.md  checkpoint and next steps
    requirements.txt                pinned packages
    env_check.py                    environment/API check (no camera access)
    net_check.ps1                   read-only network check
    discover_cameras.py             camera discovery and verified (--expect) connection
    capture_stereo.py               Stage C synchronised left/right mono capture (local only)
    calibration_check.py            read-only calibration read and content comparison
    stereo_geometry.py              Stage E host analysis: calibration summary, rectification, vertical disparity, FOV
    rectify_stereo.py               Stage E raw + rectified capture (StereoDepth) with geometry analysis
    analyse_stage_e.py              offline re-analysis of Stage E runs (reads results only)
    analyse_epipolar.py             cross-scene epipolar analysis and offline evaluation of candidate corrections
    coverage_check.py               ArUco marker sheets and field-of-view coverage check from saved runs
    results/                        machine-generated logs, JSON, calibration copies
    .venv/                          project virtual environment (not documentation)
```

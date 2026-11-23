# Phase 2 remote-supervision study: questions for the CRATER/AIML team

> **DRAFT, NOT SENT** (prepared 5 November 2026; section A4, questions 28–34, added 6 November 2026). For the researcher to review and edit before anything is shared.

## Background

Phase 2 of this PhD study has participants at North Terrace supervising the UR20 pick-and-place task at CRATER. They view it through two stereo cameras, either on a desktop monitor (2D) or on a Meta Quest 3 (stereoscopic).

At defined decision points, participants can:
- let the robot continue;
- hold the task while they look more closely through the camera views (no robot motion; updated 6 Nov);
- request a retry (a fresh placement attempt);
- request small, bounded placement corrections, one nudge at a time (updated 6 Nov).

We have read the `lab_digital_twin` repository (branch `albert-phase2`, commit `55cfb61`) as source code only. We have **not** run any of it, connected to any robot or service, or changed anything in the repository.

Our current plan keeps three things completely separate:
- **Video**, one-way from the cameras.
- **Experiment state and participant choices**, through our own authenticated experiment server.
- **Robot control**, carried out at CRATER only, by a single controlling program that would reuse your `robot.py` and could be rehearsed first in your simulator.

No participant device would ever talk to the robot, the twin server or the gripper server.

Before any robot-related work, we would value your guidance on the questions below.
- **Part A** covers what we need answered now, because it shapes the design.
- **Part B** can wait until hardware integration.

---

## Part A: needed now (these shape the design)

### A1. Permission, supervision and safety

1. Would you be willing, in principle, for a separate Phase 2 program to command the UR20, the rail and the gripper during supervised trials? If so, under what conditions? For example: who must be present, sign-off of motion limits, or a risk assessment.
2. Who would be the authorised operator with E-stop access during trials? Is there a written procedure for remote or semi-remote operation of the cell that we should follow?
3. What speed, acceleration and force limits should apply to robot motions that a participant has triggered (inspection moves, retries, small corrections)?
4. For a bounded placement correction, what range would you consider safe? We were thinking of a few millimetres up to about ±10–20 mm in the horizontal plane, applied only to pre-measured above and descent poses. Should any axes or rotations be excluded altogether?
5. `robot.py` includes an optional RTDE watchdog (off by default). Would you want it enabled for supervised remote operation, given the trade-off between unexpected stops and having no on-robot dead-man?
6. Should participant-requested actions always need the operator to confirm them on site, or may some run automatically within agreed limits?

### A2. Network isolation and access control

7. The twin server (port 8080) and the gripper server (port 8081) accept commands without authentication. We would treat the robot LAN as a closed network that no participant device, the university network or the other campus can reach. Is that already the case? Who manages the network controls at CRATER?
8. How are the robot LAN (192.168.1.x), the camera PoE network and the university network connected today? Could one CRATER computer sit on the camera network and also reach North Terrace, without bridging the two?
9. Which CRATER machine could host:
   - the camera gateway and video relay;
   - the experiment server;
   - the robot-control program?

   Are there any restrictions on installing software or opening ports on those machines?
10. Is time synchronisation (NTP) available on the CRATER machines? We need a shared clock to line up video frames, participant actions and robot events.

### A3. Which software is actually deployed

11. Does `robot.py` on `albert-phase2` (commit `55cfb61`) match what runs against the cell? Which `ur_rtde` version is installed?
12. Is the generated `rtde_control_track.script` current? Where does `make_track_control_script.py` live? It is not in this branch.
13. Apart from the twin server, what else connects to the UR20 over RTDE in normal use (for example the Basler calibration rig, `twin_proximity_real`, or other scripts)? We understand the controller accepts at most five RTDE clients.
14. Will the `proximity_planner` or `camera_lib` (Basler/EVK4) components be running during Phase 2 sessions? They would compete for robot connections and for computing resources.

### A4. Participant corrections: what moves, who approves, and safety (added 6 Nov 2026)

Our interface now lets participants correct a placement in small steps ("nudges"). Each nudge is a separate request: it is acknowledged, checked against limits, carried out on its own and reported back before the next one is allowed. Nothing is queued or batched. All of this currently runs only in a simulation on one laptop, with no connection to the cell. The simulation uses provisional settings (steps of 1, 2 or 5 mm, at most ±15 mm per axis and 12 nudges per decision point). These are not proposed robot limits.

28. **Held or released element.** Our simulation assumes a correction happens while the gripper still holds the element, at or just above the release pose. Is that the right model for the cell, or would a correction be applied after release (for example by re-grasping)? What are the implications for grip stability, contact with the element below or beside it, and collision risk?
29. **Step sizes and bounds.** Is one-nudge-at-a-time correction acceptable in principle? What step sizes, per-axis and cumulative bounds, and maximum number of nudges per decision point would you set? In which frame and axes (for example along the rail and across it; is vertical motion or rotation ever acceptable)?
30. **Execution reporting.** Could the controlling program report separate times for receipt of a request, acceptance, start of motion, completion of motion, and readiness for the next command? Can it report the achieved displacement (for example from the TCP pose), and how reliable would that be? We would record it but not show it to participants.
31. **Operator or facilitator approval.** Should each participant nudge or retry be approved on site by the operator (or a facilitator) before any motion? If so, what delay should we expect, and could approval be given once per decision point rather than for every nudge?
32. **Intervention safety.** What speeds, accelerations, force or torque limits, contact detection and interlocks should apply to participant-triggered nudges and retries? In which situations must the system refuse a correction (for example the element already in contact, a neighbouring element too close, or certain rail positions)? What should happen if a protective stop occurs during a nudge?
33. **What a retry is.** Physically, what is a "fresh placement attempt" (for example release and re-pick, or return to the above-pose and descend again)? At what point can the system reliably report that the new attempt has begun? Our interface resets the displayed correction only at that moment.
34. **Loss of the participant link.** If the participant link or the experiment server drops during a nudge, should the current small movement complete and then hold (our current assumption), or stop immediately?

---

## Part B: needed later (hardware integration)

### B1. Task definition and calibration

15. When could the measured slot poses replace the placeholders in `Albert/pick_place_poses.json`? Only the lantern drop is marked as measured.
16. What is the confirmed rail travel (the code uses 9400 mm and mentions an earlier 9700 mm)? Are the divider (4700 mm) and the two site ranges correct for the real layout?
17. Has the Phase 2 layout model (`albert_phase2_setup.glb`) been checked against the lab, including which side of the rail the boxes are on and their rail positions?
18. Is the controller's TCP set to the gripper pad centre (0.1946 m), matching the twin?
19. Have the grip and release openings (regolight 60/110 mm, lantern 40/100 mm) been validated with the real blocks?
20. Is the UR3e used in Phase 2 at all? Is there a measured `models/calibration.json`?

### B2. Cameras on the cell

21. Can the wrist camera (an OAK-D Pro PoE) be mounted on the UR20, with its PoE cable routed along the arm and carriage over the full 9.4 m of rail travel? Who would approve the mounting and the cable route?
22. Do the tripods and camera models in the layout model show the intended overview-camera position? We would use them to plan the field-of-view check.
23. Are there any lighting, infrared or reflective-surface constraints at CRATER we should know about? Our cameras' infrared projectors stay off.

### B3. Gripper and NUC

24. What is the NUC's actual address? The configuration says `192.168.1.51` and the README example says `.50`. Is the gripper server running as the systemd service?
25. Should `object_detected` from the gripper be treated as reliable enough to log as a grasp outcome?

### B4. Assets and data

26. May the UR20, UR3e, Robotiq and layout 3D models be used inside our Unity application, which runs on the participant PC and the Quest 3? Are there licence or redistribution limits?
27. Do you have a preferred format for robot event logs, if any? Would you like copies of the trial logs for your own records?

---

## What we are not doing in the meantime

- We will not connect to, test or access the robot LAN, the twin server or the gripper server.
- We will not run any COROL code.
- We will not modify the COROL repository.
- Our streaming work stays on a single laptop (localhost) until the network questions above are settled.

Thank you. We are happy to talk any of this through, or to share our draft architecture and requirements documents.

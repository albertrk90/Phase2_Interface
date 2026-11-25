# Lunar Lantern: status (25 Nov 2026)

Everything here is simulation only, in the twin on the local branch `albert-phase2-alpha`.

## Layout
The layout comes from `U:/.../GLB/PHASE 2 digital twin import - lantern and regolight.glb`.

- **Scene:** `models/phase2_experiment_scene.glb` is now this export without its 126 "built brick" reference nodes (`Albert/phase2/scene_import.py`; record in `data/phase2_scene_import.json`).
- **What moved:** the RegoLight elements are unchanged apart from the camera tripod. Screen Mid moved 600 mm toward RegoLight; its centre is now at rail 4029. The lantern site moved too:
  - pick tray at rail 4740–5940;
  - formwork and build tray at rail ~7630–8030, with the face toward the rail end.
- **Pockets:** `data/lantern_pockets.json` (`lantern_layout.py`) holds the 90 pockets, 12 rows of 7 or 8. Each pose is fitted from its built plate, within 1.6 mm (mean). Tilt runs from 57° on row 1 to 8° on row 12.

## Trial (`data/lantern_assembly_manifest.json`, `lantern_manifest.py`): provisional
- **Placements:** 16 in the middle band, the central 5, 6 and 5 pockets of rows 5, 6 and 7 (picture: `ll_selection_face.png`).
  - **Order:** bottom row first; within a row, nearest the rail first.
  - **CDPs:** P05, P10 and P14.
- **Picks:** the 16 tray plates farthest from the rail, far column first (`ll_pick_tray.png`).
- **Baseline (default, to confirm):** rows 1–4 are preinstalled (30 plates); 2 plates stay in the tray.
- **Recovery slot:** the build tray's far corner on the robot's side, rail ~8160. The plate stands as it does in the pick tray, so it needs a holder.
- **Errors:** none for now.
- **Checks:**
  - no plate overlaps another;
  - plates touch the formwork by at most 0.15 mm;
  - the recovery slot is 204 mm clear of the formwork.
- **Node offsets:** each plate's node origin is about 1 m from the plate and differs per plate. Use `*node_pose_world` for object moves.

## Reach (provisional, before the teach)
Your measured drop (rail 6150, 47.8°) maps to pocket R06C7, which is P11. It approaches about 20° off the plate's long axis, sliding the plate down into its cradle.
- **Placements:** the same pocket-relative pose solves the UR20 inverse kinematics for all 16, at rail 8750–8830 mm.
- **Picks:** the farthest pick column (x = 1.64 m) solves too.

## HOME
HOME is the arm upright at the middle screen, rail 4030. It is also the new divider.
- **Start of a trial:** `trial_baseline` leaves HOME upright, the rail carries the arm to the first pick station, and only then does the arm go to the travel pose (your `enter_site` pattern).
- **End of a trial:** the new step `trial_home` takes the robot back to HOME.
- **Verified:**
  - `twin_link/twin_home_check.py`: 6/6;
  - RegoLight e2e on the new scene: 14/14;
  - RegoLight arm links stay at least 0.47 m from the moved screen.
- **Not yet wired:** the Unity call to `trial_home` at the end of a trial.

## Site camera
`site_lantern` (`phase2/virtual_cameras.json`, v1) sits on your lantern tripod, just in front of the camera body, aimed at the middle of the band.
- **Views:** `ll_site_cam_v1_*.jpg`.
- **Occlusion:** the arm comes in from the rail side and partly covers the band's rail-side end (P01, P06, P12).
- **RegoLight:** `site` is unchanged (`regolight_site_cam_after_import.jpg`).

## Next
1. **Teach session for the grasp:** pick one plate and place it in P01 (Teach tab, Record pose with the plate held). A second taught seat in another row checks the extrapolation.
2. **Trial host:** extend it to Lunar Lantern (per-architecture manifest, taught sequence, recovery slot, travel pose), with a nominal run.
3. **Unity:** choose the architecture, use `site_lantern` for LL trials, and call `trial_home` at the end of each trial.

## Update (25 Nov 2026, evening)
- **Grasp taught:** one pose, `data/poses/2026-11-25_1737_ll_pose_pick_grasped.json`. The fingers close across the 20 mm thickness, with their tips through the hole near the plate's tip; the TCP sits on the plate axis, 113 mm above the centre.
- **Row 6:** now uses columns 1–6. Its column 7 is out of reach from any station that keeps the arm clear. This renumbers P06–P11.
- **Every other pocket is filled at the start:** 74 pockets, so the participant finishes with the whole lantern.
  - The 32 spare tray plates are relocated into pockets, and the tray holds only the 16 to pick.
  - The other 42 are fixed plates kept from the built layout: "lantern fixed plate R..C..", scenery, never moved.
  - Physically the lab needs 90 plates.
- **Release 10 mm short, both architectures:** the brick settles the last 10 mm (a scripted settle, `by: settle_after_release`).
  - RegoLight: trial host and nominal run.
  - Lantern: 10 mm up the plate axis.
- **Nominal lantern run:** `Albert/phase2/lantern_plan.py` → `Albert/phase2_lantern_nominal_poses.json`; run with `Albert/phase2_lantern_nominal_sim.py --watch`.
  - **Rail:** moves only with the arm in a tucked travel pose.
  - **Approach:** each pocket is reached through a point 150 mm out in front of it, then down the plate axis.
  - **Worst clearances:** fingers 14 mm from the formwork; carried plate 33 mm from other plates; arm (approximate model) 115 mm.
  - **Result:** 16/16 in about 570 s, with no arm or gripper contact detected.
  - **Watcher:** runs the viewer's triangle test itself every 40 ms, because the page's own counter doesn't report in a headless page. Proven on a deliberate arm-through-formwork pose.
- **RegoLight e2e: 15/15.** The new check E15 confirms all 18 releases happened 10 mm short and each brick then settled.

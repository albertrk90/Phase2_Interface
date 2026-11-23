# Task 07 AI2 interface mock-up ("Site Window")

A design mock-up for review only. It is **not** part of the Unity application, and nothing here is built, installed or launched by the project.

- **Open:** `index.html` in a browser. It loads IBM Plex from Google Fonts if online, and falls back to system fonts otherwise.
- **Proposal:** [`docs/plans/Phase2_Task07_AI2_Interface_Design_Proposal.md`](../../docs/plans/Phase2_Task07_AI2_Interface_Design_Proposal.md).
- **Revision 2** (6 Nov 2026): decisions from Inspect (R1); incremental, one-at-a-time nudging with a visible lifecycle, kept separate from Retry (R2); View and Adjust wings beside the video.
- **Reviewer controls** (the top bar, which is not part of the interface):
  - reject the next request or nudge;
  - withhold the receipt of the next request or nudge (then **Resolve**);
  - fail the next nudge's movement;
  - inject a video interruption;
  - pause as the experimenter;
  - switch the scene;
  - open the simulated client event log.
- **Jump to a state:**
  - `index.html#demo=decision`, `inspect`, `overview`, `nudge`, `moving`, `inspectnudge`, `confirm`, `rejected`, `retry`, `freeze` or `paused`;
  - `index.html#xr` opens the Quest 3 sketch.
- **Interaction:** mouse only.
  - In Inspect, click the image to zoom in at that point and drag to pan.
  - The keyboard does nothing, by design.
- **Simulation only:** every acknowledgement, execution stage and timing comes from a placeholder backend inside the page. In the placeholder scenes, the element moves when a simulated nudge executes; the real still image is static. **None of it represents real robot behaviour**, which must be commissioned with CRATER/AIML.

## Imagery provenance

| File | Source | Notes |
|---|---|---|
| `assets/camA_E1_seq30_rect_left.png` | Copied from `camera_validation/results/rectify_20261104_170326_19443010B14C872F00_E1_A_default/images/group030_seq30_rect_left.png`, which is unchanged | SHA-256 `8daa9390…ef00c05d` (identical to the source). Camera A, E1, approved configuration. The mock-up applies the approved crop (x 39–1276, y 6–775). No people in view |
| Placeholder scenes | Drawn procedurally in `index.html` | Labelled PLACEHOLDER IMAGERY |

The Camera B recordings (E2/E4) were deliberately **not** used: they show an identifiable person.

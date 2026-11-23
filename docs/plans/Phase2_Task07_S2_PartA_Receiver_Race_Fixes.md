# Task 07: S2 close-out, Part A: receiver race fixes R1 and R2 (results)

**Status (7 Nov 2026): R1 and R2 fixed and verified.**
- **Regression:** the full M1 + S2 regression is green in the Editor and the Windows player.
- **One regression failure during the run:** an S2 harness logging defect (§4), now fixed and re-verified.
- **Gate:** under the researcher's gate ("if the regressions fail, stop and report before S3"), **S3 has not been started**.

**Evidence:** `unity/Phase2Client/test_results/s3_partA_receiver_races/` (git-ignored). Earlier failure evidence is preserved where it was:
- `test_results/unity_rx_20261106_173556_editor_A_playmode`
- `…174409_editor_B_s2`
- `ai2_s2_20261106_174409_editor`
- `…174659_win64player`

---

## 1. Fixes (approved, 6 Nov 2026)

| | Defect | Fix | Files |
|---|---|---|---|
| **R1** | `StereoPresenter` emitted `freshness_reset` **after** releasing its lock (`integrity_error` likewise), so two simultaneous eye resets could be logged in the opposite order to the presenter's own op trace | **Every presenter event is now emitted while the presenter lock is held** (the other five event types already were), so `events.jsonl` follows the op order. Safe under the lock and no blocking I/O: `EventLog.Emit` only serialises and does a non-blocking `TryAdd` to its background writer, the same path `ops.csv` already uses under this lock. Nothing calls back into the presenter, so no lock-order cycle is possible. Event definitions and formats are unchanged | `Video/Core/StereoPresenter.cs` |
| **R2** | `ReceiverCore.OnFrame` told the presenter about a frame **before** storing its pixels, so a display tick in between could select a pair with no image (`display_image_missing`) | **Pixels are stored before the presenter can see the frame**; a pair can only become selectable once both eyes' images exist. The same buffering rules: late or obsolete frames (≤ floor) are never stored; the store stays bounded (24 per eye) with eviction counted; frames the presenter then discards are released by the existing `ReleaseUpTo(floor)`. **Plus** a new `LumaStore.CopyPair`: both eyes are copied atomically or neither destination is touched, so a selected pair can never mix in another frame's image | `Video/Core/ReceiverCore.cs`; `Video/Unity/StereoReceiverBehaviour.cs` (uses `CopyPair`) |

**Pre-fix sources preserved:** `test_results/s3_partA_receiver_races/prefix_source/` holds the three original files, with SHA-256 in `prefix_source_sha256.txt`.

---

## 2. Deterministic tests that reproduce the defects

`Assets/Phase2/Tests/Editor/ReceiverRaceTests.cs` (7 tests, in the existing `Phase2.Compat.Tests` assembly):

| Test | Method | Pre-fix code | Fixed code |
|---|---|---|---|
| `R1_ResetEvents_FollowPresenterOrder_ForcedInterleaving` | The sink holds the left-eye event until the right eye's event arrives (500 ms cap): it forces the exact pre-fix window | **FAIL, 6/6 runs** | PASS |
| `R1_Stress_ConcurrentResetsAndTicks_EventOrderEqualsOpOrder` | 2 × 3000 concurrent resets while ticking | **FAIL, 6/6** | PASS |
| `R2_PixelsStoredBeforePresenterSeesFrame_Invariant` | At the instant the presenter sees a frame (inside its op trace), that frame's pixels must already be stored | **FAIL, 6/6** | PASS |
| `R2_Stress_ConcurrentReadersAndDisplay_NoMissingOrForeignImage` | Two reader threads (paired, ≤ 8 frames apart) + a display thread; every selected pair must have its own pixels | **FAIL, 6/6** (thousands shown, some without pixels) | PASS |
| `R2_EverySelectedPair_ShowsItsOwnPixels_SingleThread` | Content check | PASS (no window single-threaded) | PASS |
| `R2_CopyPair_IsAllOrNothing` | Atomic copy; bounded store unchanged (capacity, eviction count) | n/a (new API) | PASS |
| `R2_LateFrames_StillNeverStored` | Floor rule unchanged | n/a | PASS |

**Runs:** Roslyn + scratch runner. Pre-fix: 3 runs + 3 runs with the bounded-skew stress (`prefix_reproduction.txt`, `bounded_skew_prefix_vs_fixed.txt`). Fixed: 5 runs, **35/35**. Unity EditMode: all 7 pass.

**Observation R5 (pre-existing, not changed):** the first version of the R2 stress test let one reader run more than 256 frames ahead of the other. The presenter keeps only the last 256 records per eye, so a completed pair could lose an eye record before a tick, and `Tick` then threw `KeyNotFoundException` (`OrderedMap` lookup).
- **Why it is outside the envelope:** this needs about 12.8 s of inter-eye skew at 20 fps with no display tick, far outside paired-camera operation.
- **Treatment:** the test now models paired cameras (≤ 8 frames apart) and **still reproduces R2 on the pre-fix code 3/3**.
- **Not changed:** the presenter logic (validated, Python parity). It is noted for awareness.

---

## 3. Regression results (fixed code)

| Suite | Result |
|---|---|
| **EditMode, all** (`editmode_all.xml`) | **109/109 PASS**: 50 Compat (C01–C09; the **20 Python-oracle presenter traces**, so event content and order still match the validated reference; camera source; clock reference; **7 race tests**) + 59 Experiment (S1 + S2) |
| **PlayMode, 6 runs** (`playmode_run1…6.xml`) | **12/12 test passes** (M1 replay + S2 two-camera, each run) |
| Offline verification of the 6 M1 PlayMode runs (`verify_unity_run.py`, unchanged) | **6/6 OVERALL PASS**; oracle replay exact every time |
| Offline verification of the 6 S2 PlayMode sessions (`verify_s2_run.py`) | **All 12 receiver oracle replays PASS.** Overall: run 1 **FAIL** on one S2 view-log rule (§4); runs 2–6 **PASS** |
| **M1 Windows player**, rebuilt (`M1Build.BuildPlayer`), 2 × `replay_A` + 2 × `camera_E1_A` | **4/4 OVERALL PASS**, including the M1 rig's **pixel-exact render check** |
| **S2 Windows player**, rebuilt, 2 scripted sessions | **2/2 OVERALL PASS**; 33/33 scripted checks each |

**R1 and R2 occurrences after the fix:** none, across 26 receiver runs (6 M1 Editor, 12 S2 Editor, 4 M1 player, 4 S2 player):
- **R1:** no event-order mismatch. Before the fix it appeared in 4 of 18 runs.
- **R2:** no `display_image_missing`.

Thresholds and acceptance criteria are unchanged.

---

## 4. Regression failure found and fixed (S2 harness logging, not the receivers)

**Run 1's S2 verification** flagged `outside_inspect_primary_at_1x`: **1 frame of 107,874** appeared to show Camera A at 1× after a decision point with primary B had opened.

- **Investigation** (`ai2_s2_20261106_180521_editor`):
  - the `decision_open` event was stamped 9.4 µs before that row;
  - the row itself showed workflow `monitoring`;
  - the next frame (0.84 ms later) showed the decision open on Camera B at 1×.
- **The plate never showed a wrong camera.**
- **Cause:** two clocks in my S2 harness log.
  - Events carry their scheduled simulation time.
  - View rows were stamped with the wall time in `LateUpdate`.
  - An event scheduled inside a frame's sub-millisecond Update→LateUpdate gap is processed in the next frame, yet appeared to precede the row.
- **Fix** (`Experiment/Unity/S2Session.cs`): each view row is stamped with the frame's simulation time (the time up to which events were processed), the clock the client and backend events use.
- **Re-verified:** PlayMode runs 4–6 and both S2 player runs: all PASS.
- **Unrelated to R1 and R2**, and no change to any receiver, rule or threshold.

---

## 5. Residual note

`integrity_error` is now emitted inside the lock that updates its counters, in `Tick`'s second critical section. The Python oracle models a tick as one atomic step. A theoretical order difference therefore remains possible only if an integrity error coincides with a reader reset landing between `Tick`'s two critical sections.
- It has never been observed.
- An integrity error is itself a test failure.
- Merging `Tick`'s critical sections would mean restructuring validated logic, so I did not do it.

---

## 6. Next

S3 (the Site Window Windows interface) is ready to start on your go-ahead. The receivers, the S2 integration and the verifiers are all green.

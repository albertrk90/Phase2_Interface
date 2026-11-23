# Task 07: first Windows AI2 supervisory interface, with simulated trial and robot states (implementation plan)

**Status: plan only (6 Nov 2026); nothing implemented.**
- **No real robot integration**, no COROL, no network command path. Trial and robot states come from an in-process **simulated backend**.
- **Reuses:** `unity/Phase2Client` and the validated video presentation (`StereoReceiverBehaviour`, `DisplayRig`, crop, logs), unchanged.

## 1. Basis (recorded design; nothing new assumed)

- **AI2 workflow** (Task 04A addendum §7–8; Side Quest audit §8.4):
  - the task runs as discrete steps; at a **decision point** the participant chooses **Allow** (continue), **Inspect** (hold or look) or **Intervene** (retry, or a bounded correction);
  - the backend issues a **decision token**, and the client's choice must carry that token;
  - every intent is **ACKed or NACKed** with a client command ID;
  - **participants send intents, never motion**: no poses, speeds or robot names;
  - **no placement-correctness information** reaches the participant client.
- **One Unity codebase** for the 2D (Windows) and later XR (Quest) conditions: the same AI2 logic, UI and logging. The video path stays separate from the command path.
- **Reused patterns from Side Quest:** the decision token (`DECISION_READY <seq>`), ACK/NACK and timeouts, the main-thread queue, and the `XRUIStateManager` state skeleton (rewritten, not copied).

## 2. Architecture

| Layer | Contents | Unity dependency |
|---|---|---|
| `Phase2.Experiment.Core` (new assembly, pure C#) | Message schema v0 (JSON lines). Client state machine. Decision-token and command-ID tracking. ACK timeout. Event records in the existing `EventLog` schema | None (reusable on Quest; EditMode-testable) |
| `IExperimentBackend` seam | `Connect`, `Send(intent)`, events `OnState` / `OnAck` / `OnNack` / `OnLinkDown` | None |
| `SimulatedBackend` (new, in-process) | Scripted trials. Robot steps (`idle`, `moving`, `at_decision_point`, `holding`, `retrying`, `paused`, `fault`). Decision points. Configurable delays, missing or late ACK, NACK, link loss. Deterministic seed | None |
| `Phase2.Experiment.Unity` (new) | Supervisory UI panel over the left-eye display. Input (mouse and keys). Main-thread dispatch. Status display | UI Toolkit (or uGUI) |
| Video (unchanged) | `StereoReceiverBehaviour`, `DisplayRig`, crop, right-eye developer inset, logs. Sources: file replay of `camera_E1_A` (real Camera A imagery) or synthetic replay; a live RTSP preview only in a later approved session | Existing |

**Message schema v0** (versioned):
- **Backend → client:**
  - `session`, `trial_start`;
  - `step {index, label, robot_state}`;
  - `decision_open {token, options[], opened_t}`, `decision_close {token, reason}`;
  - `ack {client_cmd_id, token}`, `nack {client_cmd_id, reason}`;
  - `trial_end`, `paused` / `resumed` (experimenter).
- **Client → backend:**
  - `ai2 {token, choice: allow|inspect|retry|correct, correction?, client_cmd_id, client_t_mono, client_t_utc, displayed_seq}`;
  - `inspect_end {token, …}`.
- **Correction:** if enabled, chosen from a bounded discrete set (e.g. ±5 mm steps), never free coordinates.

**Logging:** every UI state change, intent, ACK/NACK and decision interval goes to the existing JSONL event log with QPC and UTC times. **Each intent records the video frame seq displayed at that moment**, linking decisions to the exact imagery seen. Decision latency is measured from decision open to the choice.

## 3. Client state machine (participant-facing)

```
Connecting -> Observing <-> DecisionOpen -> AwaitingAck -> (ACK) Observing | Inspecting | Intervening -> Observing
                       \-> Paused (experimenter) ; Ended ; LinkLost (no input accepted)
```

**Rules:**
- Input is accepted **only** while `DecisionOpen` and the token is current. A stale token is NACKed and logged.
- One intent per decision; duplicate clicks are suppressed.
- An ACK timeout (configurable, e.g. 3 s) produces a visible "not confirmed" state and a log entry. There is no silent retry.
- Video keeps playing in every state; the UI never blocks the display tick.

## 4. Milestones (all offline; each closes at a review gate)

| # | Deliverable | Verification |
|---|---|---|
| **I1** | `Experiment.Core` and `SimulatedBackend` (no UI) | EditMode tests: every transition; token mismatch, stale or duplicate intent; ACK timeout; NACK; link loss; schema round-trip; the log schema matches `EventLog` |
| **I2** | Supervisory UI scene (a new scene; M1 scene untouched) over the file-replay video, with scripted simulated sessions | PlayMode: a full simulated trial (several decision points, each choice, a fault, a pause). Display frame-time p99 stays within M1.8 (≤ 1.5 × the display period) with the UI active. Video oracle replay still exact |
| **I3** | Windows player build and a scripted 5-minute simulated session; log checker (Python) | Offline: decision latencies, intent ↔ displayed frame seq, ACK accounting, no input outside open decisions |
| Gate | Review with the researcher (layout, wording, timing) | Before any backend or network work |

**Not in scope:** the real experiment backend, WebSocket and authentication, the task orchestrator, COROL, robots, Camera B and source switching, the Quest build, questionnaires.

## 5. Decisions needed from the researcher before I1

1. **Option set and semantics:** Allow / Inspect / Intervene. Is Intervene split into retry and bounded correction? Correction steps and bounds.
2. **Decision timing:** who opens a decision point; timeout and default action (if any); whether experimenter approval is needed.
3. **Participant status fields:** step number, robot moving or paused, time remaining. None may reveal placement correctness.
4. **Inspect in simulation:** a hold only, or a simulated inspection pose. It is video-neutral while replayed imagery is used.
5. **UI conventions:** layout over the left-eye image (it must not cover the task area), wording, keyboard and mouse.
6. **Logging fields** required for the analysis plan.

## 6. Boundaries and risks

- **Boundaries:**
  - no real robot or COROL code is imported or run;
  - the simulated backend is in-process (no sockets);
  - video components and the validated M1 and camera configuration are unchanged.
- **Risks:**
  - **AI2 semantics** may change after the researcher's design. Mitigation: a versioned schema and configuration-driven options.
  - **UI cost** on the display tick. Mitigation: the M1.8 frame-time check in I2.
  - **The continuity freezes** (Task 06 follow-up) will appear in sessions using live video; this is independent of the interface work.

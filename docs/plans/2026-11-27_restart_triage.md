# Restart triage from the 27 Nov manual run (session S4-P01-01)

Source: `twin_link/runs/sessions/S4-P01-01/session_events.jsonl`, events 220–259. No code was changed; this note is the starting point for the fix. The run used the **study ID P01**.

## What happened

| Time (UTC) | Event | Verdict |
|---|---|---|
| 05:20:33 | B1-T2 starts (Lunar Lantern, 2D) | ok |
| 05:21:14 | B: **Restart this trial**. Interruption opened and closed, trial terminated, replacement **B1-T2-R1** assigned, trial reset entered. | ok |
| 05:21:15 | `corol_twin_home` for B1-T2: **REJECTED**, "busy: …B1-T2-LL-P01 is still running" | **bug** |
| 05:21:15 | `corol_twin_baseline` for B1-T2-R1: **REJECTED**, same reason | **bug: root cause** |
| 05:21:19 | A: go-ahead for the trial | ok, but nothing can start |
| 05:21:23 | The OLD trial's placement LL-P01 completes in the twin. It is logged under B1-T2-R1's IDs, although its request ID is B1-T2's. | logging bug |
| 05:21:23–05:23:03 | Trial reset never completes: the rejected baseline is not re-sent, so the twin is never confirmed ready. **Stuck.** | **bug** |
| 05:23:03 | B: **Restart this block**. B1-T1, B1-T2, B1-T2-R1 and B1-T3 are marked void, new attempts are created, and the reset of B1-T1-R1 begins. | ok |
| 05:23:06 / 05:23:25 | A's go-ahead; baseline COMPLETED; B1-T1-R1 starts. | ok |
| 05:23:32–05:24:02 | A hold request (hold before place), A's pause, and the placement ends "attached" (held). | expected behaviour of the hold, not a restart issue |
| 05:24:12 | App closed. **Restart session not exercised.** | — |

## Root cause

**Twin moves cannot be interrupted, and nothing after a restart waits for the move in progress.** When a trial stops in the middle of a placement, the twin finishes that placement. Meanwhile:
- the HOME request and the next trial's baseline are sent at once;
- the trial host accepts one request at a time, so it rejects both as "busy";
- the baseline is never re-sent, so the trial reset waits forever.

The same applies to any trial that stops mid-placement: Terminate this trial, End session, Discontinue, and Restart block during a running trial. Restart block happened to work only because the robot was already idle when it was pressed.

## Proposed fixes (not done)

1. **Wait for the move in progress before a reset.** Before posting `trial_baseline`, wait until no twin request is in flight; `_corolInFlight` already exists from the end-session work. If the host still answers "busy", re-send once it is idle, and never re-send after any other answer.
2. **HOME at trial end:** wait the same way, or skip it when the next step is a baseline (the baseline moves the robot anyway).
3. **Logging:** record a late placement result under the trial that requested it, not the current one.
4. **Facilitator pages:** while waiting, A's and B's pages say "Waiting for the robot to finish its current move", as the end-session flow already does.
5. **Tests:** a test host that stays "busy" for a few seconds after a terminate. Restart trial, Restart block (during a placement) and End session must each complete without facilitator help.
6. **Still to exercise live:** Restart session, and Restart block while a placement is running.

## Housekeeping

The restart test used the **study ID P01**. Session `S4-P01-01` and P01's entry in `allocation_register.json` must be deleted before the real P01 (pilots should use P901–P924). `S4-P901-01` is a pilot session and can stay or go.

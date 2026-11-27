# Onboarding video: script draft v0.1 (27 Nov 2026)

**Status:** draft for review. The video is `intro_to_study.mp4`, "Introduction to the study". Participants watch it once, after Facilitator B's go-ahead. They can pause and replay it. Continue appears only when it has played to the end.

**Target length:** about 5½ minutes, in 9 segments.

**Narration:** about 130 words per minute, calm and neutral.

**Footage:** recorded from the real interface (2D window) running on the digital twin. Narration is in **bold quotes**; on-screen captions are in `code`. Interface labels are quoted exactly as the interface shows them.

## Rules for the wording (from the study design)

1. **Never imply that a stop means something is wrong.** Decision points are where the participant judges; some placements need no action. Do not say "error", "mistake", "fault", "correct" or "wrong".
2. **Do not reveal the design.** Say nothing about:
   - how many decision points carry a deviation;
   - where the questions appear, or that one decision point per trial is skipped;
   - that deviations are scheduled.
3. **Same words as the screen.** Allow, Inspect, Intervene, Place and release, Retry placement, Nudges remaining, Away from rail / Towards rail, Along rail / Across.
4. **The SAGAT familiarisation text is read in full, word for word** (segment 6). The protocol counts the video as the participant's familiarisation (`covers_sagat_familiarisation`).
5. **No real study material.** Record with a development ID such as **P950**, not P01–P24 or a pilot mirror (P901–P924). The question screen must show the generic practice items ("Sample question"), never a bank question.
6. **Interfaces.** Footage is from the 2D window. For the headset, one sentence says the controls are the same (segment 7). Re-record that part if the XR build differs.

---

## Segment 1: Welcome and roles (0:00–0:35)

**Footage:** title card, then a wide shot of the twin with the robot at HOME. Short cuts: the participant desk; a "Facilitator A at the robot site" card.

> **"Thank you for taking part. In this study you will supervise a robot that is building a structure at a remote site. The robot does the building. Your role is to watch its work and decide, at certain points, whether it can carry on.**
> **Two facilitators work with you. Facilitator B is here with you. Facilitator A is at the robot site and handles anything physical. Today's robot and site are a simulation, so nothing you do can cause harm."**

`Your role: supervise · decide · intervene when you judge it necessary`

## Segment 2: The two structures (0:35–1:20)

**Footage:** one full placement of each architecture from the site camera, at real speed, then a still of a finished structure.

> **"You will supervise two kinds of structure.**
> **The first is RegoLight: blocks laid side by side on a sloped wall. The robot picks each block from a tray, carries it over and lowers it into its place among its neighbours.**
> **The second is the Lunar Lantern: curved plates that slot into tilted pockets, row by row. The robot lowers each plate along its own slope into its pocket.**
> **In both, each element is placed, released, and the robot then moves back so you can see the result."**

`RegoLight · blocks on a sloped wall` / `Lunar Lantern · plates in tilted pockets`

## Segment 3: The screen (1:20–2:15)

**Footage:** the Site Window during building. Highlight each area as it is named.

> **"This is your screen. The large image is the live view from the site.**
> **You have two cameras: the site view, from a fixed camera looking at the structure, and the wrist view, from a camera on the robot's hand.**
> **Above the image you can see what the robot is doing, for example 'Robot placing element'.**
> **At the bottom are your three main controls: Allow, Inspect and Intervene.**
> **On the left are the inspection tools; on the right, the adjustment panel. Both open only when you choose Inspect or Intervene.**
> **If the picture ever freezes or shows 'Video interrupted', keep watching: it does not tell you anything about the robot."**

`Site view · Wrist view` · `Allow · Inspect · Intervene`

## Segment 4: A decision point (2:15–3:10)

**Footage:** a placement finishes. The robot releases, retreats and holds above the element. The status shows `Element released · holding for your decision`, and the hint `Decision point · choose how to proceed` appears. Show **Inspect**: switch camera, click to zoom, drag, **Reset view**, **End inspection**. Then Allow → confirm.

> **"Several times during each trial the robot stops after releasing an element and waits for you. This is a decision point. Take a moment to look at the element that was just placed. There is no time limit on your decision.**
> **Choose Inspect to look more closely: switch cameras, click the image to zoom in, and drag to move around. Reset view takes you back.**
> **If you judge that the element can stay as it is, choose Allow. The robot then continues with the next element.**
> **Some decision points need nothing from you, and some may need an adjustment. That judgement is yours.**
> **After your first decision at each decision point you will be asked how confident you are, on a scale from 1, 'Not at all confident', to 7, 'Extremely confident'."**

`Allow: accept the current state and continue`

## Segment 5: Intervening (3:10–4:30)

**Footage, RegoLight first:**
1. Intervene → recovery requested → the notice `Your facilitator is preparing the brick for pick-up…` → the robot picks the block up and holds it.
2. Two nudges, showing the stages of each one.
3. **Place and release** → `Released. Reassess the resulting placement.` → Allow.

**Then the Lantern (short):** the adjust panel showing only **Away from rail / Towards rail**.

**Then Retry (short):** **Retry placement…** with its confirmation text.

> **"If you judge that the element needs adjusting, choose Intervene. Facilitator A sets the element so the robot can pick it up again, and the robot then holds it for you.**
> **While it is held, you can nudge it, one small step at a time. For RegoLight you can nudge it along the rail or across. For the Lunar Lantern, plates move along their row: away from the rail or towards it.**
> **Each nudge is sent and carried out on its own. Watch it go from sent, to accepted, to moving, to done before the next one. The panel shows how many nudges you have left.**
> **When you are satisfied, choose Place and release. The robot lowers and releases the element. Look at the result again; you can then Allow, or intervene again.**
> **Retry placement starts the placement again from the beginning, the way the robot normally places it. Any nudges you made are not kept.**
> **You can also ask the robot to hold while it is building, using Inspect or Intervene, if you see something you want to look at."**

`Intervene → robot holds the element → nudge → Place and release`
`Retry placement: start again · nudges not kept`

## Segment 6: Questions during the task (4:30–5:05)

**Footage:** the view goes dark; the question screen with "Question 1 of 3" and generic practice options; answer three; the view returns.

> **"Sometimes the view will be hidden and a few questions will appear. The construction pauses while you answer, and the view comes back afterwards. There are no time limits and you get no feedback.**
> **Answer using the construction state you observed immediately before the view was hidden. Select the option that best describes that state. Choose 'Cannot determine' if you cannot answer from the information you observed. For prediction questions, assume that no corrective intervention is made and construction proceeds according to the planned sequence."**

(The second paragraph is the SAGAT familiarisation text, verbatim from the protocol. If the protocol text changes, re-record this segment.)

`The view returns after the questions`

## Segment 7: How the session runs (5:05–5:35)

**Footage:** a block introduction screen, a "Trial 3 of 12 complete" screen, then a still of the headset.

> **"The session has four blocks: each structure once on this screen and once in a headset. The controls in the headset are the same. Each block has three trials. Before the first block you will do two short practice runs.**
> **After each trial you will see a short summary screen. At the end of each block you will complete a short survey with the facilitator. You can ask for a break at any time."**

`4 blocks × 3 trials · practice first · short survey at the end of each block`

## Segment 8: Close (5:35–5:50)

> **"Take the time you need at each decision, and decide as you would if this were a real site. If anything is unclear, ask Facilitator B now. When you are ready, select Continue."**

---

## Recording notes

- **Setup:**
  1. `start_twin_trial.ps1`, ID **P950**.
  2. Record the participant window only (1920 × 1080), with the facilitator pages off screen.
  3. Facilitators act from the web pages as usual.
- **What to record from:**
  - a practice run for segments 4–6;
  - a measured trial at a decision point with a visible deviation for segment 5. P950 gets a medium deviation at every active decision point.
  - Show at least one Allow on an element that looks fine.
- **Do not show:** facilitator pages; any P01–P24 or P901–P924 session; the SAGAT bank; the "Development rehearsal" tag.

  The tag is participant-visible. Check whether the build shows it. If it does, crop it out, or agree a recording build without it.
- **Length check:** segments 1–8 are about 5:50. If it runs long, trim segment 2 to one placement each, and cut the hold-while-building sentence in segment 5 (the practice run covers it).

## Decisions (researcher, 27 Nov 2026)

1. **Decision time:** no time limit; segment 4 now says so.
   - Separately, the protocol's look-only observation interval at each decision point is 1 s, although its note said 10 s. That interval comes before the controls open and is identical at every decision point.
   - It is kept at 1 s and the note is corrected.
   - SAGAT set 6 (movement during the observation period) needs a longer, interpretable interval before it can be validated.
2. **Survey:** Survey B only, at the end of each block (segment 7 updated).
3. **Breaks:** participants may ask for a break at any time (segment 7; the Pause button on B's page).
4. **Narration: synthesised.**
   - Use one voice and one setting throughout, and keep the voice name and settings with the files, so segment 6 can be regenerated identically if the familiarisation text changes.
   - Generate one audio file per segment and lay it over the footage; segment lengths then follow the audio.
   - Check pronunciation of "RegoLight" (REG-oh-light, as in regolith; confirm with the team) and "Lunar Lantern". Use a plain, unhurried rate: about 130 words per minute, or slightly slower for segment 6.

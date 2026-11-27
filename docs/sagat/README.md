# SAGAT question bank (status 27 Nov 2026: DRAFT)

`sagat_question_bank_v2.csv` is the researcher's bank. It has six sets per architecture, each with one L1, one L2 and one L3 question. Set membership is `probe_set_id` in the notes.

It is imported into the live protocol `unity/Phase2Client/Assets/Phase2/Experiment/Protocols/phase2_s41_corol_regolight_nominal_taught.json` (version `0.9.0-sagat-bank-v2-dev`).

## What runs
- **Measured freezes:** each one shows one complete predefined set, as L1, then L2, then L3.
- **Allocation:** `sagat_set_allocation` in the protocol (file `unity/Phase2Client/Tools/data/sagat_set_allocation_v1.json`).
  - Per participant and architecture, all six sets once: three in 2D, three in XR.
  - Across P01–P24, each set appears 12 times in 2D and 12 in XR, and 8 times at each of early, middle and late. Trial position T1/T2/T3 is also 8 each.
- **Independent of Williams:** the inputs are the CDP allocations, which say where each freeze is. The Williams sequence is not an input.
  - As a diagnostic, how often each set falls in a participant's first block of that architecture varies. For example, LL-6 is 6/24 and LL-1 is 14/24. This is not balanced.
- **Development ids (P900–P999):** a fixed rule. Sets 1–3 go in the architecture's first block and sets 4–6 in its second.
- **Practice probes:** the generic practice items, never a bank set.
- **Replacement trials:** keep the replaced trial's set.
- **Never performance-based:** nothing is selected from participant performance.

## Not ready / not done
- **Bank status:** draft, not protocol-locked.
  - The protocol carries only question text and options.
  - `answer_rule` and `notes` stay in this CSV, which is pinned by its sha256. They never reach the participant.
- **Sets 5 and 6:** `pending_validation`. Each freeze that uses them is flagged `sagat_set_pending_validation_<set>`.
  - Set 5 needs validation of the downstream placement relationship.
  - Set 6 needs an interpretable settling sequence during the observation interval.
- **Scoring:** none. Each freeze is logged with `scoring_status: unscored` and `freeze_state_basis: simulated` (the twin's state). Any later key derived from the twin must stay labelled apart from physically verified keys.
- **applies_when:** only `any` is implemented. The importer refuses other values until they are defined.
- **Eligibility check:** "requires a subsequent planned placement" holds at every freeze location (P05→P06, P10→P11, P14→P15 on both architectures). It is checked by the allocator and again at each freeze.

## What is logged (session_events.jsonl)
- **`sagat_freeze`:**
  - `instrument_id` (bank id), `instrument_version`, `bank_status`, `bank_source_sha256`;
  - `question_set`, `set_number`, `set_readiness`, `set_eligibility`;
  - `set_assignment_source`, `set_allocation_version` / `_sha256`;
  - `subsequent_planned_placement`, `item_ids`;
  - `scoring_status`, `freeze_state_basis`.
- **`sagat_item_shown`:** item id, SA level, text, `options_presented`.
- **`sagat_response`:** item id, `question_set`, `bank_version`, `option_index`, `option`, `options_presented`, timing.
- **`cdp_closed`:** `sagat_set` and the flags.
- **`session_manifest.json`:** `sagat_question_bank` (bank id, version, sha256, allocation version and sha256, set source).

## Changing the bank
From `unity/Phase2Client`, using the twin venv's Python:
```
python -I Tools/import_sagat_bank.py --csv ../../docs/sagat/sagat_question_bank_vN.csv Assets/Phase2/Experiment/Protocols/phase2_s41_corol_regolight_nominal_taught.json
python -I Tools/sagat_set_allocation.py --protocol <same protocol> --embed <same protocol>
python -I Tools/test_sagat_bank_tools.py
```
- Make a new CSV version rather than editing v2.
- The allocator takes about 45 s.
- Re-run it after any change to the bank or to the participant schedule. Unity refuses an allocation made for another bank or schedule.

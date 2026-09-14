# 13: Replace scheduled communications safely

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 12

**What to build:** Prepare a replacement locally and execute confirmed removal-before-submission without leaving two intended versions scheduled.

## Acceptance criteria

- [ ] Preparing a replacement leaves the original schedule active and prominently visible until explicit cancellation or replacement Confirmation.
- [ ] Confirmation binds the exact replacement Preparation and schedule; prior Confirmation does not transfer.
- [ ] Verify removal of the original external scheduled draft before submitting the replacement; unknown removal prevents submission.
- [ ] If removal succeeds but replacement submission fails, pause with accurate evidence and do not automatically restore the original.
- [ ] Treat uncertain replacement submission as Unknown Outcome and reconcile before another attempt.
- [ ] If the original sends during cancellation, freeze its Sent Record and pause; further communication requires a new linked action and Confirmation.
- [ ] Test restart and interruption across each replacement step, preserve hidden preparation history, and perform controlled live acceptance of supported operations.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled external mailbox capabilities through the dedicated extension separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

# 14: Reconcile direct mailbox changes

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 11

**What to build:** Record direct mailbox edits, cancellation, and sending without restoring stale plans or transferring authorization.

## Acceptance criteria

- [ ] Detect supported direct changes through manual refresh and the existing mandatory Reconciliation triggers.
- [ ] Record observed external state and discrepancies with prior local plans, preserving immutable sent content and additional evidence.
- [ ] External edits do not inherit prior Confirmation and never trigger automatic restoration of the old content or schedule.
- [ ] Show changed schedules and sending outcomes in task inspection; pause affected execution when new evidence blocks it.
- [ ] Offer configurable periodic observation without granting it authority to alter external sending state.
- [ ] Boundary tests and controlled extension checks cover direct editing, cancellation, sending, repeated observations, and unchanged local Sent Records.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled external mailbox capabilities through the dedicated extension separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

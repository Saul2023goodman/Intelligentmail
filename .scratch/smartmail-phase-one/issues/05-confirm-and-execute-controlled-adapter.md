# 05: Confirm and execute through a controlled adapter

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 04

**What to build:** Review and confirm exact messages and demonstrate the complete execution workflow against a controlled mailbox adapter.

## Acceptance criteria

- [ ] Review sender, recipients, subject, attachment names and contents, readiness, execution details, and full message before individual or batch Confirmation.
- [ ] Only exact confirmed Ready Preparation can generate an external execution request; new blockers or changed content invalidate eligibility.
- [ ] A controlled adapter demonstrates successful execution, observed failure, and Unknown Outcome without real sends.
- [ ] Persist Confirmation, Execution Attempts, and evidence; mailbox-confirmed Sent creates immutable content and a Sent Record independently of delivery or reading.
- [ ] A blocking failure pauses the current Execution Flow; local inspection remains available, and already executed actions cannot execute again.
- [ ] Rewrite invalidates Confirmation and is refused until an active attempt is stopped or resolved; post-Sent communication requires a new linked action.
- [ ] Boundary tests verify no unconfirmed external requests, exact attachment binding, batch pause, immutable sent history, and preparation-only absence of mailbox writes.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.


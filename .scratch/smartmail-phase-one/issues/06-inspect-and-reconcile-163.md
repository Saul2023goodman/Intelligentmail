# 06: Inspect and reconcile the real 163.com mailbox

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 01

**What to build:** Observe the real mailbox through a browser adapter and expose persisted evidence and manual Reconciliation in SmartMail.

## Acceptance criteria

- [ ] Open the intended student's mailbox with operator-assisted login, verification, or CAPTCHA handling; do not bypass interactive authentication.
- [ ] Read supported mailbox history and message observations without creating external drafts or changing sending state.
- [ ] Persist inspectable observations, platform references where available, and Evidence Coverage; unsupported or ambiguous observations remain explicit.
- [ ] Manual refresh reconciles available observations into the local record without treating mailbox state as the primary store.
- [ ] Expose per-capability availability without assuming that successful reading verifies sending, scheduling, cancellation, or Recall.
- [ ] Use controlled real-mailbox acceptance checks for observable evidence and authentication; use adapter fixtures for repeatable command-boundary tests.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

Controlled mailbox access is required for browser verification. Never mark live behavior verified from simulated evidence.


# 09: Execute confirmed immediate sends in 163.com

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 07, 08

**What to build:** Execute operator-confirmed immediate sending through the real 163.com page with evidence-based outcomes and recovery.

## Acceptance criteria

- [ ] Open and fill the real compose interface only for ready operator-controlled execution, using the exact confirmed sender, recipient, content, and attachment snapshot.
- [ ] Reconcile before execution, honor new blockers, and perform no immediate send without applicable Confirmation.
- [ ] Observe mailbox confirmation before marking Sent and freezing sent content and execution history.
- [ ] Pause the current Execution Flow for authentication, blocking failure, or unresolved outcomes; reconcile before continuation.
- [ ] Accept immediate sending independently from native scheduling and expose a disabled capability if it cannot be verified reliably.
- [ ] Run controlled live acceptance for the immediate-send path plus repeatable boundary tests for failures, takeover, and immutable Sent Records.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.


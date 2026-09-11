# 08: Recover interrupted execution and manual takeover

Status: resolved
Labels: implemented
Blocked by: 05, 06

**What to build:** Resume interrupted confirmed work from persisted evidence without blind retries, and support explicit reconcile-and-continue after Manual Takeover.

## Acceptance criteria

- [x] Persist execution intent and attempt evidence sufficiently to distinguish not attempted, observed outcomes, and Unknown Outcome across crash boundaries.
- [x] Reconcile unfinished work after restart and uncertain external actions before deciding whether further execution is permitted.
- [x] Positive evidence of prior success prevents a repeated request; unresolved outcome pauses for intervention rather than being converted to failure.
- [x] Explicit reconcile-and-continue observes manual work before progressing; acknowledgment alone is not proof of Sent.
- [x] Automatically resume only still-valid confirmed work; retain existing blocking pauses and require a newly confirmed time if the confirmed time has expired.
- [x] Authentication interruptions and operator intervention leave local preparation and inspection usable.
- [x] Boundary tests inject crashes before submission, during submission, and after success before outcome persistence; assert no blind retries or unconfirmed actions.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

## Comments

2026-09-11: Implemented Ticket 08 through the existing SmartMail command/query boundary. Execution Attempts now persist committed intent, submission phase, outcome evidence, and timestamps. Restart recovery converts an in-progress attempt to Unknown Outcome and a `recovery_required` pause; a pre-submission controlled crash remains `not_attempted` and is safely reusable, while a sent outcome persisted before local Sent Record creation is finalized on restart without another external request.

Added `execution resume`, `execution takeover`, and `execution reconcile-and-continue` terminal operations. Reconciliation performs a read-only mailbox refresh and resolves an attempt only from a unique outbound observation with mailbox-confirmed `sent`; acknowledgment, drafts, partial evidence, authentication interruption, and ambiguity do not establish Sent. Manual Takeover is retained as inspectable evidence, and continuation runs only supplied active, unchanged, still-valid Confirmations. Existing blocking pauses remain in force, and expired Confirmations require an explicit renewed Confirmation with a fresh time.

The controlled adapter now provides deterministic authentication and crash-boundary fixtures. Ticket 08 adds nine command-boundary tests for restart recovery, safe pre-submission resume, positive reconciliation, Manual Takeover, acknowledgment safety, authentication interruption, blocker retention, expiry, and after-success recovery. The complete suite passes **145 tests with 5 representative-material tests skipped**. See [Supported Execution Recovery Pattern 08](../../../docs/recovery-pattern-08.md) and [validation](../../../docs/ticket-08-validation.md).

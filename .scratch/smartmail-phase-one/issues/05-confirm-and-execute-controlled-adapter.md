# 05: Confirm and execute through a controlled adapter

Status: resolved
Labels: implemented
Blocked by: 04

**What to build:** Review and confirm exact messages and demonstrate the complete execution workflow against a controlled mailbox adapter.

## Acceptance criteria

- [x] Review sender, recipients, subject, attachment names and contents, readiness, execution details, and full message before individual or batch Confirmation.
- [x] Only exact confirmed Ready Preparation can generate an external execution request; new blockers or changed content invalidate eligibility.
- [x] A controlled adapter demonstrates successful execution, observed failure, and Unknown Outcome without real sends.
- [x] Persist Confirmation, Execution Attempts, and evidence; mailbox-confirmed Sent creates immutable content and a Sent Record independently of delivery or reading.
- [x] A blocking failure pauses the current Execution Flow; local inspection remains available, and already executed actions cannot execute again.
- [x] Rewrite invalidates Confirmation and is refused until an active attempt is stopped or resolved; post-Sent communication requires a new linked action.
- [x] Boundary tests verify no unconfirmed external requests, exact attachment binding, batch pause, immutable sent history, and preparation-only absence of mailbox writes.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled external mailbox capabilities through the dedicated extension separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

## Comments

2026-09-11: Confirmed the seam with the operator before writing tests. Four decisions were settled:

1. **The controlled adapter is injected through the constructor and selected at the terminal.** `SmartMail(home, mailbox=adapter)` is the Python boundary; the terminal gains global `--adapter {disabled,controlled}` and `--adapter-script PATH`. The default adapter is `DisabledMailbox` — no enabled capability, so nothing leaves the machine until a capability is separately verified.
2. **This slice binds immediate execution details only.** A Confirmation carries `{"kind": "immediate"}`; windows, timezone, spacing and daily limits belong to tickets 10 and 11.
3. **`confirmation` and `execution` are separate command groups.** `confirmation review PREPARATION_ID`, `confirmation confirm PREPARATION_ID [ID ...]` (one Confirmation per Preparation), `confirmation list|show`, `execution run|list|show|status|stop`, and `sent list|show`.
4. **"Stop or resolve" is the minimal release.** `execution stop ATTEMPT_ID` marks an unresolved (`in_progress`/`unknown`) attempt stopped and releases an `unknown_outcome` pause; a `failed` attempt is terminal and needs reconciliation (tickets 06 and 08).

Implementation: new `confirmations`, `execution_attempts`, `sent_records`, `sent_attachments` and `execution_flow` tables (added idempotently by `schema.sql`), and a `smartmail/mailbox.py` adapter boundary (`DisabledMailbox`, `ControlledMailbox`). A Confirmation binds the Preparation identity, a content digest over sender/recipient/subject/body and an attachments digest over the confirmed labels, names and SHA-256 values. `run_execution` recomputes both digests and refuses on any change or new Blocker, records an Attempt before submitting, and creates a frozen `sent_record` with private copies of the attachment bytes on adapter-confirmed Sent. `rewrite` now refuses while an attempt is unresolved or after Sent, and invalidates the replaced Preparation's active Confirmation.

Completed TDD cycles at the core command/query seam plus the terminal shell: review, binding/renewal/batch, success and the immutable Sent Record, eligibility refusals and the disabled default, failure and Unknown Outcome pauses, stop/rewrite/post-Sent rules, restart persistence, then CLI wiring. Final run: **112 tests passed, no skips**, including the opt-in representative tests.

Representative results: `sample.zip` produced 17 Preparations; Tessa Laird's reviewed message bound CV SHA-256 `1a04f288…d67e` (28,258 bytes) at `{"kind": "immediate"}` with zero execution requests recorded; a controlled `sent` produced one `sent` Attempt and a Sent Record whose frozen CV matched the preserved Source Material; an `unknown` outcome paused the flow (`unknown_outcome`, detail `connection lost`) with all 17 Preparations still inspectable, a run while paused refused, and `execution stop` returning the flow to `idle`.

Pattern: [Supported Confirmation and Controlled Execution Pattern 05](../../../docs/confirmation-pattern-05.md). Results and pilot: [validation](../../../docs/ticket-05-validation.md). Real 163.com inspection/execution and recovery are tickets 06, 08 and 09.


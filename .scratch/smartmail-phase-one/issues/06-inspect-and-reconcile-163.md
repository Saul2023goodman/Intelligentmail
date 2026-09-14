# 06: Inspect and reconcile the real 163.com mailbox

Status: resolved
Labels: implemented
Current validation: dedicated-extension live acceptance pending
Blocked by: 01

**What to build:** Observe the real mailbox through the dedicated extension and expose persisted evidence and manual Reconciliation in SmartMail.

## Acceptance criteria

- [x] Connect the intended student's Mailbox through the operator-selected dedicated extension after login, verification, or CAPTCHA handling; do not bypass interactive authentication.
- [x] Read supported mailbox history and message observations without creating external drafts or changing sending state.
- [x] Persist inspectable observations, platform references where available, and Evidence Coverage; unsupported or ambiguous observations remain explicit.
- [x] Manual refresh reconciles available observations into the local record without treating mailbox state as the primary store.
- [x] Expose per-capability availability without assuming that successful reading verifies sending, scheduling, cancellation, or Recall.
- [x] Use controlled real-extension acceptance checks for observable evidence and authentication; use extension-peer and adapter fixtures for repeatable command-boundary tests.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and controlled extension-peer evidence where needed. Verify enabled extension capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

Controlled extension access is required for live mailbox verification. Never mark live behavior verified from simulated evidence.

## Comments

2026-09-11: Implemented persisted, read-only 163.com observation and manual Reconciliation through the existing `SmartMail` command/query boundary. The named headed browser session delegates login, verification and CAPTCHA to the Operator and stores no credentials. A refresh against the wrong authenticated account persists `wrong_mailbox` and imports no message rows.

The live acceptance used the intended mailbox after operator-assisted login. The expanded adapter discovered five recognized built-in folders from the live DOM, mapped them to folder IDs 1–5, paginated in pages of 50, enumerated 294 canonical IDs across 10 pages, and fetched structured metadata details for all 294 with zero detail failures. Per-folder totals were Inbox 19, Drafts 2, Sent 10, Deleted 263 and Spam 0. Every folder reports complete enumeration and detail coverage; top-level whole-mailbox coverage remains false because virtual views, unrecognized custom folders and bodies remain excluded.

Metadata-only detail calls preserve unread state. Exploration established that the separate body-HTML endpoint marks an unread message read even with tracking suppression; the target was restored immediately and a reload confirmed the original four unread Inbox messages. The production collector therefore excludes body HTML and records that limitation on every message. The full acceptance scan left four unread messages unchanged.

Manual refresh persisted 294 observations and 294 explicit Reconciliation findings, and inspection after a separate CLI restart returned all canonical IDs and structured detail objects. Reconciliation preserves `draft`, `deleted` and `spam` as non-delivery states and does not mutate canonical local state (`local_state_changed: false`). All four state-changing 163 capabilities remain independently disabled and unverified.

Final ordinary suite: 120 tests passed with 5 representative-material tests skipped by their opt-in environment gate. Ticket 06 has eight controlled boundary tests covering persisted refresh/restart, folder/detail Evidence Coverage, preserved non-delivery states, wrong-mailbox refusal, explicit ambiguity, per-capability isolation, exact Sent Record and unresolved-attempt links without canonical mutation, and terminal inspection. See [pattern](../../../docs/reconciliation-pattern-06.md) and [validation](../../../docs/ticket-06-validation.md).

2026-09-14 pivot: the retired Playwright CLI implementation and its named browser-session commands are no longer the product path. The current implementation uses the dedicated `Mailbox Extension` and an explicit `Extension Connection` through Native Messaging. Existing live measurements above remain historical evidence about the 163.com surface; they do not verify the extension. Re-run the acceptance through `--adapter 163-extension` before marking `read_history` verified. See [extension validation](../../../docs/extension-validation.md) and [pivot guide](../../../docs/browser-extension-pivot.md).


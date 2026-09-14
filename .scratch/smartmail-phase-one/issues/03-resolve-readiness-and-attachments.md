# 03: Resolve readiness Exceptions and attachments

Status: resolved
Labels: implemented
Blocked by: 02

**What to build:** Resolve preparation problems inside SmartMail and obtain Ready Preparation with the correct unchanged attachment contents.

## Acceptance criteria

- [x] List and inspect blocking Exceptions with their source evidence and readiness findings.
- [x] Correct fields and Source Associations through terminal commands, applying field-specific precedence without guessing identity or recipients.
- [x] Associate attachments where the evidence is reliable; allow manual file selection or import when a file is missing or ambiguous. **Confirmed operator decision: association is suggested, never automatic.** A body/source declaration creates an *advisory* slot with the best candidate; the operator confirms, replaces, adds or removes it.
- [x] Preserve attachment bytes without conversion, merging, or content modification.
- [x] Revalidate the complete Preparation after correction; readiness remains separate from sending authority.
- [x] Boundary tests cover missing recipient or subject, conflicting identity, missing attachment, correction, and persistence without external writes. **Confirmed operator decision: an unresolved attachment never blocks readiness**, so the missing-attachment case is asserted as advisory (a candidate-less slot) rather than blocking.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled external mailbox capabilities through the dedicated extension separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

## Comments

2026-09-11: Confirmed the design with the operator before writing tests. Three decisions were settled:

1. **Attachment slots are advisory only.** When the message body or a Source Material indicates an attachment type, SmartMail creates a *suggested* slot (for example `Student CV`) and shows the best matching file candidate. It must not finalize the association. The operator can confirm the suggested file, replace it, remove the slot, or add further slots. Slots never block readiness and there is no `require` operation — only an explicit requirement would make a slot mandatory, and none is implemented.
2. **Identity conflicts are resolved by an explicit confirmation command.** `task confirm-identity` clears that Task's own `identity_ambiguity` Blocker and revalidates its Preparations. No identity is guessed or merged; each affected Task is confirmed individually.
3. **The seam is `exceptions list/show`, `task confirm-identity`, and Preparation-scoped `set-subject` / `set-recipient` / `suggest` / `confirm` / `attach` / `add-attachment` / `remove-attachment`.** Confirmed as proposed.

Implementation: findings computation was centralized in one `_revalidate` step so creation and every correction recompute the whole Preparation. New local tables `corrections`, `attachment_slots` and `attachments` keep Correction Records and byte snapshots.

Completed TDD cycles at the core command/query seam plus the terminal shell. Final run: **63 tests passed, no skips**, including the opt-in representative test.

Representative results: 17 Preparations each receive one advisory `Student CV` slot with the single candidate `姚思培/Sipei Yao - CV.docx`; nothing is confirmed automatically; 4 `invalid_recipient` Task Exceptions are listed with their workbook evidence; and the Susanna Castleden recipient conflict is corrected to the recorded address. Confirmed CV bytes match the preserved Source Material (SHA-256 `1a04f288…d67e`, 28,258 bytes).

Pattern: [Supported Readiness and Attachment Pattern 03](../../../docs/readiness-pattern-03.md). Results and pilot: [validation](../../../docs/ticket-03-validation.md). Rewrite with inspectable history is ticket 04.

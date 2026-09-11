# 03: Resolve readiness Exceptions and attachments

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 02

**What to build:** Resolve preparation problems inside SmartMail and obtain Ready Preparation with the correct unchanged attachment contents.

## Acceptance criteria

- [ ] List and inspect blocking Exceptions with their source evidence and readiness findings.
- [ ] Correct fields and Source Associations through terminal commands, applying field-specific precedence without guessing identity or recipients.
- [ ] Automatically associate required attachments where reliable; allow manual file selection or import when a file is missing or ambiguous.
- [ ] Preserve attachment bytes without conversion, merging, or content modification.
- [ ] Revalidate the complete Preparation after correction; readiness remains separate from sending authority.
- [ ] Boundary tests cover missing recipient or subject, conflicting identity, missing attachment, correction, and persistence without external writes.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.


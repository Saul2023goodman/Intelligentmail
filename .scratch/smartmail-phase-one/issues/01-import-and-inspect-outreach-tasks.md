# 01: Import and inspect Outreach Tasks

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: None (can start immediately)

**What to build:** Import a representative master list into an explicitly selected Campaign and inspect persisted Outreach Tasks and their Source Materials.

## Acceptance criteria

- [ ] Select or create a Campaign through the terminal; import establishes Student, Supervisor, Institution, and Mailbox records and Student × Supervisor × Campaign task identity.
- [ ] Establish the first Supported Intake Pattern from representative materials during coding, including justified aliases and column variations; do not require source restructuring.
- [ ] Known supervisor addresses share a Supervisor identity only with explicit reliable evidence; unresolved identity matches are surfaced rather than guessed.
- [ ] Inspect task details and open preserved original Source Materials through the terminal.
- [ ] Restart preserves imported tasks, source evidence, and campaign membership.
- [ ] Exercise import, inspection, ambiguity, and restart through the stable core command/query boundary; choose only the technology needed for this complete slice.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

Representative source materials are required to validate real intake support. Their absence must be recorded rather than replaced with claims based only on invented samples.


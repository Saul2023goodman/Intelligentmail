# 01: Import and inspect Outreach Tasks

Status: resolved
Labels: implemented
Blocked by: None (can start immediately)

**What to build:** Import a representative master list into an explicitly selected Campaign and inspect persisted Outreach Tasks and their Source Materials.

## Acceptance criteria

- [x] Select or create a Campaign through the terminal; import establishes Student, Supervisor, Institution, and Mailbox records and Student × Supervisor × Campaign task identity.
- [x] Establish the first Supported Intake Pattern from representative materials during coding, including justified aliases and column variations; do not require source restructuring.
- [x] Known supervisor addresses share a Supervisor identity only with explicit reliable evidence; unresolved identity matches are surfaced rather than guessed.
- [x] Inspect task details and open preserved original Source Materials through the terminal.
- [x] Restart preserves imported tasks, source evidence, and campaign membership.
- [x] Exercise import, inspection, ambiguity, and restart through the stable core command/query boundary; choose only the technology needed for this complete slice.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

Representative source materials are required to validate real intake support. Their absence must be recorded rather than replaced with claims based only on invented samples.

## Comments

2026-09-11: User supplied `C:\Users\Zeng\Downloads\sample.zip` during implementation. Inspected its actual master workbook, merged cells, headers, source filenames and CV identity evidence before defining the intake pattern. Implemented the terminal shell and stable `SmartMail` boundary using Python, SQLite and openpyxl.

Completed TDD cycles at this ticket's agreed core command/query seam. Final run: 15 tests passed, including the opt-in real-material test with no skips. Separate CLI processes validated Campaign/Student creation, import, inspection and preserved-source materialization. Actual results: 59 tasks, 11 Institutions, 55 usable recipient addresses, four persisted recipient Blockers, 22 preserved Source Materials. Native desktop viewer launch was not visually verified; source materialization and hashes were verified. No browser capability is enabled in this slice.

Usage: [README](../../../README.md). Rules: [Supported Intake Pattern 01](../../../docs/intake-pattern-01.md). Detailed results and retained local pilot commands: [validation](../../../docs/ticket-01-validation.md). Draft interpretation and per-task document association remain ticket 02.

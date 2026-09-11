# 02: Prepare communications from existing documents

Status: resolved
Labels: implemented
Blocked by: 01

**What to build:** Associate existing draft documents with Outreach Tasks and produce inspectable local Preparation using supported deterministic rules.

## Acceptance criteria

- [x] Inspect representative documents during coding and define supported layouts, field precedence, and justified related variations.
- [x] Associate document content to the correct Outreach Task with traceable Source Associations; identity and recipient conflicts prevent Ready Preparation.
- [x] Apply supported cleanup, normalization, substitution, and restructuring automatically without a routine human acceptance step.
- [x] Preserve source evidence and Transformation Records and open a full message preview from the terminal.
- [x] Missing values come only from unambiguous Authoritative Sources; unsupported transformations or internal-note separation become Exceptions rather than invented content.
- [x] Preparation persists across restart and produces no external mailbox draft writes; boundary tests assert expected content, associations, and unsupported cases.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

## Comments

2026-09-11: Inspected all 19 draft documents in the same `sample.zip` used for ticket 01 before defining the pattern. Their layout is uniform: an `Email:` recipient line, a `Dear ...` greeting, body paragraphs, a `Yours sincerely,` sign-off, and a trailing `Research source:` internal note. Filenames follow `<Institution>_<Supervisor name>.docx`. Seventeen drafts name a Supervisor in the master list; the two UTS drafts (Nahum McLean, Nga Wun Doris Li) do not.

Confirmed four design decisions with the operator before writing tests: (1) no subject is invented — a missing subject is a blocking readiness finding; (2) the trailing research note is separated as a supported transformation and retained as an internal note; (3) the draft recipient is authoritative for the message, a differing recorded address is a blocking conflict, and the draft fills a missing recorded address; (4) attachment association is deferred to ticket 03.

Completed TDD cycles at the core command/query seam (`prepare_from_documents`, `list_preparations`, `get_preparation`, `preview_preparation`, `list_unassociated_documents`) plus terminal commands `prepare`, `preparation list|show|preview`, and `imports findings`. Final run: 34 tests passed, no skips, including the opt-in representative test.

Representative results: 17 Preparations, 2 `unassociated_document` findings, 1 `recipient_conflict` (Susanna Castleden), 1 filled missing address (Callum Morton), and 17 `missing_subject` findings; no Preparation is Ready until a subject is supplied. A real CLI pilot in separate processes is retained under `.smartmail/ticket02-pilot`. A repeat-preparation duplication bug in document findings was found by the pilot and fixed with a regression test.

Pattern: [Supported Document Pattern 02](../../../docs/preparation-pattern-02.md). Results and pilot: [validation](../../../docs/ticket-02-validation.md). Supplying subjects, resolving conflicts and associating attachments remain ticket 03.


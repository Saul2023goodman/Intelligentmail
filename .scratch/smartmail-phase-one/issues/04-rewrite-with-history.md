# 04: Rewrite preparation with inspectable history

Status: resolved
Labels: implemented
Blocked by: 03

**What to build:** Replace active Preparation with a fresh Preparation while keeping prior content and associations inspectable.

## Acceptance criteria

- [x] Rewrite creates fresh Preparation identity and hides Superseded Preparation from normal active-work views.
- [x] History inspection exposes prior content, Source Associations, and transformation evidence alongside original Source Materials.
- [x] New imports cannot silently replace active accepted work; supported replacement is explicit in the workflow.
- [x] Any existing Confirmation cannot transfer to a fresh Preparation; integrate this behavior when Confirmation is introduced.
- [x] Preparation and attachment snapshots preserve historical content independently of later edits to the original file path.
- [x] Boundary tests cover repeated Rewrite, active versus historical inspection, and crash/restart persistence.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

## Comments

2026-09-11: Confirmed the seam with the operator before writing tests. Three decisions were settled:

1. **The Rewrite command is `preparation rewrite PREPARATION_ID --source SOURCE_ID`.** It prepares a fresh Preparation for the same Outreach Task from the named preserved Source Material and marks the prior Preparation Superseded. A Source Material is accepted only when it parses as a supported draft and its `<Institution>_<Supervisor name>.docx` association resolves to the same Task.
2. **Superseded versions are hidden from active views and inspected through `preparation history PREPARATION_ID`.** `preparation list` and `exceptions` report only active Preparations; `history` returns the Task's version chain newest first with content, Source Material, Source Association evidence and Transformation Records.
3. **A new import cannot replace active work.** When `prepare` finds a draft whose Task already has an active Preparation from a different Source Material, it records a blocking `replacement_requires_rewrite` document finding naming the active Preparation and leaves that work untouched. Only an explicit `preparation rewrite` replaces it, and a successful Rewrite clears the finding.

Implementation: `preparations` gained a nullable `superseded_by` self-reference (with an idempotent `ALTER TABLE` migration for existing stores) and dropped the `(task_id, source_id)` uniqueness so repeated Rewrite always yields a fresh identity. Active-work queries filter on `superseded_by IS NULL`; `prepare` reuses an active Preparation only for the same Source Material.

Completed TDD cycles at the core command/query seam plus the terminal shell: fresh identity and hidden Superseded version, history inspection, the `replacement_requires_rewrite` finding, validation and repeated Rewrite, snapshot independence and restart persistence, then CLI wiring. Final run: **81 tests passed, no skips**, including the opt-in representative test.

Representative results: importing `sample.zip` and preparing produced 17 Preparations; a revision import carrying the same master, the CV and a revised `University of Melbourne_Tessa Laird.docx` produced no new Preparation and one `replacement_requires_rewrite` finding; `preparation rewrite` created a fresh Preparation, marked the corrected, CV-confirmed earlier version Superseded, and left its SHA-256 `1a04f288…d67e` CV and subject correction inspectable in history. The active list stayed at 17 across a restart.

On criterion 4: Rewrite already produces a distinct Preparation identity and records the Superseded link, so a Confirmation bound to the replaced Preparation cannot apply to the fresh one. No Confirmation surface exists in this slice, so the binding itself is introduced with ticket 05; this slice ships and tests the identity boundary it depends on.

Pattern: [Supported Rewrite Pattern 04](../../../docs/rewrite-pattern-04.md). Results and pilot: [validation](../../../docs/ticket-04-validation.md). Confirmation and controlled execution are ticket 05.

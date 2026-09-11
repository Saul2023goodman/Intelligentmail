# 07: Detect historical duplicates before execution

Status: resolved
Labels: implemented
Blocked by: 05, 06

**What to build:** Use available historical evidence to prevent repeated execution and surface duplicate initial outreach before sending.

## Acceptance criteria

- [x] Combine imported history and supported mailbox observations with deterministic matching and recorded Evidence Coverage.
- [x] Prevent Repeat Execution of an already executed Communication Action.
- [x] Flag repeated initial outreach for the same Student and Supervisor within a Campaign, including known alternate supervisor addresses.
- [x] Keep different Students distinct and do not classify linked authorized Follow-up Actions as duplicate initial outreach.
- [x] No matching evidence yields No Duplicate Found qualified by coverage; incomplete history alone is nonblocking, while genuinely ambiguous matches require review.
- [x] Reconcile before execution and pause the current Execution Flow when a newly discovered duplicate or identity conflict blocks a confirmed action.
- [x] Boundary tests exercise historical matches, ambiguity resolution, distinct students, incomplete coverage, and new evidence after Confirmation.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

## Comments

2026-09-11: The seam was confirmed with the operator before any test was written. Four decisions were settled:

1. **A dedicated `duplicate` command group with persisted checks.** `duplicate check PREPARATION_ID`, `duplicate list --campaign`, `duplicate show ID`; every check records its finding, matches and Evidence Coverage.
2. **A minimal action-kind and link marker now, not deferred to ticket 16.** `preparations.action_kind` (default `initial`) with an optional link to earlier outreach, frozen into the Sent Record; `preparation link-follow-up` marks a linked Follow-up Action so it is never reported as duplicate initial outreach.
3. **The matching model is mailbox-to-student and recipient-to-supervisor.** Only incomplete or conflicting evidence requires review; no additional ambiguity categories were invented.
4. **Incomplete coverage never blocks on its own.** No Duplicate Found is qualified by coverage and execution proceeds; only a real match or genuine ambiguity blocks.

Implementation: a new `duplicate_checks` table plus `action_kind` and link columns on `preparations` and `sent_records`, added idempotently by `schema.sql` and `_migrate`. `check_duplicate` inspects the Campaign's immutable Sent Records and the Student's own outbound mailbox observations, recording per-source coverage, the known Supervisor addresses and explicit limitations. Findings are `repeat_execution`, `duplicate_suspicion`, `ambiguous_match`, `linked_follow_up` and `no_duplicate_found`. `run_execution` re-checks after authorization and before creating an Attempt, pausing the Execution Flow on a review-required finding; existing refusals for Repeat Execution, changed content and new readiness blockers are unchanged.

TDD cycles at the core command/query seam plus the terminal shell: No Duplicate Found with coverage, Repeat Execution, duplicate suspicion by known and alternate address, unrelated recipients, distinct Students, linked Follow-up Actions, conflicting identity and its resolution through `task confirm-identity`, incomplete observation evidence and its resolution by a cleaner observation, reconcile-before-execution pauses for single and batch runs, nonblocking incomplete coverage, restart persistence, then CLI wiring. Final ordinary suite: **136 tests passed with 5 representative-material tests skipped by their opt-in environment gate**. Ticket 07 has sixteen controlled boundary tests.

A terminal pilot built one Prepared message, confirmed it, and only then observed a prior outbound send: the first check was `no_duplicate_found` with incomplete coverage, the next was `duplicate_suspicion`, and `execution run` paused the flow with reason `duplicate_suspicion`, zero attempts and the Confirmation still active. See [pattern](../../../docs/duplicate-pattern-07.md) and [validation](../../../docs/ticket-07-validation.md).

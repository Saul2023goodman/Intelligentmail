# Ticket 07 validation: historical duplicate detection

Run on 2026-09-11. All behaviour is exercised through the core command/query boundary used by the terminal shell, with persisted SQLite state and the controlled mailbox adapter. No live mailbox capability is claimed by this ticket.

## Test outcome

| | Before | After |
| --- | --- | --- |
| Ordinary suite | 120 passed, 5 skipped | **136 passed, 5 skipped** |
| New boundary tests (`tests/test_duplicates.py`) | — | **16** |

The 5 skips are the opt-in representative-material tests gated by `SMARTMAIL_SAMPLE_ZIP`.

## Coverage of the acceptance criteria

| Criterion | Boundary tests |
| --- | --- |
| Combine imported history and mailbox observations with recorded Evidence Coverage | `NoDuplicateFoundTests`, `DuplicateSuspicionTests`, `DuplicatePersistenceTests` |
| Prevent Repeat Execution | `RepeatExecutionTests.test_an_already_executed_action_is_reported_as_repeat_execution` |
| Flag repeated initial outreach, including alternate supervisor addresses | `test_a_prior_send_to_a_known_supervisor_address_is_duplicate_suspicion`, `test_a_prior_send_to_a_known_alternate_address_is_duplicate_suspicion` |
| Different Students distinct; linked Follow-up Actions not duplicates | `DistinctStudentTests`, `LinkedFollowUpTests` |
| No Duplicate Found qualified by coverage; incomplete history nonblocking; ambiguity requires review | `AmbiguousEvidenceTests`, `test_incomplete_coverage_alone_does_not_block_execution` |
| Reconcile before execution and pause on new evidence | `ExecutionReconciliationTests` |
| Terminal interaction and restart persistence | `DuplicateTerminalTests`, `DuplicatePersistenceTests` |

## Terminal pilot

A pilot store was built through the shell: campaign `2027 outreach`, Student with Mailbox `student@163.com`, one imported bundle (master + `Example University_Dr Alex Green.docx` + `Test Student - CV.docx`), one Prepared message with subject `PhD supervision enquiry` and a confirmed CV attachment.

**Before any history was observed**, `duplicate check` returned `no_duplicate_found` with two recorded sources (`sent_records` inspected 0, complete; `mailbox_observations` inspected 0, not complete) and two limitations:

```
No mailbox observation has established history coverage for this Mailbox
No match is not proof that no prior send exists outside the inspected coverage
```

**A controlled refresh then observed one prior outbound send** (platform reference `prior-send-1`, recipient `alex@example.edu`, status `sent`) under coverage with `supported_scope_complete: true`. The next check returned `duplicate_suspicion`, `review_required: true`, basis `known_supervisor_address`, one match, and coverage `complete: true` with `supervisor_addresses: ["alex@example.edu"]`.

**Confirmation existed before the duplicate was discovered.** `execution run` on that Confirmation returned:

```json
{
  "attempts": [],
  "paused": true,
  "flow": {
    "state": "paused",
    "reason": "duplicate_suspicion",
    "detail": "A prior outbound send to a known Supervisor address was recorded in the Mailbox; repeated initial outreach requires resolution"
  }
}
```

No external request was submitted and the Confirmation stayed `active`. `execution status --campaign` reported the same pause, and a further `execution run` was refused while the flow was paused.

The pilot store retained three checks — `no_duplicate_found` (review not required, coverage incomplete, 0 observations inspected), then two `duplicate_suspicion` checks (review required, coverage complete, 1 observation inspected): the explicit check and the automatic pre-execution check.

## Measured behaviours

- A batch stops at the duplicated action: the first Confirmation executed and submitted one request, the second paused the flow and submitted nothing.
- Incomplete coverage with no match proceeded to execution and still recorded a `no_duplicate_found` check.
- New ambiguous evidence (an observation flagged ambiguous by the refresh) paused the flow with reason `ambiguous_match`.
- Confirming a conflicting Supervisor identity with `task confirm-identity` turned an `ambiguous_match` into a deterministic `duplicate_suspicion`.
- A second Student addressing the same Supervisor reported `no_duplicate_found` from the first Student's Mailbox history.
- A Preparation marked as a linked Follow-up Action reported `linked_follow_up` instead of a duplicate suspicion.

## Retained artefacts

- Pattern: [Supported Duplicate Detection Pattern 07](duplicate-pattern-07.md)
- Tests: `tests/test_duplicates.py`
- Schema: `duplicate_checks` table; `action_kind` and link columns on `preparations` and `sent_records`

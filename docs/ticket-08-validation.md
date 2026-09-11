# Ticket 08 Validation: interrupted execution and Manual Takeover

Date: 2026-09-11  
Boundary: persisted SmartMail command/query API and terminal shell with the controlled mailbox adapter  
Live-platform status: no new 163.com sending capability is claimed

## Test outcome

The repository suite now reports:

```text
Ran 145 tests in 60.251s
OK (skipped=5)
```

The five skips are the existing opt-in representative-material tests gated by `SMARTMAIL_SAMPLE_ZIP`.

## Ticket 08 scenarios

| Behavior | Boundary coverage |
| --- | --- |
| Restart after a process interruption does not retry an uncertain submission | `test_crash_before_submission_pauses_recovery_without_a_blind_retry` |
| A pre-submission crash preserves a safe `not_attempted` intent | `test_crash_before_submission_keeps_intent_safe_to_resume` |
| Positive mailbox evidence creates Sent without a second request | `test_reconcile_and_continue_requires_positive_mailbox_evidence_before_sent`, `test_crash_after_external_success_is_reconciled_without_a_second_request` |
| Manual Takeover requires observation before continuing the next Confirmation | `test_manual_takeover_reconciles_then_continues_the_next_confirmation` |
| Acknowledgment without evidence remains Unknown Outcome | `test_manual_acknowledgment_without_sent_evidence_stays_unknown` |
| Authentication interruption leaves Preparation inspectable and pauses execution | `test_authentication_interruption_pauses_execution_but_keeps_preparation_usable` |
| Existing execution blockers are retained on resume | `test_resume_does_not_bypass_an_existing_execution_blocker` |
| Expired Confirmation requires a new confirmed time | `test_expired_confirmation_requires_a_newly_confirmed_time` |

The controlled adapter's crash fixtures exercise the before-submission and after-success boundaries directly; the generic adapter exception path covers a process interruption during submission. The ledger persists intent, phase markers, request content, outcome evidence, and timestamps, so restart recovery can distinguish safe-to-resume intent from Unknown Outcome. No recovery path creates an external request without an active, unchanged, still-valid Confirmation.

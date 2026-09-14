# Ticket 11 validation: replies, linked follow-ups and operational reporting

Run on 2026-09-14. All behaviour is exercised through the core command/query boundary used by the terminal shell, with persisted SQLite state, controlled time (`--now` / injected clock) and the controlled mailbox adapter. No live mailbox capability is claimed by this ticket; native scheduling, cancellation races and direct external edits remain ticket 12.

## Test outcome

| | Before | After |
| --- | --- | --- |
| Ordinary suite | 200 passed, 5 skipped | **248 passed, 5 skipped** |
| Reply association (`tests/test_replies.py`) | — | **17** |
| Follow-up eligibility and actions (`tests/test_followups.py`) | — | **21** |
| Operational reporting (`tests/test_reports.py`) | — | **9** |
| Integrated closed-loop scenario (`tests/test_ticket11_integration.py`) | — | **1** |

The 5 skips are the opt-in representative-material tests gated by `SMARTMAIL_SAMPLE_ZIP`. The 163 extension peer suite (`extensions/netease163/tests/commands.test.mjs`) still passes unchanged: **11 passed**. That suite verifies the extension's command contract only; this ticket neither adds nor verifies any live external capability.

## Coverage of the acceptance criteria

### Reply association and automatic replies

| Criterion | Boundary tests |
| --- | --- |
| Deterministic evidence: known Supervisor address + thread subject, and timing after a known Sent Record; only reliable matches associate | `ReliableReplyTests` (send-thread reply, timing-after-send) |
| Messages from unknown addresses or before any outreach stay unassociated | `test_a_message_from_an_unknown_address_stays_unassociated`, `test_a_reply_before_any_outreach_thread_is_not_silently_associated` |
| Ambiguous matches surface for operator resolution and never silently drive eligibility | `AmbiguousResolutionTests`, `FollowUpEligibilityTests.test_an_unresolved_ambiguous_association_never_silently_drives_eligibility` |
| Ordinary replies stop follow-up eligibility with no interest/rejection classification | `FollowUpEligibilityTests.test_an_ordinary_reply_stops_eligibility_without_classification` |
| Recognized Automatic Replies use explicit rules on observable fields and stay separately inspectable | `AutomaticReplyTests` (EN subject marker, CN subject token, `auto_submitted` header evidence; unmarked message stays ordinary) |
| Unsupported signals recorded as Evidence Coverage limitations, not guessed | `test_a_chinese_localized_observed_time_is_a_recorded_coverage_limitation`; every association records excluded metadata (`message_body_html`, unrecognized custom folders) |
| Persistence across restart | `ReplyPersistenceTests`, `AutomaticReplyTests.test_automatic_replies_remain_separately_inspectable_after_restart` |
| Terminal interaction | `ReplyTerminalTests` (`reply list|show|resolve`) |

### Follow-up eligibility and linked Follow-up Actions

| Criterion | Boundary tests |
| --- | --- |
| Campaign rule (delay, maximum, templates), deterministic due dates under controlled time | `FollowUpRuleTests`, `FollowUpEligibilityTests.test_eligibility_waits_for_the_configured_delay_then_becomes_due` |
| Only reliably associated ordinary replies stop eligibility; automatic replies do not; OOO return dates are ignored | `test_an_ordinary_reply_stops_eligibility_without_classification`, `test_a_recognized_automatic_reply_does_not_stop_eligibility` |
| Template content rendered only when every value exists; otherwise "due for operator preparation", never invented | `PreparedFollowUpTests` (template ready, missing-template action, operator-supplied source material) |
| Separate linked Communication Action; duplicate check reports `linked_follow_up`, never duplicate outreach | `test_a_due_task_with_a_template_gets_a_linked_ready_follow_up_preparation`, integrated scenario |
| Own Confirmation; digest binding, duplicate re-check, reconciliation and pause-on-blocker all apply | `FollowUpSafeguardTests` |
| Reply arriving after Confirmation pauses the flow before any request, Confirmation stays active | `test_a_reply_arriving_after_confirmation_pauses_without_an_obsolete_send` (reason `new_associated_reply`); `preparations.py` rewrite clears the pause only when the reply is resolved away |
| Refusal of unconfirmed follow-up; enabled execution through controlled adapter | `test_unconfirmed_follow_up_is_refused_and_submits_nothing`, `test_confirmed_follow_up_executes_through_the_controlled_adapter_and_links` |
| Maximum count across prepared + sent; chained actions; restart | `test_maximum_count_is_enforced_across_prepared_and_sent_follow_ups`, `test_chained_follow_ups_honor_delay_and_the_action_survives_restart` |
| Terminal interaction | `FollowUpTerminalTests` (`followup configure|status|prepare|list|show|prepare-action`) |

### Operational reporting

| Criterion | Boundary tests |
| --- | --- |
| Filter and summarize by Campaign, Student, Supervisor, Institution, Mailbox, message status, duplicate status, Exceptions and follow-up state | `ReportSummaryTests` (five filter tests) |
| Separate `locally_planned`, `externally_scheduled`, `sent`, `observed_failure`, `unknown_outcome`, `intake_only` states | `test_message_states_cover_scheduled_sent_failure_and_unknown` |
| Externally Scheduled derived from controlled outbound evidence (`status: scheduled` to a known Supervisor address), no ticket-12 dependency | same test, via the controlled adapter fixture |
| Drill-down to Task, all Preparation versions, source evidence, attempts, sent records, duplicate checks with coverage, reply associations and follow-up actions | `ReportDrillDownTests` |
| Duplicate findings shown with their Evidence Coverage | `test_duplicate_status_filter_keeps_coverage_honest` |
| Reports available while paused and identical after restart | `ReportPersistenceTests` |
| Terminal interaction | `ReportTerminalTests` (`report show|task`) |

### Integrated core validation

The representative scenario in `tests/test_ticket11_integration.py` drives one persistent store end to end: two-task intake with attachment resolution, batch Confirmation, controlled sends, ordinary and automatic inbound replies, diverging eligibility, a linked Follow-up Action with its own Confirmation and sent record, a genuinely ambiguous cross-campaign reply resolved by the operator, report summary plus task drill-down, and full reproduction after restart. The other required workflow shapes remain continuously covered by their ticket suites: ambiguous intake (ticket 06), Rewrite before and after a confirmed Sending Plan (tickets 04/10), expired confirmed times (ticket 10), and Manual Takeover reconciliation (ticket 08).

## Terminal pilot

Three shell-level tests build real stores via `python -m smartmail --home <home> [--now <time>] [--adapter controlled --adapter-script <file>]` and assert the emitted JSON, so the pilot flows are part of the green suite:

- `ReplyTerminalTests`: a controlled refresh after a sent outreach produces an associated reply on `reply list --campaign`; a second prepared-but-unsent Campaign to the same Supervisor makes a thread-less reply appear as `ambiguous` with both candidate task ids; `reply resolve <id> --task <candidate>` pins it (`operator_resolved`) and `--dismiss` is the alternative.
- `FollowUpTerminalTests`: `followup configure --delay-days 3 --max 2 --subject-template ... --body-template ...`, then under `--now 2026-09-18T09:00:00+00:00` `followup status` reports `due`, `followup prepare` emits a linked Preparation, its own `confirmation confirm`, and `execution run` against a controlled outcomes script (`{"outcomes": ["sent"]}`) submits exactly one request and marks the action `sent`.
- `ReportTerminalTests`: `report show --campaign` emits counts, filters and per-task rows; `report task <id>` returns the drill-down payload including preparation versions, evidence and execution history.

## Measured behaviours

- Association is deterministic on two anchored signals only: known Supervisor address plus a normalized reply thread subject (reply and automatic markers stripped), or timing-after-send when exactly one Task can match; a known address alone never associates — an off-thread message observed before the send, or with an unparseable observed time, stays in review as `no_open_outreach_thread`. Shared Supervisor addresses and conflicting identities are recorded as named ambiguity bases (`no_open_outreach_thread`, `shared_supervisor_address`, `conflicting_identity`, `multiple_candidate_tasks`).
- Automatic recognition is rule-based on observable metadata only: the `auto_submitted` header evidence, explicit English automatic markers, and a fixed English/Chinese subject-token set. An unmarked message is ordinary; semantics are never inferred.
- A follow-up sent at most once per due window: an already-open action blocks re-preparation; prepared and sent actions together count toward the maximum.
- The post-Confirmation pause inserts no attempt row and makes no external request; the Confirmation remains active and `execution run` remains refused until resolution or Rewrite clears the blocker. Rewriting a confirmed follow-up invalidates that Confirmation, releases the pause only for the blocked confirmation, and the reliable Ordinary Reply still refuses the replacement's Confirmation.
- A Rewritten follow-up Preparation keeps `action_kind = follow_up` and its anchor, the Follow-up Action is repointed to the replacement, and the duplicate check still returns `linked_follow_up`; the chain is never re-counted as initial outreach.
- Follow-up sent records carry `action_kind = follow_up` and `follows_sent_record_id`; report rows preserve the chain. The per-Task message state follows the latest terminal Execution Attempt, so a failed or unknown Follow-up Attempt is reported as `observed_failure`/`unknown_outcome`, never hidden behind the earlier recorded send.
- Preparing a follow-up without templates commits the `due_for_preparation` Action in its own transaction, so the operator queue survives across separate shell processes.
- The report is readable during a paused flow and its counts reproduce bit-for-bit (apart from `generated_at`) after reopening the store.

## Detection boundary and limitations

- The read-only observation remains metadata-only: `message_body_html` and unrecognized custom folders are excluded by the adapter and recorded as Evidence Coverage limitations on every association. Body-derived classification is deliberately absent.
- Ordinary replies are not classified as interest, rejection, or document requests; only their reliable existence affects eligibility.
- Out-of-office return dates are recorded nowhere and do not move follow-up timing.
- `externally_scheduled` is modelled from controlled outbound evidence only. No live native schedule was created, cancelled or replaced; that is ticket 12.
- Timing metrics and semantic-outcome funnels are out of scope; unknown outcomes are reported as `unknown_outcome`, not retried.

## Retained artefacts

- Tests: `tests/test_replies.py`, `tests/test_followups.py`, `tests/test_reports.py`, `tests/test_ticket11_integration.py`
- Operations: `smartmail/_operations/replies.py`, `smartmail/_operations/followups.py`, `smartmail/_operations/reporting.py`
- Schema: `reply_associations`, `follow_up_rules`, `follow_up_actions` tables; `action_kind` / `follows_sent_record_id` views on preparations and sent records; `scheduled` accepted as an outbound observation status
- Terminal: `reply`, `followup` and `report` command groups

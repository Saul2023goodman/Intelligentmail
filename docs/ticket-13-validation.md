# Ticket 13 validation: batch execution runs

Measured outcomes for the Execution Run boundary, exercised through the Core command/query
boundary used by the terminal shell with persistent local state and controlled adapters only.
No live account is required by these tests; fixture outcomes never establish platform behaviour.

## Test boundary

`python -m unittest tests.test_execution_runs` — 19 tests, all passing. Added to the full suite:
**396 tests, 0 failures** (12 opt-in skips), including the pre-existing execution, confirmation,
plan, schedule, recovery, duplicate, reply and terminal suites.

| Acceptance | Measured |
|---|---|
| A whole run completes | 3 Confirmations → `state=completed`, `executed_count=3`, `not_reached_count=0`, all items `sent`, 3 adapter requests |
| One Campaign, one kind | mixing immediate + scheduled is refused ("exactly one kind"); a cross-Campaign set is refused ("one Campaign"); both before any run row or adapter request exists |
| A disabled kind is refused first | with `DisabledMailbox`, `run_batch` raises before creating a run row or an Execution Attempt |
| Availability per kind | `run_kind_capability` reports `immediate` available and `scheduled` unavailable on the same adapter, with the adapter's own basis |
| A failure stops the run | outcomes `sent, failed, sent` → items `sent, observed_failure, not_reached`, `executed_count=2`, `state=stopped`, flow paused, 2 requests |
| A refusal stops the run | content changed after Confirmation → `sent, refused, not_reached`; the flow stays idle and later runs are still possible |
| `not_reached` runs later | the never-reached Confirmation completes in a later run; both reached Confirmations are refused with "already reached" (the sent one is also `consumed`) |
| A paused flow refuses a new run | after an unknown outcome, a second run is refused before any further request |
| Restart leaves a run `running` | a crash during submission leaves `state=running` in the same process; after reopening the store the run is `stopped` with `unknown_outcome` + `not_reached`, and never claims `sent` |
| Reconciliation keeps it honest | resolving the interrupted attempt sets the item to `sent`, but the run stays `stopped` until it is reopened — resolution never rewrites the run into a success |
| Queue states | one Campaign produced `awaiting_execution`, `already_sent`, `ready_to_authorize` and `not_ready` (`recipient_conflict`) simultaneously |
| History after the panels empty | after a completed batch `list_confirmations` is empty and the queue reports `already_sent`, yet `get_execution_run` still returns 2 items and the run list still holds it |
| Scheduled runs | 2 scheduled Confirmations → 2 `externally_scheduled` items, 2 `schedule_requests`, **0** immediate requests, 0 Sent Records, queue `externally_scheduled` |
| Plan confirmation → awaiting group | a confirmed plan yields 2 `awaiting_execution` rows of kind `scheduled`; placing them is one scheduled run; `run_execution` on the same Confirmations is refused as an immediate send |
| One review, one authorization, one run | `execution_review` → `execution_confirm` returns the Confirmations → `execution_run {confirmation_ids}` completes with `summary.sent = 3` |
| Single-id compatibility | `execution_run {confirmation_id}` still returns `attempts[0].state == "sent"` and `paused == false`, and now also carries the run |
| Terminal shell | `execution batch` produces a `completed` run with `summary.sent = 2`; `execution runs`, `execution run-show` and `execution queue` return it and its items afterwards |

## Frontend

`npm run build` (tsc + vite) and `npm run lint` (oxlint) pass with 0 errors. The Batch execution
page now reads `execution_workspace`'s `queue`, `runs` and `availability` instead of assembling
them locally: one selection defaulting to every `ready_to_authorize` Preparation, a primary
"Review and send N" and a secondary "Authorize only", distinct immediate and scheduled regions
that each state their scope, a progress line, and a result dialog with a per-outcome summary and
the stopped-run route to the execution ledger.

## Decisions carried

- **Native scheduling default**: kept opt-in (`--enable-extension-schedule`, `verified: false`).
  Ticket 12 closed `live-acceptance-partial` with the transport-level worker sign-off still
  outstanding, so an unverified external capability is not enabled by default. Availability is
  now reported per kind and the scheduling path no longer sits behind the immediate-send
  capability, which is the part of the operator direction ticket 13 actually needs.
- **Outcome vocabulary**: non-immediate kinds record `externally_scheduled`, `cancelled` and
  `replaced` rather than `sent`, because the glossary forbids calling an Externally Scheduled
  draft Sent and a removal is not a send.

## Not covered here

Live 163.com acceptance of a scheduled run. Each enabled external capability keeps its own
controlled real-mailbox acceptance; the run mechanism was validated with controlled adapters.

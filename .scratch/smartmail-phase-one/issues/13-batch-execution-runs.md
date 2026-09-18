# 13: Batch execution runs — one authorization, one run, traceable batch results

Status: resolved
Labels: implemented
Validation: docs/ticket-13-validation.md
Blocked by: None (ticket 12 is resolved). The native-scheduling default-gating decision in
Comments is settled as "keep opt-in, report availability per kind"; the run mechanism did not
depend on the answer and is implemented and validated either way.

**What to build:** Replace the Batch execution page's six-panel, two-selection, one-request-per-message
flow with a single batch operation: the operator reviews one queue, authorizes once, and Core carries
out one **Execution Run** whose results are persisted and inspectable. An Execution Run is a
first-class Core concept: one operator-initiated, ordered execution of a set of already-confirmed
Communication Actions, retaining what was requested, what was reached, what was observed, and what was
never reached. Confirmation and Execution stay separate decisions in Core; the batch page only stops
forcing the operator to re-select and re-review between them. Sending Plans stay a first-class path —
a confirmed plan produces scheduled Confirmations that enter the same run mechanism.

## Why the current shape is wrong

- Authorization and execution use two independent selections (`preparation_id[]` in Ready tasks,
  `confirmation_id[]` in Confirmation), so authorizing N actions requires selecting the same N again
  and reviewing the same content twice before anything is sent.
- `execution_run` accepts a single `confirmation_id`, so the page issues N HTTP requests in a `for`
  loop with no progress, no per-item outcome, and no record of what was never reached when the run
  stops on a paused Execution Flow.
- `Confirm plan (N)` sits beside `Confirm immediate` but acts on the whole Campaign's proposals
  (`_plan_candidates`), not on the operator's selection — an easy, irreversible mis-authorization.
- After a batch, `list_confirmations` returns only active Confirmations and the ready list drops
  sent Preparations, so both panels empty out and no "18 of 20 sent, 2 outstanding" summary exists.
- Availability is all-or-nothing across a mixed batch: one disabled kind disables the whole run.

## Acceptance criteria

### Execution Run is a Core concept

- [x] Add the Execution Run and Execution Run Item terms to the domain glossary: one operator-
      initiated ordered execution of a set of active Confirmations, and one Confirmation's place in a
      run with its own observed outcome. Avoid: batch job, automatic retry, sending session.
- [x] Persist runs in `schema.sql`: `execution_runs(id, campaign_id, kind, state, requested_count,
      executed_count, started_at, finished_at, detail)` and `execution_run_items(run_id,
      confirmation_id, sequence, attempt_id, outcome, detail)` with `UNIQUE(run_id, sequence)`.
      `outcome` is one of `sent`, `observed_failure`, `unknown_outcome`, `refused`, `not_reached`;
      `state` is one of `running`, `completed`, `stopped`.
- [x] Every run belongs to exactly one Campaign and has exactly one `kind` (`immediate`, `scheduled`,
      `cancellation`, `replacement`); a mixed-kind request is refused before any external action.
- [x] A run is created only by an explicit operator request; nothing starts, resumes, or retries a run
      automatically, and observing a run never mutates the mailbox.

### One authorization, one run

- [x] Add `run_batch(confirmation_ids, *, kind=None)` at the Core boundary: validate the whole set
      first (same Campaign, every Confirmation active, single kind, required capability available,
      Execution Flow not paused), then execute in order, writing each item's outcome as it is observed.
- [x] Each Confirmation is executed by its own existing single-action path (immediate send, native
      schedule placement, Cancellation, Scheduled Replacement); the batch never re-implements or
      bypasses those safeguards, and each still gets its own Execution Attempt.
- [x] A paused Execution Flow or a refused action stops the run: reached items keep their observed
      outcome, every remaining item is recorded as `not_reached`, the run becomes `stopped`, and the
      result states how many were reached, how many were not, and why the run stopped.
- [x] A run that reaches every item becomes `completed`; `executed_count` counts only reached items.
- [x] `execution_confirm` returns the Confirmations it created so the batch page can carry them
      straight into a run without a second selection or a second full review.

### Traceable batch results

- [x] `get_execution_run(run_id)` and `list_execution_runs(campaign_id)` expose the run with its items,
      including `not_reached` entries, through the Core boundary used by the terminal shell.
- [x] A `not_reached` item stays eligible for a later, explicitly requested run; a reached item is
      never re-executed by a subsequent run, and an already-sent Preparation is refused as before.
- [x] A run interrupted by restart stays `running` until it is reconciled: recovery re-establishes
      each attempt's outcome, then the run reaches `completed` or `stopped` with accurate items, and
      an unresolved attempt never becomes `sent` by default.
- [x] Run history is inspectable after the Campaign's panels have emptied, so a finished batch is
      still answerable ("what did that run actually do") without re-deriving it from raw attempts.

### Core-computed execution queue

- [x] Add an `execution_queue(campaign_id)` query returning one row per active Preparation with its
      authorization state: `ready_to_authorize`, `awaiting_execution` (an active Confirmation has no
      terminal outcome yet), `externally_scheduled`, `already_sent`, or `not_ready` with the blocking
      codes. Readiness is never reported as authorization.
- [x] The batch page derives its queue and its "awaiting execution" groups from this query instead of
      assembling them locally from reviews, schedules, and confirmations.

### Frontend: one batch flow

- [x] One selection only, defaulting to every `ready_to_authorize` Preparation, so the normal path is
      subtraction (deselect the one or two to hold back) rather than building a selection from empty.
- [x] Primary action "Review and send N": one review dialog, one authorization, then the run, with
      visible progress and a result summary (sent / failed / unknown / not reached).
- [x] Secondary action "Authorize only" keeps the separated two-step path available for an operator
      who wants to authorize now and run later; authorized actions then appear under awaiting
      execution and can be run without re-selecting.
- [x] Authorize and run for immediate and for scheduled actions live in distinct regions, each stating
      its scope, so a Campaign-wide plan confirmation can no longer be mistaken for the current
      selection's confirmation.
- [x] A stopped run shows where it stopped, how many items were never reached, the pause reason, and a
      route to the Execution Ledger to resolve it; after resolution the remaining items can be run
      explicitly, and the run result never claims success from completion alone.
- [x] Availability is reported per kind, so a disabled kind blocks only its own region and says why.

### Scheduling stays a first-class path

- [x] Propose, adjust, and confirm a Sending Plan as today; confirming a plan yields scheduled
      Confirmations that appear as an awaiting-execution group of kind `scheduled`.
- [x] Placing those schedules is one run of kind `scheduled`, with the same progress, stopping, and
      `not_reached` semantics; a scheduled Confirmation is never executed as an immediate send.
- [x] Native scheduling availability is reported independently of immediate sending, and the
      scheduling path is not hidden behind the immediate-send capability.

### Regression and compatibility

- [x] `execution_run` keeps accepting a single `confirmation_id` while also accepting
      `confirmation_ids`; every existing caller, terminal command, and test keeps working.
- [x] The existing safeguards still hold inside a batch: content and attachment digests, Confirmation
      expiry, superseded Preparations, duplicate review, blocking readiness findings, and the
      post-Confirmation ordinary-reply pause for non-initial actions.
- [x] The full Core test suite passes, and every Core behaviour above is covered at the command/query
      boundary with controlled adapters only — no live account is required by tests.

## Testing boundary

Exercise operator-visible behaviour through the Core command/query boundary used by the terminal
shell, with persistent local state and controlled adapters: a whole run completes; a run stops
mid-batch and records `not_reached`; remaining items run later without re-sending reached ones;
mixed-kind and cross-Campaign requests are refused before any external action; restart leaves a run
`running` until reconciliation; run history remains inspectable after the batch finishes. Fixture
outcomes never establish platform behaviour — each enabled external capability keeps its own
controlled real-mailbox acceptance, and live acceptance stays separate from these tests. Do not test
internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain
glossary. The frontend consumes the same allowlisted Core commands and adds no domain decisions of its
own; every rule, validation, and outcome stays owned by Core. No automatic scheduling of runs, no
retry automation, no AI, and no SMTP/IMAP fallback. See the [sending plan pattern](../../../docs/sending-plan-pattern-10.md),
the [confirmation pattern](../../../docs/confirmation-pattern-05.md), the [recovery pattern](../../../docs/recovery-pattern-08.md),
and the [frontend workflow](../../../docs/frontend-workflow.md).

## Comments

2026-09-18: Written from an operator-workflow review of the Batch execution page rather than a new
external capability. Operator direction settled four points: authorization and execution merge into one
primary path with "authorize only" kept as a secondary action; a batch is one Core call that stops on a
pause and reports a complete summary; runs are persisted in Core rather than derived in the UI; and
scheduling is core functionality with native scheduling supported by default. The last point conflicts
with the current gating — `native_scheduling` today requires `--enable-extension-schedule`, is reported
`verified: false`, and ticket 12 closed as `live-acceptance-partial` with the transport-level worker
sign-off still outstanding. Decide before implementation whether the default is reversed now (keeping
`verified: false` honestly reported) or only after the remaining live acceptance sets `verified: true`;
the run mechanism itself does not depend on the answer.

2026-09-18: Implemented. Execution Run is a Core concept (`execution_runs`,
`execution_run_items`, `run_batch`, `get_execution_run`, `list_execution_runs`,
`execution_queue`); the batch page now reads the Core-computed queue and runs one
authorization as one run. Decision on the gating question raised above: **the default is not
reversed now.** Ticket 12 closed `live-acceptance-partial` with the transport-level worker
sign-off still outstanding, so enabling an unverified external capability by default would
contradict the "evidence, not assumption" rule. Native scheduling stays opt-in
(`--enable-extension-schedule`) and honestly `verified: false`; what ticket 13 needed from that
direction — availability reported per kind, and the scheduling path no longer sitting behind the
immediate-send capability — is delivered, so a disabled kind blocks only its own region and says
why. One deviation from the outcome list above: non-immediate runs record
`externally_scheduled`, `cancelled` and `replaced` instead of `sent`, because the glossary
forbids calling an Externally Scheduled draft Sent and removal is not a send. Live acceptance of
a scheduled run remains separate.

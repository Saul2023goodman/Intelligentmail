# Supported Execution Run Pattern 13

An **Execution Run** is one Operator-initiated, ordered execution of a set of already-confirmed
Communication Actions. Confirmation and Execution stay separate decisions in Core; the run only
stops the Operator from re-selecting the same work and re-reading the same content between them.
A run belongs to exactly one Campaign and has exactly one kind (`immediate`, `scheduled`,
`cancellation`, `replacement`), and it retains what was requested, what was reached, what was
observed, and what was never reached.

```powershell
execution queue --campaign CAMPAIGN_ID
execution batch CONFIRMATION_ID [CONFIRMATION_ID …]
execution runs --campaign CAMPAIGN_ID
execution run-show RUN_ID
```

`execution run` keeps its original meaning: it carries Confirmations out through the immediate
single-action path. `execution batch` is the one that produces an Execution Run.

Nothing starts, resumes or retries a run automatically. Observing a run never mutates the mailbox.

## The execution queue

`execution_queue(campaign_id)` returns one row per active Preparation with its **authorization**
state. Readiness is never reported as authorization.

| State | Meaning |
|---|---|
| `ready_to_authorize` | No active Confirmation, nothing sent, no blocker: it *may* be authorized |
| `awaiting_execution` | An active Confirmation exists and has no terminal outcome yet |
| `externally_scheduled` | A tracked external schedule owns the commitment |
| `already_sent` | A Sent Record exists |
| `not_ready` | Blocking readiness findings, reported as codes |

The batch page derives its queue and its awaiting-execution groups from this query; it never
assembles them locally from reviews, schedules and confirmations.

## One authorization, one run

`run_batch(confirmation_ids, *, kind=None)` validates the whole set **before** any external
action: one Campaign, one kind, every Confirmation active, the required capability available, no
already-reached item, and an idle Execution Flow. Only then does it execute in order, writing
each item's outcome as it is observed.

Each Confirmation is carried out by its own existing single-action path — immediate send, native
schedule placement, Cancellation, Scheduled Replacement — with its own Execution Attempt. The
batch never re-implements or bypasses their safeguards: content and attachment digests,
Confirmation expiry, superseded Preparations, duplicate review, blocking readiness findings and
the post-Confirmation ordinary-reply pause all still hold inside a run.

A paused Execution Flow or a refused action **stops** the run: reached items keep their observed
outcome, every remaining item is recorded as `not_reached`, the run becomes `stopped`, and the
result states how many were reached, how many were not, and why. A run that reaches every item
becomes `completed`. `executed_count` counts only reached items.

| Item outcome | Meaning |
|---|---|
| `sent` | The mailbox confirmed the message was sent |
| `externally_scheduled` | A native schedule was placed; **never** called Sent |
| `cancelled` / `replaced` | The Cancellation or Scheduled Replacement was observed |
| `observed_failure` | The mailbox reported a failure |
| `unknown_outcome` | Evidence does not establish the result; reconciliation is required |
| `refused` | Core refused the action before any external request |
| `not_reached` | The run stopped before this action |

The non-immediate kinds add their own observed success term because the glossary forbids calling
an Externally Scheduled draft Sent, and because removal is not a send.

`execution_confirm` returns the Confirmations it created, so the batch page carries them straight
into a run without a second selection or a second full review.

## Traceable batch results

`get_execution_run(run_id)` and `list_execution_runs(campaign_id)` expose the run with its items,
including the `not_reached` entries. A `not_reached` item stays eligible for a later, explicitly
requested run; a reached item is never re-executed by a subsequent run, and an already-sent
Preparation is refused as before. Run history stays inspectable after the Campaign's panels have
emptied, so "what did that run actually do" remains answerable without re-deriving it from raw
attempts.

A run interrupted by a restart stays `running` until it is reconciled: recovery re-establishes
each attempt's outcome first, then the run reaches `completed` or `stopped` with accurate items.
An unresolved attempt never becomes `sent` by default. Reconciliation later corrects the item,
and never turns a stopped run into a success.

## Scheduling stays a first-class path

Propose, adjust and confirm a Sending Plan as before; confirming a plan yields scheduled
Confirmations that appear as an awaiting-execution group of kind `scheduled`. Placing those
schedules is one run of kind `scheduled`, with the same progress, stopping and `not_reached`
semantics. A scheduled Confirmation is never executed as an immediate send.

Native scheduling availability is reported independently of immediate sending: a disabled kind
blocks only its own region and says why. The scheduling path is never hidden behind the
immediate-send capability. Native scheduling remains an opt-in, `verified: false` capability
(`--enable-extension-schedule`) until its controlled real-mailbox acceptance is complete.

## Compatibility

`execution_run` keeps accepting a single `confirmation_id` while also accepting
`confirmation_ids`; a one-item run still returns the single-action result shape (`attempts`,
`paused`, `flow`, `schedule`, `replacement_placed`), so every existing caller, terminal command
and test keeps working.

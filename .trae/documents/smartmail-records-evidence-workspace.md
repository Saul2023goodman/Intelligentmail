# SmartMail Records — Historical Evidence Workspace

## Context

The SmartMail Core (tickets 01–12) persists a complete evidence ledger: Preparation
version lineage (Rewrite/supersede), Confirmations (active/consumed/invalidated), the
Execution Ledger (attempts with intent/submission/outcome phases), immutable Sent
Records, native schedule lifecycles (replaced/cancelled/cancel\_unknown), mailbox
observations, Reconciliations, duplicate checks, reply associations and Follow-up
Actions. The existing frontend pages (Workflow, Source mapping, Readiness review,
Batch execution, Mailbox reconciliation) each show one slice; none presents the
historical chain of evidence for an Outreach Task.

This change adds a **read-only Records page**: a dense three-pane evidence workspace
(task list → evidence timeline → inspector) optimized for traceability and
drill-down, with **no editing or execution controls**.

User-approved decision: the UI bridge gains read-only aggregate commands, because
`list_confirmations` only returns active confirmations and no public op lists the
confirmation history. Core domain logic stays untouched; `ui.py` only composes
existing public queries (same pattern as `mailbox_ui.py` / `execution_ui.py`).

## Backend changes

### 1. `smartmail/_operations/confirmations.py` — one read-only query

Add after `list_confirmations` (same SQL minus the `status = 'active'` filter):

```python
def list_confirmation_history(self, campaign_id: str) -> list[dict]:
    """Every Confirmation a Campaign produced: active, consumed and invalidated."""
```

Returns existing `_confirmation_view` rows in rowid (chronological) order:
`{id, preparation_id, task_id, status, execution, content_digest, attachments_digest, invalidated_reason, confirmed_at}`.

### 2. New `smartmail/records_ui.py` — read-side composition only

Two functions, mirroring `mailbox_workspace`/`execution_workspace`:

**`records_workspace(core, campaign_id)`** →

```
{ campaign, generated_at, flow, rule, counts, tasks }   # from core.operations_report
confirmations: core.list_confirmation_history(campaign_id)
attempts:      lean list_execution_attempts (attempt_view fields, request minus "body")
sent_records:  core.list_sent_records (full: frozen sender/recipient/subject/body,
               attachments[{label,name,sha256,size}], evidence, reference,
               action_kind, follows_sent_record_id)
schedules:     core.list_external_schedules(campaign_id=...)  # incl. replaces_schedule_id
plans:         lean list_plans: {id,status,created_at,configuration,
               proposals/unavailable/impossible → [{preparation_id,task_id,status,
               reason,scheduled_at,scheduled_utc,confirmation_id}]}
duplicate_checks: core.list_duplicate_checks
reply_associations: lean _reply_view (drop evidence/evidence_coverage/observation.evidence;
               keep status, reply_kind, basis, matched_rule, resolved_by_operator,
               created_at, resolved_at, candidate ids, observation{counterpart,subject,observed_time,status})
follow_up_actions: core.list_follow_up_actions
mailboxes:     ui.mailbox_summaries(core)  (reuse existing helper)
```

**`records_task(core, task_id)`** → `core.report_task(task_id)` (task with
participants/exceptions/source\_associations, ALL preparation versions in rowid order,
sources, full attempts, full sent records, duplicate checks, reply associations,
follow\_up) plus:

```
confirmations: history filtered to the task
schedules:     core.list_external_schedules(task_id=...)
mailbox:       { observations: list_mailbox_observations(student_id),
                 reconciliations: list_reconciliations(student_id) }
```

Bodies appear only in drill-down (`records_task`) and frozen Sent Records; lists stay lean.

### 3. `smartmail/ui.py` — dispatch wiring

In `dispatch()`, after the `mailbox_workspace` branch (names must not start with
`execution_`):

```python
if command == "records_workspace": return records_workspace(core, request["campaign_id"])
if command == "records_task":      return records_task(core, request["task_id"])
```

## Frontend changes

### Core contract (lockstep)

* New `frontend/src/core/records-types.ts` mirroring the payloads above exactly
  (`RecordsWorkspace`, `RecordsTaskDetail`, `ConfirmationHistory`, `LedgerAttempt`,
  `SentRecord`, `ScheduleRecord`, `LeanPlan`, `LeanReply`, `DuplicateCheck`,
  `FollowUpAction`, `RecordsTaskRow`).

* `frontend/src/core/index.ts`: re-export types; add Commands entries
  `records_workspace: {args:{campaign_id}, result: RecordsWorkspace}` and
  `records_task: {args:{task_id}, result: RecordsTaskDetail}`.

### Route + shell integration (coordinated change)

* `frontend/src/app/routes.ts`: `records: { hash: "#records", label: "Records", icon: "book" }`.

* `frontend/src/App.tsx`: `{route === "records" && <RecordsPage />}`.

* Add `<NavigationItem route="records" />` to the hardcoded rails in
  `WorkspacePage.tsx` (nav block \~L548-557; also add `"records"` to the early-return
  list at L474), `ReviewPage.tsx`, `ExecutionPage.tsx`, `IntakePage.tsx`
  (`MailboxPage` maps all routes automatically).

### New page `frontend/src/pages/records/`

Follow the `MailboxPage` pattern: `AppShell` → `.workspace` → `Topbar` (breadcrumb
"Records") → heading with read-only notice ("Read-only evidence workspace — records
never change external state") → controls (campaign select via `core('workspace',{})`,
search, filter chips from `counts`: message\_status / duplicate\_status / exceptions)
→ bounded `main` → footer. CSS in `Records.css` scoped under `.records-page`
(`.rc-` prefix). No mutation commands imported anywhere in the page.

Three panes (grid, all `min-height:0`, internal scroll only — viewport contract):

1. **Task list** (left): supervisor/institution/student, message-state chip,
   duplicate badge, blocker count, follow-up state; dense rows.
2. **Evidence timeline** (middle): built by `records-model.ts` from `records_task`:

   * version nodes with `v1…vN` badges in backend rowid order; supersede edges via
     `superseded_by` (branch connectors, superseded styling);

   * per version: confirmation nodes (status + humanized `invalidated_reason`:
     rewrite/expired/renewed/content\_changed/adjusted/removal\_unverified/
     original\_sent\_during\_replacement), attempt nodes (phase chain
     intent→submission→outcome→recorded, state colors), schedule nodes (state incl.
     replaced/cancelled; replacement chain via `replaces_schedule_id`), frozen Sent
     Record nodes (immutable styling, reference + attachment sha256), duplicate
     checks, replies, follow-up actions, observation/reconciliation findings.

   * Ordering rule: never re-sort timestamp-less records (preparations, corrections,
     transformations keep insertion order); timestamped events order within their
     node; Sent Records anchor to their attempt's `outcome_observed_at`.
3. **Inspector** (right): selected node detail — content fields with bounded `pre`
   body, transformations/corrections, readiness findings, attachment digests,
   evidence coverage, and raw evidence in `<details><pre>{JSON.stringify(…)}</pre></details>`
   (MailboxPage dialog pattern).

`presentation.ts` maps states to CONTEXT.md vocabulary with token colors
(`--green/--blue/--rose/--purple/--amber`): Sent, Externally Scheduled, Unknown
Outcome, Observed Failure, Locally Planned, Superseded Preparation, Confirmation
active/consumed/invalidated, Reconciliation findings, Associated Reply, Follow-up Due.

Narrow windows (≤900px): tab reflow Tasks / Timeline / Inspector (ReviewPage
`panel` pattern); short windows collapse heading (Mailbox.css pattern). Empty store
must render bounded panes with an empty state (no page scroll).

## Tests

* `tests/test_ui.py` — new `RecordsBridgeTests(ExecutionTestCase)` reusing
  `ready_preparation()`, `ControlledMailbox`, `observed_history()`; every test asserts
  `self.mailbox.requests == []` after dispatching records commands:

  1. consumed + invalidated (`rewrite`) confirmations both visible in history;
  2. superseded lineage: both versions, prior `status == "superseded"`, rowid order;
  3. sent record frozen fields + attachment sha256/size + reference/action\_kind keys;
  4. ledger: attempt phase/timestamp fields; `['unknown']` outcome appears;
  5. schedule lifecycle: place → replacement → `replaced`/`cancelled` +
     `replaces_schedule_id`; cancellation confirmation kind visible;
  6. observations/reconciliations and a matched reply surface in `records_task.mailbox`;
  7. unknown command still refused.

* `frontend/tests/foundation.test.mjs`: add `resolveRoute("#records") === "records"`.

* New `frontend/tests/records.test.mjs` (node --test): timeline model unit tests —
  version chain, id linkage, replacement chain, insertion-order preservation,
  sent-time anchoring.

* Optional: add `records` to `frontend/tests/viewport.browser.js` route loop.

## Demo seed (dev utility)

New `scripts/seed_records_demo.py` (imports test builders `master/document/bundle/
draft_paragraphs` from `tests.test_execution`, `observed_history` from
`tests.test_reconciliation`; drives `SmartMail` with `ControlledMailbox` and a
controlled clock into `.smartmail-demo`, override via `SMARTMAIL_HOME`):
immediate send → frozen Sent Record; rewrite chain; unknown outcome; scheduled →
replaced; cancellation; observation + reconciliation + reply; follow-up rule +
prepared action. Prints the dev command to run next.

## Verification

1. `python -m unittest tests.test_ui` then `python -X utf8 -m unittest discover -s tests`.
2. `cd frontend && npm run build && npm run lint && npm test`.
3. `python scripts/seed_records_demo.py`; then
   `SMARTMAIL_HOME=../.smartmail-demo npm run dev` → open `#records`; check the three
   panes, timeline chains (v1→v2 supersede, replacement branch, frozen sent node),
   drill-down inspector, filters, and empty-store state.
4. Viewport contract:
   `npx --yes --package @playwright/cli playwright-cli -s=layout open http://127.0.0.1:5179`

   * `run-code --filename frontend/tests/viewport.browser.js` (with records route),
     verifying no page-level scroll at 390×844 … 1920×1080 and 900×450.


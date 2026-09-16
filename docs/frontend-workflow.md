# First frontend page

The React page maps the reference canvas to existing Core concepts, rather than
introducing a configurable workflow engine. Its node counts are sets of Outreach
Tasks and may overlap across Communication Actions. Connections describe supported
paths, not execution history or automatic transitions.

| Stage | Existing Core evidence |
| --- | --- |
| Source materials | Campaign Outreach Tasks from `operations_report` |
| Preparation | Active `list_preparations` |
| Ready preparation | Core readiness findings have zero blockers |
| Confirmation | Recorded active `list_confirmations`; execution still rechecks validity |
| Operator review | Task exceptions, Preparation blockers, or duplicate suspicion |
| Externally scheduled | Reported mailbox schedule observations |
| Sent record | Reported sent outcome backed by the execution ledger |
| Observed failure / Unknown outcome | Separate report states; never conflated |
| Associated reply | Ordinary reply received in Core follow-up evaluation |
| Follow-up due | Core Follow-up Rule eligibility |

The task inspector calls `report_task` for active Preparation content, attachment
associations, readiness findings, original Source Material names, duplicate
coverage and Execution Attempts. Campaign creation and duplicate checks directly
call `create_campaign` and `check_duplicate`. No UI code performs readiness,
duplicate, reply, scheduling or sending decisions.

## Local transport

The Vite development server proxies an allowlisted JSON protocol over private
stdio to one long-lived `python -m smartmail.ui` process. A single Core instance
avoids invoking restart recovery on every UI query. Vite binds to loopback and
requires same-origin JSON POST requests, with bounded request sizes and timeouts.
The Python bridge owns no network listener and exposes no mailbox commands.
ADR-0001's extension Native Messaging boundary remains unchanged.

This is a local development frontend. `npm run build` checks and bundles the UI;
the static build and `vite preview` alone do not start the Core bridge. Startup
uses Core's existing lifecycle/recovery, just like the CLI. Do not open this
workspace against a store that is currently executing in another process.

Import, preparation corrections, confirmation, execution, reconciliation and
follow-up creation continue through the existing CLI. The in-page guide explains
intake setup. No sample campaigns or messages are inserted into the user store.

## Verification

`python -m unittest tests.test_ui` verifies real persisted report/detail payloads,
readiness blockers, duplicate coverage, isolated campaign scope, forbidden
commands, malformed protocol input and Unicode campaign persistence.
`npm run build` and `npm run lint` validate the frontend.

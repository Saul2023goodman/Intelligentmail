# Code structure

`from smartmail import SmartMail, SmartMailError` remains the application interface.
`PLAN_DEFAULTS` is also available from `smartmail`. The terminal application runs
with `python -m smartmail`.

## Where to make changes

| Location | Responsibility |
| --- | --- |
| `smartmail/core.py` | Assemble SmartMail; own the store connection, schema initialization, migrations and clock |
| `smartmail/errors.py` | Operator-visible command/query error |
| `smartmail/_operations/records.py` | Campaigns, Students, imports, preserved Source Material, Outreach Tasks and Exceptions |
| `smartmail/_operations/preparations.py` | Document association, Preparation, readiness corrections and Rewrite history |
| `smartmail/_operations/attachments.py` | Advisory attachment slots, operator associations and immutable attachment bytes |
| `smartmail/_operations/confirmations.py` | Exact-content digests, Confirmation review, issuance and expiry |
| `smartmail/_operations/execution.py` | Authorized submission, Execution Attempts and immutable Sent Records |
| `smartmail/_operations/recovery.py` | Execution Flow pauses, restart recovery, Manual Takeover and reconcile-and-continue |
| `smartmail/_operations/reconciliation.py` | Read-only Mailbox observations, Evidence Coverage and Reconciliation findings |
| `smartmail/_operations/duplicates.py` | Duplicate Suspicion checks and linked Follow-up Actions |
| `smartmail/_operations/planning.py` | Sending Plan configuration, time windows, capacity, adjustment and Confirmation |
| `smartmail/cli/parser.py` | Argument definitions and help text |
| `smartmail/cli/commands.py` | Translate parsed commands into SmartMail calls; open materialized source copies |
| `smartmail/cli/__init__.py` | Select adapter and clock, manage store lifetime, format output and errors |
| `smartmail/__main__.py` | Executable entry point and terminal encoding |
| `smartmail/mailboxes/base.py` | Mailbox capability interface and disabled adapter |
| `smartmail/mailboxes/controlled.py` | Deterministic evidence without external sends |
| `smartmail/mailboxes/extension.py` | Dedicated extension adapter and confirmed attachment transfer |
| `smartmail/bridge/queue.py` | Durable single-delivery commands, deadlines, connection lease and file chunks |
| `smartmail/bridge/native.py` | Native Messaging framing and bounded protocol dispatch |
| `smartmail/bridge/authorization.py` | Read-only recheck of persisted Confirmation before a send permit |
| `smartmail/bridge/install.py` | Explicit Windows Chrome/Edge host registration |
| `smartmail/snapshots.py` | Shared canonical content and attachment digests |
| `extensions/netease163/` | Manifest, connection popup, worker and isolated mailbox scripts |

The existing `intake.py`, `documents.py` and `identity.py` implement deterministic
parsing and normalization. `mailbox.py` provides stable imports for the external
adapter interface and its disabled, controlled and dedicated extension implementations.
`schema.sql` remains alongside `core.py`. The extension bridge has separate transport
storage; it does not initialize or recover the business store. See the
[extension migration guide](browser-extension-pivot.md) for installation and protocol rules.

## Internal composition

The classes in `_operations` are private method groups (mixins), assembled only
by `SmartMail`. They share the same instance, SQLite connection, mailbox adapter
and clock. They must not be instantiated separately. Each method has one owner;
the groups do not override one another or use inheritance order to select behavior.

This is an internal organization of one persistent module, not a set of independent
stores. Cross-group calls use `self` on the assembled SmartMail instance. For
example, Confirmation reads Preparation and checks duplicates; Execution verifies
Confirmation and records Sent evidence; Recovery reconciles Mailbox observations
before continuing Execution. These calls retain their existing transaction scope
and commit order. Do not add a connection, commit, or constructor to an operation
group merely because it lives in a separate file.

Imports flow from the public package to `core.py`, then to operation groups and
their parsing/adapter dependencies. Operation groups import `SmartMailError` from
`errors.py`, never from the public package, and do not import each other. Add new
business behavior to its owning group; keep orchestration and business decisions
out of the terminal argument and output modules.

## Verification

Tests exercise the public SmartMail interface with temporary stores and controlled
mailbox evidence. Keep those tests independent of the internal method grouping.

```powershell
.\.venv\Scripts\python -X utf8 -m unittest discover -s tests -v
```

Representative-material tests require the explicitly configured archive described
in the README. The ordinary regression suite does not send real email.

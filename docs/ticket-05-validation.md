# Ticket 05 validation

Validated on Windows with Python 3.14.5, openpyxl 3.1.5 and SQLite 3.50.4 on 2026-09-11.

The agreed testing seam is the core command/query boundary used by the terminal, with real temporary local stores and a controlled mailbox adapter. Implementation followed one failing behavior test, minimal implementation, then a passing run per slice: reviewing the exact message, binding and renewing Confirmations, executing through the controlled adapter, the immutable Sent Record, eligibility refusals, the paused Execution Flow, stop/Rewrite/post-Sent rules, restart persistence, then the terminal shell. No private methods or database queries are used as test assertions.

The seam was confirmed with the operator before any test was written. Four decisions were settled: the controlled adapter is injected through the constructor and selected at the terminal with `--adapter controlled` plus an outcome script; this slice binds **immediate** execution details only (scheduling is tickets 10–11); the terminal gains `confirmation` and `execution` command groups, with batch confirmation giving each Preparation its own Confirmation; and "stop or resolve" is the minimal `execution stop` release, leaving reconcile-and-continue to tickets 06 and 08.

## Automated coverage

`tests/test_confirmation.py` and `tests/test_execution.py` cover: the review exposing sender, recipient, subject, attachment names with SHA-256 and size, readiness findings, execution details and the full message; confirmation binding the exact Preparation, content digest and attachment digest; idempotent re-confirmation and renewal after a content change; batch confirmation; refusals for unready, superseded and unknown Preparations; local preparation and confirmation producing **zero** external requests; a confirmed Ready Preparation sending through the controlled adapter and freezing an immutable Sent Record whose attachment bytes read back after later local edits; refusals when content changed or a new Blocker appeared and when the capability is disabled; already-executed actions refusing a second run; observed failure and Unknown Outcome pausing the Execution Flow and stopping the batch; local inspection remaining available during a pause; run-while-paused being refused; `execution stop` releasing an Unknown Outcome and clearing the pause; Rewrite refused while an attempt is unresolved and allowed after stopping; Rewrite invalidating the replaced Confirmation; post-Sent Rewrite and re-confirmation being refused; restart persistence of Confirmations, Attempts, Sent Records, frozen attachment bytes and a paused flow; and the terminal shell through separate processes for `confirmation review|confirm`, `execution run|status|stop`, `sent list|show` and the disabled default capability.

Two pre-existing guardrail tests that asserted the exact `SmartMail.__init__` signature as a proxy for "no sending surface" were strengthened to assert the behavior directly: the default adapter reports no enabled capability.

The opt-in representative archive tests additionally check the observed outcome below.

Without `SMARTMAIL_SAMPLE_ZIP`, the representative tests report skips instead of claiming real-material validation. Without the archive the suite is **112 tests, 5 skipped**; with the archive configured it is **112 tests passed, no skips**.

## Representative results

| Observed result | Value |
| --- | --- |
| Preparations after `prepare` | 17 |
| Reviewed recipient / subject | `tessa.laird@unimelb.edu.au` / `PhD supervision enquiry` |
| Reviewed attachment | `Sipei Yao - CV.docx`, 28,258 bytes, SHA-256 `1a04f288…d67e` |
| Execution details | `{"kind": "immediate"}` |
| Execution requests before any run | 0 |
| Attempt after run (controlled `sent`) | `sent` |
| Sent Record attachment | Same SHA-256 `1a04f288…d67e`, 28,258 bytes — identical to the preserved Source Material |
| Sent Records | 1 |
| Execution Flow after the send | `idle` |
| Unknown Outcome | Attempt `unknown`; flow `paused`, reason `unknown_outcome`, detail `connection lost` |
| Local inspection during the pause | `preparation list` returned all 17 |
| Run while paused | Refused (exit code 2) |
| After `execution stop` | Attempt `stopped`; flow `idle` |

The pilot imported `sample.zip`, prepared 17 Preparations, corrected Tessa Laird's subject and confirmed the student's CV. `confirmation review` printed the recipient, subject, `{"kind": "immediate"}` and the CV digest; `confirmation confirm` produced one Confirmation and `execution list` still showed no attempts. `execution run` from the controlled `sent` script produced one `sent` Attempt and a Sent Record whose frozen CV matched the preserved source byte for byte, leaving the flow `idle`. A second Preparation run from an `unknown` script paused the flow with detail `connection lost` while all 17 Preparations stayed inspectable; a further run was refused; `execution stop` marked the attempt `stopped` and returned the flow to `idle`.

## Terminal pilot

Separate CLI processes created a Campaign and Student, imported the representative ZIP, prepared local messages, corrected and confirmed the CV, reviewed and confirmed the Preparation, executed it through the controlled adapter, and inspected the Sent Record and flow, then ran an Unknown Outcome scenario and stopped it.

```powershell
$home = '.smartmail/ticket05-pilot'
$script = "$home/outcomes.json"
'{"outcomes": ["sent"]}' | Set-Content $script
.\.venv\Scripts\python -X utf8 -m smartmail --home $home campaign create 'Ticket 05 representative execution'
.\.venv\Scripts\python -X utf8 -m smartmail --home $home student create 'Sipei Yao' --mailbox 'artsipei@163.com'
.\.venv\Scripts\python -X utf8 -m smartmail --home $home import C:\Users\Zeng\Downloads\sample.zip --campaign $campaign --student $student
.\.venv\Scripts\python -X utf8 -m smartmail --home $home prepare --import $import
.\.venv\Scripts\python -X utf8 -m smartmail --home $home preparation set-subject $preparation 'PhD supervision enquiry'
.\.venv\Scripts\python -X utf8 -m smartmail --home $home preparation confirm $preparation --slot $slot
.\.venv\Scripts\python -X utf8 -m smartmail --home $home confirmation review $preparation
.\.venv\Scripts\python -X utf8 -m smartmail --home $home confirmation confirm $preparation
.\.venv\Scripts\python -X utf8 -m smartmail --home $home --adapter controlled --adapter-script $script execution run $confirmation
.\.venv\Scripts\python -X utf8 -m smartmail --home $home sent show $sent_record
.\.venv\Scripts\python -X utf8 -m smartmail --home $home execution status --campaign $campaign
```

The inspectable local pilot is retained under `.smartmail/ticket05-pilot` (ignored by Git):

- Campaign: `ceee58b3-32f9-426a-a2da-824978100d85`, named `Ticket 05 representative execution`.
- Student: `20331df2-07c7-45e5-be61-7292d0844dcd`, Mailbox `artsipei@163.com`.
- Import: `9e506ca5-2f4e-4b7c-8ac3-d581de5de1a8`.
- Tessa Laird Preparation: `b48e8a61-ca75-4f5d-8cd9-66c7eb5486d5`; Sent Record `84410c72-b2b4-47b8-a510-61a0dd16cc60`.
- Second Preparation (Unknown Outcome scenario): `98e13e9f-45bc-410b-bf9b-0d54753c020d`.

No browser capability is enabled or required by this slice; the only adapter exercised is the controlled one.

Pattern: [Supported Confirmation and Controlled Execution Pattern 05](confirmation-pattern-05.md). Related: [Supported Rewrite Pattern 04](rewrite-pattern-04.md).

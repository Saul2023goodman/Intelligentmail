# SmartMail

Tickets 01 to 10 provide a local terminal application to import and inspect Outreach Tasks, prepare local messages from existing draft documents, resolve readiness Exceptions and attach supporting files, rewrite preparation with inspectable history, confirm and execute through a mailbox adapter, reconcile persisted read-only observations from the real 163.com mailbox, detect historical duplicates before execution, recover interrupted execution with explicit operator takeover, execute operator-confirmed immediate sends in the real 163.com compose interface with Sent-folder evidence, and propose, adjust and confirm deterministic Sending Plans under configured windows, timezone, spacing and daily limits. The headless `SmartMail` command/query boundary owns Campaigns, Students, Mailboxes, Supervisor identity, source evidence, Preparations, corrections, Confirmations, Sending Plans, the Execution Ledger, immutable Sent Records, mailbox observations, Evidence Coverage, Duplicate Checks and SQLite persistence.

## Code organization

The public `SmartMail` interface is assembled in `smartmail/core.py`; its internal
operation groups separate records, Preparation, attachments, Confirmation,
Execution, recovery, Reconciliation, duplicates and Sending Plans. Terminal
arguments, command dispatch and runtime handling live in `smartmail/cli/`.
See [the code structure guide](docs/code-structure.md) for ownership and transaction
rules when adding or changing behavior.

## Run

From the repository root, with Python 3.11 or newer:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m smartmail --help
```

Create a Campaign and explicitly register the Student and their Mailbox. Use the real Student name and address from your materials:

```powershell
$campaign = .\.venv\Scripts\python -m smartmail campaign create '2027 outreach' | ConvertFrom-Json
$student = .\.venv\Scripts\python -m smartmail student create 'Example Student' --mailbox 'student@163.com' | ConvertFrom-Json
$imported = .\.venv\Scripts\python -m smartmail import 'C:\path\sample.zip' --campaign $campaign.id --student $student.id | ConvertFrom-Json
.\.venv\Scripts\python -m smartmail task list --campaign $campaign.id
.\.venv\Scripts\python -m smartmail task show $imported.task_ids[0]
.\.venv\Scripts\python -m smartmail imports show $imported.id
```

To select existing records after restarting, use `campaign list` and `student list`, then pass their IDs explicitly to `import`. Campaign selection is never inferred from a filename, directory or previous command. Registering the same Student name and Mailbox again returns that existing Student; a conflicting owner is rejected.

`imports show` lists original filenames, Source Material IDs, sizes and SHA-256 hashes. Open a preserved material using its ID:

```powershell
.\.venv\Scripts\python -m smartmail source open SOURCE_ID
```

This opens a fresh copy in the operating system's default application. `--path-only` writes the copy and prints its absolute path without launching an application. Editing an opened copy never changes preserved source bytes.

## Prepare from draft documents

Associate the imported draft documents with their Outreach Tasks and prepare local messages:

```powershell
.\.venv\Scripts\python -m smartmail prepare --import $imported.id
.\.venv\Scripts\python -m smartmail preparation list --campaign $campaign.id
.\.venv\Scripts\python -m smartmail preparation show PREPARATION_ID
.\.venv\Scripts\python -m smartmail preparation preview PREPARATION_ID
.\.venv\Scripts\python -m smartmail imports findings $imported.id
```

`prepare` associates each supported `<Institution>_<Supervisor name>.docx` to exactly one Outreach Task, extracts the recipient, message body and any separated internal research note, and records the Transformation Records. `preparation preview` prints the full local message with sender, recipient, subject, readiness and source. `imports findings` lists documents that produced no single Preparation. Preparation is local only: it writes no external mailbox draft and does not modify preserved bytes.

Readiness is separate from sending authority. A draft with no authoritative subject, a recipient that conflicts with the Supervisor's recorded address, an identity conflict, or an unassociated document is surfaced as a blocking finding and is never invented or silently resolved. A prepared message is Ready only when its blocking findings are cleared; Ready does not authorize sending.

## Resolve readiness Exceptions and attachments

Inspect the blocking Exceptions of a Campaign with their Source Material evidence and the readiness findings of the Preparation on the same Task:

```powershell
.\.venv\Scripts\python -m smartmail exceptions list --campaign $campaign.id
.\.venv\Scripts\python -m smartmail exceptions show EXCEPTION_ID
```

Correct fields and confirm attachments. Corrections are explicit operator input; they never guess a subject, recipient or identity:

```powershell
.\.venv\Scripts\python -m smartmail preparation set-subject PREPARATION_ID 'PhD supervision enquiry'
.\.venv\Scripts\python -m smartmail preparation set-recipient PREPARATION_ID name@example.edu
.\.venv\Scripts\python -m smartmail task confirm-identity TASK_ID
.\.venv\Scripts\python -m smartmail preparation suggest PREPARATION_ID
.\.venv\Scripts\python -m smartmail preparation confirm PREPARATION_ID --slot SLOT_ID
.\.venv\Scripts\python -m smartmail preparation attach PREPARATION_ID --slot SLOT_ID --source SOURCE_ID
.\.venv\Scripts\python -m smartmail preparation attach PREPARATION_ID --slot SLOT_ID --file 'C:\path\CV.pdf'
.\.venv\Scripts\python -m smartmail preparation add-attachment PREPARATION_ID --label 'Transcript' --file 'C:\path\transcript.pdf'
.\.venv\Scripts\python -m smartmail preparation remove-attachment PREPARATION_ID --slot SLOT_ID
```

When a draft declares an enclosed file, `prepare` creates an **advisory** attachment slot (for example `Student CV`) and shows the best filename candidate. Slots never block readiness and are never confirmed automatically: confirm the suggested candidate, replace it with a preserved Source Material or a local file, add further slots, or remove them. Confirmed bytes are snapshotted with their SHA-256 and are never converted, merged or modified, so later edits to the original file path cannot change them. Every correction is recorded and the whole Preparation is revalidated.

## Rewrite with inspectable history

Revised content becomes a fresh Preparation rather than an in-place edit. A new import cannot silently replace active work: `prepare` records a blocking `replacement_requires_rewrite` finding on a document whose Task already has an active Preparation, leaving that work untouched. The operator replaces it explicitly:

```powershell
.\.venv\Scripts\python -m smartmail imports findings $imported.id
.\.venv\Scripts\python -m smartmail preparation rewrite PREPARATION_ID --source SOURCE_ID
.\.venv\Scripts\python -m smartmail preparation history PREPARATION_ID
```

`preparation rewrite` prepares a fresh Preparation for the same Outreach Task from the named Source Material and marks the earlier one Superseded. Corrections, subjects and confirmed attachments are not carried over; the fresh Preparation gets advisory slots again. Superseded Preparations disappear from `preparation list` and from `exceptions` findings but remain fully inspectable through `preparation history`, which returns the Task's versions newest first with their content, Source Material, Source Associations and Transformation Records.

## Confirm and execute through a controlled adapter

Readiness is not authority. Review the exact message, then authorize it; external execution runs only through a mailbox adapter:

```powershell
.\.venv\Scripts\python -m smartmail confirmation review PREPARATION_ID
.\.venv\Scripts\python -m smartmail confirmation confirm PREPARATION_ID [PREPARATION_ID ...]
.\.venv\Scripts\python -m smartmail confirmation list --campaign $campaign.id
.\.venv\Scripts\python -m smartmail execution run CONFIRMATION_ID [CONFIRMATION_ID ...]
.\.venv\Scripts\python -m smartmail execution status --campaign $campaign.id
.\.venv\Scripts\python -m smartmail execution list --campaign $campaign.id
.\.venv\Scripts\python -m smartmail execution stop ATTEMPT_ID --detail 'operator stopped before retry'
.\.venv\Scripts\python -m smartmail execution resume --campaign $campaign.id
.\.venv\Scripts\python -m smartmail execution takeover ATTEMPT_ID --detail 'operator completed the mailbox step'
.\.venv\Scripts\python -m smartmail execution reconcile-and-continue ATTEMPT_ID [CONFIRMATION_ID ...]
.\.venv\Scripts\python -m smartmail sent list --campaign $campaign.id
.\.venv\Scripts\python -m smartmail sent show SENT_RECORD_ID
```

`confirmation review` exposes the sender, recipient, subject, attachment names with their SHA-256 and size, readiness, execution details and the full message. `confirmation confirm` binds each Ready Preparation's identity, exact content digest and attachment digest; unchanged content re-confirms idempotently, changed content renews (the prior Confirmation is invalidated). Use `--expires-at` or `--confirmed-at` when an operation has an explicit validity window. Confirmation is local and writes nothing externally.

Execution requires an enabled adapter. The default is **disabled**, so nothing leaves the machine. Demonstrate outcomes deterministically without real sends with the controlled adapter:

```powershell
# an outcomes script, e.g. {"outcomes": ["sent"]} or {"outcomes": ["unknown"]}
.\.venv\Scripts\python -m smartmail --adapter controlled --adapter-script outcomes.json execution run CONFIRMATION_ID
```

A mailbox-confirmed `sent` creates an immutable Sent Record (frozen content and attachment bytes) and consumes the Confirmation. A `failed` or `unknown` outcome pauses the Execution Flow and stops the batch; local inspection stays available, and `execution status` reports the pause with its reason. Only adapter-confirmed sending establishes Sent; a recorded request, operator acknowledgment, or elapsed time does not. Execution intent, submission phase and outcome evidence are committed separately. After restart, a submission that may have crossed the mailbox boundary becomes `Unknown Outcome` and cannot be retried until `execution reconcile-and-continue` observes positive mailbox evidence. A crash before submission leaves a `not_attempted` intent that `execution resume` may safely reuse, but it never bypasses an existing blocker or an expired Confirmation. `execution takeover` records Manual Takeover without asserting Sent; authentication interruptions are also persisted for operator resolution. `execution stop` releases an unresolved attempt, which is required before a `preparation rewrite` of that Preparation. A Sent Preparation cannot be rewritten or re-confirmed: further communication is a new linked Communication Action.

Successful commands print UTF-8 JSON, except `preparation preview`, which prints the message. Core errors return JSON on stderr; argument errors print usage. Both exit with code 2. Task summaries include names and Exception counts; `task show` includes participant records, source row/cell evidence and blocking Exceptions. Successful intake does not establish Ready Preparation or authorize sending.

## Inspect and reconcile a real 163.com mailbox

Register the intended Student and Mailbox first. Start a manual read-only refresh with the live browser adapter and a named browser session:

```powershell
.\.venv\Scripts\python -m smartmail --adapter 163-browser --browser-session smartmail-163 mailbox capabilities
.\.venv\Scripts\python -m smartmail --adapter 163-browser --browser-session smartmail-163 mailbox refresh --student STUDENT_ID
```

If authentication, verification or a CAPTCHA is required, SmartMail opens a headed 163.com browser and persists the interruption. Complete it yourself in that browser; SmartMail does not store credentials or bypass the challenge. Then run the same `mailbox refresh` command again. Refresh discovers recognized built-in folders in the live DOM, enumerates every canonical message ID through paginated folder reads, and fetches structured header, MIME and attachment metadata for each ID. It does not open Compose, create or edit a draft, send, schedule, delete, cancel or Recall anything.

Every refresh persists the observation, canonical platform references, list and metadata-detail evidence, the adapter capability snapshot, and explicit per-folder Evidence Coverage: declared total, enumerated IDs, requested/successful pages, and requested/attempted/successful/failed details. Supported-scope completeness is distinct from whole-mailbox completeness. Virtual views, unrecognized custom folders and message-body HTML are not claimed; body HTML is deliberately excluded because its endpoint changes unread state. Inspect retained evidence and the Reconciliation it produced:

```powershell
.\.venv\Scripts\python -m smartmail mailbox observations --student STUDENT_ID
.\.venv\Scripts\python -m smartmail mailbox show OBSERVATION_ID
.\.venv\Scripts\python -m smartmail reconciliation list --student STUDENT_ID
.\.venv\Scripts\python -m smartmail reconciliation show RECONCILIATION_ID
```

Reconciliation links exact observable matches and leaves unsupported, ambiguous and unassociated observations explicit. It never treats the mailbox as SmartMail's primary store and does not change an unresolved attempt merely because a list row looks similar. The controlled adapter accepts an `observations` array in its JSON script for repeatable command-boundary tests. Reading is an independent capability and turns on no state-changing operation.

The adapter opens a **persistent** browser profile (default `.smartmail/browser-163`, override with `SMARTMAIL_BROWSER_PROFILE`) so the operator authenticates once and later refreshes and executions reuse the saved session. Playwright's default incognito-like context keeps cookies only in memory; a persistent profile is required for a reusable login.

## Execute a confirmed immediate send in 163.com

Confirmed immediate sending uses the same command boundary as the controlled adapter, against the same named session:

```powershell
.\.venv\Scripts\python -m smartmail --adapter 163-browser --browser-session smartmail-163 confirmation confirm PREPARATION_ID
.\.venv\Scripts\python -m smartmail --adapter 163-browser --browser-session smartmail-163 execution run CONFIRMATION_ID
```

Execution opens and fills the real compose interface with the **exact confirmed** sender, recipient, subject, body and attachment snapshot, attaches the confirmed bytes, and submits once. It reports `sent` only when the Sent folder confirms the message; a submission that is not confirmed stays `unknown`, and authentication interruptions are handed to the operator. 163 interposes a promotional "智能优化您的英文邮件" modal on the first submit; the adapter dismisses that prompt and completes the blocked submission rather than treating it as sent. A confirmed `sent` creates an immutable Sent Record (frozen content, attachment bytes and platform reference) and consumes the Confirmation. Set `SMARTMAIL_BROWSER_PROFILE` to relocate the profile. Native scheduling, cancellation and Recall remain disabled capabilities.

## Detect historical duplicates before execution

Recorded sends and persisted mailbox history are combined into a Duplicate Check with explicit Evidence Coverage, so repeated outreach is caught before anything is submitted:

```powershell
.\.venv\Scripts\python -m smartmail duplicate check PREPARATION_ID
.\.venv\Scripts\python -m smartmail duplicate list --campaign $campaign.id
.\.venv\Scripts\python -m smartmail duplicate show CHECK_ID
```

The Mailbox account identifies the Student and the recipient identifies the Supervisor. An observed outbound send to any known Supervisor address, including a known alternate address, is a **Duplicate Suspicion**; an already executed action is **Repeat Execution**; a match that cannot be established because the identity conflicts or the observation is incomplete is an **Ambiguous Match** requiring review. With no match, the check reports **No Duplicate Found** qualified by its Evidence Coverage: incomplete history alone never blocks work, and the recorded limitation states that no match is not proof that no prior send exists outside the inspected scope.

Another Student addressing the same Supervisor is never a duplicate, and a linked Follow-up Action is not repeated initial outreach:

```powershell
.\.venv\Scripts\python -m smartmail preparation link-follow-up PREPARATION_ID --sent SENT_RECORD_ID
```

`execution run` re-checks each Confirmation before submitting. A duplicate or ambiguous match discovered after Confirmation pauses the current Execution Flow with the finding as its reason and submits nothing; a batch stops at the affected action, and `execution status` reports the pause. Every check is persisted with its matches and Evidence Coverage and stays inspectable after a restart.

## Propose and confirm deterministic Sending Plans

Configure the constraints once, propose times for the Campaign's Ready work, review the batch, adjust individual times, then confirm exact times:

```powershell
.\.venv\Scripts\python -m smartmail plan configure --campaign $campaign.id --timezone Asia/Shanghai --window 'MON-FRI 09:00-17:00' --spacing 60 --daily-limit 2 --horizon-days 3
.\.venv\Scripts\python -m smartmail plan propose --campaign $campaign.id
.\.venv\Scripts\python -m smartmail plan show PLAN_ID
.\.venv\Scripts\python -m smartmail plan adjust PLAN_ID --preparation PREPARATION_ID --time '2026-09-15T09:00'
.\.venv\Scripts\python -m smartmail plan confirm PLAN_ID
.\.venv\Scripts\python -m smartmail plan list --campaign $campaign.id
```

Every command accepts the global `--now ISO-8601` option, which fixes the store's instant so planning and expiry are reproducible. `plan configure` stores the allowed windows, IANA timezone, spacing and daily limit, with deterministic defaults (`UTC`, `MON-FRI 09:00-17:00`, 15 minutes, 20 actions, 14 days); an unsupported timezone, window, spacing, limit or horizon is refused and nothing is stored. The horizon is the number of local days searched.

`plan propose` assigns each Ready Preparation in the Campaign's Task order to the earliest allowed instant that honours every constraint — stepping by the spacing inside the configured windows, keeping the spacing across window and day boundaries, never exceeding the daily limit, and never scheduling a wall time the timezone skips — so the same configuration, work and instant produce the same times. Re-proposing supersedes the Campaign's earlier unconfirmed proposal, which stays inspectable. Work that cannot be proposed is listed instead of dropped or crowded in: `unavailable` covers `not_ready` and `already_sent`, and `impossible` names the binding `constraint` (`daily_limit`, `spacing_minutes` or `windows`) with the arithmetic in `detail`. No scheduled time ever breaks a configured constraint.

`plan show` is the batch review: sender, recipient, subject, confirmed attachments with SHA-256 and size, readiness findings, the scheduled time with its timezone, any bound Confirmation, and the full message text. `plan adjust` sets one action's exact time and refuses a past time, a nonexistent local time, a time outside every allowed window, a spacing breach or a daily-limit breach, naming the constraint and leaving the plan unchanged. Adjusting an action that already carried a Confirmation invalidates it (`adjusted`) and returns the plan to `proposed`.

`plan confirm` authorizes every scheduled action in one operator action; each gets its own Confirmation bound to its exact Preparation, content digest and `{"kind": "scheduled", "scheduled_at", "timezone"}`. The whole batch is validated before anything is authorized, unchanged re-confirmation is idempotent, and changed content renews. Confirmation is local and writes nothing externally. A confirmed schedule is **not** an immediate send: `execution run` refuses scheduled work (the native mailbox scheduling capability is not enabled), and an elapsed confirmed time pauses the Execution Flow with `confirmation_expired`, requiring an explicitly confirmed replacement time — SmartMail never substitutes an immediate send. Placing, cancelling and replacing real 163.com schedules are tickets 11 to 13.

## Local state

The default store is `.smartmail` under the current working directory. Use `--home C:\path\store` **before** the command to consistently select another store. Keep using the same store after restarting. SQLite stores records and original bytes together in one import transaction. Materialized copies live under that store's `opened` folder. The local store and virtual environment are ignored by Git.

Supported inputs and identity rules are documented in [the first Supported Intake Pattern](docs/intake-pattern-01.md). Draft documents are associated and prepared under [Supported Document Pattern 02](docs/preparation-pattern-02.md); readiness corrections and advisory attachments are documented under [Supported Readiness and Attachment Pattern 03](docs/readiness-pattern-03.md); fresh identities and inspectable history are documented under [Supported Rewrite Pattern 04](docs/rewrite-pattern-04.md); confirmation, the controlled adapter and immutable Sent Records are documented under [Supported Confirmation and Controlled Execution Pattern 05](docs/confirmation-pattern-05.md); read-only 163.com observation and manual Reconciliation are documented under [Supported Mailbox Observation Pattern 06](docs/reconciliation-pattern-06.md); duplicate detection with Evidence Coverage is documented under [Supported Duplicate Detection Pattern 07](docs/duplicate-pattern-07.md); crash recovery and Manual Takeover are documented under [Supported Execution Recovery Pattern 08](docs/recovery-pattern-08.md); confirmed immediate sending in the real 163.com compose interface is documented under [Supported Immediate Send Pattern 09](docs/immediate-send-pattern-09.md); windows, timezone, spacing, daily limits and batch Confirmation of exact sending times are documented under [Supported Sending Plan Pattern 10](docs/sending-plan-pattern-10.md).

## Verify

```powershell
.\.venv\Scripts\python -X utf8 -m unittest discover -s tests -v
```

The ordinary suite uses anonymized fixtures derived from the observed layout. An additional pilot test reads the supplied representative archive when explicitly configured:

```powershell
$env:SMARTMAIL_SAMPLE_ZIP = 'C:\Users\Zeng\Downloads\sample.zip'
.\.venv\Scripts\python -X utf8 -m unittest discover -s tests -v
```

Without this variable the representative test is explicitly skipped. The archive is not bundled in the repository. See [ticket 01 validation](docs/ticket-01-validation.md), [ticket 02 validation](docs/ticket-02-validation.md), [ticket 03 validation](docs/ticket-03-validation.md), [ticket 04 validation](docs/ticket-04-validation.md), [ticket 05 validation](docs/ticket-05-validation.md), [ticket 07 validation](docs/ticket-07-validation.md), [ticket 08 validation](docs/ticket-08-validation.md), [ticket 09 validation](docs/ticket-09-validation.md), and [ticket 10 validation](docs/ticket-10-validation.md) for measured outcomes and the retained terminal pilots.

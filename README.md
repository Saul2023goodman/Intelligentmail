# SmartMail

Tickets 01 to 03 provide a local terminal application to import and inspect Outreach Tasks, to prepare local messages from existing draft documents, and to resolve readiness Exceptions and attach supporting files. The headless `SmartMail` command/query boundary owns Campaigns, Students, Mailboxes, Supervisor identity, source evidence, Preparations, corrections and SQLite persistence.

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

Successful commands print UTF-8 JSON, except `preparation preview`, which prints the message. Core errors return JSON on stderr; argument errors print usage. Both exit with code 2. Task summaries include names and Exception counts; `task show` includes participant records, source row/cell evidence and blocking Exceptions. Successful intake does not establish Ready Preparation or authorize sending.

## Local state

The default store is `.smartmail` under the current working directory. Use `--home C:\path\store` **before** the command to consistently select another store. Keep using the same store after restarting. SQLite stores records and original bytes together in one import transaction. Materialized copies live under that store's `opened` folder. The local store and virtual environment are ignored by Git.

Supported inputs and identity rules are documented in [the first Supported Intake Pattern](docs/intake-pattern-01.md). Draft documents are associated and prepared under [Supported Document Pattern 02](docs/preparation-pattern-02.md); readiness corrections and advisory attachments are documented under [Supported Readiness and Attachment Pattern 03](docs/readiness-pattern-03.md). Rewrite with inspectable history is the next slice.

## Verify

```powershell
.\.venv\Scripts\python -X utf8 -m unittest discover -s tests -v
```

The ordinary suite uses anonymized fixtures derived from the observed layout. An additional pilot test reads the supplied representative archive when explicitly configured:

```powershell
$env:SMARTMAIL_SAMPLE_ZIP = 'C:\Users\Zeng\Downloads\sample.zip'
.\.venv\Scripts\python -X utf8 -m unittest discover -s tests -v
```

Without this variable the representative test is explicitly skipped. The archive is not bundled in the repository. See [ticket 01 validation](docs/ticket-01-validation.md), [ticket 02 validation](docs/ticket-02-validation.md) and [ticket 03 validation](docs/ticket-03-validation.md) for measured outcomes and the retained terminal pilots.

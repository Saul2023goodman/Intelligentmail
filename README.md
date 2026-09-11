# SmartMail

Ticket 01 provides a local terminal application to import and inspect Outreach Tasks. The headless `SmartMail` command/query boundary owns Campaigns, Students, Mailboxes, Supervisor identity, source evidence and SQLite persistence.

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

Successful commands print UTF-8 JSON. Core errors return JSON on stderr; argument errors print usage. Both exit with code 2. Task summaries include names and Exception counts; `task show` includes participant records, source row/cell evidence and blocking Exceptions. Successful intake does not establish Ready Preparation or authorize sending.

## Local state

The default store is `.smartmail` under the current working directory. Use `--home C:\path\store` **before** the command to consistently select another store. Keep using the same store after restarting. SQLite stores records and original bytes together in one import transaction. Materialized copies live under that store's `opened` folder. The local store and virtual environment are ignored by Git.

Supported inputs and identity rules are documented in [the first Supported Intake Pattern](docs/intake-pattern-01.md). Drafts and attachments are preserved for inspection; extracting and associating their content is ticket 02.

## Verify

```powershell
.\.venv\Scripts\python -X utf8 -m unittest discover -s tests -v
```

The ordinary suite uses anonymized fixtures derived from the observed layout. An additional pilot test reads the supplied representative archive when explicitly configured:

```powershell
$env:SMARTMAIL_SAMPLE_ZIP = 'C:\Users\Zeng\Downloads\sample.zip'
.\.venv\Scripts\python -X utf8 -m unittest discover -s tests -v
```

Without this variable the representative test is explicitly skipped. The archive is not bundled in the repository. See [ticket 01 validation](docs/ticket-01-validation.md) for measured outcomes and the retained terminal pilot.

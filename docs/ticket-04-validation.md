# Ticket 04 validation

Validated on Windows with Python 3.14.5, openpyxl 3.1.5 and SQLite on 2026-09-11.

The agreed testing seam is the core command/query boundary used by the terminal, with real temporary local stores. Implementation followed one failing behavior test, minimal implementation, then a passing run per slice: fresh Rewrite identity and hidden Superseded versions, history inspection, the `replacement_requires_rewrite` document finding, rewrite validation and repeated Rewrite, snapshot independence and restart persistence, then the terminal shell. No private methods or database queries are used as test assertions, and no external mailbox capability is required in this slice.

The seam was confirmed with the operator before any test was written: `preparation rewrite PREPARATION_ID --source SOURCE_ID` creates the fresh Preparation, a new `preparation history PREPARATION_ID` query exposes the version chain while active views hide Superseded versions, and a new import whose document targets a Task that already has active work records a blocking `replacement_requires_rewrite` finding instead of replacing it.

## Automated coverage

`tests/test_rewrite.py` covers the fresh identity and hidden Superseded version, corrections and subjects not transferring, history exposing prior content, Source Materials, Source Associations and Transformation Records from any version, history for an unknown Preparation, the `replacement_requires_rewrite` finding and its clearing after an explicit Rewrite, mixed imports that still prepare genuinely new Tasks, validation of unknown Preparations or Sources, rejection of a Source Material that does not describe the same Task, rejection of rewriting an already Superseded Preparation, repeated Rewrite from the same Source Material producing distinct identities, attachment snapshots surviving a Rewrite and later edits to the original file, restart persistence of the active view, history and attachment snapshots, and the terminal shell through separate processes.

The opt-in representative archive test additionally checks the observed outcome below. Without `SMARTMAIL_SAMPLE_ZIP`, the representative tests report skips instead of claiming real-material validation.

Final run with the representative archive configured: **81 tests passed, no skips**.

## Representative results

| Observed result | Value |
| --- | --- |
| Preparations after `prepare` | 17 |
| Revised import (`prepare`) | 0 new Preparations, 1 blocking `replacement_requires_rewrite` finding |
| Active Preparations after Rewrite | 17 (the replaced version is hidden) |
| Superseded version | Content, subject correction, Source Association, Transformations and confirmed CV retained |
| Fresh Preparation | New identity; no inherited subject or confirmed attachment; one advisory `Student CV` slot |
| Superseded CV bytes | SHA-256 `1a04f288ad733e18efdf5575b3fa3f04164c92e779ff652097734d398664d67e`, 28,258 bytes — identical to the preserved Source Material |
| Mailbox draft writes | 0 |

Tessa Laird's Preparation was corrected (subject supplied) and its suggested CV confirmed. A revision import carrying the same master, the CV and a revised `University of Melbourne_Tessa Laird.docx` produced no new Preparation; `imports findings` reported `replacement_requires_rewrite` naming the active Preparation. `preparation rewrite` then created a fresh Preparation from the revised document, marked the earlier one Superseded, and left the earlier confirmed CV and correction inspectable in history. The fresh Preparation's preview printed `Subject: (no authoritative subject)`, `Readiness: Blocked: missing_subject`, `Attachments: (none)` and `Suggested attachments: Student CV → Sipei Yao - CV.docx`, confirming nothing was inherited.

## Terminal pilot

Separate CLI processes created a Campaign and Student, imported the original ZIP, prepared local messages, confirmed a CV, supplied a subject, imported the revision, prepared it, inspected the findings, rewrote the Preparation, and inspected the active list, history and preview before re-reading everything after a restart.

```powershell
$home = '.smartmail/ticket04-pilot'
.\.venv\Scripts\python -X utf8 -m smartmail --home $home import C:\Users\Zeng\Downloads\sample.zip --campaign $campaign --student $student
.\.venv\Scripts\python -X utf8 -m smartmail --home $home prepare --import $import
.\.venv\Scripts\python -X utf8 -m smartmail --home $home preparation set-subject $preparation 'PhD supervision enquiry'
.\.venv\Scripts\python -X utf8 -m smartmail --home $home import $revision --campaign $campaign --student $student
.\.venv\Scripts\python -X utf8 -m smartmail --home $home prepare --import $revision
.\.venv\Scripts\python -X utf8 -m smartmail --home $home imports findings $revision
.\.venv\Scripts\python -X utf8 -m smartmail --home $home preparation rewrite $preparation --source $revised_source
.\.venv\Scripts\python -X utf8 -m smartmail --home $home preparation history $active
.\.venv\Scripts\python -X utf8 -m smartmail --home $home preparation preview $active
```

The inspectable local pilot is retained under `.smartmail/ticket04-pilot` (ignored by Git):

- Campaign: `df72112f-c42d-48fc-8891-0a81da7ae2ab`, named `Ticket 04 representative rewrite`.
- Student: `4b94d935-edfa-43e3-95c8-b0250bb1d08f`, Mailbox `artsipei@163.com`.
- Original import: `033a72ad-3837-4254-ba44-72e69064b78a`; revision import: `c9b23317-4aa4-4eb7-96d6-3c83f2bf0590`.
- Superseded Preparation (Tessa Laird): `84a897b7-0ad4-4b13-ba00-d15703c3ba9b`.
- Active Preparation after Rewrite: `e0f616dc-abf3-4cca-a111-b7310bb0b67c`; revised Source Material: `148569dc-5ddb-4ed0-a64b-0a5807c0f5a2`.

After restart the active list held 17 Preparations, the replaced Preparation reported `status: superseded` with `superseded_by` naming the fresh identity, and its confirmed CV still read back with SHA-256 `1a04f288…d67e`. No browser capability is enabled or required by this slice.

Pattern: [Supported Rewrite Pattern 04](rewrite-pattern-04.md). Related: [Supported Readiness and Attachment Pattern 03](readiness-pattern-03.md).

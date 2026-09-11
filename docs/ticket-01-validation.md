# Ticket 01 validation

Validated on Windows with Python 3.14.5, openpyxl 3.1.5 and SQLite on 2026-09-11.

The agreed testing seam is the core command/query boundary used by the terminal, with real temporary local stores. Implementation followed one failing behavior test, minimal implementation, then a passing run per slice. No private methods or database queries are used as test assertions.

## Automated coverage

The suite covers Campaign restart, explicit Student/Mailbox ownership, import and participant inspection, reordered aliases and merged-cell evidence, byte preservation after original deletion and restart, edited-open-copy isolation, recipient Blockers, reliable multi-address Supervisor identity, Student/Campaign task separation, unresolved identities on all affected tasks, contradictory profiles/shared addresses, unsupported-layout rejection without partial imports, repeated unresolved-row identity, accumulated profile evidence and explicit Campaign selection.

The opt-in representative archive test checks independently observed values and archive hash. Without `SMARTMAIL_SAMPLE_ZIP`, this test reports a skip instead of claiming real-material validation.

Final run with the representative archive configured: **15 tests passed, no skips**. A terminal import without `--campaign` was also rejected before executing intake.

## Representative results

| Observed result | Value |
| --- | --- |
| Outreach Tasks | 59 |
| Institutions | 11 |
| Usable recipient addresses | 55 |
| Tasks with recipient Blockers | 4 |
| Preserved Source Materials | 22: original ZIP, workbook, CV, 19 drafts |

The four recipient Blockers belong to Prof Terri Bird, Professor Callum Morton, Professor Kathy Temin and Dr Joy Paton. Their email cells contain profile URLs. The importer preserves these values without converting them into invented addresses. The source filename contains “60”; inspection established 59 data rows, which is the tested expectation.

Two draft documents name University of Technology Sydney contacts absent from the master. They remain available as original Source Materials; no additional tasks or document associations were invented from those filenames.

## Terminal pilot

Separate CLI processes created a Campaign and Student, imported the original ZIP, listed and inspected tasks, inspected the import, and materialized the workbook using `source open --path-only`. This exercised persistence between process restarts. The opened workbook's SHA-256 matched the preserved source hash. Native desktop viewer launch was not visually verified; the path-only/materialization workflow was verified. No browser capability is enabled or required by this slice.

The inspectable local pilot is retained under `.smartmail/ticket01-pilot` (ignored by Git):

- Campaign: `4f3379c1-a865-4781-a1da-6c1ccc776cbb`, named `Ticket 01 representative validation`.
- Import: `6de4f983-4808-4024-b367-9e7305f5e6f3`.

```powershell
.\.venv\Scripts\python -m smartmail --home .smartmail/ticket01-pilot task list --campaign 4f3379c1-a865-4781-a1da-6c1ccc776cbb
.\.venv\Scripts\python -m smartmail --home .smartmail/ticket01-pilot imports show 6de4f983-4808-4024-b367-9e7305f5e6f3
```

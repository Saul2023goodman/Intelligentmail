# Ticket 02 validation

Validated on Windows with Python 3.14.5, openpyxl 3.1.5 and SQLite on 2026-09-11.

The agreed testing seam is the core command/query boundary used by the terminal, with real temporary local stores. Implementation followed one failing behavior test, minimal implementation, then a passing run per slice. No private methods or database queries are used as test assertions. Preparation is local; no external mailbox capability is required in this slice.

## Automated coverage

`tests/test_preparation.py` covers draft association and Preparation inspection, internal-note separation with Transformation Records, restart persistence, idempotent repeat preparation, missing subject, a recipient conflict, a filled missing recorded address, an unusable draft recipient, local-part case tolerance, an identity conflict on the task, unassociated and malformed documents, a preserved non-draft document (the CV), the full preview, source-byte preservation, and the terminal shell through separate processes.

The opt-in representative archive test additionally checks the observed outcomes below. Without `SMARTMAIL_SAMPLE_ZIP`, the representative tests report skips instead of claiming real-material validation.

Final run with the representative archive configured: **34 tests passed, no skips**.

## Representative results

| Observed result | Value |
| --- | --- |
| Preparations | 17 |
| Unassociated draft documents | 2: UTS Nahum McLean, UTS Nga Wun Doris Li |
| Recipient conflicts | 1: Susanna Castleden |
| Filled missing recorded address | 1: Callum Morton |
| Preparations Ready | 0 (all blocked by `missing_subject`) |
| Mailbox draft writes | 0 |

The two unassociated drafts name UTS contacts absent from the master list. They are surfaced as blocking `unassociated_document` findings with their Source Materials; no Task or Preparation is invented. Susanna Castleden's draft declares `S.Castleden@exchange.curtin.edu.au` while the master records `susanna@susannacastleden.com`, so readiness is prevented. Callum Morton's master email cell held a profile URL, already an intake Blocker; the draft supplies `callum.morton@monash.edu`. Robyn Heckenberg's addresses differ only by local-part case and are correctly treated as the same recipient.

## Terminal pilot

Separate CLI processes created a Campaign and Student, imported the original ZIP, prepared local messages, listed Preparations, reported document findings, and printed a full preview. This exercised persistence between process restarts.

```powershell
$home = '.smartmail/ticket02-pilot'
.\.venv\Scripts\python -X utf8 -m smartmail --home $home preparation list --campaign 2ae246dc-4b32-45bb-9af9-fb0e24256272
.\.venv\Scripts\python -X utf8 -m smartmail --home $home imports findings b38e0ad8-0c27-4c10-964b-833ef3491139
.\.venv\Scripts\python -X utf8 -m smartmail --home $home preparation preview 2156b6e9-621f-430b-bdec-97916650efc4
```

The inspectable local pilot is retained under `.smartmail/ticket02-pilot` (ignored by Git):

- Campaign: `2ae246dc-4b32-45bb-9af9-fb0e24256272`, named `Ticket 02 representative validation`.
- Student: `6c850b35-9c52-4758-90b8-76cf2338bcbb`, Mailbox `artsipei@163.com`.
- Import: `b38e0ad8-0c27-4c10-964b-833ef3491139`.
- Preparation with the recipient conflict: `2156b6e9-621f-430b-bdec-97916650efc4` (Susanna Castleden).
- Preparation with the filled address: `08560c83-1482-488a-a381-065b70fa055f` (Callum Morton).

The preview excludes the separated internal research note and shows the readiness finding. No browser capability is enabled or required by this slice.

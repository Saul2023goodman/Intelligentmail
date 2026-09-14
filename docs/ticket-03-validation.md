# Ticket 03 validation

Validated on Windows with Python 3.14.5, openpyxl 3.1.5 and SQLite on 2026-09-11.

The agreed testing seam is the core command/query boundary used by the terminal, with real temporary local stores. Implementation followed one failing behavior test, minimal implementation, then a passing run per slice; readiness-finding computation was centralized in one revalidation step so every correction is reflected everywhere. No private methods or database queries are used as test assertions, and no external mailbox capability is required in this slice.

## Automated coverage

`tests/test_readiness.py` covers Exception listing and inspection with source evidence and readiness findings, subject and recipient correction (including rejection of blank or unusable values and of a correction that still conflicts), the derived `identity_conflict` finding and its per-Task confirmation, advisory slot suggestion with one, several and no candidates, idempotent refresh without duplicate slots, confirming a suggested candidate, replacing from a preserved Source Material or an imported file, byte preservation and independence from later edits to the original file, slot add and remove, restart persistence, and the terminal shell through separate processes. A separate test asserts that corrections write nothing outside the local store and that there is still no send, draft or browser surface.

The opt-in representative archive test additionally checks the observed outcomes below. Without `SMARTMAIL_SAMPLE_ZIP`, the representative tests report skips instead of claiming real-material validation.

Final run with the representative archive configured: **63 tests passed, no skips**.

## Representative results

| Observed result | Value |
| --- | --- |
| Preparations | 17 |
| Suggested `Student CV` slots | 17, each with the single candidate `姚思培/Sipei Yao - CV.docx` |
| Attachments confirmed automatically | 0 — every slot is advisory until the operator confirms it |
| Blocking Exceptions | 4 `invalid_recipient`, all from the master workbook |
| Corrections applied | Susanna Castleden recipient conflict cleared to the recorded address; subject supplied |
| Confirmed CV bytes | SHA-256 `1a04f288ad733e18efdf5575b3fa3f04164c92e779ff652097734d398664d67e`, 28,258 bytes — identical to the preserved Source Material |
| Mailbox draft writes | 0 |

The 17 drafts all declare "I have attached my CV", and the archive holds one CV, so each Preparation receives one advisory `Student CV` slot with `Sipei Yao - CV.docx` as its single candidate. No slot is finalized automatically. Susanna Castleden's Preparation is the one `recipient_conflict` (`S.Castleden@exchange.curtin.edu.au` against the recorded `susanna@susannacastleden.com`); correcting it to the recorded address clears the conflict and records the operator as the field's Authoritative Source. The four `invalid_recipient` Exceptions are Task-level findings from the workbook and are listed with their Source Material, hash and the readiness findings of the Preparation attached to the same Task; three of those Tasks have no draft document and therefore no Preparation.

## Terminal pilot

Separate CLI processes created a Campaign and Student, imported the original ZIP, prepared local messages, listed Exceptions, corrected a recipient, supplied a subject, confirmed the suggested CV, added a slot from a local file, and re-read everything after a restart. This exercised persistence between process restarts.

```powershell
$home = '.smartmail/ticket03-pilot'
.\.venv\Scripts\python -X utf8 -m smartmail --home $home exceptions list --campaign db3887b0-9796-42d7-80a3-700a4e4b6549
.\.venv\Scripts\python -X utf8 -m smartmail --home $home preparation set-recipient c809bf2c-8a32-43cb-879c-7685070d952c susanna@susannacastleden.com
.\.venv\Scripts\python -X utf8 -m smartmail --home $home preparation confirm c809bf2c-8a32-43cb-879c-7685070d952c --slot SLOT_ID
.\.venv\Scripts\python -X utf8 -m smartmail --home $home preparation preview c809bf2c-8a32-43cb-879c-7685070d952c
```

The inspectable local pilot is retained under `.smartmail/ticket03-pilot` (ignored by Git):

- Campaign: `db3887b0-9796-42d7-80a3-700a4e4b6549`, named `Ticket 03 representative validation`.
- Student: `e4e3ec30-ff3b-4abc-a970-dfe9fa5c1c90`, Mailbox `artsipei@163.com`.
- Import: `681046aa-186d-4fdf-af20-512c678c4e8b`.
- Corrected and ready Preparation (Susanna Castleden): `c809bf2c-8a32-43cb-879c-7685070d952c`.

After the corrections the preview printed `Readiness: Ready`, `Attachments: Sipei Yao - CV.docx, ticket03-pilot-transcript.pdf`, and the corrected recipient and subject. The confirmed CV hash matched the preserved Source Material, and the slot snapshot survived editing the imported file. No browser capability is enabled or required by this slice.

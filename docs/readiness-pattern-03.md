# Supported Readiness and Attachment Pattern 03: Corrections and advisory attachments

Established from the user-supplied `sample.zip` on 2026-09-11, SHA-256 `f2e73a53d3503c3568cfeba730317ba232f4258636d9f5560e10dea77398f5e2` (the same archive as [Supported Intake Pattern 01](intake-pattern-01.md) and [Supported Document Pattern 02](preparation-pattern-02.md)).

Every one of the archive's 19 draft documents declares an enclosed attachment in the same sentence: *"I have attached my CV and would very much welcome the opportunity…"*. The archive contains exactly one such document, `姚思培/Sipei Yao - CV.docx`. No other attachment files are present, and no Source Material states that an attachment is *required*.

## Readiness findings and Exceptions

A Preparation's readiness findings are recomputed from its current local state whenever it is created or corrected. The supported blocking findings are:

| Finding | Condition | Resolution |
| --- | --- | --- |
| `missing_subject` | No non-blank subject | `preparation set-subject` |
| `invalid_recipient` | The recipient is not a usable address | `preparation set-recipient` |
| `recipient_conflict` | The recipient is usable but differs (ignoring local-part case) from the Supervisor's recorded address(es) | `preparation set-recipient` to a recorded address |
| `identity_conflict` | The associated Outreach Task carries a blocking `identity_ambiguity` Exception | `task confirm-identity` |

Readiness stays separate from sending authority. A Preparation with an empty finding list is Ready Preparation; nothing is sent or scheduled by becoming ready.

Task-level Exceptions are listed with their Source Material evidence and with the readiness findings of the Preparation attached to the same Task:

```
exceptions list --campaign CAMPAIGN_ID
exceptions show EXCEPTION_ID
```

## Field precedence and corrections

Corrections are operator-supplied, are recorded as inspectable Correction Records, and never guess:

| Field | Authoritative source | On correction |
| --- | --- | --- |
| Subject | Operator correction. The representative materials contain no subject source, so it is never invented and starts empty | Normalized by trimming; a blank value is rejected. Recorded with the prior value |
| Recipient | Operator correction, otherwise the draft's `Email:` declaration | Normalized like an intake address (domain lowercased, local part keeps its case). An unusable value is rejected. The conflict check is re-run, so a correction that still differs from the recorded address stays blocking |

```
preparation set-subject PREPARATION_ID "Subject"
preparation set-recipient PREPARATION_ID name@example.edu
```

Corrections only change SmartMail's local Preparation. Source bytes, Source Associations and Transformation Records remain as recorded, and the operator value becomes the field's stated Authoritative Source.

`identity_ambiguity` Blockers are confirmed per Task, not merged. The command clears that Task's own Blockers and revalidates its Preparations; every affected Task is confirmed individually, and no Supervisor identity is inferred from names.

```
task confirm-identity TASK_ID
```

## Advisory attachment slots

A supported body declaration produces a **suggested attachment slot**, for example `Student CV`. Slots carry the evidence for the suggestion and the best-matching file, and they are:

- **advisory only** — an unresolved slot never affects readiness and never produces a blocking finding;
- **never finalized automatically** — a suggested candidate is visible but no attachment is confirmed until the operator confirms, replaces or adds a file.

| Suggested slot state | Meaning |
| --- | --- |
| One filename candidate | The declaration label matches exactly one preserved `.docx` name in the same import |
| Several candidates | The label matches more than one preserved `.docx`; the operator selects one |
| No candidate | Nothing preserved matches the label; the operator selects or imports a file |

The suggestion rule is deterministic: the declared label's tokens must all appear in the filename stem, so `CV` matches `Sipei Yao - CV.docx` and `Academic CV.docx` but not the draft document or the CV-export workbook. Re-running `prepare` or `preparation suggest` refreshes advisory candidates and never duplicates a slot or changes a confirmed file.

```
preparation suggest PREPARATION_ID                              # refresh advisory candidates
preparation confirm PREPARATION_ID --slot SLOT_ID               # confirm the single suggested candidate
preparation attach PREPARATION_ID --slot SLOT_ID --source SOURCE_ID
preparation attach PREPARATION_ID --slot SLOT_ID --file C:\path\CV.pdf
preparation add-attachment PREPARATION_ID --label "Transcript" --source SOURCE_ID
preparation remove-attachment PREPARATION_ID --slot SLOT_ID
```

## Attachment contents

Confirmed attachment bytes are snapshotted into the local store with their SHA-256. No conversion, merging, or content modification is performed: bytes taken from a preserved Source Material are identical to that Source Material, and bytes imported from a file are identical to the file at import time. Later edits to the original file path never change a confirmed attachment. Removing a slot discards its confirmed snapshot.

## Not claimed

- No required, mandatory, or sending-blocking attachment. Only operator designations could create one, and none is implemented in this slice.
- No attachment packaging, conversion, merging, PDF/`.doc` interpretation, size inspection, or external upload.
- No automatic identity merging, name-based identity repair, campaign-level rules, or external mailbox draft writes.
- Preparation and attachments remain local. No browser capability is enabled in this slice.

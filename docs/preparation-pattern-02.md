# Supported Document Pattern 02: Outreach draft documents

Established from the user-supplied `sample.zip` on 2026-09-11, SHA-256 `f2e73a53d3503c3568cfeba730317ba232f4258636d9f5560e10dea77398f5e2` (the same archive as [Supported Intake Pattern 01](intake-pattern-01.md)).

The archive contains one CV, `Sipei Yao - CV.docx`, and 19 outreach draft documents arranged in `第二批` and `第三轮` folders. Every draft follows the same human layout. 17 drafts name a Supervisor present in the master list; two University of Technology Sydney drafts name contacts absent from it.

## Supported draft layout

A `.docx` is treated as an outreach draft only when its content fits this layout:

1. The first non-empty paragraph is a single recipient declaration, `Email: <address>`.
2. A greeting paragraph beginning `Dear` follows.
3. Body paragraphs run to a `Yours sincerely,` sign-off and the sender's name.
4. Optionally, trailing paragraphs beginning `Research source:` are an internal research note.

The document is associated to an Outreach Task by its filename, `<Institution>_<Supervisor name>.docx`, split on the first `_`. Documents that do not fit the layout are preserved as Source Materials but are not prepared; this includes the CV.

## Field precedence and automatic handling

| Field | Authoritative source | Automatic handling |
| --- | --- | --- |
| Sender | The Student's Mailbox (explicit operator input) | Taken as recorded |
| Recipient | The draft's `Email:` declaration | Case-insensitive match against the Supervisor's recorded addresses |
| Subject | None in the representative materials | Left empty and surfaced (never invented) |
| Body | The draft, from greeting through sign-off | Leading/trailing blanks trimmed, repeated blanks collapsed |
| Internal note | Trailing `Research source:` paragraphs | Separated from the message and retained |
| Attachments | Not associated by this pattern | Deferred to subsequent readiness/attachment work |

- The draft recipient is authoritative for the message being prepared. It is normalized like an intake address: the domain is lowercased, the local part keeps its declared case, and the declared form is stored.
- If the Supervisor has a **usable recorded address that differs** from the draft declaration, a blocking `recipient_conflict` finding is recorded and readiness is prevented. Comparison ignores local-part case, so `Robyn.Heckenberg@curtin.edu.au` and `robyn.heckenberg@curtin.edu.au` are the same recipient.
- If the Supervisor has **no usable recorded address** (for example the master email cell held a profile URL instead), the draft fills the recipient and a `recipient_filled_missing_address` Transformation Record is kept.
- An unparseable `Email:` declaration records a blocking `invalid_recipient` finding.
- **No subject is invented.** None of the drafts or workbook columns is a subject source, so every Preparation carries a blocking `missing_subject` finding. Supplying a subject is a correction, not an automatic transformation.

## Transformation Records

Each Preparation records what was done to the source: `recipient_extracted`, `body_restructured`, `internal_note_separated` where the note was present, and `recipient_filled_missing_address` where the draft filled a missing recorded address. The message body retains the author's text verbatim, including curly punctuation; only blank-line spacing is normalized.

## Association, ambiguity and unsupported cases

- Association matches exactly one Outreach Task within the import's Campaign and Student, by Institution (case-insensitive) and Supervisor name with the same title/whitespace normalization used for intake. No Task or Preparation is invented from a document.
- Zero matches records an `unassociated_document` finding; more than one records an `ambiguous_document` finding. Both are blocking and inspectable with the Source Material.
- A `.docx` that cannot be read records an `unsupported_document` finding.
- Preparation is idempotent: repeating it reuses each Preparation identity and does not duplicate findings.
- Preparation is **local only**. It reads preserved bytes, writes no external mailbox draft, and does not modify source bytes.

Placeholder substitution and template expansion are not present in the representative materials and are not claimed. This pattern does not claim arbitrary document parsing, PDF or `.doc` intake, attachment association, or any browser capability.

## Observed results

Preparing the supplied archive produces 17 Preparations, two `unassociated_document` findings (the two UTS drafts), one `recipient_conflict` (Susanna Castleden: the draft declares `S.Castleden@exchange.curtin.edu.au`, the master records `susanna@susannacastleden.com`), one filled missing address (Callum Morton, whose master cell held a profile URL), and 17 `missing_subject` findings. No Preparation is Ready until a subject is supplied. Attachments remain preserved for the readiness/attachment work.

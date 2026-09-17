# Supported Intake Pattern 01: Supervisor master list

Established from the user-supplied `sample.zip` on 2026-09-11, SHA-256 `f2e73a53d3503c3568cfeba730317ba232f4258636d9f5560e10dea77398f5e2`.

The inspected workbook, `姚思培/姚思培_60筛导初版.xlsx`, has a row-one header, 59 Supervisor rows, 11 Institutions, vertical merged Institution cells, and ancillary research/application columns. The archive also contains one CV and 19 draft documents. The master has no Student or sender Mailbox column, so these are explicit operator inputs. The CV provides evidence the operator can inspect; this slice does not infer Student identity from filenames or extract CV contact details automatically.

## Extraction

- Accept an existing `.xlsx`, or a `.zip` containing exactly one `.xlsx`. UTF-8 archive names are respected; legacy names use GBK as observed in the representative Windows archive. Preserve the ZIP and every non-directory member without modifying content. Unsafe member paths are rejected.
- Exactly one worksheet must have the required recognized headers in row 1. Its position, name and active-sheet selection do not matter. Other sheets remain preserved in the original workbook but are not interpreted.
- Column order is unrestricted. Surrounding header whitespace and English letter case are ignored. Duplicate aliases for one field are rejected instead of selecting an arbitrary authoritative column.
- Institution values may come from the anchor of an actual vertical merge in the Institution column. Unmerged blanks are not forward-filled. Supervisor names are never inherited from nearby rows.
- Institution and Supervisor values must be present. Formula-based identity fields, missing required headers, empty lists and ambiguous master sheets are rejected before import writes. A rejected import leaves existing work unchanged and returns an operator-visible error.
- The profile URL column is optional. Additional columns and formatting are preserved, and original row cells are included in task evidence. Entirely empty rows are skipped. Research notes are not interpreted as message content.
- Trim extracted text and email whitespace. Preserve email local-part case; normalize only the domain to lowercase. Accept one plain ASCII email address per recipient cell. Missing addresses, URLs, multiple addresses, display-name syntax and unsupported address forms create an `invalid_recipient` Blocker. Valid-looking typos are not guessed or repaired.

| Field | Observed header | Supported nearby aliases |
| --- | --- | --- |
| Institution | 大学 | 学校, 院校, Institution, University |
| Supervisor name | 导师 | 导师姓名, Supervisor |
| Recipient address | 邮箱📮 | 邮箱, 电子邮箱, Email |
| Supervisor profile | URL | 导师主页, Profile URL |

Aliases are narrowly equivalent labels for the observed fields, including omission of the decorative mailbox emoji and direct English translations. They are deliberate supported variations, not claims that additional production samples were supplied. Tests exercise reordered aliases, optional profile data, merged cells and duplicate-column rejection.

## Identity and evidence

An Outreach Task has unique Student × Supervisor × Campaign identity. Different Students or Campaigns produce separate tasks even when they share a Supervisor. Repeating an import is idempotent: tasks, Source Materials and Source Associations are reused rather than duplicated when identity is established.

### Repeat imports and idempotency

Every import returns a per-row report with an outcome and a summary. Row outcomes:

| Outcome | Meaning |
| --- | --- |
| `new` | The row created a new Outreach Task. |
| `reused` | The row attached to an existing Task through reliable identity or source-record continuity. |
| `duplicate` | Another row in this same workbook already resolved to the same Task with no new evidence; one Task is retained and both rows remain associated as evidence. A non-blocking `duplicate_import_row` Exception names both row coordinates. |

- Identical Source Material bytes are stored once per Campaign × Student. Importing the exact same file again reports `duplicate: true`, returns the original import id, creates no second import, Source or association, and reports every row as `reused`.
- A revision bundle whose master bytes are unchanged but whose other members are new remains a new import: the master rows are reused, while only the genuinely new member bytes are preserved. This keeps revised draft documents available for Rewrite without duplicating master evidence.
- A repeat of the exact same workbook bytes, worksheet and source row reuses that recorded Supervisor identity even when the row remains unresolved, across Students and Campaigns. This is source-record continuity, not a name-based identity guess.
- Re-importing changed information that matches a reliably identified Supervisor is reported in the row's `changes`: `profile_added` fills a previously empty profile, `address_added` records an additional known Supervisor address, and `address_absent_in_row` retains the recorded address instead of raising `invalid_recipient`. Routine enrichment never creates an Exception; non-blocking duplicate rows and blocking identity/recipient findings stay explicit. Task Exceptions are recorded once per condition, so repeat imports never duplicate them.

### Prior outreach conflicts at import

Import also checks the same deterministic duplicate evidence as [Pattern 07](duplicate-pattern-07.md): a same-Campaign immutable Sent Record of initial outreach, or an outbound `sent` Mailbox Observation in the Student's own Mailbox to a known Supervisor address (excluding ambiguous observations and unresolved identities), produces a blocking `prior_outreach_conflict` Exception on the Task. Cross-Campaign Sent Records alone do not conflict; a later student-wide Mailbox observation surfaces the conflict in every affected Campaign.

The Blocker prevents confirmation of new `initial` Preparations; linked Follow-up Actions remain ready and report `linked_follow_up`. The operator resolves reviewed evidence explicitly:

```powershell
python -m smartmail task resolve-prior-outreach TASK_ID
```

Supervisor matches require a compatible name and exact trimmed Institution plus a shared recorded email address or the same explicitly supplied Supervisor profile URL. Name comparison ignores letter case, repeated whitespace and leading Dr/Prof/Professor titles. Profile comparison normalizes scheme/host case and a trailing slash/empty fragment; it does not follow redirects, fetch websites or infer equivalence between different profile URLs. Contradictory nonempty profiles prevent address-based merging. Later reliable profile evidence is retained for subsequent matching.

Same-name/same-Institution candidates without reliable shared evidence remain separate. Shared addresses or profiles with conflicting identities are also surfaced. `identity_ambiguity` Blockers identify candidate Supervisor IDs and are attached to all affected existing tasks, across Students and Campaigns. No automatic merging of multiple candidates is performed. Resolution commands belong to subsequent correction/readiness work.

Every task's Source Associations retain the Source Material ID, worksheet, row, original row cells, extracted values and the exact source cell used for each extracted field, including merged Institution anchors. Original workbook bytes preserve formatting, links, merged ranges and ancillary evidence. Source hashes and original names are inspectable through `imports show`.

Draft documents and CVs are available in the import's Source Materials. They are not silently associated with individual Supervisors by filename. This pattern does not claim arbitrary document parsing, CSV/legacy XLS intake, multiple-master bundle selection, email delivery validation or any browser capability.

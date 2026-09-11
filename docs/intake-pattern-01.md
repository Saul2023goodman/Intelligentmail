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

An Outreach Task has unique Student × Supervisor × Campaign identity. Different Students or Campaigns produce separate tasks even when they share a Supervisor. Every successful import retains new source evidence; repeating an import reuses tasks when identity is established.

Supervisor matches require a compatible name and exact trimmed Institution plus a shared recorded email address or the same explicitly supplied Supervisor profile URL. Name comparison ignores letter case, repeated whitespace and leading Dr/Prof/Professor titles. Profile comparison normalizes scheme/host case and a trailing slash/empty fragment; it does not follow redirects, fetch websites or infer equivalence between different profile URLs. Contradictory nonempty profiles prevent address-based merging. Later reliable profile evidence is retained for subsequent matching.

A repeat of the exact same workbook bytes, worksheet and source row reuses that recorded Supervisor identity even when the row remains unresolved. This is source-record continuity, not a name-based identity guess.

Same-name/same-Institution candidates without reliable shared evidence remain separate. Shared addresses or profiles with conflicting identities are also surfaced. `identity_ambiguity` Blockers identify candidate Supervisor IDs and are attached to all affected existing tasks, across Students and Campaigns. No automatic merging of multiple candidates is performed. Resolution commands belong to subsequent correction/readiness work.

Every task's Source Associations retain the Source Material ID, worksheet, row, original row cells, extracted values and the exact source cell used for each extracted field, including merged Institution anchors. Original workbook bytes preserve formatting, links, merged ranges and ancillary evidence. Source hashes and original names are inspectable through `imports show`.

Draft documents and CVs are available in the import's Source Materials. They are not silently associated with individual Supervisors by filename. This pattern does not claim arbitrary document parsing, CSV/legacy XLS intake, multiple-master bundle selection, email delivery validation or any browser capability.

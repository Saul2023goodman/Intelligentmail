# 03: Make Student and Campaign scope explicit

Status: ready-for-agent
Blocked by: None (can start immediately)

**What to build:** One Student owns exactly one Campaign, and the workspace states that instead of guessing it. The relationship is persisted and owned by Core — registering a Student establishes their Campaign, a Campaign records the Student who owns it, and the link survives a restart — so a page can only be wrong about layout, never about whose work it is showing. The workflow canvas and source mapping already scope by the Student's own Campaign. What remains is the rest of the workspace: every page that still offers a raw Campaign chooser offers the Student scope instead, and a Campaign no Student owns is never presented as a Student's work.

## Acceptance criteria

- [ ] Batch execution, mailbox reconciliation and records evidence offer the same Student scope as the workflow canvas and source mapping; the chosen Student determines the Campaign on every page, and no page compares Student names with Campaign names.
- [ ] A Campaign that no Student owns (a standalone grouping) is never attributed to a Student; where it holds Outreach Tasks, it stays inspectable as retained evidence instead.
- [ ] Student switching, scope switching and page-to-page navigation keep one consistent scope, and the chosen scope survives a reload.
- [ ] Existing stores stay usable: a Student registered before the relationship was persisted is healed on registration, and previously imported Campaigns, Students, Mailboxes and Outreach Tasks keep their relationships and remain inspectable.

## Comments

2026-09-17: Raised from the frontend ↔ Core adaptation review, then corrected: a Student **is** the Campaign (one Student, one Campaign) — the defect was that the relationship was never persisted, so the bridge and the workflow canvas each re-derived it by comparing a Campaign name with a Student name. Consequences of that inference: two Students sharing a name silently shared one Campaign and its work, and a Campaign recorded under its own name could not be reached by any Student at all.

2026-09-17: The persistence half is implemented. `campaigns` now records its owning Student; registering a Student establishes their Campaign in the same transaction and returns `campaign_id`; Student and Mailbox listings report that `campaign_id`; opening an existing store recovers the link once, only where exactly one unlinked Campaign and exactly one Student share a name, and name matching is never used again. The bridge no longer searches or creates a Campaign by name, the workflow canvas reads the Student's own `campaign_id`, and source mapping scopes to the Student's Campaign rather than an independently chosen one. `tests/test_core.py` covers one Campaign per Student, two same-named Students, a standalone Campaign, restart persistence, and the migration of a store that recorded only names. Remaining work is the page-scope acceptance criteria above.
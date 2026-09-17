# 07: Move derived decisions into Core read models and clear the contract

Status: ready-for-agent
Blocked by: None (can start immediately)

**What to build:** The pages stop deciding what the data means. Stage membership and counts, the current Preparation version, a source's role, the set of work that is Ready and not yet consumed, mailbox match classification, and version numbering all become values Core reports, so a page can be wrong only about layout and never about the domain. Alongside that, the workspace stops reading the store's internals directly, stops spending one full per-task aggregation per task when a list is loaded, and the command contract is cleared of entries nothing calls and fields that are returned but never shown — including making the difference between an acceptance-mode capability and a verified one visible to the operator.

## Acceptance criteria

- [ ] The workflow canvas, source mapping, batch execution, mailbox reconciliation and records pages render stage counts, current version, source role, readiness sets, consumed Confirmations, mailbox classification and version numbering from values Core reports.
- [ ] The UI layer performs no direct reads of the store's internal tables; every value it shows arrives through a supported command result.
- [ ] Loading a list view for a Campaign with many Outreach Tasks does not perform one full per-task aggregation per task; list payloads stay lean and bounded, with full content available on drill-down.
- [ ] Commands with no caller are either used by a page or removed from the contract, and fields already returned but never rendered — the flow state and Reconciliation on the mailbox page, and Reconciliation results returned by a mailbox refresh — are shown or dropped.
- [ ] A capability available only in acceptance mode is visibly distinguished from a verified one, using the capability's stated basis, wherever an operator is about to rely on it.
- [ ] Importing a source set no longer forces preparation: imported material can be retained and prepared as a separate, visible step.
- [ ] Existing page behaviour, the viewport contract and the read-only boundaries are preserved, and the affected pages stay verifiable through the workspace command boundary.

## Comments

2026-09-17: Raised from the frontend ↔ Core adaptation review. Derived judgements currently live in page models (readiness sets, consumed Confirmations, latest plan selection, mailbox match classification, stage counts, version numbering); two bridge composition modules read the store's tables directly instead of going through Core queries; the mailbox workspace, readiness workbench and intake workspace each aggregate per task; and the contract carries unused commands plus unrendered fields.
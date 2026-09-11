# 07: Detect historical duplicates before execution

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 05, 06

**What to build:** Use available historical evidence to prevent repeated execution and surface duplicate initial outreach before sending.

## Acceptance criteria

- [ ] Combine imported history and supported mailbox observations with deterministic matching and recorded Evidence Coverage.
- [ ] Prevent Repeat Execution of an already executed Communication Action.
- [ ] Flag repeated initial outreach for the same Student and Supervisor within a Campaign, including known alternate supervisor addresses.
- [ ] Keep different Students distinct and do not classify linked authorized Follow-up Actions as duplicate initial outreach.
- [ ] No matching evidence yields No Duplicate Found qualified by coverage; incomplete history alone is nonblocking, while genuinely ambiguous matches require review.
- [ ] Reconcile before execution and pause the current Execution Flow when a newly discovered duplicate or identity conflict blocks a confirmed action.
- [ ] Boundary tests exercise historical matches, ambiguity resolution, distinct students, incomplete coverage, and new evidence after Confirmation.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.


# 10: Propose and confirm deterministic Sending Plans

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 05

**What to build:** Generate and adjust sending times under explicit constraints, then confirm exact plans through the terminal.

## Acceptance criteria

- [ ] Configure allowed windows, timezone, spacing, and daily limits; produce reproducible default proposals.
- [ ] Display all review fields and access to full messages before batch Confirmation; allow operator adjustment before confirmation.
- [ ] Surface impossible proposals instead of silently violating configured constraints.
- [ ] Bind Confirmation to exact Preparation and execution times; changes require renewed Confirmation.
- [ ] Expired confirmed times require an explicitly confirmed replacement time and never default to immediate sending.
- [ ] Use controlled time and the controlled adapter through the command boundary to verify plan constraints, timezone handling, content changes, and expiry.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.


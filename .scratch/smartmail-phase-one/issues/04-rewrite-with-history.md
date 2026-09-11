# 04: Rewrite preparation with inspectable history

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 03

**What to build:** Replace active Preparation with a fresh Preparation while keeping prior content and associations inspectable.

## Acceptance criteria

- [ ] Rewrite creates fresh Preparation identity and hides Superseded Preparation from normal active-work views.
- [ ] History inspection exposes prior content, Source Associations, and transformation evidence alongside original Source Materials.
- [ ] New imports cannot silently replace active accepted work; supported replacement is explicit in the workflow.
- [ ] Any existing Confirmation cannot transfer to a fresh Preparation; integrate this behavior when Confirmation is introduced.
- [ ] Preparation and attachment snapshots preserve historical content independently of later edits to the original file path.
- [ ] Boundary tests cover repeated Rewrite, active versus historical inspection, and crash/restart persistence.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.


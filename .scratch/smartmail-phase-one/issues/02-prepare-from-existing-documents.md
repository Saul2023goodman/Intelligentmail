# 02: Prepare communications from existing documents

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 01

**What to build:** Associate existing draft documents with Outreach Tasks and produce inspectable local Preparation using supported deterministic rules.

## Acceptance criteria

- [ ] Inspect representative documents during coding and define supported layouts, field precedence, and justified related variations.
- [ ] Associate document content to the correct Outreach Task with traceable Source Associations; identity and recipient conflicts prevent Ready Preparation.
- [ ] Apply supported cleanup, normalization, substitution, and restructuring automatically without a routine human acceptance step.
- [ ] Preserve source evidence and Transformation Records and open a full message preview from the terminal.
- [ ] Missing values come only from unambiguous Authoritative Sources; unsupported transformations or internal-note separation become Exceptions rather than invented content.
- [ ] Preparation persists across restart and produces no external mailbox draft writes; boundary tests assert expected content, associations, and unsupported cases.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.


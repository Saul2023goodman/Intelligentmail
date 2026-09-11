# 08: Recover interrupted execution and manual takeover

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 05, 06

**What to build:** Resume interrupted confirmed work from persisted evidence without blind retries, and support explicit reconcile-and-continue after Manual Takeover.

## Acceptance criteria

- [ ] Persist execution intent and attempt evidence sufficiently to distinguish not attempted, observed outcomes, and Unknown Outcome across crash boundaries.
- [ ] Reconcile unfinished work after restart and uncertain external actions before deciding whether further execution is permitted.
- [ ] Positive evidence of prior success prevents a repeated request; unresolved outcome pauses for intervention rather than being converted to failure.
- [ ] Explicit reconcile-and-continue observes manual work before progressing; acknowledgment alone is not proof of Sent.
- [ ] Automatically resume only still-valid confirmed work; retain existing blocking pauses and require a newly confirmed time if the confirmed time has expired.
- [ ] Authentication interruptions and operator intervention leave local preparation and inspection usable.
- [ ] Boundary tests inject crashes before submission, during submission, and after success before outcome persistence; assert no blind retries or unconfirmed actions.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.


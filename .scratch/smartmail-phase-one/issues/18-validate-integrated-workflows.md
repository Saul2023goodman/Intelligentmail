# 18: Validate integrated workflows and document results

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 13, 14, 17

**What to build:** Validate the agreed complete workflows against representative inputs and enabled real mailbox capabilities, and document reproducible operational results.

## Acceptance criteria

- [ ] Fix a representative scenario set before evaluation, mapping the specification's required behaviors to evidence and documenting supported intake boundaries.
- [ ] Exercise normal preparation and confirmed execution, ambiguous intake, attachments, rewrites before and after scheduling, duplicates, replies, and follow-ups.
- [ ] Exercise authentication interruption, Unknown Outcomes, Manual Takeover, restart recovery, expired times, direct mailbox changes, and replacement races.
- [ ] Validate immediate sending and native scheduling independently; a disabled unverified capability must not disable an independently verified one or be reported as passed.
- [ ] Require no unconfirmed sends, no blind retries, traceable preparations and outcomes, immutable Sent Records, and correct supported-case recovery.
- [ ] Include controlled real execution evidence for enabled capabilities; simulated adapter tests alone do not verify external behavior.
- [ ] Document capability availability, scenario outcomes, limitations, and the process-optimization and information-management narrative; manual touches and timing may be secondary observations rather than completion thresholds.
- [ ] Exclude Recall from completion blockers and required successful scenarios; optional Recall evidence may be documented separately.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled external mailbox capabilities through the dedicated extension separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

This replaces the previously proposed pilot ticket. Validate integrated workflows and document results without requiring a separate pilot milestone or Recall acceptance.

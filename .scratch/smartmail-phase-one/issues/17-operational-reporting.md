# 17: Report operational work with drill-down

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 07, 11, 16

**What to build:** Find completed and unfinished work using operational dimensions and drill down to task evidence.

## Acceptance criteria

- [ ] Filter and summarize by Student, Supervisor or Institution, Campaign, Mailbox, message status, duplicate status, Exceptions, and follow-up eligibility.
- [ ] Distinguish locally planned, Externally Scheduled, Sent, observed failure, and Unknown Outcome rather than collapsing them into success or failure.
- [ ] Drill down from counts into matching Outreach Tasks, Preparation, source evidence, and execution history.
- [ ] Expose Duplicate Suspicion and No Duplicate Found with Evidence Coverage rather than implying complete historical knowledge.
- [ ] Reports remain available while an Execution Flow is paused and reproduce persisted state after restart.
- [ ] Verify visible counts and drill-down membership through the command/query boundary; timing metrics and semantic-outcome funnels are not required.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled external mailbox capabilities through the dedicated extension separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

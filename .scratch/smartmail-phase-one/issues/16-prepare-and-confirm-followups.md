# 16: Prepare and confirm linked Follow-up Actions

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 09, 15

**What to build:** Track Follow-up Due and prepare and execute separately confirmed linked communications.

## Acceptance criteria

- [ ] Configure campaign follow-up timing and maximum count with deterministic eligibility based on reliably associated Ordinary Replies.
- [ ] Recognized Automatic Replies do not by themselves stop eligibility; out-of-office return dates are not required core scheduling logic.
- [ ] Prepare content automatically only when a supported rule or template and required values exist; otherwise mark due for operator preparation.
- [ ] Create a separate linked Communication Action rather than re-executing the original or treating a follow-up as duplicate initial outreach.
- [ ] Require independent sending Confirmation and use the existing execution safeguards.
- [ ] New associated reply evidence after Confirmation pauses affected execution rather than allowing an obsolete follow-up.
- [ ] Boundary tests cover due dates, count limits, missing templates, ordinary and automatic replies, new blockers, and no unconfirmed follow-up; demonstrate the enabled execution path.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled external mailbox capabilities through the dedicated extension separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

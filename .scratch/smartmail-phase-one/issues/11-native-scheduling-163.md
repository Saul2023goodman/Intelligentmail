# 11: Place and track native 163.com schedules

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 07, 08, 10

**What to build:** Place confirmed native mailbox schedules and observe their subsequent outcomes independently of immediate sending.

## Acceptance criteria

- [ ] Use the shared confirmation, duplicate, reconciliation, and interruption safeguards without depending on the immediate-send capability.
- [ ] Create the native schedule through the browser only for a confirmed exact Preparation and time, preserving observed external schedule identity.
- [ ] Mark Externally Scheduled only with external evidence; keep local plans, Unknown Outcome, and Sent distinct.
- [ ] Verify mailbox-owned execution while the local application is offline through controlled acceptance; do not substitute a local timer if native scheduling is unavailable.
- [ ] Reconcile later outcomes and recover uncertain schedule placement without duplicate submission; time elapsing alone cannot establish Sent.
- [ ] Expose native scheduling availability independently; demonstrate acceptance with immediate sending disabled or unimplemented.
- [ ] Keep external schedules visible during local execution pauses; test schedule expiry and interruption through the command boundary.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.


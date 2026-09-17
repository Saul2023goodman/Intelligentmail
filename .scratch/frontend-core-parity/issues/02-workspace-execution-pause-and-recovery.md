# 02: Discover paused execution and complete recovery in the workspace

Status: ready-for-agent
Blocked by: None (can start immediately)

**What to build:** When an Execution Flow pauses — an unresolved Execution Attempt, an Unknown Outcome, a Duplicate Suspicion discovered after Confirmation, a new Associated Reply, an expired confirmed time, or an authentication interruption — the operator sees the pause, its reason and the evidence behind it inside the Batch execution page, and can resolve it there. Today the workspace can report that a flow is paused while offering no way to act on it, and tells the operator to resolve it in the terminal shell; further confirmed work for that Campaign is refused, so the visual workspace becomes a dead end. This ticket makes the workspace the place where an interruption is understood, stopped, taken over, reconciled from Mailbox Observations, and continued.

## Acceptance criteria

- [ ] The workspace reports the current Execution Flow state and pause reason together with the evidence for the affected Outreach Task, including the phase and outcome evidence of the unresolved Execution Attempt.
- [ ] The operator can stop an unresolved Execution Attempt with a recorded reason, and the flow reports the pause as resolved where the existing rules allow.
- [ ] The operator can record Manual Takeover, and the workspace never asserts Sent from a takeover; acknowledgment alone does not establish Sent.
- [ ] The operator can request Reconciliation, review the retained Mailbox Observation and its Evidence Coverage, and then explicitly confirm continuation or resumption; an ambiguous, partial, or authentication-interrupted observation does not resolve an attempt.
- [ ] Continuation and resumption reuse only still-valid, unchanged Confirmations; expired or invalidated work requires a renewed Confirmation with an explicit time, and existing Blockers are never bypassed.
- [ ] Externally Scheduled work can be reconciled from the workspace, and direct external changes are reported as discrepancies that inherit no Confirmation and never restore old content or timing.
- [ ] Every recovery capability reachable in the terminal shell is reachable in the workspace, and the workspace never substitutes an immediate send for a scheduled Confirmation.
- [ ] Verified through the workspace command boundary: pause visibility, stop, Manual Takeover, reconcile-and-continue, restart resumption, and no repeated external request for an unresolved attempt.

## Comments

2026-09-17: Raised from the frontend ↔ Core adaptation review. The Batch execution page renders a paused-flow banner instructing the operator to resolve the flow "in Core", while the workspace command allowlist contains no stop, takeover, resume, reconcile-and-continue or external-schedule reconciliation entry. The same review found the workspace cannot create an unresolved attempt-free route out of a pause, which is why ticket 01 is sequenced first.
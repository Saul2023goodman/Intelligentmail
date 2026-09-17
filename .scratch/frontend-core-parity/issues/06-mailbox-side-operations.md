# 06: Complete mailbox-side operations in the workspace

Status: ready-for-agent
Blocked by: None (can start immediately)

**What to build:** The mailbox-side operations that today exist only in the terminal shell become available where the operator already works: setting and inspecting the observation interval for a Student Mailbox, reconciling tracked native schedules against fresh evidence, and carrying out a conditional Recall of a Sent Record. Recall stays independently gated, requires its own explicit Confirmation, and its outcome is recorded separately without ever blocking completion; observation settings grant no external authority.

## Acceptance criteria

- [ ] The operator can set the observation interval for a Student Mailbox, including disabling it, and inspect the current setting; changing it never mutates the mailbox.
- [ ] The operator can reconcile tracked Externally Scheduled work from the workspace and sees later externally owned or externally edited changes as discrepancies that inherit no Confirmation and never restore old content or timing.
- [ ] Recall is offered only when the mailbox capability is available, and the operator can review eligibility, confirm the operation explicitly, and then carry it out.
- [ ] A Recall outcome — recalled, pending, ineligible, unsupported, failed or unknown — is recorded separately and never blocks completion of the flow.
- [ ] Missing eligibility, a closed mailbox tab, or an unauthenticated session leaves the Sent Record and all other work intact and reports the outcome honestly.
- [ ] Every mailbox-side capability reachable in the terminal shell is reachable in the workspace, and read-only observation still turns on no state-changing operation.

## Comments

2026-09-17: Raised from the frontend ↔ Core adaptation review. Observation-interval settings, external-schedule reconciliation and the whole Recall path have no workspace entry, while the records page already renders Recall authorisation and outcome nodes that can therefore never be produced from the workspace.
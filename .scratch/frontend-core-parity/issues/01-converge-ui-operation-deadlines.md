# 01: Converge UI operation deadlines and align the transport

Status: ready-for-agent
Blocked by: None (can start immediately)

**What to build:** An operator who triggers a mailbox read or a confirmed external operation from the visual workspace gets an outcome that reflects what the mailbox actually did, not how long the local transport was willing to wait. Operations that are expected to take time — reading a mailbox whose supported scope holds thousands of messages, or submitting a Confirmation whose attachments approach the supported size — must not be turned into an observed failure or an Unknown Outcome merely because an internal wait expired. Where a wait genuinely elapses, the workspace states plainly that the outcome is unknown and must be reconciled, and never presents it as "did not happen".

## Acceptance criteria

- [ ] A confirmed immediate send whose attachments approach the supported size limit completes, or reports its real mailbox outcome, when driven from the workspace; it is not recorded as Unknown Outcome because an internal deadline elapsed.
- [ ] A mailbox refresh over a large supported scope returns a persisted Mailbox Observation with its Evidence Coverage, instead of a failed observation caused by the local wait.
- [ ] The wait used by the visual workspace, the extension adapter, and the transport is consistent for the same operation, and is configurable per operation kind (read, immediate send, native schedule, cancellation, Recall).
- [ ] An elapsed wait for an operation that may have crossed the mailbox boundary is presented as Unknown Outcome requiring Reconciliation, never as a failure.
- [ ] Repeating an operation is never automatic: evidence must be reconciled first, exactly as the terminal path already requires.
- [ ] Verified through the workspace command boundary with a controlled fixture that takes longer than the previous limit, for both an observation and a submission.

## Comments

2026-09-17: Raised from the frontend ↔ Core adaptation review. The workspace bridge currently caps extension waits at 20 seconds, the terminal adapter defaults to 120 seconds, and the dev-server request bridge allows 30 seconds (120 seconds for source import). Because a submission that times out is recorded as Unknown Outcome and pauses the Execution Flow, this mismatch reliably manufactures the dead end that ticket 02 removes.
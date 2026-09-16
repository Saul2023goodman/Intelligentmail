# 12: Extension native schedules, cancellation, replacement, and direct-mail reconciliation

Status: resolved
Labels: implemented, live-acceptance-partial
Validation: docs/ticket-12-validation.md (controlled real-mailbox acceptance 2026-09-16;
transport-level worker sign-off and live Recall remain explicitly documented follow-ups)
Blocked by: None (prerequisites 07, 08, 10 are resolved); can start immediately

**What to build:** Implement and accept against real 163.com the remaining dedicated-extension capabilities, keeping all business rules in the Python core: place and track confirmed native schedules that the mailbox owns while SmartMail is offline; cancel external scheduled drafts only under explicit operator control, with conditional Recall kept separate; perform confirmed Scheduled Replacement with verified removal-before-submission; reconcile direct mailbox edits without restoring stale plans or transferring Confirmation; and complete the live extension acceptance still pending since the 2026-09-14 pivot. Core-side replies, follow-ups, and reporting are ticket 11, the primary ticket, and are not part of this slice.

## Acceptance criteria

### Place and track native schedules (merged ticket 11)

- [ ] Use the shared Confirmation, duplicate, Reconciliation, and interruption safeguards without depending on the immediate-send capability.
- [ ] Create the native schedule through the dedicated extension only for a confirmed exact Preparation and time, preserving the observed external schedule identity.
- [ ] Mark Externally Scheduled only with external evidence; keep local plans, Unknown Outcome, and Sent distinct.
- [ ] Verify through controlled real-extension acceptance that the mailbox executes the schedule while the local application is offline; never substitute a local timer when native scheduling is unavailable.
- [ ] Reconcile later outcomes and recover uncertain schedule placement without duplicate submission; time elapsing alone cannot establish Sent.
- [ ] Expose native scheduling availability independently; demonstrate its acceptance with immediate sending disabled.
- [ ] Keep external schedules visible during local execution pauses; test schedule expiry and interruption through the command boundary.

### Operator-controlled cancellation and conditional Recall (merged ticket 12)

- [ ] Require explicit operator control before removing an external scheduled draft or otherwise changing its actual sending commitment.
- [ ] Observe removal before recording successful Cancellation; uncertain removal pauses rather than asserting success.
- [ ] If the message has already Sent, preserve its frozen Sent Record and report that the pending cancellation did not prevent sending.
- [ ] Show that pausing SmartMail alone leaves other external schedules active.
- [ ] Cover confirmed cancellation, uncertain removal, authentication interruption, and send-versus-cancel races through the core boundary with extension-peer fixtures and controlled live acceptance.
- [ ] Keep Recall disabled unless platform support and message eligibility are established; if enabled, require explicit Confirmation and record its observed outcome separately from Sent. Recall is never a completion blocker.

### Scheduled Replacement (merged ticket 13)

- [ ] Preparing a replacement locally leaves the original external schedule active and prominently visible until explicit cancellation or replacement Confirmation.
- [ ] Confirmation binds the exact replacement Preparation and schedule; the prior Confirmation does not transfer.
- [ ] Verify removal of the original external scheduled draft before submitting the replacement; unknown removal prevents submission.
- [ ] If removal succeeds but replacement submission fails, pause with accurate evidence and do not automatically restore the original.
- [ ] Treat uncertain replacement submission as Unknown Outcome and reconcile before another attempt.
- [ ] If the original sends during cancellation, freeze its Sent Record and pause; further communication requires a new linked action and Confirmation.
- [ ] Test restart and interruption across each replacement step, preserve hidden Preparation history, and perform controlled live acceptance of supported operations.

### Direct mailbox changes (merged ticket 14)

- [ ] Detect supported direct changes through manual refresh and the existing mandatory Reconciliation triggers.
- [ ] Record observed external state and discrepancies from prior local plans, preserving immutable sent content and additional evidence.
- [ ] External edits never inherit prior Confirmation and never trigger automatic restoration of old content or schedule.
- [ ] Show changed schedules and sending outcomes in task inspection; pause affected execution when new evidence blocks it.
- [ ] Offer configurable periodic observation without granting it authority to alter external sending state.
- [ ] Boundary tests and controlled extension checks cover direct editing, cancellation, sending, repeated observations, and unchanged local Sent Records.

### Live extension acceptance and integrated evidence (extension share of merged ticket 18, plus pivot-pending acceptance)

- [ ] Re-run live acceptance for `read_history` and `immediate_send` through the connected `163-extension` (pending since the pivot on tickets 06 and 09); retired Playwright results stay historical evidence and fixture tests never establish verification.
- [ ] Add controlled extension-peer protocol tests for each new capability (schedule placement, cancellation, replacement sequencing) alongside repeatable core-boundary failure and race tests; keep live acceptance separate.
- [ ] Produce controlled real-extension evidence for every capability this ticket enables; each capability is enabled and verified independently, so an unverified one (including Recall) neither disables a verified one nor is reported as passed.
- [ ] Run the integrated live scenarios last, against the completed ticket 11 core workflows where available: confirmed scheduling with the application offline, cancellation and replacement races, and direct external edits; document capability availability, scenario outcomes, and limitations.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and controlled extension-peer evidence. Every enabled external capability additionally requires controlled real-extension acceptance per the pivot guide; simulated fixture outcomes cannot verify platform behavior. Do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, no SMTP/IMAP fallback, and no revival of the retired Playwright path. The Native Messaging protocol stays bounded and versioned — connection, heartbeat/claim, attachment chunks, one submission permit, and result evidence; schedule and cancel operations extend it without adding arbitrary command execution. See the [pivot guide](../../../docs/browser-extension-pivot.md) and [extension validation](../../../docs/extension-validation.md).

## Comments

2026-09-14: Merged from tickets 11 (native scheduling), 12 (cancellation and conditional Recall), 13 (scheduled replacement), 14 (direct mailbox changes) and the live-acceptance share of ticket 18, per operator direction; the primary focus remains core ticket 11. All hard prerequisites (07, 08, 10) are resolved, so this ticket is unblocked; its final integrated live step naturally runs last and can validate ticket 11 workflows, but capability implementation is not gated by ticket 11. As of the pivot, native scheduling, schedule cancellation, and Recall are implemented nowhere and remain disabled by default, and extension `read_history` and `immediate_send` still have `verified: false`. The original ticket files were removed in this merge.

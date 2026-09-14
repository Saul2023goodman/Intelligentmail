# 12: Cancel external schedules under operator control

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 11

**What to build:** Confirm and verify external scheduled-draft removal, handling uncertainty and sending races; expose conditional Recall within mailbox cancellation support.

## Acceptance criteria

- [ ] Require explicit operator control before removing an external scheduled draft or altering its actual sending commitment.
- [ ] Observe removal before recording successful Cancellation; uncertain removal pauses rather than asserting success.
- [ ] If the message has already Sent, preserve its frozen Sent Record and report that pending cancellation did not prevent sending.
- [ ] Show that pausing SmartMail alone leaves other external schedules active.
- [ ] Test confirmed cancellation, uncertain removal, authentication interruption, and send-versus-cancel races through the core boundary and controlled live acceptance where supported.
- [ ] Keep Recall disabled unless platform support and message eligibility are established; if enabled, require explicit Confirmation and record its observed outcome separately from Sent.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled external mailbox capabilities through the dedicated extension separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

Recall is optional capability behavior folded into this slice, not a standalone delivery requirement. Unavailable or unverified Recall must not block this ticket, any dependent ticket, or integrated completion. Cancellation acceptance is independent of Recall.

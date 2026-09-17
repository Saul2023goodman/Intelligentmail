# 05: Close the reply-association and Follow-up loop

Status: ready-for-agent
Blocked by: None (can start immediately)

**What to build:** An operator works replies and follow-ups to completion in the workspace: an ambiguous Associated Reply is resolved to an Outreach Task or dismissed, a Campaign Follow-up Rule is configured, Follow-up Due work becomes linked Follow-up Actions from a template or from an operator-supplied Source Material, and a Follow-up Action can be recorded as following an existing Sent Record. Today the workspace displays follow-up state and reply evidence but cannot act on either, so a reply-review state can never be cleared and eligible follow-ups can never be prepared.

## Acceptance criteria

- [ ] The operator can resolve an ambiguous reply association to a specific Outreach Task, or dismiss it, and Core recomputes the affected no-reply eligibility.
- [ ] Recognized Automatic Replies stay recorded separately and never stop follow-up eligibility by themselves; a reliably associated Ordinary Reply does. The workspace never classifies interest, rejection or document requests.
- [ ] The operator can configure the Campaign Follow-up Rule — delay, maximum count, subject and body templates — and inspect deterministic Follow-up Due status per Outreach Task.
- [ ] Eligible work becomes a linked Follow-up Action either from a rendered template or, when no template applies, from an operator-supplied Source Material; content is never invented.
- [ ] A Follow-up Action can be recorded as following an existing Sent Record, so its Duplicate Check reports a linked follow-up rather than repeated outreach.
- [ ] A Follow-up Action carries its own Confirmation, duplicate re-check and pause-on-blocker behaviour, and an Associated Reply arriving after Confirmation pauses the Execution Flow before any external request.
- [ ] Verified through the workspace command boundary, including refusals for unsupported and out-of-scope requests.

## Comments

2026-09-17: Raised from the frontend ↔ Core adaptation review. Reply resolution, Follow-up Rule configuration, Follow-up Action preparation, operator-supplied preparation and follow-up linking are all reachable only through terminal commands; the pages can render the resulting states but cannot reach any of the transitions, leaving `reply_review_required` and Follow-up Due work permanently stuck in the workspace.
# 11: Associate replies, confirm linked follow-ups, and report operations (core)

Status: resolved
Labels: implemented
Priority: primary — core module is the operator-designated focus (2026-09-14)
Blocked by: None (prerequisites 03, 06, 07, 09, 10 are resolved); can start immediately

**What to build:** Close the core outreach loop without adding any external mailbox capability: persist deterministic associations between inbound observations and Outreach Tasks (reliable, ambiguous, and Recognized Automatic Replies), compute Follow-up Due eligibility and produce separately confirmed linked Follow-up Actions, and answer operational reporting with drill-down to task evidence — then validate the complete local workflows against representative inputs through the existing SmartMail command/query boundary. External scheduling work is ticket 12.

## Acceptance criteria

### Reply association and automatic replies (merged ticket 15)

- [x] Define supported deterministic association evidence during coding from real persisted observations (known Supervisor addresses, confirmed-subject thread markers, timing after a known Sent Record); only reliable matches become Associated Replies.
- [x] Surface ambiguous task associations for operator review and resolution inside SmartMail; unresolved ambiguity never silently drives eligibility.
- [x] Associated Ordinary Replies stop no-reply follow-up eligibility without classifying interest, rejection, or document requests.
- [x] Recognized Automatic Replies use supported explicit rules on observable fields, remain separately inspectable, and do not by themselves stop no-reply eligibility.
- [x] Document and test the supported detection boundary: uncertain detection is reported as uncertainty, never inferred semantic understanding; signals the read-only observation does not expose are recorded as Evidence Coverage limitations, not guessed.
- [x] Associations and observations persist across restart; boundary tests cover reliable links, ambiguous links, supported automatic replies, and ordinary messages.

### Follow-up eligibility and linked Follow-up Actions (merged ticket 16)

- [x] Configure campaign follow-up timing and maximum count; eligibility is deterministic, based only on reliably associated Ordinary Replies, and reproducible with controlled time.
- [x] Recognized Automatic Replies do not stop eligibility; out-of-office return dates are not core phase-one scheduling logic.
- [x] Prepare follow-up content automatically only when a supported rule or template and every required value exist; otherwise mark the action due for operator preparation rather than inventing content.
- [x] Each follow-up is a separate linked Communication Action, never a re-execution of the original and never reported as duplicate initial outreach.
- [x] Every follow-up requires its own sending Confirmation and runs through the existing execution safeguards: digest binding, duplicate re-check, Reconciliation before execution, and pause on new blockers.
- [x] New associated reply evidence arriving after Confirmation pauses the affected follow-up execution rather than sending an obsolete message.
- [x] Boundary tests cover due dates, count limits, missing templates, ordinary versus automatic replies, new blockers, and refusal of unconfirmed follow-up; demonstrate the enabled execution path against the controlled adapter.

### Operational reporting with drill-down (merged ticket 17)

- [x] Filter and summarize by Student, Supervisor or Institution, Campaign, Mailbox, message status, duplicate status, Exceptions, and follow-up eligibility.
- [x] Distinguish locally planned, Externally Scheduled, Sent, observed failure, and Unknown Outcome as separate states; Externally Scheduled is represented from adapter evidence (controlled fixtures now, real extension evidence from ticket 12 later) with no hard dependency on ticket 12.
- [x] Drill down from summary counts into the matching Outreach Tasks, their Preparation, source evidence, and execution history.
- [x] Expose Duplicate Suspicion and No Duplicate Found together with their Evidence Coverage rather than implying complete historical knowledge.
- [x] Reports remain available while an Execution Flow is paused and reproduce persisted state after restart.
- [x] Verify visible counts and drill-down membership through the command/query boundary; timing metrics and semantic-outcome funnels are not required.

### Integrated core validation (core-controlled share of merged ticket 18)

- [x] Fix a representative scenario set before evaluation, mapping the specification's required behaviors to evidence and documenting supported intake boundaries; reuse the already preserved representative materials.
- [x] Exercise end to end through the boundary with the controlled adapter and controlled time: intake to Ready Preparation, Confirmation, controlled Sent, immutable Sent Record, duplicate check, inbound reply, follow-up eligibility and linked Confirmation, and report drill-down; plus ambiguous intake, attachment resolution, Rewrite before and after a confirmed Sending Plan, expired times, restart recovery, and Manual Takeover reconciliation.
- [x] Report every mailbox capability independently: disabled or unverified extension capabilities are never reported as passed, and this ticket never claims live mailbox verification.
- [x] Hold the complete suite green with no unconfirmed sends, no blind retries, traceable Preparation and outcomes, and immutable Sent Records; document scenario outcomes and limitations in a validation document.
- [x] Live-extension scenarios (real native schedules, cancellation and replacement races, direct external edits, real sends) belong to ticket 12 and are not simulated as passed here; Recall is excluded from completion blockers.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state, a controlled mailbox adapter, and controlled time. Extension-peer fixtures may supply inbound observations but do not verify external behavior; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no semantic classification of ordinary replies, no phase-one frontend, and no routine exported-workbook workflow. Each behavior ships with its terminal interaction, core behavior, persistence, and behavioral tests.

The read-only observation collected since ticket 06 is metadata-only; body HTML and unrecognized custom folders stay excluded. If real reply association later needs additional read-only signals from the extension, that transport work belongs to ticket 12 — until then the core records Evidence Coverage honestly rather than guessing.

## Comments

2026-09-14: Merged from tickets 15 (associate and classify replies), 16 (prepare and confirm linked follow-ups), 17 (operational reporting) and the core-controlled share of ticket 18 (integrated validation), per operator direction; this is the primary remaining ticket and the implementation focus. All its prerequisites (03, 06, 07, 09, 10) are resolved, so it is unblocked. Ticket 17's former edge on native scheduling (old 11) is deliberately not carried over as a blocker: reporting models the Externally Scheduled state from controlled adapter evidence and lights up with live evidence once ticket 12 lands. Reuse the follow-up link marker and `action_kind` introduced in ticket 07 (`preparation link-follow-up`, frozen into the Sent Record) rather than adding a parallel link model. The original ticket files were removed in this merge.

2026-09-14: Resolved through the public SmartMail boundary with the controlled adapter and controlled time (clock injected via the constructor, never internals). 48 new boundary tests: replies 17, follow-ups 21, reports 9, one integrated closed-loop scenario; ordinary suite 200 -> 248 passed with the same 5 skipped, netease163 extension peer suite unchanged at 11 passed. New tables `reply_associations`, `follow_up_rules`, `follow_up_actions`; new operations `ReplyOperations`, `FollowUpOperations`, `ReportingOperations`; terminal groups `reply`, `followup`, `report`. Association anchors only on a sent-thread subject or timing-after-send for a known Supervisor address — address alone, pre-send timing or unparseable timing all stay in operator review. A new Ordinary Reply after a follow-up Confirmation pauses with reason `new_associated_reply` before any request; Rewriting the follow-up keeps the linked Action kind and anchor and repoints the Action, while the reply still refuses re-confirmation. Per-Task message state follows the latest terminal Attempt so a failed follow-up is not hidden behind the recorded initial send; Externally Scheduled is modelled from controlled outbound evidence only. Outcomes, criterion mapping and limitations are in docs/ticket-11-validation.md. No live mailbox capability claimed; native scheduling remains ticket 12.

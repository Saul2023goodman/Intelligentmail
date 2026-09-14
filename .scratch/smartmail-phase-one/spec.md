# SmartMail Phase One: Supervisor Outreach Operations

Status: ready-for-agent
Labels: ready-for-agent

## Problem Statement

An education agency conducts high-volume personalized supervisor outreach on behalf of students. One operator works across many student mailboxes, supervisors, institutions, spreadsheets, draft documents, and attachments. Manual coordination produces inconsistent formatting, missing fields, misplaced internal notes, uncertain associations, duplicated outreach, and unreliable execution history. Late student revisions further complicate preparation and scheduled sending.

The operator needs a reliable operational workflow that removes repetitive preparation and coordination while retaining explicit control over sending and changes to external sending commitments. The first release must complete one supervisor-outreach workflow at full depth and produce a credible graduate-application portfolio artifact demonstrating process optimization, information management, workflow design, automation, and systems thinking.

## Solution

Provide SmartMail as a local application for one active operator on one machine. A functional terminal shell exposes inspection, correction, confirmation, execution, reconciliation, and reporting through a stable headless core boundary. Operators can open original materials, previews, and history in existing desktop applications.

SmartMail imports existing representative materials into an explicitly selected Campaign, applies supported deterministic rules, associates students and supervisors, prepares communications, and surfaces Exceptions. Normal preparation requires no separate human acceptance. Ready Preparation does not authorize sending: the operator explicitly confirms an immediate send or a Sending Plan, including exact message contents and execution details.

A dedicated Chrome/Edge browser extension operates the real 163.com Mailbox for execution and observation. It connects one operator-selected, authenticated tab to the local SmartMail core through a Native Messaging host and does not receive credentials or arbitrary commands. Native mailbox scheduling owns future execution once externally confirmed; it is not a local timer. The extension assists with repetitive mailbox work while preserving operator takeover, evidence-based outcomes, and reliable restart recovery. Unverified capabilities are disabled independently.

SmartMail retains source evidence, hidden Superseded Preparations, immutable Sent Records, and an Execution Ledger. Reconciliation supports duplicate detection, observed sending state, reply association, and follow-up eligibility. Operational reporting provides task-level drill-down. Concrete intake rules are determined during coding from representative materials rather than imposed as new input templates in advance.

## User Stories

1. As an Operator, I want to import existing spreadsheets, draft documents, and attachments, so that the team does not have to restructure its materials before using SmartMail.
2. As an Operator, I want to select a Campaign for each import, so that campaign membership is explicit.
3. As an Operator, I want predictable layout variations to be supported, so that reordered columns and common field aliases do not require manual coordination.
4. As an Operator, I want original Source Materials to remain available, so that I can inspect the evidence behind preparation.
5. As an Operator, I want an Outreach Task identified by Student, Supervisor, and Campaign, so that related communications stay together.
6. As an Operator, I want known addresses for one Supervisor to share an identity, so that address variations do not bypass duplicate checks.
7. As an Operator, I want deterministic Source Associations, so that content and attachments are connected to the correct Outreach Task.
8. As an Operator, I want field-specific Authoritative Sources, so that conflicting materials are handled consistently.
9. As an Operator, I want identity and recipient conflicts to block readiness, so that ambiguous records cannot proceed to sending.
10. As an Operator, I want missing values filled only from unambiguous authoritative evidence, so that automation does not invent information.
11. As an Operator, I want supported cleanup, substitution, normalization, and restructuring to happen automatically, so that routine preparation does not require approval.
12. As an Operator, I want Transformation Records and resulting content to be inspectable, so that I can understand automated changes.
13. As an Operator, I want unsupported inputs and unresolved transformations surfaced as Exceptions, so that uncertain handling is visible.
14. As an Operator, I want to correct fields and Source Associations within SmartMail, so that exported workbooks do not become a separate operational system.
15. As an Operator, I want required attachments matched automatically when reliable, so that repetitive file selection is reduced.
16. As an Operator, I want to select or import a missing attachment manually, so that I can resolve attachment Exceptions.
17. As an Operator, I want attachment contents preserved, so that preparation does not silently convert or modify documents.
18. As an Operator, I want readiness findings for each Preparation, so that I know what prevents execution.
19. As an Operator, I want local preparation without external draft creation, so that the mailbox is used for actual execution and scheduling rather than routine content work.
20. As an Operator, I want to inspect task details and open source files, message previews, and history from a terminal shell, so that phase one is usable without a frontend.
21. As an Operator, I want default deterministic Sending Plans, so that I do not manually assign every sending time.
22. As an Operator, I want configurable windows, timezones, spacing, and daily limits, so that plans reflect operational requirements.
23. As an Operator, I want to adjust a proposed Sending Plan before confirmation, so that I retain control over execution.
24. As an Operator, I want batch review of sender, recipient, subject, attachments, scheduled time, timezone, readiness, and full content, so that confirmation is informed.
25. As an Operator, I want explicit confirmation before immediate sending or activation of a schedule, so that automation cannot independently commit communications.
26. As an Operator, I want Confirmation bound to exact content and execution details, so that later changes do not inherit authorization.
27. As an Operator, I want confirmed batches to proceed without my constant presence, so that repetitive browser operations are automated.
28. As an Operator, I want native 163.com scheduling where verified, so that the mailbox can own sending at the planned time.
29. As an Operator, I want a blocking failure to pause the current Execution Flow, so that automation waits for my intervention.
30. As an Operator, I want local preparation, inspection, and reporting available during an execution pause, so that an interruption does not stop unrelated local work.
31. As an Operator, I want login, verification, and CAPTCHA interruptions handed to me, so that I can restore external access and continue.
32. As an Operator, I want Unknown Outcomes reconciled before another attempt, so that a lost confirmation does not cause a duplicate send.
33. As an Operator, I want an explicit reconcile-and-continue operation after Manual Takeover, so that completed manual work is observed before automation resumes.
34. As an Operator, I want valid confirmed work reconciled and resumed after restart, so that a crash does not force me to rebuild a batch.
35. As an Operator, I want expired sending times to require new confirmation, so that late recovery does not cause an unexpected immediate send.
36. As an Operator, I want newly discovered Blockers to stop execution despite prior Confirmation, so that conflicting evidence is respected.
37. As an Operator, I want content changes handled as a Rewrite, so that replaced preparation cannot retain its prior Confirmation.
38. As an Operator, I want Superseded Preparations hidden from active work but inspectable in history, so that current work stays clear without losing traceability.
39. As an Operator, I want active execution stopped or resolved before a Rewrite, so that the content of an unresolved attempt is not replaced underneath it.
40. As an Operator, I want to prepare a replacement locally while an existing external schedule remains visible and active, so that preparation does not silently cancel confirmed work.
41. As an Operator, I want confirmed Scheduled Replacement to verify removal of the original external scheduled draft first, so that both versions are not knowingly left scheduled.
42. As an Operator, I want replacement failure after removal to pause without restoring the original automatically, so that the actual external state is clear.
43. As an Operator, I want an original message that sends during cancellation to become Sent and frozen, so that any replacement is reconsidered as a new linked communication.
44. As an Operator, I want Cancellation, Recall, and other changes to external sending state under explicit operator control, so that assistance does not become unrestricted external action.
45. As an Operator, I want Recall exposed only where supported and eligible, so that unsupported withdrawal is not promised.
46. As an Operator, I want mailbox-confirmed sending marked Sent regardless of delivery or reading, so that sending status has a precise meaning.
47. As an Operator, I want immutable sent content and execution history, so that history and duplicate detection remain reliable.
48. As an Operator, I want direct mailbox changes recorded without automatic restoration, so that SmartMail reflects what actually happened.
49. As an Operator, I want externally altered content to lack inherited SmartMail Confirmation, so that old authorization is not misapplied.
50. As an Operator, I want Reconciliation before confirmed execution, after uncertainty, on unfinished restart, and on manual refresh, so that execution uses available current evidence.
51. As an Operator, I want optional periodic checks, so that observed mailbox state can stay current while SmartMail is running.
52. As an Operator, I want mailbox history and imported records used in duplicate checks, so that previous outreach is accounted for.
53. As an Operator, I want Repeat Execution blocked and repeated initial outreach flagged within the same Outreach Task, so that accidental repetition is prevented.
54. As an Operator, I want different Students contacting one Supervisor treated separately, so that legitimate outreach is not labeled duplicate solely by recipient.
55. As an Operator, I want No Duplicate Found qualified by Evidence Coverage, so that incomplete history is represented honestly without automatically blocking work.
56. As an Operator, I want only reliably Associated Replies to affect follow-up eligibility, so that ambiguous conversations require review.
57. As an Operator, I want an Ordinary Reply to stop no-reply follow-up eligibility without semantic classification, so that existing conversations do not receive inappropriate proposed follow-ups.
58. As an Operator, I want Recognized Automatic Replies recorded separately, so that they do not by themselves stop no-reply follow-up eligibility.
59. As an Operator, I want configurable follow-up timing and count limits, so that eligibility follows campaign rules.
60. As an Operator, I want follow-ups automatically prepared when a supported rule or template exists and otherwise marked due for preparation, so that missing content does not produce invented communications.
61. As an Operator, I want each Follow-up Action separately linked and confirmed, so that eligibility never becomes permission to send.
62. As an Operator, I want reporting by Student, Supervisor or Institution, Campaign, Mailbox, message status, duplicate status, Exceptions, and follow-up eligibility, so that I can locate unfinished and completed work.
63. As an Operator, I want report drill-down to tasks and evidence, so that summary counts are actionable.
64. As an Operator, I want core records and evidence to survive a crash, so that recovery does not depend on the mailbox being the primary system of record.
65. As an Operator, I want unsupported platform capabilities disabled individually, so that verified capabilities remain usable.
66. As the project owner, I want a representative real-work pilot with documented scenario outcomes, so that the artifact demonstrates reliable operational automation and intentional human control.

## Implementation Decisions

### Delivery and boundaries

- The implementation is a local Python application with a persisted SQLite store and an existing behavioral test suite. This specification remains the product scope; current implementation and validation details live in the repository documentation.
- Use one headless core with a stable command/query boundary and a terminal shell. The boundary supports imports, inspection, corrections, Rewrite, planning, Confirmation, execution, Reconciliation, intervention, and reporting. The extension popup is a connection control, not a replacement for the headless SmartMail operator interface.
- Keep preparation, workflow rules, readiness, Confirmation, history, and reporting independent of the browser adapter. The current 163 adapter is a dedicated extension transport; additional platforms can attach through the same capability boundary later.
- Use deterministic code only: explicit rules, matching, validation, state transitions, scheduling, and statistics. No AI, semantic inference, or inferred content. Unresolved evidence becomes an Exception.
- One machine, one active Operator, and one local store. Persist source evidence, preparations, associations, confirmations, workflow state, execution evidence, and immutable Sent Records within SmartMail.
- Use a Manifest V3 Chrome/Edge extension plus Native Messaging for the 163 webmail seam. The native host has a bounded, versioned, single-delivery protocol and a durable transport queue separate from the SmartMail business store. The extension is explicitly connected to one authenticated tab; it has no cookies, debugger or arbitrary-site permission. The previous Playwright CLI path is not a production fallback. Browser layout selectors and live capability claims remain acceptance-dependent.

### Intake, readiness, and content lifecycle

- Determine concrete Supported Intake Patterns and field-specific precedence during coding using representative existing materials. Include justified nearby variations such as column reordering, common aliases, optional fields, and similar document layouts. Do not require up-front source restructuring or claim support for arbitrary documents.
- Imports require an explicitly selected Campaign. Outreach Task identity is Student × Supervisor × Campaign; known email addresses map to the same Supervisor identity.
- Preserve original Source Materials and inspectable Transformation Records. Normal supported preparation is automatic, including reliable cleanup, normalization, substitution, and restructuring, without routine acceptance or material-change approval gates before execution confirmation.
- Validate the supported required fields and associations, including sender, recipients, subject, body, and required attachments. Identity or recipient conflicts block readiness; missing values may be filled only from an unambiguous Authoritative Source. Unsupported internal-note separation or other transformations must surface an Exception rather than invent a result.
- Corrections belong to the core workflow and terminal shell. Attachment Exceptions can be resolved by selecting or importing files. Automatic attachment conversion, merging, and content modification are excluded.
- Rewrite produces fresh Preparation identity and invalidates prior Confirmation. Prior content and associations become hidden, inspectable Superseded Preparations; delete-and-rewrite does not mean erasing evidence.
- Stop or resolve an active Execution Attempt before rewriting its Preparation. Sent content is never rewritten: subsequent communication is a new linked Communication Action.

### Confirmation and planning

- Readiness and authority are separate. Every immediate send and active schedule requires explicit operator Confirmation; there is no standing autonomous-send delegation.
- Offer deterministic defaults with configurable windows, timezone, spacing, and daily limits. Operators may adjust proposals before confirming them.
- Batch review exposes sender, recipient, subject, attachments, scheduled time and timezone, readiness findings, and access to full content. Confirmation binds exact message content, attachment contents, and execution details; a same-path attachment replacement cannot change confirmed bytes silently.
- Changes to confirmed content or schedule require renewed Confirmation. A newly discovered Blocker pauses the current Execution Flow even when Confirmation exists.
- Draft preparation stays local. Do not create external mailbox drafts as a preparation or synchronization step. Opening and filling the mailbox compose interface occurs as part of ready, operator-controlled sending or scheduling; mailbox observation for Reconciliation remains supported.

### Browser execution and scheduling

- The dedicated extension operates the real 163.com webpage in an explicitly selected authenticated tab. It is the intended execution channel, including native scheduling and supported cancellation or Recall, rather than a fallback for mail protocols.
- The Native Messaging protocol supports only connection, bounded observation/submit commands, attachment-byte chunks, one submission permit and result evidence. Reconnection never replays a claimed command; the host rechecks persisted Confirmation before permitting the single submit.
- The extension exposes capability availability and evidence-bearing observations, including Sent, Externally Scheduled, failed or not completed where established, and Unknown Outcome. UI interaction alone is not proof that the external operation occurred.
- Once confirmed externally, native scheduling is owned by the mailbox. Verify offline behavior with controlled acceptance tests before relying on it. Do not silently substitute local timed sending for an unavailable native scheduling capability.
- Operator presence is not required throughout a confirmed batch. Authentication, verification, CAPTCHA, ambiguous outcomes, tab/document changes, connection loss or blocking execution failures pause the current Execution Flow for intervention. Local preparation and reporting remain available.
- A local pause does not cancel existing external schedules. Keep outstanding externally scheduled commitments visible.
- Explicit operator control is required for actions that create or change actual sending commitments, including cancellation, deletion of scheduled drafts, replacement, and Recall. Automatic local preparation does not grant that authority.

### Scheduled Replacement and external races

- A local replacement may be prepared while the original external schedule remains active. Display that fact prominently; a new import or Rewrite alone does not cancel it.
- On confirmed Scheduled Replacement, remove the original external scheduled draft and verify removal before submitting the replacement. Do not submit while removal remains uncertain.
- If removal succeeds and replacement submission fails, pause and report the observed state. Do not automatically restore the original. If replacement submission is uncertain, record Unknown Outcome and reconcile it rather than asserting that no schedule exists.
- If the original was already Sent, freeze its Sent Record and pause replacement. Any further communication requires a new linked action and renewed Confirmation.
- Recall is a separate conditional operation, not a general undo for institutional outreach. Keep its observed outcome separate from the historical fact that a message was Sent.

### Reconciliation, interruption, and persistence

- Reconcile before confirmed execution, after uncertain actions, after restart with unfinished execution, and on manual refresh. Periodic observation may be configurable.
- Persist enough intent, confirmation, attempt, and outcome evidence to recover across interruption before, during, and after an external operation. Unknown Outcome must not be converted into failure solely because confirmation was lost.
- Do not blindly retry. Inspect evidence first; resume or retry only when reconciled state and still-valid Confirmation permit it. Unresolved outcomes require operator intervention.
- Manual Takeover returns through an explicit reconcile-and-continue operation. An acknowledgment alone does not establish Sent.
- After restart, valid confirmed work may resume automatically following Reconciliation. A previously blocked flow still requires its intervention, and expired sending times require a newly confirmed time rather than immediate sending.
- Record direct external changes without restoring the prior plan automatically. Externally changed content does not inherit SmartMail Confirmation.
- Mailbox confirmation establishes Sent regardless of delivery or reading. Scheduled time elapsing does not establish Sent. Retain immutable sent content and execution records; later observations are additional history rather than edits to sent content.
- Crash/restart recovery is required. Separate disaster-recovery infrastructure is not part of phase one.

### Duplicates, replies, and reporting

- Use available mailbox history and imported records. Deterministic matches establish existing sends; genuinely ambiguous matches require review. No match produces No Duplicate Found with Evidence Coverage recorded; incomplete history alone is not a Blocker.
- Prevent Repeat Execution of an already executed action. Flag repeated initial outreach for the same Student and Supervisor within a Campaign. Distinct Students are not duplicates merely because they share a Supervisor; authorized Follow-up Actions remain separately linked.
- Only reliably Associated Replies affect eligibility. Ambiguous associations require review. Ordinary Replies stop no-reply follow-up eligibility without classifying interest, rejection, or document requests.
- Recognized Automatic Replies use supported deterministic detection, remain separately recorded, and do not themselves stop no-reply eligibility. Out-of-office return-date adjustment is not core phase-one follow-up logic.
- Follow-up timing and maximum count are configurable. A supported rule or template may create Preparation automatically; otherwise mark Follow-up Due for operator preparation. Every follow-up requires sending Confirmation.
- Reporting covers the agreed operational dimensions with task and evidence drill-down. Distinguish local plans, external schedules, Sent, failure observations, and Unknown Outcomes. Timing metrics and semantic-outcome funnels are not priorities.

## Testing Decisions

- Primary testing seam, confirmed by the user: the stable core command/query boundary used by the terminal shell. Exercise complete workflows against persisted local state and a controlled mailbox adapter, asserting operator-visible results, authorized external requests, ledger evidence, and recovery behavior rather than internal helper calls or storage layout.
- Supplement that seam with controlled extension-peer tests, a local browser smoke test for packaged scripts, and controlled real-extension acceptance for each enabled 163.com capability. Simulated adapter or fixture results cannot establish actual platform support. Keep ordinary workflow tests independent of live accounts.
- There are no existing application tests or prior test seams in this repository. The confirmed boundary follows the agreed headless-core design.
- The scenarios cover intake/preparation, Confirmation and planning, execution and persistence, Reconciliation, duplicate detection, replies/follow-ups, and operational reporting through the same high-level boundary. Use controllable time and explicit external evidence for reproducible scheduling and failure cases.
- Establish a representative case set before evaluating the pilot. During coding, turn source samples and supported variants into acceptance fixtures with expected associations, prepared content, and Exceptions; define unsupported cases explicitly. Do not use test coverage as a claim of correctness for arbitrary inputs.

Required behavioral scenarios:

1. Normal source intake through Ready Preparation, explicit immediate-send Confirmation, mailbox-confirmed Sent, immutable Sent Record, and report drill-down.
2. Supported column aliases, reorderings, optional fields, and document variations produce the intended results without requiring source restructuring.
3. Ambiguous student/supervisor association, conflicting recipient information, missing required values, and missing attachments block readiness and are resolvable in the shell.
4. Supported transformations preserve source evidence and explain results; unsupported note separation or content handling raises an Exception rather than silently inventing text.
5. Local preparation causes no external draft writes. Unconfirmed actions cause no send or schedule commitment.
6. Batch Confirmation binds exact Preparation, attachment contents, and schedule; Rewrite or changed execution details invalidate it.
7. Default and adjusted schedules honor configured windows, timezone, spacing, and daily limits; impossible proposals are surfaced instead of silently violating constraints.
8. Native scheduling creates an observed external scheduled draft and sends with the local application offline where the capability is enabled. Clock passage alone does not mark it Sent.
9. A blocking failure pauses the current Execution Flow, leaving local work usable and outstanding external schedules visible.
10. Authentication interruption allows operator completion and controlled continuation without duplicate execution.
11. Lost confirmation after a send or schedule creates Unknown Outcome; positive reconciliation avoids a duplicate attempt, and unresolved evidence requests intervention.
12. Crash before submission, during submission, and after external success but before local outcome recording recovers without an unconfirmed send or blind retry.
13. Restart resumes still-valid confirmed work after Reconciliation; a missed sending time requires new Confirmation and a pre-existing blocking pause is not bypassed.
14. Manual Takeover followed by reconcile-and-continue observes the actual outcome before further execution.
15. A new duplicate, associated reply relevant to the action, or conflicting identity discovered after Confirmation blocks the affected action and pauses execution.
16. Superseded Preparation is hidden from active work, inspectable in history, and cannot transfer its Confirmation to fresh Preparation.
17. An active Execution Attempt is stopped or resolved before Rewrite.
18. Local replacement preparation leaves the original external schedule active until operator-confirmed cancellation or replacement.
19. Scheduled Replacement verifies removal before submitting new content; failed or uncertain removal prevents submission.
20. Removal followed by failed or uncertain replacement submission pauses with accurate evidence and no automatic restoration of the original.
21. Original sending during cancellation produces a frozen Sent Record and requires a new linked, confirmed action for further communication.
22. Direct mailbox edits or cancellation are observed without restoration or inherited Confirmation.
23. Available historical sends and imported records detect duplicates across known supervisor addresses; unrelated Students remain distinct; incomplete coverage with no match remains nonblocking.
24. Reliably associated Ordinary Replies stop eligibility; Recognized Automatic Replies do not; ambiguous associations require review.
25. Follow-up rules respect timing and count limits, create linked Preparation only where supported, and never send without Confirmation.
26. Reports distinguish operational states and drill down to the matching tasks and evidence.
27. Unverified platform capabilities are disabled independently; Recall is attempted only through confirmed, supported operations and is never treated as guaranteed withdrawal.

Completion requires correct handling of supported representative cases, no unconfirmed sends, no blind retries, traceable versions and outcomes, and reliable interruption recovery. The pilot must include real execution of enabled capabilities. Manual touches and operator time may be recorded as secondary efficiency evidence; intentional operator control is not a failure and these metrics do not determine completion.

## Out of Scope

- AI, probabilistic semantic inference, invented content, and semantic classification of ordinary replies.
- A frontend or final visual interface; an exported exception workbook as the main operator interface.
- Standing autonomous-send delegation or elimination of intentional operator Confirmation.
- Additional workflow types or additional production mailbox adapters beyond 163.com.
- Automatic attachment conversion, merging, or content modification.
- In-place replacement of sent messages or erasure of inspectable superseded history.
- Named ownership, assignment, handoff, permission roles, workload balancing, or concurrent multi-operator access.
- Separate disaster-recovery infrastructure and guarantees against machine or disk loss.
- Guaranteed delivery, reading, universal Recall, or unverified native platform behavior.
- Prioritizing timing analytics, strategy comparisons, semantic-outcome funnels, or out-of-office return-date scheduling over the operational workflow.
- Predefining concrete intake layouts before coding and sample inspection.

## Further Notes

- This specification synthesizes the final confirmed conversation decisions. They supersede earlier proposals for standing delegation, workbook-based Exceptions, physical deletion of old preparation, continued batch execution after blockers, and mandatory restart reapproval.
- The domain glossary is the canonical vocabulary. This document supplies behavioral scope and acceptance criteria rather than adding implementation details to that glossary.
- Concrete intake patterns, precedence rules, supported transformations, and reply-association/detection evidence must be established and tested during implementation. Representative materials have not yet been supplied in the workspace; that is an implementation dependency, not a reason to reopen the agreed product scope.
- Real-page navigation, extension account identification, observable identifiers, schedule removal races, sending-time interpretation, offline scheduling, and history coverage need controlled extension verification. The retired Playwright acceptance is historical evidence only. Native scheduling and extension immediate sending must not be presented as verified solely because they appear in this specification.
- The portfolio narrative should explain the process, information ownership, exception handling, operator authority, and measured scenario outcomes. Do not claim guaranteed correctness beyond the supported and validated handling boundary.

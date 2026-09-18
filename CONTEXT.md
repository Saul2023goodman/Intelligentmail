# SmartMail Communication Operations

SmartMail organizes supervisor outreach on behalf of students, from source materials and preparation through operator-confirmed execution, reconciliation, and follow-up. This glossary defines the language of that work.

## Language

### Participants and scope

**Student**:
The person on whose behalf outreach is conducted and to whom the sending mailbox belongs.
_Avoid_: Customer, sender account

**Supervisor**:
The intended academic contact, whose identity may include multiple known email addresses.
_Avoid_: Email address as identity

**Institution**:
The organization associated with a supervisor in the outreach records.

**Mailbox**:
A student's external email mailbox, through which communications are sent and received.
_Avoid_: Student, operator account

**Operator**:
The person who inspects and corrects work, confirms external actions, and resolves interruptions.
_Avoid_: Approver role, delegated autonomous sender

**Campaign**:
An explicitly selected grouping of outreach work that supplies the scope for duplicate checks, follow-up rules, and reporting.
_Avoid_: Inferred campaign

**Outreach Task**:
The work associated with one student, one supervisor, and one campaign, including its initial outreach and linked subsequent communications.
_Avoid_: Email, draft, sending batch

### Materials and preparation

**Source Material**:
An original imported spreadsheet, document, attachment, or record available as evidence for outreach preparation.
_Avoid_: Prepared message, current truth

**Source Association**:
An explicit relationship connecting source material or a source value to an outreach task or part of its preparation.
_Avoid_: Filename guess

**Authoritative Source**:
The source designated to govern a particular field under the supported precedence rules.
_Avoid_: Globally authoritative file

**Supported Intake Pattern**:
A recognized arrangement of source information for which deterministic extraction and association rules are defined, including supported variations of representative materials.
_Avoid_: Arbitrary document understanding

**Transformation Record**:
Evidence of a supported preparation change, identifying its source, result, and the rule applied.
_Avoid_: Inferred rewrite

**Communication Action**:
One intended outbound communication within an outreach task, whether initial outreach, a follow-up, or another linked communication.
_Avoid_: Outreach task, execution attempt

**Preparation**:
The local working content and source associations for a communication action, including its sender, recipients, subject, body, and attachments.
_Avoid_: External draft, sent message

**Ready Preparation**:
A preparation satisfying the supported validation and association rules with no unresolved blocking issue.
_Avoid_: Approved message, authorized send

**Superseded Preparation**:
A preparation removed from active work by a rewrite but retained as inspectable history.
_Avoid_: Erased history, active version

**Rewrite**:
Replacement of a preparation with a fresh preparation rather than an in-place modification; the prior preparation is superseded and its confirmation does not transfer.
_Avoid_: Hard deletion, editing a sent message

**Exception**:
A condition requiring operator resolution because supported handling cannot proceed reliably, such as an ambiguous association or missing required attachment.
_Avoid_: Routine sending confirmation

**Blocker**:
An unresolved condition that prevents an affected preparation or action from proceeding, including conflicting evidence discovered after confirmation.
_Avoid_: Warning that can be silently ignored

### Plans and authority

**Sending Plan**:
A proposed set of communication actions and their immediate or scheduled execution details, available for operator adjustment and batch confirmation.
_Avoid_: External schedule, active authorization

**Confirmation**:
An explicit operator authorization bound to an exact communication preparation and its execution details, or to a specified external cancellation or replacement operation.
_Avoid_: Standing send delegation, readiness, inherited approval

**Confirmed Action**:
An action with applicable operator confirmation whose content and execution conditions still hold and for which no newly discovered blocker prevents execution.
_Avoid_: Unconditionally executable action

**External Scheduled Draft**:
The message held by the external mailbox for a scheduled send, distinct from SmartMail's local preparation.
_Avoid_: Local draft, local timer

**Mailbox Observation**:
A retained, read-only account of messages and coverage obtained from a Mailbox at a particular observation time. It is evidence for Reconciliation and duplicate detection; it does not replace a local Preparation or authorize an external action.
_Avoid_: Mailbox mirror, external draft, proof of delivery

**Scheduled Replacement**:
An operator-confirmed operation that removes an existing external scheduled draft before submitting its replacement, with removal verified before the new submission.
_Avoid_: Atomic swap, editing a sent message

**Cancellation**:
An operator-controlled removal of a pending external sending commitment; a request alone does not establish that cancellation occurred.
_Avoid_: Local pause, recall

**Recall**:
A platform-dependent attempt to withdraw an already sent message under the platform's eligibility conditions, with its own reported outcome.
_Avoid_: Guaranteed undo, cancellation of a pending schedule

### Execution and evidence

**Execution Flow**:
The currently progressing sequence of confirmed external operations, paused for operator intervention when a blocking execution failure occurs.
_Avoid_: All local work, mailbox-wide sending suspension

**Execution Attempt**:
One attempt to carry out a confirmed external operation, whose outcome is established from available external evidence.
_Avoid_: Communication action, proof of sending

**Execution Run**:
One operator-initiated, ordered execution of a set of active Confirmations belonging to a single Campaign and a single execution kind, retaining what was requested, what was reached, what was observed, and what was never reached.
_Avoid_: Batch job, automatic retry, sending session

**Execution Run Item**:
One Confirmation's place in an Execution Run, carrying its own observed outcome, including the record that it was never reached.
_Avoid_: Queue entry, retry slot, sending receipt

**Externally Scheduled**:
The state in which the external mailbox confirms that a message is scheduled for sending.
_Avoid_: Sent, locally planned

**Sent**:
The state established when the external mailbox confirms that a message was sent, regardless of delivery or reading status.
_Avoid_: Delivered, read, scheduled time elapsed

**Sent Record**:
The frozen, immutable content and execution record of a sent message, retained for history, reconciliation, and duplicate detection.
_Avoid_: Editable preparation, replaceable message

**Unknown Outcome**:
An execution result for which available evidence does not reliably establish whether the attempted external operation occurred.
_Avoid_: Failed send, safe to retry

**Reconciliation**:
Comparison of SmartMail's records with available mailbox evidence and imported records to establish observed outcomes and discrepancies.
_Avoid_: Restoring the old plan, granting confirmation to external edits

**Draft Adjustment**:
An operator correction to the active local Preparation, such as its recipient or subject, followed by renewed validation. A change to message content invalidates the applicable Confirmation; replacing the body creates a fresh Preparation through Rewrite and retains the prior version.
_Avoid_: Editing a Sent Record, editing an external draft, silent overwrite

**Execution Ledger**:
The retained history of confirmations, attempts, observed outcomes, and reconciliation findings for external operations.
_Avoid_: Sent folder, editable current status

**Manual Takeover**:
Operator handling of an interrupted external operation, followed by explicit reconciliation and continuation of the execution flow.
_Avoid_: Operator acknowledgment as proof of sending

### Duplicates, replies, and follow-ups

**Repeat Execution**:
Another execution of the same already executed communication action, which must be prevented.
_Avoid_: Authorized follow-up

**Duplicate Suspicion**:
Evidence of potentially repeated initial outreach for the same student and supervisor within a campaign, requiring resolution before affected execution.
_Avoid_: Different students contacting the same supervisor

**Evidence Coverage**:
The sources and available history inspected for reconciliation or duplicate detection.
_Avoid_: Complete mailbox history by assumption

**No Duplicate Found**:
The finding that no matching prior send was identified within the available evidence coverage.
_Avoid_: Proof that no prior send exists

**Associated Reply**:
A received message reliably linked to an outreach task through supported evidence; ambiguous links remain subject to review.
_Avoid_: Guessed conversation match

**Ordinary Reply**:
An associated reply treated as an ordinary response rather than a recognized automatic reply, without classification of its conversational meaning.
_Avoid_: Interested, rejected, confirmed human authorship

**Recognized Automatic Reply**:
An associated reply identified by supported deterministic rules as machine-generated, recorded separately without itself stopping no-reply follow-up eligibility.
_Avoid_: Ordinary reply, semantic response classification

**Follow-up Rule**:
A supported campaign rule defining follow-up timing and count limits, optionally paired with a template for automatic preparation. A Rule by itself describes eligibility; only an enabled Follow-up Automation Confirmation authorizes unattended execution.
_Avoid_: Per-message send instruction, inferred authorization

**Follow-up Automation Confirmation**:
An operator's standing authorization of one exact version of a Campaign's Follow-up Rule, content templates, and timing configuration. It permits SmartMail to derive exact per-action Confirmations while that version is enabled; it never bypasses reply, duplicate, readiness, mailbox-capability, or paused-flow checks.
_Avoid_: Unbounded send permission, implicit approval, ordinary per-action Confirmation

**Follow-up Due**:
The condition in which an outreach task meets its follow-up rules and has no reliably associated ordinary reply preventing eligibility.
_Avoid_: Confirmed follow-up, permission to send

**Follow-up Action**:
A separate communication action linked to earlier outreach, prepared from a supported rule or template or by an operator. It requires an exact per-action Confirmation, which may be derived from an enabled Follow-up Automation Confirmation instead of repeated operator review.
_Avoid_: Duplicate initial outreach, resend of the same action

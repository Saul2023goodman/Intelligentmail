# Supported Mailbox Observation Pattern 06

This pattern observes a real 163.com Mailbox through the dedicated SmartMail
Chrome/Edge extension. The extension runs in the operator's explicitly selected,
authenticated mailbox tab and connects to the local application through the
versioned Native Messaging host. It does not launch a browser or receive mailbox
credentials. This pattern covers read-only observation and Reconciliation; it
does not verify immediate sending, native scheduling, cancellation or Recall.

## Operator-assisted connection

Install and register the extension using [the migration guide](browser-extension-pivot.md),
then open `https://mail.163.com` and log in in the intended tab. The extension popup
must show the same address as the Student's registered Mailbox before a refresh is
accepted:

```powershell
python -m smartmail.bridge --home .smartmail status
python -m smartmail --home .smartmail --adapter 163-extension mailbox capabilities
python -m smartmail --home .smartmail --adapter 163-extension mailbox refresh --student STUDENT_ID
```

Connection and authentication are operator actions. If login, verification or a
CAPTCHA is required, or the tab/document is reloaded, the extension reports an
interruption and SmartMail persists it. Reconnect the selected tab after resolving
the interruption. A tab logged into another address is persisted as `wrong_mailbox`
and its message rows are discarded.

## Read-only observation boundary

After the extension has connected, refresh performs only these actions:

1. Confirm the authenticated account matches the intended Mailbox.
2. Discover the five recognized built-in folders from the visible DOM: Inbox,
   Drafts, Sent, Deleted and Spam.
3. Enumerate canonical message IDs in bounded pages and read header, MIME-part and
   attachment metadata for each ID.
4. Return direction, folder, canonical ID, counterpart, subject, observed time,
   mailbox status, list evidence and metadata-detail evidence.

The extension never opens Compose during observation, fetches message-body HTML,
edits a draft, sends, schedules, deletes, cancels or recalls. Draft, Deleted and
Spam rows remain explicit non-delivery states. Sent is established only by positive
platform metadata; otherwise the row is `ambiguous`.

Each folder retains its reported total, enumerated-ID count, page and detail
attempts, failures and completeness. Supported-scope completeness is separate from
whole-mailbox completeness: custom folders, virtual views and bodies are outside
the declared scope. A missing local match therefore remains qualified by the
available Evidence Coverage.

## Persistence and Reconciliation

Every refresh persists an immutable Mailbox observation run with the Student,
Mailbox, extension adapter, capability snapshot, interruption detail, Evidence
Coverage and per-message evidence. The same operation creates a Reconciliation.

An exact platform reference can link an outbound observation to one local Sent
Record. Exact recipient and subject can link it to one unresolved Execution Attempt
when no Sent Record exists. Multiple candidates remain ambiguous; an unmatched row
remains unassociated. Inbox replies are not guessed into an Outreach Task by this
pattern. `local_state_changed` remains false: Mailbox evidence is retained for
inspection and does not rewrite the Execution Ledger or resolve an attempt on its
own.

## Independent capabilities

The extension adapter reports each platform capability separately. A connected
extension makes read history available for this observation scope, but it does not
make that capability live-verified. Immediate sending is disabled unless the
operator explicitly enables extension acceptance mode, and remains unverified
until real-extension acceptance is recorded. Native scheduling, schedule
cancellation and Recall stay disabled. Reading never grants a state-changing
capability.

Controlled `observations` fixtures and the extension bridge tests exercise this
same command/query boundary without a live account. Simulated results do not count
as platform verification. The earlier Playwright-based acceptance is retained only
as historical evidence in [Ticket 06 validation](ticket-06-validation.md); it does
not establish the current extension's verification state.

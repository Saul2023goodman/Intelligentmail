# Supported Immediate Send Pattern 09

This pattern sends one operator-confirmed immediate Communication Action through
the dedicated 163.com browser extension. Preparation, readiness, Confirmation,
duplicate checks, Execution Flow and the immutable Sent Record remain SmartMail
responsibilities. The extension supplies the authenticated webmail page and the
final external evidence. It does not provide native scheduling, cancellation or
Recall.

## Exact confirmed snapshot

Core execution creates a durable command only for an active Confirmation and
Execution Attempt. The command contains the exact sender, recipient, subject, body,
attachment descriptors and Confirmation binding. Confirmed attachment bytes are
transferred to the Native Messaging host in bounded chunks; no browser-visible
operation receives an arbitrary local path.

The host claims a command once. Reconnection does not replay a claimed command,
and a busy extension heartbeat does not claim another one. A command expires after
its deadline. Before granting its single submission permit, the host rechecks the
persisted Confirmation, preparation digests, readiness Blockers, Execution Flow,
attempt identity, execution kind and existing Sent Records.

## Operator connection

```powershell
python -m smartmail.bridge --home .smartmail status
python -m smartmail --home .smartmail --adapter 163-extension mailbox capabilities
python -m smartmail --home .smartmail confirmation review PREPARATION_ID
python -m smartmail --home .smartmail confirmation confirm PREPARATION_ID
python -m smartmail --home .smartmail --adapter 163-extension --enable-extension-send execution run CONFIRMATION_ID
```

The extension popup must be connected to the authenticated Mailbox belonging to
the selected Student. Login, verification and CAPTCHA are completed by the
operator in that tab. If the tab changes account, reloads, closes, or loses the
Native Messaging connection, the action pauses and must be reconciled. The send
flag is an explicit acceptance switch; it does not mark the capability verified.

## Submission sequence

1. Verify the command deadline and matching authenticated Mailbox.
2. Read each confirmed attachment chunk, validate its byte count and SHA-256, and
   create an in-memory `File` object in the extension.
3. Require one supported in-page Compose control and exactly one unambiguous
   recipient, subject and message editor. Cross-origin or ambiguous editors are
   refused.
4. Fill the exact confirmed values, set the confirmed files, and wait for an
   explicit upload-complete state. The extension does not accept dialogs, alter
   content, or perform a second submit.
5. Recheck the account, recipient chips, empty CC/BCC fields, subject, body and
   attachment names/sizes. Recheck the command deadline and consume the one host
   submission permit.
6. Click Send once. A navigation, disconnect or exception after that click is
   `unknown`; it is never retried automatically.
7. Enumerate the Sent folder and require one new canonical ID with positive send
   status, the exact sender, recipient and subject, and a timestamp within the
   submission window. Only that evidence returns `sent`.

## Evidence and recovery

An old same-subject message, a click, a toast, a dialog, an upload filename or a
timeout is not Sent. Zero or multiple candidate rows return `unknown`. SmartMail
persists the Execution Attempt and pauses the current Execution Flow. The operator
uses `execution takeover` and `execution reconcile-and-continue` after inspecting
the mailbox; the extension never retries an uncertain submission.

A `sent` result freezes the exact content, attachment bytes and platform reference
in an immutable Sent Record and consumes the Confirmation. `failed`,
`authentication_required` and `unknown` leave the Confirmation available for the
operator's explicit resolution. A connected extension does not authorize a
Sending Plan or any external cancellation.

## Capability independence and validation

Immediate sending remains separate from read history, native scheduling, schedule
cancellation and Recall. The old Playwright path is removed from the product and
its real-account result is historical only; see [the pivot guide](browser-extension-pivot.md)
and [the historical Ticket 09 validation](ticket-09-validation.md). Current
extension behavior is covered by Python bridge/adapter tests, Node protocol tests,
and the optional local browser smoke test under `extensions/netease163/tests/`.

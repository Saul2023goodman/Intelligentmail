# Supported Immediate Send Pattern 09

Ticket 09 enables operator-confirmed immediate sending through the real 163.com compose interface at the same core command/query boundary used by the terminal shell. It builds on the Confirmation and Execution Ledger of earlier tickets and adds a live `immediate_send` capability; it does not verify or enable scheduling, cancellation or Recall.

## Exact confirmed snapshot

External submission is driven only by a Confirmation. The adapter receives the exact confirmed sender, recipient, subject, body and attachment snapshot, and nothing else. Core execution materializes the confirmed attachment bytes to private files, hands them to the adapter boundary, and removes them once the single submission returns, so the persisted Execution Ledger request is never polluted with local paths.

## Live browser boundary

```powershell
python -m smartmail --adapter 163-browser --browser-session smartmail-163 confirmation confirm PREPARATION_ID
python -m smartmail --adapter 163-browser --browser-session smartmail-163 execution run CONFIRMATION_ID
```

The adapter uses a named Playwright CLI session and a **persistent** user-data directory (`.smartmail/browser-163`, override with `SMARTMAIL_BROWSER_PROFILE`). Playwright's default context is incognito-like and keeps cookies only in memory, so a persistent profile is required for a login that survives daemon restarts. If the session is not open the adapter opens the headed browser and returns `authentication_required`; the operator completes login, verification or CAPTCHA and runs the command again. SmartMail neither receives nor stores credentials.

## Submission sequence

1. Reach the authenticated webmail page for the named session and confirm the logged-in address matches the confirmed sender.
2. Attach a dialog handler to the page and every context page. A **native** alert/confirm left open blocks the CLI's evaluation context for *every* later command in that session, so dialogs are accepted as they appear and their text is recorded in the outcome evidence.
3. Open the compose interface (the label matches as "写 信" after whitespace normalization).
4. Fill the confirmed recipient (`.nui-editableAddr-ipt`, committed as a chip), subject (`input[id$="_subjectInput"]`) and body, then attach the confirmed files and wait for each upload to register. The rich-text body's `contenteditable` lives in an unnamed iframe that initialises **after** the rest of the form, so the payload polls the frame list for it (up to 25 s) rather than sampling once, with a hidden plain-text `textarea.APP-editor-textarea` fallback.
5. **Guard:** refuse to submit unless the confirmed recipient and subject are present in the compose header.
6. Submit once. 163 raises a promotional "智能优化您的英文邮件" modal on the first submit that silently blocks the send; the adapter dismisses that prompt and completes the blocked submission. A visible validation error is recorded as `failed` rather than retried.
7. Return the session to the mailbox so later read-only observations see the folder tree.

## Evidence-based Sent

The adapter reports `sent` only when the Sent folder confirms the message, using `mbox:listMessages` plus a metadata-only `mbox:readMessage`, within an observation window. The window parses the server-local `sentDate`, so an earlier identical subject cannot produce a false match. When the message is not confirmed the outcome is `unknown`, never `sent`. Confirmed sending creates an immutable Sent Record (frozen content, attachment bytes and platform reference) and consumes the Confirmation; `failed`, `unknown` and `authentication_required` pause the Execution Flow for reconciliation or operator resolution.

## Capability independence

`immediate_send` is enabled and reported on its own, with `read_history` verified earlier and `native_scheduling`, `schedule_cancellation` and `recall` left disabled with an explicit basis. Verifying immediate sending never authorizes a scheduled or state-changing operation.

The controlled adapter still provides deterministic `sent`, `failed`, `unknown` and `authentication_required` fixtures for repeatable boundary tests; the live adapter is exercised separately in controlled live acceptance. See [validation](ticket-09-validation.md).

# 09: Execute confirmed immediate sends in 163.com

Status: resolved
Labels: implemented
Current validation: dedicated-extension live acceptance pending; sending disabled by default
Blocked by: 07, 08

**What to build:** Execute operator-confirmed immediate sending through the dedicated 163.com extension with evidence-based outcomes and recovery.

## Acceptance criteria

- [x] Connect the operator-selected Mailbox tab through the dedicated extension and fill the real compose interface only for ready operator-controlled execution, using the exact confirmed sender, recipient, content, and attachment snapshot.
- [x] Reconcile before execution, honor new blockers, and perform no immediate send without applicable Confirmation.
- [x] Observe mailbox confirmation before marking Sent and freezing sent content and execution history.
- [x] Pause the current Execution Flow for authentication, blocking failure, or unresolved outcomes; reconcile before continuation.
- [x] Accept immediate sending independently from native scheduling and expose a disabled capability if it cannot be verified reliably.
- [x] Run controlled extension-peer acceptance for the immediate-send protocol plus repeatable boundary tests for failures, takeover, and immutable Sent Records; keep live extension acceptance separate.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and controlled extension-peer evidence where needed. Verify enabled extension capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

## Comments

2026-09-11: Implemented Ticket 09 through the existing SmartMail command/query boundary. `NetEase163Mailbox.submit` now opens and fills the real compose interface for the exact confirmed snapshot, attaches the confirmed bytes, submits once, and reports `sent` only after the Sent folder confirms the message through `mbox:listMessages` plus a metadata-only `mbox:readMessage`. `immediate_send` is enabled and reported independently of `native_scheduling`, `schedule_cancellation` and `recall`, which stay disabled. A confirmed `sent` creates an immutable Sent Record (frozen content, attachment bytes and platform reference) and consumes the Confirmation; `failed`, `unknown` and `authentication_required` outcomes pause the Execution Flow.

Core execution now materializes the exact confirmed attachment snapshot to private files, hands them to the adapter boundary, and removes them once the single submission returns, without polluting the persisted Execution Ledger request.

Live acceptance on real 163.com found and fixed three concrete obstacles: the compose label renders as "写 信" so exact-text matching fails; the subject input id ends `_subjectInput` and the recipient is `.nui-editableAddr-ipt`; and clicking 发送 raises a promotional "智能优化您的英文邮件" modal that silently blocks the send. The first attempt therefore returned `unknown` (correctly, not Sent) and is preserved in the Ledger; the production payload now dismisses that modal and completes the blocked submission. The adapter also opens a **persistent** browser profile (`.smartmail/browser-163`, override with `SMARTMAIL_BROWSER_PROFILE`), because Playwright's default incognito-like context kept cookies only in memory and lost the login on every restart. A pre-send guard refuses to submit unless the confirmed recipient and subject are present in the compose header, and the sent-time filter parses the server-local `sentDate` so an earlier identical subject cannot false-match.

Ticket 09 adds twelve command-boundary tests using a deterministic Playwright stand-in for the exact snapshot, immutable Sent Record, confirmation consumption, authentication pause, failure/unknown outcomes, capability independence, takeover-before-reconciliation, private attachment copies, and the persistent browser profile. The complete suite passes **157 tests with 5 representative-material tests skipped**. See [validation](../../../docs/ticket-09-validation.md).

2026-09-11 (re-acceptance): Re-ran the full path on a second, brand-new mailbox (`z13818145478@163.com`) whose Inbox held only 163's own welcome/security mail and whose Drafts was empty. Two account-specific obstacles surfaced and were fixed. First, the rich-text body editor's contenteditable lives in an unnamed iframe that initialises **after** the rest of the compose form, so the payload's single frame sample missed it and the attempt returned `failed` ("Could not locate the compose message body"); the payload now polls the frame list for the editor (up to 25 s) with a plain-text textarea fallback. Second, a **native** dialog left open by the send flow surfaced as `Tool "browser_run_code_unsafe" does not handle the modal state` and blocked every later evaluation in that session; the payload now registers a dialog handler on the page and every context page, accepts each dialog, and records its text in the outcome evidence under `dialogs`. The adapter also now includes the raw browser output in the "unsupported or ambiguous send result" error to keep such failures diagnosable. Recorded acceptance: attempt `sent` (`phase: recorded`), reference `743:xtbC5wBTHWqj3mDiQQAA39`, Sent Record `999fd9fa-e671-463b-8eaf-79532ef27fd4`, sent `2026-09-11 18:56:32`; the post-send read-only refresh recognised all five built-in folders with complete enumeration (inbox 3, drafts 0, sent 3, deleted 0, spam 0). Added a thirteenth boundary test guarding the late-editor polling and the native-dialog handling. Suite: **158 tests with 5 representative-material tests skipped**.

2026-09-14 pivot: the retired `NetEase163Mailbox` Playwright adapter, browser-session flags and injected scripts were removed. Confirmed immediate sending now travels through the dedicated `Mailbox Extension` and Native Messaging bridge. A durable queue claims each command once; the native host rechecks the active Confirmation and Execution Attempt immediately before issuing one submission permit; the extension transfers confirmed attachment bytes in bounded chunks and requires a new, exact Sent-folder match. Extension sending is disabled by default and its capability is unverified until a new real-extension acceptance. The live Playwright results above remain immutable historical evidence and are not reused as current verification. See [current pattern](../../../docs/immediate-send-pattern-09.md), [extension validation](../../../docs/extension-validation.md) and [pivot guide](../../../docs/browser-extension-pivot.md).

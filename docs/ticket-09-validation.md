# Ticket 09 Validation: Confirmed Immediate Send in 163.com (historical)

> Historical record: this validation was completed against the retired Playwright
> CLI adapter on 2026-09-11. The current product removes that runtime path and
> uses the dedicated extension described in [the pivot guide](browser-extension-pivot.md).
> The real-account results below remain immutable history; they do not verify the
> extension or enable its sending capability.

Date: 2026-09-11
Platform: retired real 163.com webmail Playwright CLI session
Safety boundary: only operator-confirmed immediate sending; native scheduling, cancellation and Recall stay disabled

## Command-boundary verification

The ordinary suite exercises Ticket 09 through the same `SmartMail` methods and terminal commands used by the Operator:

- `mailbox capabilities`
- `confirmation review` / `confirmation confirm`
- `execution run` / `execution status` / `execution list`
- `execution takeover` / `execution reconcile-and-continue`
- `sent list` / `sent show`

Final result:

```text
Ran 158 tests in 82.595s
OK (skipped=5)
```

Thirteen Ticket 09 tests use a deterministic stand-in for the Playwright CLI. They verify the exact confirmed snapshot reaching the adapter, immutable Sent Record content and attachment bytes, consumption of the Confirmation, `authentication_required` pause, `failed` and `unknown` outcomes, wrong-capability refusal, takeover-before-reconciliation, repeatable private attachment copies, that a closed browser is opened with a **persistent** profile, and that the send payload keeps polling for the late-loading body editor and keeps accepting native dialogs. The five skipped tests are the repository's existing opt-in representative-material cases, not live mailbox tests.

## Operator-assisted authentication

The headed browser opened the standard 163.com login surface. The Operator entered credentials and completed interactive login directly. SmartMail neither received nor stored the credentials and did not bypass verification or CAPTCHA.

### Root cause fixed: the login must be persistent

The first live attempts lost the login on every restart. The cause was structural, not incidental: the Playwright default context is **incognito-like**, so cookies live only in memory and vanish when the browser process exits. Every earlier "logged in" therefore disappeared as soon as the daemon restarted, and the persisted cookie store stayed empty.

The adapter now opens a **persistent user-data directory** (`--persistent --profile <store>/browser-163`, default `.smartmail/browser-163`, overridable with `SMARTMAIL_BROWSER_PROFILE`). The operator authenticates once and every later `mailbox refresh` and `execution run` reuses the on-disk session. A regression test asserts the open command carries `--persistent`, `--profile` and the resolved profile path.

## Live immediate-send acceptance

A real Preparation was built, confirmed, and executed through the enabled `163-browser` adapter. The adapter opened the real compose interface, filled the **exact confirmed** recipient, subject, body and attachment, and reported Sent only after the mailbox itself confirmed it.

### The obstacle that had to be solved

Clicking 发送 does not, by itself, submit. On the first submit 163 interposes a promotional modal — **"智能优化您的英文邮件"** with 取消 / 立即体验 — that *silently blocks* the send. The first live attempt therefore submitted nothing: the compose was left as a draft and the adapter correctly returned **`unknown`** ("Compose was submitted but the Sent folder did not confirm the message within the observation window") rather than claiming Sent. That `unknown` attempt is preserved in the Execution Ledger.

Selectors were confirmed against the live DOM rather than guessed (the compose label renders with letter-spacing as "写 信"; the subject input id ends `_subjectInput`; the body editor is a contenteditable frame). The production payload now dismisses the promotional modal (matched by text, closed via its close control) and submits again — no retry of an unconfirmed action, only completion of a blocked one.

### Observed and persisted result

The end-to-end run created an immutable Sent Record backed by mailbox evidence:

| Field | Value |
| --- | --- |
| Adapter outcome | `sent` |
| Execution Attempt state | `sent` (`phase: recorded`) |
| Confirmation | consumed |
| Mailbox address | `fakeryh@163.com` |
| Recipient | `3356198166@qq.com` |
| Subject | `PhD supervision enquiry #1789122763` |
| Sent date (server) | `2026-09-11 18:33:27` |
| Platform reference | `733:xtbC3Rf2YGqj2PcZWgAA35` |
| Evidence source | `163.com mbox:listMessages plus metadata-only mbox:readMessage`, folder `sent` |

Sent was established from the Sent folder, never from the click. The Sent Record froze the exact content and attachment bytes with its platform reference. A re-list of the Sent folder returned 12 rows with the confirmed message first.

### Post-send read-only observation

A `mailbox refresh` after the send discovered the built-in folders and returned a Reconciliation whose findings were all non-delivery states (`observed_non_delivery_state` for Deleted rows) with `local_state_changed: false`. The adapter returns the session to the mailbox after submitting, so observations see the folder tree rather than the compose module.

## Re-acceptance on a second, fresh account

The full path was accepted a second time on a different, brand-new mailbox (`z13818145478@163.com`). Its Inbox held only 163's own welcome/security mail and Drafts was empty, so the run started from a genuinely clean account. The headless command set was unchanged: `student create` → `import` → `prepare` → `preparation confirm` → `confirmation confirm` → `execution run` → `mailbox refresh`.

Both accounts use the same adapter and payload; the only per-run input is the confirmed sender, recipient and snapshot.

### Obstacle 1 — the body editor frame loads late

The first attempt on the new account filled recipient and subject but returned **`failed`**: "Could not locate the compose message body". Ticket 09's original payload sampled the frame list once, immediately after the compose opened. On this account the rich-text editor's contenteditable lives in an unnamed iframe that initialises **after** the rest of the form, so the single sample missed it. This was reported as `failed` and paused the Campaign (`execution_failed`) — correctly not Sent, and no message was delivered.

The payload now **polls** the frame list for the `body[contenteditable="true"]` editor (up to 25 s) instead of sampling once, with a hidden plain-text textarea fallback.

### Obstacle 2 — a native dialog desynchronises the CLI

A later attempt hit a different wall: `163.com returned an unsupported or ambiguous send result`. The underlying cause was recorded by the follow-up observation as `Tool "browser_run_code_unsafe" does not handle the modal state` — a **native** alert/confirm left open by the send flow, which blocks *every* later evaluation in that session, not just the submission.

The payload now registers a dialog handler on the page and on every context page (including popups), accepts each dialog as it appears, and records its text in the outcome evidence under `dialogs`. With the handler in place the same run completed normally and the post-send read-only refresh succeeded.

To make such a failure diagnosable rather than silent, the adapter now includes the raw browser output in the "unsupported or ambiguous send result" error.

### Observed and persisted result

| Field | Value |
| --- | --- |
| Adapter outcome | `sent` |
| Execution Attempt state | `sent` (`phase: recorded`) |
| Confirmation | consumed |
| Mailbox address | `z13818145478@163.com` |
| Recipient | `3356198166@qq.com` |
| Subject | `PhD supervision enquiry #1789124147` |
| Sent date (server) | `2026-09-11 18:56:32` |
| Platform reference | `743:xtbC5wBTHWqj3mDiQQAA39` |
| Sent Record | `999fd9fa-e671-463b-8eaf-79532ef27fd4` |
| Evidence source | `163.com mbox:listMessages plus metadata-only mbox:readMessage`, folder `sent` |

The post-send `mailbox refresh` recognised all five built-in folders with complete enumeration — `inbox 3`, `drafts 0`, `sent 3`, `deleted 0`, `spam 0` — and the Reconciliation persisted the three sent observations, including the confirmed message.

## Side effects and safety

Test messages went only to the operator-approved recipient `3356198166@qq.com`. On the first account two clearly-marked messages were delivered: one during the diagnostic that established the modal behaviour, and one for the recorded end-to-end acceptance. On the second account three were delivered: two short-lived diagnostics that isolated the attachment/dialog behaviour, and the recorded acceptance (`#1789124147`). No leftover draft remained in Drafts on either account — the second account's Drafts folder was empty and stayed empty. No Inbox message was opened; the collector still fetches headers and MIME metadata only, so unread state is unchanged. Screenshots and traces stay under ignored `output/playwright/` and `.playwright-cli/` paths and are not repository artifacts.

## Legacy capability result

| Capability | Available | Live verified |
| --- | --- | --- |
| Read history | Yes | Yes, for the declared built-in-folder and metadata-detail scope |
| Immediate send | Yes | Yes, from confirm → real compose → Sent-folder evidence |
| Native scheduling | No | No |
| Schedule cancellation | No | No |
| Recall | No | No |

The retired adapter verified immediate sending independently of scheduling. That
result is not inherited by `163-extension`; extension immediate sending remains
disabled by default and unverified until a new extension acceptance is recorded.

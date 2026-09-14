# Dedicated 163 extension validation

This document records validation of the post-pivot implementation. It covers the
Native Messaging bridge, the `163-extension` Mailbox adapter and the packaged
Manifest V3 extension. No live mailbox account or real recipient was used in these
checks. The old Playwright account runs are preserved separately as historical
Ticket 06 and Ticket 09 evidence.

## Current automated result

Run from the repository root:

```powershell
.\.venv\Scripts\python -X utf8 -m unittest discover -s tests -v
node --test extensions/netease163/tests/commands.test.mjs
```

The current run completed with:

```text
Python: Ran 205 tests; OK (5 representative-material tests skipped)
Node:   11 tests; pass
```

The Python suite covers the public SmartMail boundary, durable command queue,
Native Messaging framing, Windows host-manifest generation, extension adapter
capabilities, confirmed attachment transfer, persisted Confirmation rechecks,
single-delivery behavior, disconnect/expiry handling, wrong-Mailbox evidence,
authentication pauses, Unknown Outcome recovery and the fact that the old
`163-browser` option is rejected. The Node suite covers command ordering, one
submission permit, disconnect and deadline guards, read-only isolation, attachment
truncation, exact Sent matching and the extension manifest's restricted permissions.

## Local browser smoke test

When Playwright and a Chromium executable are available, run the isolated fixture
test:

```powershell
$env:SMARTMAIL_PLAYWRIGHT_MODULE = 'C:\path\to\node_modules\playwright'
$env:SMARTMAIL_CHROMIUM_EXECUTABLE = 'C:\path\to\chrome.exe'
node extensions/netease163/tests/browser-smoke.cjs
```

The smoke test loads the unpacked extension in a fresh temporary profile and serves
a local fixture at the `mail.163.com` origin. It checks the extension service
worker, isolated scripts, account identification, read-only observation, exact
attachment bytes, one Send click and rejection of a second send. It reports:

```json
{"extensionLoaded":true,"isolatedScripts":true,"readOnlyObservation":true,"exactAttachment":true,"sendCount":1,"repeatRefused":true,"outcome":"sent"}
```

All fixture requests are locally fulfilled or aborted. The test creates no Native
Messaging registration, does not use the operator's browser profile, and cannot
establish live 163.com support.

## What remains unverified

The extension has not yet been accepted against a real 163.com account. Therefore
`read_history` and `immediate_send` are reported as available only according to
connection/acceptance mode and have `verified: false`; immediate sending is disabled
unless `--enable-extension-send` is supplied. A future live acceptance must verify:

- the extension's account identification and connection lifecycle on the target
  Chrome/Edge versions;
- the actual five-folder metadata-only observation and unread-state preservation;
- the supported 163 in-page Compose layout and attachment upload completion;
- exactly one confirmed send and a new canonical Sent-folder match;
- authentication, modal/dialog and navigation interruptions without blind retry.

Native scheduling, schedule cancellation and Recall remain independently disabled
and require separate implementation and acceptance. Simulated fixture outcomes and
the retired Playwright validations cannot satisfy those acceptance requirements.

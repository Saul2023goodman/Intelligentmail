# Ticket 12 validation: native schedules, Cancellation, Replacement, Recall, direct changes

Controlled real-mailbox evidence for the dedicated 163 extension's new external
operations, plus the repeatable boundary and extension-peer tests that keep each
capability honest. Business authority stays in the Python core; the extension
only carries out one confirmed operation and returns observed evidence.

## 1. Static reverse engineering and live protocol evidence

The 163 js6 bundles (`p0.b59cb1c5.js`, `p1.8fa64494.js`, saved under the user's
Downloads) were reverse engineered statically, and the remaining unknowns were
resolved against the logged-in mailbox through Chrome DevTools (port 9222) with
zero-side-effect introspection of the running page, then controlled real
requests. Findings implemented by the extension:

| Capability | Verified protocol |
|---|---|
| Place native schedule | `POST /js6/s?sid=…&func=mbox:compose`, `var=` XML, `action=schedule`, `attrs.scheduleDate` as `<date>YYYY-MM-DD HH:mm:ss</date>` in **Beijing wall clock**; response XML `scheduledSent{msid,mid}` |
| Scheduled draft identity | composite list id `"<msid>:<mid>"` in folder 2 with `flags.scheduleDelivery=true`; `sentDate` is the planned time |
| Attachment | `POST /js6/compose/upload.jsp?…&composeId=<cid>&type=native`, multipart `Filedata`; `attachId/attachmentId`, referenced as `<object><int name="id">…</int></object>` |
| Cancel schedule | removing the scheduled draft: `mbox:updateMessageInfos` `{ids,attrs:{fid:4}}`; successful Cancellation is recorded only after drafts-folder absence **and** Deleted-folder presence are observed |
| Delete guardrail | direct `mbox:deleteMessages` can answer `FA_HOOK_SECURITY_3` (risk-control handshake); the move-to-trash call does not. The extension never drives the interactive security UI |
| Send undo | `mbox:cancelDeliver {tinfo}` is the 30-second post-send undo and is **not** used for schedule cancellation |
| Recall | `mbox:recallMessage {mid}`; `S_OK` with `var.recallresult` codes 0/1 pending, 2/3 success, 4+ failed; `FA_UNSUPPORT_RECALL`, `FA_MAIL_EXPIRED` |
| Capability flags | `$.Ext.letterRecall=true` on the accepted account; per-message eligibility still comes from full-letter evidence |
| XML serializer | taken verbatim from the running `$.Util.obj2Dom/dom2Str/date2Str`: int/long/boolean/string/date/array/object tags, self-closing empty arrays, leaf-only XML escaping |

## 2. Controlled live acceptance with the shipped scripts (2026-09-16)

The **packaged repository files** `common.js` and `schedule.js` were injected into
the authenticated tab (same ISOLATED-world code the worker injects) and driven via
CDP. Every probe addressed the operator's own mailbox
(`fakeryh@163.com`), used an unmistakable test subject, and was removed to the
Deleted folder in the same run.

1. Plain schedule placement then observed removal — `outcome=scheduled`
   (`schedule_delivery=true`, exact Beijing time, composite id
   `761:xtbC+QTpU2qqLmTznwAA3h`), then `outcome=removed` with
   `folder_drafts=false, folder_deleted=true`.
2. Attached schedule placement (shipped `uploadAttachment` → compose with the
   returned id) — `outcome=scheduled` (`realAttached` row confirmed in an earlier
   raw probe), then `outcome=removed`.

Cancellation was therefore verified as removal-before-recording. No message was
left scheduled to fire. Recall was **not** executed live: it mutates a real
already-sent message, requires per-message eligibility, and the ticket keeps it
behind a separate explicit opt-in (`--enable-extension-recall`); only its request
shape and response codes were statically verified.

The Native Messaging transport itself (queue, heartbeat, chunks, permit) was not
re-exercised end-to-end with the worker in this session; protocol v1 is unchanged
in shape and covered by the peer tests below. Reload the unpacked extension and
run `schedule place` through a registered host for the final transport-level
sign-off.

## 3. Repeatable tests

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest tests.test_schedules tests.test_extension_schedules `
  tests.test_extension_mailbox tests.test_extension_bridge tests.test_reconciliation tests.test_execution
node --test extensions/netease163/tests/commands.test.mjs `
  extensions/netease163/tests/schedule-commands.test.mjs
```

Results: 85 Python tests OK; 21 Node tests OK. Added coverage:

- **placement**: Externally Scheduled state and external identity without a Sent
  Record; independent capability gate; elapsed-time refusal; Unknown placement
  pauses and is never duplicated; failed placement creates nothing; duplicate
  active schedule rejected;
- **cancellation**: explicit Cancellation Confirmation; observed removal →
  `cancelled`; uncertain removal → `cancel_unknown` pause with no success claim;
  already-Sent race freezes the immutable Sent Record and reports the pending
  cancellation did not prevent sending; other schedules stay active;
- **replacement**: fresh Preparation + its own scheduled Confirmation (no
  transfer); removal verified before submission; unknown removal blocks
  submission; removal success + unknown replacement leaves the original removed
  (never restored); original Sent during replacement freezes and blocks new
  communication;
- **direct changes**: still-active observation; externally edited time is a
  discrepancy that pauses without restoring content or inheriting Confirmation;
  disappearing evidence never becomes Sent by elapsed time; observed Sent
  evidence freezes the Sent Record; externally-owned schedules are reported as
  non-local evidence;
- **recall**: disabled by default; explicit Confirmation; outcomes recorded
  separately, never a completion blocker;
- **extension peer**: schedule/cancel/recall over the durable bridge with permit
  gating, attachment chunking, capability independence, permit-before-click and
  Unknown-after-permit semantics; XML/Beijing serialization unit tests.

Full suite: 287 tests, with 6 pre-existing date-sensitive follow-up/report
failures unrelated to this ticket (their fixtures assume dates on/before
2026-09-15 while the machine date is 2026-09-16; they fail identically on the
clean HEAD worktree).

## 4. Capability and command surface

Independent capabilities, all `verified: false` until live sign-off:
`read_history`, `immediate_send` (`--enable-extension-send`),
`native_scheduling` and `schedule_cancellation`
(`--enable-extension-schedule`), `recall` (`--enable-extension-recall`).

New operator boundary:

```text
confirmation confirm <id> --schedule-at "2026-09-20 15:30" [--timezone Asia/Shanghai]
schedule place <confirmation_id>
schedule list [--campaign …] [--state externally_scheduled]
schedule cancel-review <id> | cancel-confirm <id> | cancel-run <confirmation_id>
schedule replace-confirm <schedule_id> <replacement_confirmation_id> | replace-run <confirmation_id>
schedule reconcile --student <id>
recall review <sent_record_id> | confirm <sent_record_id> | run <confirmation_id>
observation set-interval --student <id> --seconds 300 | observation show --student <id>
```

`mailbox_settings.observation_interval_seconds` is observation-only
configuration; no code path performs writes from periodic observation.

## 5. Remaining limitations

- Transport-level live sign-off with the reloaded worker + registered native host.
- Recall live acceptance (deliberately gated; needs explicit operator choice).
- Browser-smoke Playwright run: its `node_modules`/browser are absent after the
  environment restore; rerun when Playwright is reinstalled (fixture-only proof).

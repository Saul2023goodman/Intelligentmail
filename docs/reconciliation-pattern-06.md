# Supported Mailbox Observation Pattern 06

Established against the real 163.com webmail on 2026-09-11 with operator-assisted authentication. The pattern verifies live-DOM folder discovery, folder-level pagination, canonical message identifiers and metadata-only detail reads. It does not fetch message-body HTML or verify sending, scheduling, cancellation or Recall.

## Operator-assisted browser access

```powershell
python -m smartmail --adapter 163-browser --browser-session smartmail-163 mailbox refresh --student STUDENT_ID
```

The adapter uses a named, headed Playwright CLI browser session and stores no mailbox password. When no session is open it opens `https://mail.163.com`. Login, verification and CAPTCHA completion belong to the Operator. A refresh during that interruption persists `authentication_required` with empty Evidence Coverage. The Operator reruns refresh after reaching the mailbox.

The intended Mailbox comes from the selected Student. If the authenticated 163.com address differs, SmartMail persists `wrong_mailbox` and imports no messages from that account.

## Verified observation boundary

After authentication, refresh performs only these interactions:

1. Expand the live DOM's built-in-folder group when needed and recognize Inbox, Drafts, Sent, Deleted and Spam with their platform folder IDs.
2. Read each recognized folder in pages of 50 until its reported total of canonical message IDs is enumerated.
3. Fetch structured header, MIME-part and attachment metadata for every enumerated ID through `mbox:readMessage`.
4. Return direction, folder, exact canonical ID, counterpart, subject, observed time, mailbox state, list evidence and detail evidence.

The browser collector does not select a message, invoke toolbar mutations or visit Compose. Inbox messages become `received`; Drafts, Deleted and Spam retain explicit `draft`, `deleted` and `spam` states and are not treated as delivery evidence. A Sent message becomes `sent` only when platform metadata establishes recipient success; otherwise its status stays `ambiguous`.

Each folder's Evidence Coverage records its ID, reported total, enumerated-ID count, page size, requested and successful pages, requested/attempted/successful/failed details, errors, enumeration completeness and detail completeness. Rate-limited metadata reads receive bounded backoff retries, and exhausted retries remain explicit failures. `supported_scope_complete` is true only when all five recognized built-in folders and every enumerated detail complete. Top-level `complete` remains false because virtual views, unrecognized custom folders and message bodies remain outside scope. Therefore an unmatched local record is not proof that a corresponding mailbox message does not exist outside that declared scope.

`mbox:readMessage` metadata reads preserve unread flags. The separate body-HTML endpoint does not: live exploration showed that fetching it marks an unread message read. The body endpoint is therefore excluded and every message records that exclusion in its evidence.

## Persistence and Reconciliation

Every manual refresh creates an immutable Mailbox observation run plus message observations in the local SQLite store. It retains:

- intended Student and Mailbox;
- adapter and per-capability snapshot;
- time, status and interruption detail;
- Evidence Coverage;
- canonical platform reference plus list and structured detail evidence;
- explicit ambiguity text where supported fields were unavailable.

The same command creates a Reconciliation. Outbound Sent evidence can link to one exact local Sent Record by platform reference or by exact recipient and subject. If there is no Sent Record, it can link to one unresolved Execution Attempt by exact recipient and subject. Multiple matches remain `ambiguous_local_match`; unmatched rows remain unassociated. Draft, Deleted and Spam observations become `observed_non_delivery_state` findings rather than delivery claims. Inbox reply association is intentionally deferred and recorded as `unassociated_inbound` rather than guessed.

Reconciliation in this slice records evidence and links for inspection. It reports `local_state_changed: false`: the mailbox is not the primary store, and a similar list row does not automatically resolve or retry an Execution Attempt.

## Independent capabilities

`mailbox capabilities` reports all platform operations independently.

| Capability | Live 163 browser adapter |
| --- | --- |
| Read history | Available and live-verified for the declared folder and metadata-detail scope above |
| Immediate send | Disabled and unverified |
| Native scheduling | Disabled and unverified |
| Schedule cancellation | Disabled and unverified |
| Recall | Disabled and unverified |

Successful reading never enables or verifies a state-changing capability.

## Controlled fixtures

Ordinary tests pass `observations` through the controlled adapter script and exercise refresh, inspection, persistence, wrong-mailbox refusal, explicit ambiguity and Reconciliation at the same core command/query boundary as the terminal shell. These fixtures establish repeatable SmartMail behavior but do not count as live platform verification.

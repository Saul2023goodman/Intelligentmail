# Ticket 06 Validation: 163.com Observation and Reconciliation

Date: 2026-09-11  
Platform: real 163.com webmail in a named, headed Playwright CLI browser session  
Safety boundary: live-DOM discovery, folder pagination and metadata-only detail reads

## Command-boundary verification

The ordinary suite exercises Ticket 06 through the same `SmartMail` methods and terminal commands used by the Operator:

- `mailbox capabilities`
- `mailbox refresh --student STUDENT_ID`
- `mailbox observations --student STUDENT_ID`
- `mailbox show OBSERVATION_ID`
- `reconciliation list --student STUDENT_ID`
- `reconciliation show RECONCILIATION_ID`

Final result:

```text
Ran 120 tests in 42.587s
OK (skipped=5)
```

Eight Ticket 06 tests use controlled observation fixtures. They verify refresh, persistence and restart inspection, per-folder Evidence Coverage, preservation of structured details and non-delivery states, wrong-mailbox refusal, explicit unsupported/ambiguous evidence, independent capabilities, exact links to a Sent Record or unresolved Execution Attempt without canonical mutation, and terminal inspection. The five skipped tests are the repository's existing opt-in representative-material cases, not live mailbox tests.

## Operator-assisted authentication

The headed browser opened the standard 163.com login surface. The Operator entered credentials and completed interactive login directly. SmartMail neither received nor stored the credentials and did not bypass verification or CAPTCHA.

An authentication-required refresh was persisted with zero observed folders, incomplete Evidence Coverage and an `observation_unavailable` Reconciliation finding. After the Operator completed login, the same named browser session was reused for successful refreshes.

## Live folder and detail acceptance

The collector expanded the built-in-folder group in the live DOM, recognized the five supported folders, requested each folder in pages of 50, enumerated canonical IDs, and performed a metadata-only `mbox:readMessage` for every ID. It did not visit Compose or invoke draft editing, send, schedule, delete, cancel or Recall actions.

Observed and persisted result:

| Folder | ID | Declared total | IDs enumerated | Pages | Details succeeded | Details failed | Complete |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Inbox | 1 | 19 | 19 | 1 | 19 | 0 | Yes |
| Drafts | 2 | 2 | 2 | 1 | 2 | 0 | Yes |
| Sent | 3 | 10 | 10 | 1 | 10 | 0 | Yes |
| Deleted | 4 | 263 | 263 | 6 | 263 | 0 | Yes |
| Spam | 5 | 0 | 0 | 1 | 0 | 0 | Yes |
| **Total** |  | **294** | **294** | **10** | **294** | **0** | **Yes, supported scope** |

The observation status is `complete` and `supported_scope_complete` is true. Top-level whole-mailbox `complete` remains false: virtual views, unrecognized custom folders and message bodies are explicitly outside scope. All 294 canonical IDs and 294 structured detail objects were returned after reopening the SQLite store in a separate process. Reconciliation produced 294 inspectable findings and reported `local_state_changed: false`.

## Unread-state safety

A metadata-only detail read against an unread Inbox message returned headers, flags, subject, timestamp, raw headers, antispam information, HTML-part metadata and attachment metadata. Re-listing the folder showed the message's unread flag unchanged.

Exploration separately tested the body-HTML URL with tracking suppression enabled. Fetching that URL changed the target's server-side read flag. The message was immediately restored to unread through the visible mailbox control, and a full page reload confirmed the original four unread Inbox messages. The production collector therefore never calls the body endpoint and records the exclusion on every message. After the full 294-detail acceptance scan, a fresh list request again reported four unread and 15 read Inbox rows, while the visible Inbox count remained four.

Screenshots and the Playwright trace were captured locally under ignored `output/playwright/` and `.playwright-cli/` paths. They intentionally are not repository artifacts.

## Capability result

| Capability | Available | Live verified |
| --- | --- | --- |
| Read history | Yes | Yes, for the declared built-in-folder and metadata-detail scope |
| Immediate send | No | No |
| Native scheduling | No | No |
| Schedule cancellation | No | No |
| Recall | No | No |

The browser adapter's execution guard remains disabled. Successful history reading cannot authorize or imply any state-changing operation.

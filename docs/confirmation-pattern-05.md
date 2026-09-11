# Supported Confirmation and Controlled Execution Pattern 05

Established from the user-supplied `sample.zip` on 2026-09-11, SHA-256 `f2e73a53d3503c3568cfeba730317ba232f4258636d9f5560e10dea77398f5e2` (the same archive as [Supported Intake Pattern 01](intake-pattern-01.md), [Supported Document Pattern 02](preparation-pattern-02.md), [Supported Readiness and Attachment Pattern 03](readiness-pattern-03.md) and [Supported Rewrite Pattern 04](rewrite-pattern-04.md)).

Readiness is not authority. A Ready Preparation must be **confirmed** by the operator before any external action, and external actions run only through a **mailbox adapter**. This slice introduces Confirmation, a controlled adapter, the Execution Ledger, immutable Sent Records, and the paused Execution Flow — with no real sends and no verified platform capability.

## Confirmation

```
confirmation review PREPARATION_ID
confirmation confirm PREPARATION_ID [PREPARATION_ID ...]
confirmation list --campaign CAMPAIGN_ID
confirmation show CONFIRMATION_ID
```

`confirmation review` returns everything inspected before authorizing: sender, recipient, subject, the confirmed attachment names with their SHA-256 and size (contents readable through the core), the readiness findings, the execution details (`{"kind": "immediate"}`), the full message text, whether the Preparation was already Sent, and any active Confirmation ID.

`confirmation confirm` authorizes one or more Ready Preparations in a single operator action. Each Preparation gets its **own** Confirmation, bound to:

- the Preparation identity (`preparation_id`, `task_id`);
- a `content_digest` over the exact sender, recipient, subject and body;
- an `attachments_digest` over the confirmed attachment labels, names and SHA-256 values;
- the execution details (`{"kind": "immediate"}`).

Confirmation rules:

- Only a currently Ready, active Preparation can be confirmed; a blocked Preparation is refused and names its blocking findings.
- Re-confirming unchanged content is idempotent and returns the same Confirmation.
- Confirming after a content change **renews**: the prior Confirmation becomes `invalidated` with reason `renewed`, and a new Confirmation binds the new digests.
- Confirmation is local. It makes no external request and writes nothing to the mailbox.

## Controlled execution

```
execution run CONFIRMATION_ID [CONFIRMATION_ID ...]
execution list --campaign CAMPAIGN_ID
execution show ATTEMPT_ID
execution status --campaign CAMPAIGN_ID
execution stop ATTEMPT_ID [--detail TEXT]
sent list --campaign CAMPAIGN_ID
sent show SENT_RECORD_ID
```

External execution runs only through an adapter. The default adapter is **disabled**: it exposes no capability, so `execution run` refuses and nothing leaves the machine. The controlled adapter demonstrates outcomes without real sends and is selected explicitly:

```
--adapter controlled [--adapter-script PATH]
```

The adapter script is a JSON file, either a list of outcomes or `{"outcomes": [...]}`. Each outcome is `sent`, `failed` or `unknown`, optionally with `detail`. Each `submit` records the exact request it received.

`execution run` executes Confirmations **in order**, and for each:

1. verifies the Confirmation is active and the Preparation is active, Ready, and not already Sent;
2. recomputes the content and attachment digests and refuses if either changed since Confirmation;
3. records an Execution Attempt (observable in the Execution Ledger) before submitting;
4. submits the exact request — sender, recipient, subject, body, and attachments by name and SHA-256 — to the adapter;
5. records the observed outcome.

Outcomes:

| Adapter outcome | Attempt state | Effect |
| --- | --- | --- |
| `sent` | `sent` | Creates an immutable **Sent Record**; the Confirmation becomes `consumed` |
| `failed` | `failed` | Pauses the Execution Flow (`execution_failed`) and stops the batch |
| `unknown` | `unknown` | Pauses the Execution Flow (`unknown_outcome`); the outcome is not treated as failure |

`execution status` reports the current Execution Flow for a Campaign: `idle`, or `paused` with its reason and detail. While paused, further execution is refused; local preparation, inspection and reporting remain available. Clock passage, a recorded request, or operator acknowledgment never establish Sent on their own — only adapter-confirmed Sent does.

## Sent Records are frozen

A mailbox-confirmed Sent creates a Sent Record holding the exact content and a private copy of the confirmed attachment bytes, independent of delivery or reading status and of any later edit to the Preparation or its original files. `sent show` reports the frozen recipient, subject, evidence and attachment names with SHA-256 and size; the frozen bytes are readable through the core. A Sent Preparation cannot be confirmed again: further communication requires a new linked Communication Action.

## Stop, Rewrite and post-Sent

An Execution Attempt is `in_progress` while submitting and `unknown` when its outcome is not established. Both are **unresolved**.

```
execution stop ATTEMPT_ID
```

`execution stop` stops an unresolved attempt, records that it was stopped, and releases an `unknown_outcome` pause; a `failed` attempt is terminal and is refused because it needs reconciliation (tickets 06 and 08).

- Rewrite is **refused** while an attempt for that Preparation is unresolved; it succeeds once the attempt is stopped or resolved.
- Rewrite **invalidates** the replaced Preparation's active Confirmation (reason `rewrite`) — the fresh Preparation starts with no authorization. It remains refused for a Sent Preparation.

## Persistence

Confirmations, Execution Attempts, Sent Records with their frozen attachment bytes, and the paused Execution Flow are stored locally and survive restart. Nothing is inferred from a missing record.

## Not claimed

- No real mailbox, no login, no scheduler and no browser capability; only the controlled adapter exists in this slice.
- No automatic retry, no reconciliation and no crash-recovery decision-making (tickets 06 and 08).
- No sending times, windows, timezone, spacing or daily limits (tickets 10 and 11).
- No carry-over of Confirmation across Rewrite, and no editing of Sent content.

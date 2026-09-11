# Supported Rewrite Pattern 04: Fresh Preparations with inspectable history

Established from the user-supplied `sample.zip` on 2026-09-11, SHA-256 `f2e73a53d3503c3568cfeba730317ba232f4258636d9f5560e10dea77398f5e2` (the same archive as [Supported Intake Pattern 01](intake-pattern-01.md), [Supported Document Pattern 02](preparation-pattern-02.md) and [Supported Readiness and Attachment Pattern 03](readiness-pattern-03.md)).

A student revises outreach content after preparation has begun. The revised wording must not silently reuse the earlier Preparation's identity, corrections or attachments, and the replaced version must remain inspectable. SmartMail therefore treats a content change as a **Rewrite**: a fresh Preparation with a new identity, and a hidden-but-inspectable Superseded Preparation.

## Rewrite

```
preparation rewrite PREPARATION_ID --source SOURCE_ID
```

`PREPARATION_ID` is the Task's active Preparation. `SOURCE_ID` is a preserved Source Material from `imports show` — the revised draft, typically carried by a new import.

A Rewrite is supported only when:

- the named Preparation exists and is active (a Superseded Preparation cannot be rewritten again, and unknown IDs are rejected);
- the Source Material exists, is readable, and parses under the [supported draft layout](preparation-pattern-02.md);
- its filename association (`<Institution>_<Supervisor name>.docx`) resolves to the **same** Outreach Task as the Preparation being replaced.

The result is:

- a **fresh Preparation identity** for the same Outreach Task, prepared from the revised Source Material (same recipient extraction, body restructuring, internal-note separation and field precedence as `prepare`);
- the prior Preparation marked **Superseded**, with its own content, Source Association, Transformation Records, Correction Records and confirmed attachment bytes retained unchanged;
- fresh advisory attachment slots for the new Preparation. Confirmed attachments are **not** carried over — a slot is a suggestion until the operator confirms it again.

A subject supplied by correction on the prior Preparation is not inherited: the new Preparation re-runs readiness from its own content and is normally `Blocked: missing_subject` until the operator corrects it.

## Active work versus history

Superseded Preparations are hidden from active-work views:

- `preparation list --campaign CAMPAIGN_ID` lists only active Preparations;
- `exceptions list` / `exceptions show` report only the active Preparation's readiness findings for the Task.

Every version stays inspectable through the Task's version chain:

```
preparation history PREPARATION_ID
```

It accepts any version's ID and returns the Task's versions newest first, each with its full content, Source Material (`id`, `name`, `sha256`), Source Association evidence, Transformation Records, Correction Records, attachment slots and `status` (`active` / `superseded`), plus the Task ID and the current `active_id`.

## New imports cannot replace active work

A new import is not a replacement channel. When `prepare` finds a draft document whose Outreach Task already has an active Preparation from a **different** Source Material, it records a blocking document finding instead of creating or superseding anything:

| Document finding | Condition | Resolution |
| --- | --- | --- |
| `replacement_requires_rewrite` | The Task already has an active Preparation from another Source Material | `preparation rewrite ACTIVE_PREPARATION_ID --source SOURCE_ID` |

The detail names the active Preparation to replace. Active work, its corrections and its attachments are left untouched; nothing is superseded automatically. `imports findings IMPORT_ID` lists the finding. A successful Rewrite from that Source Material clears it.

Re-running `prepare` on the same import stays idempotent: a document whose Task already has an active Preparation **from the same Source Material** reuses that Preparation and adds nothing. Documents whose Task has no active Preparation still prepare normally, so a mixed import creates only the genuinely new Preparations.

## Persistence and snapshots

Preparation content, Superseded links and attachment bytes are stored locally and survive restart. Confirmed attachment bytes are snapshotted into the local store with their SHA-256 and are independent of later edits to the original file path, so a Superseded version's attachment still reads back as the bytes confirmed at the time. No conversion, merging or content modification is performed.

## Confirmation

Rewrite produces a new Preparation identity, so a future Confirmation bound to the replaced Preparation cannot transfer to the fresh one. Confirmation does not exist in this slice; the Rewrite slice records the distinct identity and Superseded link so Confirmation can bind to Preparations by identity when [ticket 05](../.scratch/smartmail-phase-one/issues/05-confirm-and-execute-controlled-adapter.md) introduces it.

Stopping or resolving an active Execution Attempt before rewriting is likewise deferred to the execution slice: this slice performs no execution, so there is nothing to stop.

## Not claimed

- No in-place editing of a Preparation, and no deletion of Superseded history.
- No automatic replacement from a new import, and no automatic carry-over of corrections or confirmed attachments.
- No re-derivation of content by rewriting the *same* Source Material into different text; a Rewrite replaces content with another preserved Source Material.
- No Execution Attempt handling, Confirmation transfer, scheduled-send cancellation or browser capability. Preparation and Rewrite remain local.

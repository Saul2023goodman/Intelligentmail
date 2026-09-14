# Supported Sending Plan Pattern 10

A Sending Plan proposes **when** a Campaign's Ready work will be sent, under constraints the Operator configures once: allowed windows, timezone, spacing between actions and a daily limit. The Operator reviews the whole batch, adjusts individual times, and confirms exact times. Nothing is placed in the mailbox yet: native scheduling is a separate, unverified capability (ticket 11), and a confirmed schedule is **never** carried out as an immediate send.

```powershell
plan configure --campaign CAMPAIGN_ID [--timezone TZ] [--window 'MON-FRI 09:00-17:00'] `
               [--spacing MINUTES] [--daily-limit N] [--horizon-days N]
plan propose --campaign CAMPAIGN_ID
plan list --campaign CAMPAIGN_ID
plan show PLAN_ID
plan adjust PLAN_ID --preparation PREPARATION_ID --time '2026-09-15T09:00'
plan confirm PLAN_ID
```

Every command accepts the global `--now ISO-8601` option, which fixes the store's instant. Planning, expiry and acceptance evidence are therefore reproducible.

## Configuration

`plan configure` stores the Campaign's constraints; calling it with no options returns them unchanged. An unconfigured Campaign starts from deterministic defaults: timezone `UTC`, `MON-FRI 09:00-17:00`, spacing `15` minutes, daily limit `20`, horizon `14` days.

- `--window` is repeatable. Each value is `DAYS HH:MM-HH:MM`, where `DAYS` is a comma-separated list or a forward range (`MON,TUE` or `MON-FRI`).
- The horizon is the number of local days searched, starting with the configured timezone's current day.
- An unsupported timezone (an IANA name is required), an unparsable window, an end not after its start, or a non-positive spacing, limit or horizon is refused with the offending constraint named. Nothing is stored.

## Proposal

`plan propose` assigns each Ready Preparation in the Campaign's deterministic Task order to the earliest allowed instant that honours every constraint:

- instants are generated inside the configured windows, stepping by the spacing, in the configured timezone;
- a wall-clock reading that the timezone skips (a daylight-saving jump) is never scheduled, so no action lands on an instant the Operator did not choose;
- an action keeps at least the configured spacing from the one before it, across window and day boundaries;
- at most the daily limit is placed per local day;
- the search stops at the horizon.

Proposals are reproducible: the same configuration, work and instant produce the same times. Re-proposing supersedes the Campaign's earlier **unconfirmed** proposal, which stays inspectable by ID.

Work that cannot be proposed is listed rather than silently dropped or squeezed in:

| Group | Meaning |
| --- | --- |
| `proposals` | scheduled actions with an exact time and timezone |
| `unavailable` | `not_ready` (a blocking readiness finding) or `already_sent` (Repeat Execution) |
| `impossible` | the configured constraints cannot provide a usable time; carries `reason`, the binding `constraint` (`daily_limit`, `spacing_minutes` or `windows`) and the arithmetic in `detail` |

`plan show` is the batch review: for every action it returns sender, recipient, subject, confirmed attachment labels with name, SHA-256 and size, readiness findings, readiness, the scheduled time with its timezone, the bound Confirmation (if any) and the **full message text**. Confirming never requires opening another command.

## Adjustment

`plan adjust PLAN_ID --preparation PREPARATION_ID --time TIME` sets one action's exact time before Confirmation. The time is an ISO-8601 reading: without an offset it is read in the plan's timezone, with one it is converted to it.

An adjustment is refused, naming the constraint, when the time is:

- in the past — an elapsed time always needs an explicitly chosen replacement;
- nonexistent in the plan's timezone;
- outside every allowed window, or on a day no window covers;
- closer than the configured spacing to another action of the plan;
- a breach of the daily limit for that local day.

The stored plan is unchanged by a refused adjustment. Adjusting an action that already carried a Confirmation **invalidates** it (`invalidated_reason: adjusted`) and returns the plan to `proposed`, because the authorization was bound to the previous exact time. A Reviewer who wants different constraints changes the configuration and re-proposes rather than smuggling a violation into a confirmed plan.

## Batch Confirmation

`plan confirm PLAN_ID` authorizes every scheduled action in one Operator action. Each action gets its **own** Confirmation — the same binding as ticket 05, plus the exact execution time:

```json
{"kind": "scheduled", "scheduled_at": "2026-09-15T09:00:00+08:00", "timezone": "Asia/Shanghai"}
```

- The whole batch is validated before anything is authorized: a superseded Preparation, a newly blocking finding, an already Sent action, or an elapsed time refuses the plan with nothing confirmed.
- Re-confirming unchanged content and times is idempotent and returns the same Confirmations; changed content renews (`renewed`).
- The plan reports `confirmed` only while every scheduled action carries a Confirmation.
- A superseded plan, or a plan with nothing to schedule, is refused.
- Confirmation is local. It makes no external request.

## Expiry

A confirmed time is bound to its instant. Once it has elapsed:

- `execution resume` (and any execution) pauses the Execution Flow with `confirmation_expired` and the detail that an explicitly confirmed replacement time is required;
- `plan confirm` refuses the plan, naming the elapsed action, until the Operator adjusts or re-proposes it;
- `plan adjust` refuses any time in the past.

The detail states the guarantee explicitly: SmartMail never substitutes an immediate send for an elapsed time.

## A confirmed schedule is not an immediate send

`execution run` refuses a `scheduled` Confirmation — before any Execution Attempt is recorded or any adapter request is made — with the message that placing and running a confirmed schedule requires the native mailbox scheduling capability, which is not enabled. Confirmed schedules are therefore never carried out early, and `immediate_send` remains the only enabled external capability.

## Persistence

The configuration, every plan with its proposals, and the Confirmations bound to them are stored locally and survive restart. Plan statuses (`proposed`, `confirmed`, `superseded`) are recomputed from the stored proposals, never inferred from a missing record.

## Not claimed

- No native 163.com schedule is created, removed or replaced; no Cancellation and no Recall (tickets 11, 12 and 13).
- No automatic placement when a confirmed time arrives: a schedule that has never been placed externally cannot send itself.
- No local timer substitutes for a mailbox-owned schedule, and no workflow sends anything without an Operator Confirmation.

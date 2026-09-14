# Ticket 10 Validation: Deterministic Sending Plans

Date: 2026-09-14
Scope: propose and confirm deterministic Sending Plans under configured windows, timezone, spacing and daily limits
Safety boundary: local planning and Confirmation only; native mailbox scheduling stays disabled, so a confirmed time is never carried out as an immediate send
Controlled time: every command ran with an explicit `--now`, so proposals, adjustments and expiry are reproducible

## Command-boundary verification

The ordinary suite drives Ticket 10 through the same `SmartMail` methods and terminal commands the Operator uses:

- `plan configure` / `plan propose` / `plan list` / `plan show`
- `plan adjust` / `plan confirm`
- `confirmation review` / `confirmation show`
- `execution run` / `execution resume` / `execution list` / `execution status`
- `sent list`

Final result:

```text
Ran 196 tests in 117.067s

OK (skipped=5)
```

Thirty-eight Ticket 10 tests cover configuration defaults and refusals, deterministic proposals, the configured spacing and daily limits, timezone resolution including a daylight-saving wall time that is skipped rather than silently shifted, plan review fields, impossible proposals, operator adjustment, batch Confirmation with renewal and invalidation, expiry, restart persistence, and the terminal shell. The five skips are the repository's existing opt-in representative-material cases.

## Representative terminal pilot

The pilot ran the terminal shell against the supplied private archive (`sample.zip`, SHA-256 `f2e73a53d3503c3568cfeba730317ba232f4258636d9f5560e10dea77398f5e2`) in a fresh local store, with controlled time and the controlled adapter available. It is retained as `.smartmail/ticket10-pilot.py` in the ignored local store and is not a repository artifact.

| Configuration | Value |
| --- | --- |
| Timezone | `Asia/Shanghai` |
| Allowed window | `MON-FRI 09:00-12:00` |
| Spacing | 60 minutes |
| Daily limit | 2 actions |
| Horizon | 3 days |
| Controlled instant | `2026-09-14T09:30:00+08:00` (Monday morning) |

### Proposal

`import` + `prepare` produced 17 Preparations. Four were made Ready; the plan scheduled exactly those and listed the remaining 13 as `unavailable` (`not_ready`), with no constraint violation:

| Action | Proposed time |
| --- | --- |
| 1 | `2026-09-14T10:00:00+08:00` |
| 2 | `2026-09-14T11:00:00+08:00` |
| 3 | `2026-09-15T09:00:00+08:00` |
| 4 | `2026-09-15T10:00:00+08:00` |

The 09:00 slot was already past at the controlled instant, both days stop at the daily limit of two, and every pair of times is an hour apart. `impossible` was empty because the constraints could accommodate the four Ready actions.

### Batch review

`plan show` returned the whole plan for review: sender `artsipei@163.com`, recipient `tammy.hulbert@rmit.edu.au`, subject `PhD supervision enquiry`, readiness `true`, the confirmed attachment `Sipei Yao - CV.docx` with SHA-256 `1a04f288ad733e18efdf5575b3fa3f04164c92e779ff652097734d398664d67e` (28,258 bytes) — the same CV binding as ticket 05 — and the full message text including the sign-off. No further command was needed before Confirmation.

### Impossible and elapsed adjustments are refused

| Attempt | Exit | Reported |
| --- | --- | --- |
| `--time 2026-09-14T13:00:00` (Monday, outside 09:00-12:00) | 2 | `The time 2026-09-14T13:00:00+08:00 is outside every allowed window of this Sending Plan (MON 13:00 in Asia/Shanghai)` |
| `--time 2026-09-14T09:15:00` (inside the window, already past) | 2 | `The time 2026-09-14T09:15:00+08:00 must be in the future; an elapsed time needs an explicitly confirmed replacement time` |

Neither attempt changed the stored plan. A permitted adjustment moved action 4 to `2026-09-15T11:30:00+08:00`.

### Batch Confirmation

`plan confirm` authorized all four actions and returned `confirmed`, one Confirmation each, bound to the exact Preparation and time:

```text
2026-09-14T10:00:00+08:00  →  {"kind": "scheduled", "scheduled_at": "2026-09-14T10:00:00+08:00", "timezone": "Asia/Shanghai"}
2026-09-14T11:00:00+08:00
2026-09-15T09:00:00+08:00
2026-09-15T11:30:00+08:00
```

`confirmation review` reported the same execution details, so the reviewed time and the authorized time are the same value.

## A confirmed schedule never becomes an immediate send

`execution run` on a confirmed schedule was refused **before** any Execution Attempt existed:

| Evidence | Value |
| --- | --- |
| Exit code | 2 |
| Error | `External execution kind is not enabled: scheduled; placing and running a confirmed schedule requires the native mailbox scheduling capability, which is not enabled` |
| Execution Attempts | 0 |
| Sent Records | 0 |
| Adapter requests | 0 |

## Expiry requires an explicitly confirmed replacement

With controlled time advanced to `2026-09-14T11:30:00+08:00` (past two confirmed times inside the same day):

| Evidence | Value |
| --- | --- |
| `execution resume` | paused |
| Execution Flow | `paused`, reason `confirmation_expired` |
| Detail | `The confirmed sending time has elapsed; an explicitly confirmed replacement time is required. SmartMail never substitutes an immediate send for an elapsed time` |
| Confirmation status | still `active` — an elapsed time is not a new authorization |
| Execution Attempts / Sent Records | 0 / 0 |
| `plan confirm` at that instant | refused, naming the elapsed action |

The Operator then chose replacement times explicitly (`2026-09-16T09:00:00+08:00`, `2026-09-16T10:00:00+08:00`), which invalidated the two affected Confirmations with `invalidated_reason: adjusted` and returned the plan to `proposed`. Re-confirming produced two new Confirmations for the two future actions, kept the two untouched ones, and released the expiry pause — after which `execution resume` refused again with the native-scheduling message rather than sending anything.

## Side effects and safety

No message was sent, scheduled, drafted, cancelled or cancelled-and-replaced: no Execution Attempt was created, no Sent Record was frozen, and no adapter request was made in the whole pilot. The plan, its Confirmations and the released pause live only in the local store. Native scheduling, cancellation and Recall remain disabled capabilities and are not claimed by this ticket.

## Acceptance criteria

| Criterion | Evidence |
| --- | --- |
| Configure allowed windows, timezone, spacing and daily limits; reproducible default proposals | `plan configure` persists and re-reads the configuration; identical configuration, work and instant reproduce identical times; unsupported timezone, window, spacing, limit or horizon is refused |
| Display all review fields and full messages before batch Confirmation; allow adjustment first | `plan show` returns sender, recipient, subject, attachments with SHA-256 and size, readiness, time and timezone plus the full message; `plan adjust` moved an action before Confirmation |
| Surface impossible proposals instead of silently violating constraints | `unavailable` and `impossible` groups carry `reason`, binding `constraint` and arithmetic; a property test asserts no scheduled time breaks the window, spacing or daily limit; violations are refused |
| Bind Confirmation to exact Preparation and execution times; changes require renewal | One Confirmation per action with `{"kind": "scheduled", "scheduled_at", "timezone"}`; unchanged re-confirmation is idempotent, a content change renews, and an adjusted time invalidates the prior Confirmation |
| Expired confirmed times require an explicitly confirmed replacement and never default to immediate | `plan confirm` and `plan adjust` refuse elapsed times; `execution resume` pauses with `confirmation_expired`; `execution run` refuses scheduled work entirely |
| Controlled time and the controlled adapter through the command boundary | The whole pilot ran through the terminal shell with `--now`; an unexpired scheduled Confirmation still refuses to execute while `immediate_send` stays the only enabled external capability |

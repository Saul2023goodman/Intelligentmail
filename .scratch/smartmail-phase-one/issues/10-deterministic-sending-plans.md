# 10: Propose and confirm deterministic Sending Plans

Status: resolved
Labels: implemented
Blocked by: 05

**What to build:** Generate and adjust sending times under explicit constraints, then confirm exact plans through the terminal.

## Acceptance criteria

- [x] Configure allowed windows, timezone, spacing, and daily limits; produce reproducible default proposals.
- [x] Display all review fields and access to full messages before batch Confirmation; allow operator adjustment before confirmation.
- [x] Surface impossible proposals instead of silently violating configured constraints.
- [x] Bind Confirmation to exact Preparation and execution times; changes require renewed Confirmation.
- [x] Expired confirmed times require an explicitly confirmed replacement time and never default to immediate sending.
- [x] Use controlled time and the controlled adapter through the command boundary to verify plan constraints, timezone handling, content changes, and expiry.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled external mailbox capabilities through the dedicated extension separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

## Comments

2026-09-14: Confirmed the seam with the operator before writing tests. Four decisions were settled:

1. **A new `plan` command group at the core boundary.** `configure_plan`, `propose_plan`, `list_plans`, `get_plan`, `adjust_plan` and `confirm_plan`, with the terminal gaining `plan configure|propose|list|show|adjust|confirm`. New `plan_configurations`, `sending_plans` and `sending_plan_proposals` tables; Confirmations keep the existing `confirmations` table and gain the `scheduled` execution kind (`{"kind": "scheduled", "scheduled_at": ..., "timezone": ...}`).
2. **A confirmed schedule is never carried out as an immediate send.** `execution run` refuses a `scheduled` Confirmation before any Execution Attempt is recorded or any adapter request is made, naming the unverified native scheduling capability. Placing real 163.com schedules stays ticket 11.
3. **Impossible proposals are surfaced, not hidden.** The plan returns `proposals`, `unavailable` and `impossible` groups; an impossible action carries `reason`, the binding `constraint` (`daily_limit`, `spacing_minutes` or `windows`) and the arithmetic in `detail`; no scheduled time ever violates a configured constraint.
4. **IANA timezones with controlled time.** `zoneinfo` with `tzdata` (added to `requirements.txt`) resolves the timezone; `SmartMail(home, mailbox=..., clock=...)` and the terminal's global `--now` fix the store's instant so planning and expiry are reproducible.

Implementation: `configure_plan` merges partial updates onto deterministic defaults and validates every constraint before storing; `propose_plan` generates allowed instants inside the configured windows in the configured timezone, steps by the spacing, enforces the spacing across window and day boundaries, caps each local day at the daily limit, bounds the search at the horizon, and skips a wall time the timezone skips; `get_plan` is the batch review including the full message per action; `adjust_plan` validates a single exact time against the plan's own configuration and invalidates the affected Confirmation (`adjusted`); `confirm_plan` validates the whole batch before authorizing and gives each action its own Confirmation bound to content, attachments and exact time. Confirming a superseded Preparation, a newly blocked finding, an already Sent action or an elapsed time refuses the batch with nothing confirmed. `_expired_detail` now states that an elapsed time requires an explicitly confirmed replacement and that SmartMail never substitutes an immediate send.

Completed TDD cycles at the core command/query seam plus the terminal shell: configuration and refusals, deterministic proposals with windows/spacing/daily limits, timezone resolution including a skipped daylight-saving wall time, plan review, impossible proposals, adjustment, batch Confirmation with renewal and invalidation, expiry, restart persistence, then CLI wiring with `--now`. Final run: **196 tests passed, 5 opt-in skips**.

Representative results (the supplied private archive `sample.zip`, controlled time, controlled adapter): 17 Preparations, four made Ready, proposed under `Asia/Shanghai` / `MON-FRI 09:00-12:00` / spacing 60 / daily limit 2 / horizon 3 at `2026-09-14T09:30:00+08:00` as `Mon 10:00`, `Mon 11:00`, `Tue 09:00`, `Tue 10:00`, with the remaining 13 listed as `unavailable` (`not_ready`) and none impossible. A time outside the window and a past time were both refused with exit 2 and the constraint named; the plan was unchanged. Batch Confirmation produced four `scheduled` Confirmations; `execution run` refused with zero attempts and zero Sent Records; after advancing the controlled time past two confirmed times, `execution resume` paused with `confirmation_expired` (Confirmation still `active`, still nothing sent), and explicitly chosen replacement times invalidated the two affected Confirmations (`adjusted`) before a clean renewal. 38 Ticket 10 tests cover the slice.

Pattern: [Supported Sending Plan Pattern 10](../../../docs/sending-plan-pattern-10.md). Results and pilot: [validation](../../../docs/ticket-10-validation.md). Native scheduling, cancellation and Scheduled Replacement are tickets 11, 12 and 13.


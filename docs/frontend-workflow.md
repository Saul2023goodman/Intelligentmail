# First frontend page

The React page maps the reference canvas to existing Core concepts, rather than
introducing a configurable workflow engine. Its node counts are sets of Outreach
Tasks and may overlap across Communication Actions. Connections describe supported
paths, not execution history or automatic transitions.

## Canonical lifecycle

```mermaid
flowchart LR
  A[Selected Student Mailbox] -->|read-only observation| B[Mailbox Observation]
  B --> C[SmartMail database]
  C -->|Reconciliation| D[Evidence and local matches]
  D --> E[Preparation duplicate check]
  E -->|no blocker| F[Draft Adjustment]
  E -->|suspicion or ambiguity| G[Operator review]
  F --> H[Revalidate and renew Confirmation]
  H --> I[Existing execution flow]
```

The arrow into the database means persistence of evidence, not a mailbox sync.
The database keeps external observations and local Preparations as separate
records. Reconciliation can create associations and findings; it never silently
changes a Preparation. A Draft Adjustment is valid only for an active local
Preparation whose external commitment is resolved.

| Stage | Existing Core evidence |
| --- | --- |
| 读取外部邮箱 | `refresh_mailbox` through the existing read-only 163 extension; produces a Mailbox Observation |
| SmartMail 数据库 | Persists Mailbox Observations, coverage and Reconciliation findings alongside local records |
| 比对与查重 | Read-time Reconciliation, followed by per-Preparation `check_duplicate` |
| Source materials | Campaign Outreach Tasks from `operations_report` |
| 更新 / 调整草稿 | Active `list_preparations`, Draft Adjustment corrections and source-based Rewrite |
| Ready preparation | Core readiness findings have zero blockers |
| Confirmation | Recorded active `list_confirmations`; execution still rechecks validity |
| Operator review | Task exceptions, Preparation blockers, or duplicate suspicion |
| Externally scheduled | Reported mailbox schedule observations |
| Sent record | Reported sent outcome backed by the execution ledger |
| Observed failure / Unknown outcome | Separate report states; never conflated |
| Associated reply | Ordinary reply received in Core follow-up evaluation |
| Follow-up due | Core Follow-up Rule eligibility |

The task inspector calls `report_task` for active Preparation content, attachment
associations, readiness findings, original Source Material names, duplicate
coverage and Execution Attempts. Campaign creation and duplicate checks directly
call `create_campaign` and `check_duplicate`. The editor calls atomic
`update_preparation_fields` (existing correction/readiness rules, with confirmation
invalidation) and `rewrite_local_preparation` (existing Rewrite plus a guard against
modifying external commitments). No UI code performs readiness,
duplicate, reply, scheduling or sending decisions.

## Local transport

The Vite development server proxies an allowlisted JSON protocol over private
stdio to one long-lived `python -m smartmail.ui` process. A single Core instance
avoids invoking restart recovery on every UI query. Vite binds to loopback and
requires same-origin JSON POST requests, with bounded request sizes and timeouts.
The Python bridge owns no network listener. It exposes mailbox observation and the
same Confirmation-bound execution operations used by Core. External write
capabilities remain disabled by default and can be enabled individually for an
explicit extension acceptance session through Vite startup environment flags. The
adapter uses a 20-second timeout within the UI bridge request deadline; Core still
rechecks capability, Confirmation, content and execution state before every action.
ADR-0001's extension Native Messaging boundary remains unchanged.

This is a local development frontend. `npm run build` checks and bundles the UI;
the static build and `vite preview` alone do not start the Core bridge. Startup
uses Core's existing lifecycle/recovery, just like the CLI. Do not open this
workspace against a store that is currently executing in another process.

Confirmation, scheduled replacement and follow-up creation use the existing guarded
Core commands. The UI can import a supported source set, prepare supported documents,
review readiness, read the connected mailbox, inspect saved observations and
reconciliation findings, correct local subject and recipient, confirm retained
attachment bytes, run duplicate checks, and Rewrite from an already imported
document. No sample campaigns or messages are inserted into the user store.

Enabled Follow-up automation confirms only the trigger policy: the operator saves a
versioned eligibility, template and trigger-time configuration. Core evaluates it and
creates at most one linked Ready Preparation for a due Task. That Preparation then
joins the global Batch execution Ready Pool; Batch execution remains the only owner
of selection, planning, exact sending Confirmation and execution safeguards. See
[the trigger-to-Ready-Pool design](followup-automation.md).

## Verification

`python -m unittest tests.test_ui` verifies real persisted report/detail payloads,
readiness blockers, duplicate coverage, isolated campaign scope, forbidden
commands, malformed protocol input and Unicode campaign persistence.
`npm run build` and `npm run lint` validate the frontend.

## 读取、入库、比对、草稿调整闭环

1. 操作员明确选择学生邮箱，连接该邮箱的 163 扩展，再点击读取。
2. Core 将邮件元数据、读取批次、状态和覆盖范围持久化，并运行现有对账逻辑。
3. 来源材料与 Mailbox Observation 共同作为数据库中的证据。导入材料负责显式建立任务关联；
   读取邮箱本身不会猜测学生、导师或 Campaign，也不会自动创建 Preparation。
4. 比对在读取时发生；查重由操作员在具体 Preparation 上发起，结果包含覆盖限制。
   重复疑似或冲突进入人工处理。历史批次保留，不把多次观察计作唯一邮件数。
5. 本地草稿可进行 Draft Adjustment，修改主题和收件人；正文替换使用导入文档的 Rewrite，保留旧版本。
   来源选择仅包含当前学生与 Campaign 的导入文档，Core 继续检查导师、机构匹配。
   修改后的草稿重新校验、查重和确认，再进入原有执行流程。
6. 已发送、已被替代、存在未知结果或外部定时承诺的 Preparation 不允许直接调整。
   定时替换仍走既有 Scheduled Replacement 流程。

外部草稿观察与 SmartMail 本地 Preparation 是两个模型。当前扩展提供的列表元数据
不是完整可编辑正文，也不构成覆盖本地草稿或向外部写回草稿的授权。

邮箱观察按学生邮箱保存，独立于 Campaign；任务、查重和草稿列表保持 Campaign 范围。
新入口的计数分别使用“学生邮箱”和“读取批次”，不会冒充任务数。

## 学生工作区切换

一位学生绑定一个邮箱与一个 Campaign，切换工作区即同时切换三者。切换入口是
`Topbar` 右侧常驻的工作区切换器（`src/app/scope-switcher.tsx`），在全部页面中
位置与行为一致：触发器显示当前学生、邮箱与网关状态点；展开面板列出全部学生，
每行给出邮箱、网关连接状态与读取批次，并在切换前说明切换后的网关后果（已连接、
需重连、尚未连接）。新增学生是面板底部独立的行动项，不与切换项同形。

作用域的唯一真源是 `src/app/scope.tsx` 中持久化的 `WorkspaceScope`，写入方只有
切换器与首次进入时的一次性选择；Workflow 页顶部只陈述当前工作区（Campaign、
邮箱、读取批次、任务数、网关），不再提供第二套切换控件，也不再保存第二份学生
状态。各页面继续只读取作用域，不自行改写。

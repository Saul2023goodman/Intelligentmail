import type { CSSProperties } from 'react'
import type { OutreachTask, StageId } from '../domain'
import { stages } from '../data'
import type { StageMeta } from '../data'
import { Icon } from '../icons'

/* ── Filters ────────────────────────────────────────────────────────────
   Every filter is a report enum, so the board and the reports page can
   never disagree. The chip is the state — no separate "apply" step.      */

export interface FilterDef {
  id: string
  label: string
  tone?: 'alarm'
  test: (t: OutreachTask) => boolean
}

export const filters: FilterDef[] = [
  {
    id: 'blocked',
    label: '受阻',
    tone: 'alarm',
    test: (t) => t.blockers.length > 0 || t.duplicate === 'repeat_execution',
  },
  {
    id: 'ready',
    label: '就绪待确认',
    test: (t) => t.stage === 'ready',
  },
  {
    id: 'unknown',
    label: '结果未知',
    test: (t) => t.status === 'unknown_outcome',
  },
  {
    id: 'conflict',
    label: '冲突',
    test: (t) =>
      t.blockers.some((b) => b.kind === 'recipient_conflict') ||
      t.duplicate === 'duplicate_suspicion',
  },
  {
    id: 'ambiguous',
    label: '歧义',
    test: (t) => t.reply === 'ambiguous' || t.duplicate === 'ambiguous_match',
  },
  {
    id: 'due',
    label: '跟进到期',
    test: (t) => t.followup.eligibility === 'due',
  },
]

export function applyFilters(
  tasks: OutreachTask[],
  active: Set<string>,
): OutreachTask[] {
  if (active.size === 0) return tasks
  const defs = filters.filter((f) => active.has(f.id))
  return tasks.filter((t) => defs.some((d) => d.test(t)))
}

/* ── Card signal ────────────────────────────────────────────────────── */

function cardSignal(t: OutreachTask, stage: StageMeta): StageMeta['signal'] {
  if (t.status === 'unknown_outcome' || t.reply === 'ambiguous') return 'unknown'
  if (t.duplicate === 'ambiguous_match') return 'unknown'
  if (t.blockers.length > 0 || t.duplicate === 'repeat_execution') return 'alarm'
  return stage.signal
}

function noteTone(t: OutreachTask): string {
  if (t.status === 'unknown_outcome' || t.reply === 'ambiguous') return 'unknown'
  if (t.blockers.length > 0 || t.duplicate === 'repeat_execution') return 'alarm'
  if (t.duplicate === 'duplicate_suspicion') return 'amber'
  if (t.stage === 'sent') return 'verified'
  return 'neutral'
}

/* ── Task card ──────────────────────────────────────────────────────── */

export function TaskCard({
  task,
  stage,
  selected,
  pulse,
  glide,
  reject,
  arriving,
  onSelect,
  onAction,
}: {
  task: OutreachTask
  stage: StageMeta
  selected: boolean
  pulse: boolean
  glide: boolean
  reject: boolean
  arriving: boolean
  onSelect: () => void
  onAction: () => void
}) {
  const signal = cardSignal(task, stage)
  const locked = task.stage === 'sent'

  return (
    <button
      className="card"
      data-signal={signal}
      data-selected={selected}
      data-pulse={pulse}
      data-glide={glide}
      data-reject={reject}
      data-arriving={arriving}
      data-locked={locked}
      onClick={onSelect}
      onDoubleClick={onAction}
      aria-pressed={selected}
      aria-label={`${task.id} ${task.student} 至 ${task.supervisor}，${stage.label}`}
      title={`${task.student} → ${task.supervisor}`}
    >
      <span className="card-signal" aria-hidden="true" />
      <span className="card-top">
        <span className="card-id mono">{task.id}</span>
        {task.plannedAt ? (
          <span
            className="card-time mono"
            data-armed={task.stage === 'ready' || task.stage === 'confirmed'}
          >
            {task.revisedFrom && <s>{task.revisedFrom}</s>}
            {task.plannedAt}
            {task.revisedFrom && <sup>a</sup>}
          </span>
        ) : task.sentRecord ? (
          <span className="card-time mono">{task.sentRecord.sentAt.slice(6)}</span>
        ) : null}
      </span>
      <span className="card-party">
        <span className="who">{task.student}</span>
        <Icon.arrowRight />
        <span className="target">{task.supervisor}</span>
      </span>
      {task.annotation ? (
        <span className="card-note" data-tone={noteTone(task)}>
          {task.annotation}
        </span>
      ) : stage.shortcut ? (
        <span className="card-key">
          <span className="kbd mono">{stage.shortcut}</span>
          {stage.action}
        </span>
      ) : null}
    </button>
  )
}

/* ── Track lane ─────────────────────────────────────────────────────── */

export function TrackLane({
  stage,
  tasks,
  selectedId,
  pulsingIds,
  glideId,
  rejectId,
  arrivingId,
  tail,
  onSelect,
  onAction,
  onTail,
}: {
  stage: StageMeta
  tasks: OutreachTask[]
  selectedId: string | null
  pulsingIds: Set<string>
  glideId: string | null
  rejectId: string | null
  arrivingId: string | null
  tail?: { label: string; count: number }
  onSelect: (id: string) => void
  onAction: (id: string) => void
  onTail?: () => void
}) {
  const actionable = ['verify', 'blocked', 'ready', 'followup'].includes(stage.id)
  const dim = stage.id === 'sent'

  return (
    <section
      className="lane"
      data-actionable={actionable}
      data-dim={dim}
      data-empty={tasks.length === 0 && !tail}
      aria-label={`${stage.label} ${stage.canonical}，${tasks.length} 项`}
      style={
        {
          '--lane-signal':
            stage.signal === 'unknown'
              ? 'var(--ink-3)'
              : stage.signal === 'mute'
                ? 'var(--ink-4)'
                : `var(--${stage.signal})`,
        } as CSSProperties
      }
    >
      <div className="lane-gutter">
        <span className="lane-count mono" aria-hidden="true">
          {String(tasks.length + (tail?.count ?? 0)).padStart(2, '0')}
        </span>
        <span className="lane-title">
          <span className="lane-label">{stage.label}</span>
          <span className="lane-canonical">{stage.canonical}</span>
        </span>
        <span className="lane-semantic" title={stage.semantic}>
          {stage.semantic}
        </span>
      </div>

      <div className="lane-stream">
        {tasks.length === 0 && !tail && (
          <span className="lane-empty">
            <Icon.shield size={13} />
            该轨道当前为空
          </span>
        )}
        {tasks.map((t) => (
          <TaskCard
            key={t.id}
            task={t}
            stage={stage}
            selected={t.id === selectedId}
            pulse={pulsingIds.has(t.id)}
            glide={t.id === glideId}
            reject={t.id === rejectId}
            arriving={t.id === arrivingId}
            onSelect={() => onSelect(t.id)}
            onAction={() => onAction(t.id)}
          />
        ))}
        {tail && (
          <button className="lane-more" onClick={onTail}>
            <Icon.layers size={13} />
            {tail.label}
            <span className="mono">＋{tail.count}</span>
          </button>
        )}
      </div>
    </section>
  )
}

/* ── List view: same data, same filters, higher working density ─────── */

const stageById = new Map<StageId, StageMeta>(stages.map((s) => [s.id, s]))

export function TaskTable({
  tasks,
  selectedId,
  onSelect,
  sort,
  onSort,
}: {
  tasks: OutreachTask[]
  selectedId: string | null
  onSelect: (id: string) => void
  sort: { key: string; dir: 'asc' | 'desc' }
  onSort: (key: string) => void
}) {
  const cols: { key: string; label: string }[] = [
    { key: 'id', label: '任务' },
    { key: 'student', label: '学生' },
    { key: 'supervisor', label: '主管' },
    { key: 'stage', label: '阶段' },
    { key: 'status', label: '消息状态' },
    { key: 'blockers', label: '阻断' },
    { key: 'duplicate', label: '查重' },
    { key: 'followup', label: '跟进' },
    { key: 'plannedAt', label: '计划时刻' },
  ]

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {cols.map((c) => (
              <th
                key={c.key}
                data-sort={sort.key === c.key ? sort.dir : undefined}
                aria-sort={
                  sort.key === c.key
                    ? sort.dir === 'asc'
                      ? 'ascending'
                      : 'descending'
                    : 'none'
                }
                onClick={() => onSort(c.key)}
              >
                {c.label}
                {sort.key === c.key && (sort.dir === 'asc' ? ' ↑' : ' ↓')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tasks.length === 0 && (
            <tr>
              <td colSpan={cols.length} className="table-empty">
                当前筛选无匹配任务 · 清除筛选后重试
              </td>
            </tr>
          )}
          {tasks.map((t) => {
            const st = stageById.get(t.stage)
            return (
              <tr
                key={t.id}
                data-selected={t.id === selectedId}
                onClick={() => onSelect(t.id)}
              >
                <td data-strong="true">{t.id}</td>
                <td style={{ color: 'var(--ink-1)' }}>{t.student}</td>
                <td>{t.supervisor}</td>
                <td>
                  <span
                    className="pill"
                    style={{
                      color:
                        st?.signal === 'alarm'
                          ? 'var(--alarm)'
                          : st?.signal === 'amber'
                            ? 'var(--amber)'
                            : st?.signal === 'verified'
                              ? 'var(--verified)'
                              : st?.signal === 'unknown'
                                ? 'var(--ink-2)'
                                : 'var(--cool)',
                      borderStyle: st?.signal === 'unknown' ? 'dashed' : 'solid',
                    }}
                  >
                    {t.stage}
                  </span>
                </td>
                <td className="mono" style={{ fontSize: 'var(--t-mini)' }}>
                  {t.status}
                </td>
                <td data-strong="true">
                  {t.blockers.length > 0 ? (
                    <span style={{ color: 'var(--alarm)' }}>
                      ✕{t.blockers.length}
                    </span>
                  ) : (
                    <span style={{ color: 'var(--ink-4)' }}>—</span>
                  )}
                </td>
                <td className="mono" style={{ fontSize: 'var(--t-mini)' }}>
                  {t.duplicate}
                </td>
                <td className="mono" style={{ fontSize: 'var(--t-mini)' }}>
                  {t.followup.eligibility}
                </td>
                <td data-strong="true">{t.plannedAt ?? '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

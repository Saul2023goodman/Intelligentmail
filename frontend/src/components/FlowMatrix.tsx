import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import type { OutreachTask, StageId } from '../domain'
import { stages } from '../data'

/* ── Row facts ───────────────────────────────────────────────────────────
   Every row answers the same four questions, left to right, in reading
   order: who is this, where on the journey, what is the matter now,
   and what do I do next. No empty matrix cells anywhere. */

function issueText(task: OutreachTask): string {
  if (task.stage === 'verify')
    return task.status === 'unknown_outcome' ? '结果未知' : '关联待裁决'
  if (task.stage === 'blocked') return task.blockers[0]?.label ?? '重复执行阻断'
  if (task.stage === 'ready') return '就绪不等于授权'
  if (task.stage === 'confirmed') return task.plannedAt ?? '授权已绑定，等待执行'
  if (task.stage === 'executing') return task.attempt?.note ?? '等待外部证据'
  if (task.stage === 'sent') return task.sentRecord?.sentAt ?? '记录已冻结'
  return `第 ${task.followup.round} 轮 · 需独立确认`
}

interface ActionMeta {
  label: string
  quiet: boolean
  kbd?: string
}

function actionMeta(task: OutreachTask): ActionMeta {
  switch (task.stage) {
    case 'verify':
      return {
        label: task.status === 'unknown_outcome' ? '立即对账' : '裁决回复',
        quiet: false,
        kbd: 'R',
      }
    case 'blocked':
      return {
        label: task.blockers[0]?.action ?? '裁决查重',
        quiet: false,
        kbd: 'E',
      }
    case 'ready':
      return { label: '确认发送', quiet: false, kbd: 'C' }
    case 'followup':
      return { label: '独立确认', quiet: false, kbd: 'C' }
    case 'confirmed':
      return { label: '查看许可', quiet: true }
    case 'executing':
      return { label: '查看证据', quiet: true }
    case 'sent':
      return { label: '查看记录', quiet: true }
  }
}

export function FlowMatrix({
  tasks,
  selectedId,
  onOpen,
  onPrimary,
  onBatchConfirm,
}: {
  tasks: OutreachTask[]
  selectedId: string | null
  onOpen: (id: string) => void
  onPrimary: (id: string) => void
  onBatchConfirm: (ids: string[]) => void
}) {
  /* The seven workflow states are themselves the filter: the state axis
     above the tracks carries each state's name, live count and toggle. */
  const [stageFilter, setStageFilter] = useState<StageId | null>(null)
  /* Batch selection is separate from detail selection: ticked rows reveal
     the contextual action strip without leaving the board. */
  const [checked, setChecked] = useState<ReadonlySet<string>>(() => new Set())
  const rows = useMemo(
    () => (stageFilter ? tasks.filter((t) => t.stage === stageFilter) : tasks),
    [tasks, stageFilter],
  )
  const counts = useMemo(() => {
    const map = new Map<StageId, number>()
    for (const s of stages) map.set(s.id, 0)
    for (const t of tasks) map.set(t.stage, (map.get(t.stage) ?? 0) + 1)
    return map
  }, [tasks])

  const toggleOne = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const someChecked = rows.some((t) => checked.has(t.id))
  const allChecked = rows.length > 0 && someChecked && rows.every((t) => checked.has(t.id))
  const toggleAll = () =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (allChecked) rows.forEach((t) => next.delete(t.id))
      else rows.forEach((t) => next.add(t.id))
      return next
    })

  /* Batch actions appear only once a context exists: a status filter or an
     explicit row selection. The readback gate accepts ready tasks. */
  const contextVisible = stageFilter !== null || checked.size > 0
  const batchTargets =
    checked.size > 0
      ? tasks.filter((t) => checked.has(t.id) && t.stage === 'ready').map((t) => t.id)
      : stageFilter
        ? rows.filter((t) => t.stage === 'ready').map((t) => t.id)
        : []

  /* FLIP — "position performs itself". Rows arrive already sorted by stage,
     so whenever a task crosses one, every displaced row glides to its new
     place instead of teleporting. WAAPI, --m-glide (260ms), one curve. */
  const rowEls = useRef(new Map<string, HTMLDivElement>())
  const lastRects = useRef(new Map<string, DOMRect>())
  const lastStageIndex = useRef(new Map<string, number>())

  /* Board and detail are never on screen together: the board is
     display:none exactly while a task is selected. Stage transitions
     happen while the board is hidden, so the FLIP comparison must run
     again when the board returns — hence selectedId in the deps. */
  const prevContextVisible = useRef(false)
  useLayoutEffect(() => {
    if (selectedId) {
      // hidden: preserve every recorded position
      prevContextVisible.current = contextVisible
      return
    }
    const chromeChanged = prevContextVisible.current !== contextVisible
    prevContextVisible.current = contextVisible
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    rows.forEach((task) => {
      const el = rowEls.current.get(task.id)
      if (!el) return
      /* A new commit can interrupt a glide still playing. Cancel it before
         measuring so getBoundingClientRect returns the true layout, never a
         transform-polluted rect — then invert from the real positions. */
      /* getAnimations() defaults to subtree:false — only animations whose
         target is this row, never the node animation inside it. */
      el.getAnimations().forEach((a) => a.cancel())
      const rect = el.getBoundingClientRect()
      if (rect.width === 0 && rect.height === 0) return
      const prev = lastRects.current.get(task.id)
      /* When the contextual strip enters or leaves it shifts every row.
         That is chrome, not a stage transition: refresh rects silently. */
      if (!chromeChanged && !reduce && prev) {
        const dy = prev.y - rect.y
        if (Math.abs(dy) > 0.5) {
          el.animate(
            { transform: [`translateY(${dy}px)`, 'translateY(0px)'] },
            { duration: 260, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'both' },
          )
        }
      }
      lastRects.current.set(task.id, rect)
    })
  }, [rows, selectedId, contextVisible])

  /* First-paint rects can be measured before the layout fully settles
     (fallback font metrics, banner wrapping): every row then sits a few
     pixels off, and the first real commit would invert against a phantom
     shift. Refresh the recorded rects twice silently — after a double
     animation frame, and once fonts are ready. Startup-only: it must never
     cancel glides created by later mutations. */
  useEffect(() => {
    let cancelled = false
    const fonts = document.fonts
    const remeasure = () => {
      if (cancelled) return
      rowEls.current.forEach((el, id) => {
        /* Never record a transform-polluted rect from a glide in flight */
        if (el.getAnimations().some((a) => a.playState === 'running')) return
        const rect = el.getBoundingClientRect()
        if (rect.width > 0 && rect.height > 0) lastRects.current.set(id, rect)
      })
    }
    const raf = requestAnimationFrame(() => requestAnimationFrame(remeasure))
    if (fonts.status !== 'loaded') fonts.ready.then(remeasure)
    else window.addEventListener('load', remeasure, { once: true })
    /* Chrome above the list (env / pause banners) can rewrap during the
       first ~100ms and move every row by a few pixels; a last silent
       baseline pass after settle absorbs whatever the earlier passes
       missed. It never cancels a glide already playing. */
    const settle = window.setTimeout(remeasure, 300)
    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      window.clearTimeout(settle)
      window.removeEventListener('load', remeasure)
    }
  }, [])

  /* Stage-index bookkeeping follows the glide: while the board is hidden
     nothing updates, so a node that crossed a stage still reads as
     "moved" when the board returns and performs its directional arrival.
     Once the glide has played, commit the new indices. */
  useEffect(() => {
    if (selectedId) return
    const t = window.setTimeout(() => {
      rows.forEach((task) =>
        lastStageIndex.current.set(
          task.id,
          stages.findIndex((s) => s.id === task.stage),
        ),
      )
    }, 245)
    return () => window.clearTimeout(t)
  }, [rows, selectedId])

  return (
    <section className="flow" aria-label="外联任务作业列表">
      <div className="flow-tools">
        <span className="flow-total mono">
          {rows.length} / {tasks.length} TASKS
        </span>
      </div>

      {contextVisible && (
        <div className="flow-context" key={stageFilter ? `f:${stageFilter}` : 'sel'}>
          <span className="ctx-summary">
            {stageFilter && (
              <button
                className="ctx-chip"
                data-stage={stageFilter}
                title="清除状态筛选"
                onClick={() => setStageFilter(null)}
              >
                {stages.find((s) => s.id === stageFilter)?.label}
                <b className="mono">{rows.length}</b>
                <span className="ctx-x" aria-hidden="true">×</span>
              </button>
            )}
            {checked.size > 0 && (
              <button
                className="ctx-chip ctx-chip-plain"
                title="清除已选任务"
                onClick={() => setChecked(new Set())}
              >
                已选
                <b className="mono">{checked.size}</b>
                <span className="ctx-x" aria-hidden="true">×</span>
              </button>
            )}
          </span>
          <span className="ctx-spacer" />
          {batchTargets.length > 0 ? (
            <button className="btn btn-primary btn-sm" onClick={() => onBatchConfirm(batchTargets)}>
              批量复核
              <span className="btn-count">{batchTargets.length}</span>
            </button>
          ) : (
            <span className="ctx-note">该状态暂无可批量执行的操作</span>
          )}
        </div>
      )}

      <div className="journey">
        <span className="sr-only">
          一行一个外联任务的连续轨道；上方七个状态标记带计数，点击可按状态筛选。
        </span>
        <div className="state-axis">
          <span className="axis-check">
            <input
              type="checkbox"
              className="row-check"
              aria-label="全选当前列表"
              checked={allChecked}
              ref={(el) => {
                if (el) el.indeterminate = someChecked && !allChecked
              }}
              onChange={toggleAll}
            />
          </span>
          <span className="micro axis-identity">任务 · OUTREACH</span>
          <div className="axis-track" role="group" aria-label="按工作流状态筛选">
            {stages.map((stage) => (
              <button
                key={stage.id}
                className="state-mark"
                data-stage={stage.id}
                data-active={stageFilter === stage.id}
                aria-pressed={stageFilter === stage.id}
                title={stage.semantic}
                onClick={() =>
                  setStageFilter(stageFilter === stage.id ? null : stage.id)
                }
              >
                <span className="state-dot" aria-hidden="true" />
                <span className="state-name">{stage.label}</span>
                <b className="state-count mono">{counts.get(stage.id) ?? 0}</b>
              </button>
            ))}
          </div>
          <span className="micro axis-issue">当前问题 · ISSUE</span>
          <span className="micro axis-action">下一步 · NEXT</span>
        </div>

        <div className="journey-list">
          {rows.map((task) => {
            const stageIndex = stages.findIndex((s) => s.id === task.stage)
            const prevStageIndex = lastStageIndex.current.get(task.id)
            const moved =
              prevStageIndex !== undefined && prevStageIndex !== stageIndex
            const glideFrom =
              moved && prevStageIndex !== undefined
                ? stageIndex > prevStageIndex
                  ? '8px'
                  : '-8px'
                : '0px'
            const meta = actionMeta(task)
            const moreBlockers =
              task.stage === 'blocked' ? task.blockers.length - 1 : 0
            return (
              <div
                key={task.id}
                className="journey-row"
                role="row"
                data-stage={task.stage}
                data-checked={checked.has(task.id)}
                data-selected={selectedId === task.id}
                ref={(el) => {
                  if (el) rowEls.current.set(task.id, el)
                  else rowEls.current.delete(task.id)
                }}
              >
                <span className="j-check">
                  <input
                    type="checkbox"
                    className="row-check"
                    checked={checked.has(task.id)}
                    onChange={() => toggleOne(task.id)}
                    aria-label={`选择任务 ${task.id}`}
                  />
                </span>

                <button
                  className="j-identity"
                  onClick={() => onOpen(task.id)}
                  aria-label={`打开任务 ${task.id} ${task.student}`}
                >
                  <span className="j-id-line">
                    <b className="mono">{task.id}</b>
                    <small>{task.action === 'follow_up' ? '跟进' : '初邮'}</small>
                  </span>
                  <span className="j-who">
                    {task.student}
                    <i aria-hidden="true">→</i>
                    {task.supervisor}
                  </span>
                </button>

                <div className="j-track">
                  <div
                    className="track"
                    style={{ '--idx': stageIndex } as CSSProperties}
                    role="img"
                    aria-label={`七站轨道，当前第 ${stageIndex + 1} 站：${stages[stageIndex].label}`}
                  >
                    {stages.map((stage, i) => (
                      <span className="track-cell" key={stage.id}>
                        <span
                          className={`track-node${
                            i < stageIndex
                              ? ' past'
                              : i === stageIndex
                                ? ' now'
                                : ''
                          }`}
                          data-stage={i === stageIndex ? stage.id : undefined}
                          data-moved={i === stageIndex && moved ? true : undefined}
                          style={
                            i === stageIndex && moved
                              ? ({ '--glide-from': glideFrom } as CSSProperties)
                              : undefined
                          }
                          title={`${i + 1}. ${stage.label}`}
                          aria-hidden="true"
                        />
                      </span>
                    ))}
                  </div>
                </div>

                <button
                  className="j-issue"
                  onClick={() => onOpen(task.id)}
                  aria-label={`${task.id}：${issueText(task)}，打开详细操作`}
                >
                  <span className="issue-dot" aria-hidden="true" />
                  <span className="issue-text">{issueText(task)}</span>
                  {moreBlockers > 0 && (
                    <span className="issue-more mono">+{moreBlockers}</span>
                  )}
                </button>

                <button
                  className={`j-action${meta.quiet ? ' is-quiet' : ''}`}
                  onClick={() => onPrimary(task.id)}
                  aria-label={`${meta.label} · ${task.id}`}
                >
                  <span className="j-action-label">{meta.label}</span>
                  {meta.kbd && <kbd className="j-kbd">{meta.kbd}</kbd>}
                </button>
              </div>
            )
          })}
        </div>

        {!rows.length && (
          <div className="flow-empty">
            该状态当前没有任务。
            <button className="btn btn-ghost" onClick={() => setStageFilter(null)}>
              显示全部状态
            </button>
          </div>
        )}
      </div>

      <footer className="flow-footer">
        <span>
          <i className="issue-dot" /> 颜色 = 当前状态
        </span>
        <span>状态标记即筛选器 · 每行一条连续轨道 · 外部结果以证据为准</span>
        <span className="mono">TRACK / {String(rows.length).padStart(2, '0')}</span>
      </footer>
    </section>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import type { RefObject } from 'react'
import type { OutreachTask } from '../domain'
import { stages } from '../data'
import { Icon } from '../icons'

/* ── Focus trap ─────────────────────────────────────────────────────── */

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])'

function useFocusTrap(ref: RefObject<HTMLElement | null>, active: boolean) {
  useEffect(() => {
    if (!active) return
    const node = ref.current
    if (!node) return
    const previous = document.activeElement as HTMLElement | null
    const first = node.querySelector<HTMLElement>(FOCUSABLE)
    first?.focus()

    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null,
      )
      if (items.length === 0) return
      const firstEl = items[0]
      const lastEl = items[items.length - 1]
      if (e.shiftKey && document.activeElement === firstEl) {
        e.preventDefault()
        lastEl.focus()
      } else if (!e.shiftKey && document.activeElement === lastEl) {
        e.preventDefault()
        firstEl.focus()
      }
    }
    node.addEventListener('keydown', onKey)
    return () => {
      node.removeEventListener('keydown', onKey)
      previous?.focus()
    }
  }, [ref, active])
}

/* ── Command palette ────────────────────────────────────────────────── */

function score(task: OutreachTask, q: string): number {
  const needle = q.toLowerCase()
  if (!needle) return 0
  if (task.id.toLowerCase() === needle) return 100
  if (task.id.toLowerCase().startsWith(needle)) return 80
  if (task.id.toLowerCase().includes(needle)) return 60
  if (task.student.toLowerCase().includes(needle)) return 50
  if (task.supervisor.toLowerCase().includes(needle)) return 45
  if (task.recipient.toLowerCase().includes(needle)) return 40
  if (task.subject.toLowerCase().includes(needle)) return 25
  if (task.mailbox.toLowerCase().includes(needle)) return 20
  return 0
}

export function CommandPalette({
  tasks,
  onSelect,
  onClose,
}: {
  tasks: OutreachTask[]
  onSelect: (id: string) => void
  onClose: () => void
}) {
  const [q, setQ] = useState('')
  const [cursor, setCursor] = useState(0)
  const panelRef = useRef<HTMLDivElement>(null)
  useFocusTrap(panelRef, true)

  const results = useMemo(() => {
    if (!q.trim()) return tasks.slice(0, 8)
    return tasks
      .map((t) => ({ t, s: score(t, q.trim()) }))
      .filter((r) => r.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 24)
      .map((r) => r.t)
  }, [q, tasks])

  useEffect(() => setCursor(0), [q])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        setCursor((c) => Math.min(c + 1, results.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setCursor((c) => Math.max(c - 1, 0))
      } else if (e.key === 'Enter') {
        e.preventDefault()
        const hit = results[cursor]
        if (hit) onSelect(hit.id)
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [results, cursor, onSelect, onClose])

  const stageLabel = (id: string) => stages.find((s) => s.id === id)?.label ?? id

  return (
    <div className="scrim palette-wrap" onMouseDown={onClose}>
      <div
        className="palette"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="命令面板"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="palette-input-row">
          <Icon.search size={16} />
          <input
            className="palette-input"
            value={q}
            placeholder="搜索任务编号、学生、主管、收件人或主题…"
            onChange={(e) => setQ(e.target.value)}
            aria-label="搜索"
            aria-controls="palette-results"
            autoComplete="off"
            spellCheck={false}
          />
          <span className="kbd mono">esc</span>
        </div>
        <div className="palette-results" id="palette-results" role="listbox">
          {results.length === 0 && (
            <div className="palette-group">
              <span style={{ fontSize: 'var(--t-body)', color: 'var(--ink-3)' }}>
                无匹配实体 · 全局搜索只检索实体，不执行动作
              </span>
            </div>
          )}
          {!q && <div className="palette-group micro">recent · 最近选中</div>}
          {q && <div className="palette-group micro">entities · {results.length}</div>}
          {results.map((t, i) => (
            <button
              key={t.id}
              className="palette-item"
              data-active={i === cursor}
              role="option"
              aria-selected={i === cursor}
              onMouseEnter={() => setCursor(i)}
              onClick={() => onSelect(t.id)}
            >
              <span className="palette-item-id mono">{t.id}</span>
              <span className="palette-item-main">
                <span className="palette-item-title">
                  {t.student} → {t.supervisor}
                </span>
                <span className="palette-item-sub mono">{t.recipient}</span>
              </span>
              <span className="micro">{stageLabel(t.stage)}</span>
            </button>
          ))}
        </div>
        <div className="palette-foot">
          <span className="palette-hint">
            <span className="kbd mono">↑↓</span> 选择
          </span>
          <span className="palette-hint">
            <span className="kbd mono">↵</span> 打开检查栏
          </span>
          <span className="palette-hint" style={{ marginLeft: 'auto' }}>
            <Icon.command size={11} /> 仅检索实体，不执行外发
          </span>
        </div>
      </div>
    </div>
  )
}

/* ── Precision confirm ────────────────────────────────────────────────
   The readback gate. The operator must scroll the frozen body to the end,
   tick the review box, and type the task number exactly. There is no path
   from "ready" to "sent" that bypasses this panel.                     */

export function ConfirmDialog({
  queue,
  index,
  onIndex,
  onCancel,
  onConfirm,
}: {
  queue: OutreachTask[]
  index: number
  onIndex: (i: number) => void
  onCancel: () => void
  onConfirm: (task: OutreachTask, mode: 'immediate' | 'plan', expiresAt: string) => void
}) {
  const task = queue[index]
  const panelRef = useRef<HTMLDivElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const [bodyRead, setBodyRead] = useState(false)
  const [reviewed, setReviewed] = useState(false)
  const [readback, setReadback] = useState('')
  const [touched, setTouched] = useState(false)
  const [mode, setMode] = useState<'immediate' | 'plan'>('immediate')
  const [expiresAt, setExpiresAt] = useState('2026-09-16 18:00')
  useFocusTrap(panelRef, true)

  const matches = readback.trim().toUpperCase() === task.id.toUpperCase()
  const unlocked = matches && reviewed

  /* Every task in a batch gets its own gate. State resets on move. */
  useEffect(() => {
    setBodyRead(false)
    setReviewed(false)
    setReadback('')
    setTouched(false)
    setMode('immediate')
  }, [task.id])

  useEffect(() => {
    const el = bodyRef.current
    if (!el) return
    if (el.scrollHeight <= el.clientHeight + 2) setBodyRead(true)
  }, [task.id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onCancel()
      }
      /* Enter never skips the gate: it only submits once readback matches. */
      if (e.key === 'Enter' && unlocked) {
        e.preventDefault()
        onConfirm(task, mode, expiresAt)
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [unlocked, task, mode, expiresAt, onCancel, onConfirm])

  const onBodyScroll = () => {
    const el = bodyRef.current
    if (!el) return
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 6) setBodyRead(true)
  }

  const dup = task.duplicate
  const cov = task.coverage

  return (
    <div className="scrim confirm-wrap" onMouseDown={onCancel}>
      <div
        className="confirm"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="confirm-head">
          <span className="confirm-head-icon" aria-hidden="true">
            <Icon.lock size={13} />
          </span>
          <span>
            <span className="confirm-title" id="confirm-title">
              发送确认 · 请逐字复核并输入任务编号
            </span>
            <span className="confirm-sub">
              弹层内全部只读。要修改内容请先取消 — 编辑会使既有确认失效。
            </span>
          </span>
          {queue.length > 1 && (
            <span className="confirm-batch mono">
              {index + 1} / {queue.length}
            </span>
          )}
          <button className="icon-btn" onClick={onCancel} aria-label="取消">
            <Icon.close size={15} />
          </button>
        </div>

        <div className="confirm-scroll">
          <div className="confirm-frozen">
            <div className="confirm-frozen-head">
              <span className="micro">冻结快照 · frozen at confirmation</span>
              <Icon.shield size={11} />
            </div>
            <div className="confirm-grid">
              <div className="confirm-row">
                <span className="field-label">任务</span>
                <span className="field-value mono" data-mono="true" style={{ fontWeight: 600 }}>
                  {task.id}
                </span>
              </div>
              <div className="confirm-row">
                <span className="field-label">发件人</span>
                <span className="field-value mono" data-mono="true">
                  {task.sender}
                </span>
              </div>
              <div className="confirm-row">
                <span className="field-label">收件人</span>
                <span className="field-value mono" data-mono="true">
                  {task.recipient}
                  {task.supervisorAliases.includes(task.recipient) && (
                    <span style={{ color: 'var(--ink-3)', marginLeft: 9, fontSize: 'var(--t-mini)' }}>
                      主管已登记地址
                    </span>
                  )}
                </span>
              </div>
              <div className="confirm-row">
                <span className="field-label">主题</span>
                <span className="field-value">{task.subject}</span>
              </div>
              <div className="confirm-row">
                <span className="field-label">查重</span>
                <span className="field-value" style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  <span className={`pill pill-solid ${dup === 'no_duplicate_found' ? 'pill-verified' : dup === 'repeat_execution' ? 'pill-alarm' : 'pill-caution'}`}>
                    {dup}
                  </span>
                  <span style={{ fontSize: 'var(--t-mini)', color: 'var(--ink-3)' }}>
                    覆盖度{' '}
                    {cov.folders.map((f) => `${f.folder} ${f.pages}/${f.pagesTotal} 页`).join(' · ')}
                    {cov.blindSpots.length > 0 && ` · 盲区 ${cov.blindSpots.length} 项见明细`}
                  </span>
                </span>
              </div>
            </div>
          </div>

          {task.attachments.length > 0 && (
            <div className="sect">
              <div className="sect-head">
                <span className="micro">附件 · 指纹已冻结</span>
              </div>
              <div className="confirm-attach">
                {task.attachments.map((a) => (
                  <div className="confirm-attach-row" key={a.id}>
                    <Icon.paperclip size={13} />
                    <span>{a.name}</span>
                    <span className="dim">{Math.round(a.bytes / 1024)} KB</span>
                    <span className="sha">sha {a.sha}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="sect">
            <div className="sect-head">
              <span className="micro">正文 · 需滚动到底</span>
            </div>
            <div
              className="confirm-body"
              ref={bodyRef}
              onScroll={onBodyScroll}
              data-read={bodyRead}
              tabIndex={0}
              role="region"
              aria-label="冻结正文，需滚动到底部"
            >
              {task.body}
            </div>
            <div className="confirm-scrollcue" data-done={bodyRead}>
              {bodyRead ? (
                <>
                  <Icon.shield size={11} /> 已读至末尾 · 全文 {task.body.length} 字符
                </>
              ) : (
                <>
                  <Icon.chevronDown size={11} /> 向下滚动以读完整封正文
                </>
              )}
            </div>
          </div>

          <div className="sect">
            <div className="sect-head">
              <span className="micro">执行方式 · execution</span>
            </div>
            <div className="radios" role="radiogroup" aria-label="执行方式">
              <button
                className="radio"
                role="radio"
                aria-checked={mode === 'immediate'}
                onClick={() => setMode('immediate')}
              >
                <span className="radio-dot" aria-hidden="true" />
                <span className="radio-text">
                  <span className="radio-label">确认后立即发送</span>
                  <span className="radio-note">
                    进入 Execution Flow，已发箱取得唯一匹配证据后判定为 sent
                  </span>
                </span>
              </button>
              <button
                className="radio"
                role="radio"
                aria-checked={mode === 'plan'}
                onClick={() => setMode('plan')}
              >
                <span className="radio-dot" aria-hidden="true" />
                <span className="radio-text">
                  <span className="radio-label">加入发送计划 #7</span>
                  <span className="radio-note">
                    Asia/Shanghai · 周一至五 09:00–17:00 · 间隔 60′ · 日上限 2
                  </span>
                </span>
              </button>
              <button className="radio" role="radio" aria-checked={false} aria-disabled="true" disabled>
                <span className="radio-dot" aria-hidden="true" />
                <span className="radio-text">
                  <span className="radio-label">
                    提交为外部原生定时{' '}
                    <Icon.compass size={11} style={{ display: 'inline', verticalAlign: '-1px' }} />
                  </span>
                  <span className="radio-note">
                    能力 native_schedule 未验收 · 可见但不可用
                  </span>
                </span>
              </button>
            </div>
          </div>

          <div className="confirm-row">
            <span className="field-label">有效期</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <input
                className="input mono"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                aria-label="确认有效期（可选）"
                style={{ width: 190 }}
              />
              <span style={{ fontSize: 'var(--t-mini)', color: 'var(--ink-3)' }}>
                过期后必须重新确认，系统永不降级为立即发送
              </span>
            </span>
          </div>

          <div className="readback">
            <label className="readback-label" htmlFor="readback">
              输入任务编号 <span className="mono">{task.id}</span> 以确认
            </label>
            <input
              id="readback"
              className="readback-input mono"
              value={readback}
              placeholder={task.id.replace(/[A-Z0-9]/gi, '·')}
              onChange={(e) => {
                setReadback(e.target.value)
                setTouched(true)
              }}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={touched && !matches}
              aria-describedby={touched && !matches ? 'readback-err' : undefined}
            />
            {touched && readback.length > 0 && !matches && (
              <span className="readback-error" id="readback-err" role="alert">
                <Icon.alert />
                编号不匹配 — 必须与 {task.id} 完全一致才能解锁确认
              </span>
            )}
            <button
              className="check"
              role="checkbox"
              aria-checked={reviewed}
              disabled={!bodyRead}
              onClick={() => bodyRead && setReviewed((v) => !v)}
            >
              <span className="check-box" aria-hidden="true">
                <Icon.check />
              </span>
              <span>
                我已逐字核对以上精确内容、附件指纹与覆盖度盲区
                {!bodyRead && (
                  <span style={{ color: 'var(--ink-4)' }}> · 需先读完正文</span>
                )}
              </span>
            </button>
          </div>
        </div>

        <div className="confirm-foot">
          <span className="confirm-foot-note">
            <Icon.shield />
            {unlocked
              ? '提交前 Native Host 复核的摘要与本页冻结的是同一组 SHA'
              : '确认键已锁定 · 输入编号并勾选复核'}
          </span>
          <span className="confirm-foot-actions">
            {queue.length > 1 && (
              <>
                <button
                  className="btn btn-ghost"
                  onClick={() => onIndex((index - 1 + queue.length) % queue.length)}
                  aria-label="上一条"
                >
                  <Icon.chevronDown size={13} style={{ transform: 'rotate(90deg)' }} />
                </button>
                <button
                  className="btn btn-ghost"
                  onClick={() => onIndex((index + 1) % queue.length)}
                  aria-label="下一条"
                >
                  <Icon.chevronDown size={13} style={{ transform: 'rotate(-90deg)' }} />
                </button>
              </>
            )}
            <button className="btn btn-ghost" onClick={onCancel}>
              取消
            </button>
            <button
              className="btn btn-primary"
              disabled={!unlocked}
              data-unlocked={unlocked}
              onClick={() => onConfirm(task, mode, expiresAt)}
            >
              确认发送
              <span className="kbd" style={{ borderColor: 'rgba(23,17,10,.3)', color: '#17110a' }}>
                ↵
              </span>
            </button>
          </span>
        </div>
      </div>
    </div>
  )
}

/* ── Toasts ─────────────────────────────────────────────────────────
   Completion and notice only. Blocking information must never live here —
   it belongs in a queue with a count.                                 */

export interface Toast {
  id: number
  text: string
  tone: 'neutral' | 'verified' | 'alarm' | 'unknown'
  leaving?: boolean
  undo?: () => void
}

export function Toasts({ items }: { items: Toast[] }) {
  return (
    <div className="toasts" aria-live="polite" aria-atomic="false">
      {items.map((t) => (
        <div className="toast" key={t.id} data-tone={t.tone} data-leaving={t.leaving}>
          {t.tone === 'verified' ? (
            <Icon.shield size={14} />
          ) : t.tone === 'alarm' ? (
            <Icon.alert size={14} />
          ) : (
            <Icon.diamond size={13} />
          )}
          <span>{t.text}</span>
          {t.undo && (
            <button className="toast-undo" onClick={t.undo}>
              撤销
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

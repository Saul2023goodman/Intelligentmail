import { useState } from 'react'
import type { Attachment, Blocker, OutreachTask } from '../domain'
import { Icon } from '../icons'

/* ── Stage gates ──────────────────────────────────────────────────────
   Prepared → Ready → Confirmed → Executing → Sent. Five gates that are
   never merged into one bar, because readiness is never authorisation.  */

const GATES = ['已制备', '就绪', '已确认', '执行中', '已发送'] as const

function gateIndex(t: OutreachTask): { index: number; alarm: boolean } {
  if (t.sentRecord) return { index: 4, alarm: false }
  if (t.attempt) return { index: 3, alarm: false }
  if (t.readiness === 'confirmed') return { index: 2, alarm: false }
  if (t.blockers.length > 0 || t.duplicate === 'repeat_execution')
    return { index: 1, alarm: true }
  return { index: 1, alarm: false }
}

function Stepper({ task }: { task: OutreachTask }) {
  const { index, alarm } = gateIndex(task)
  return (
    <div className="stepper">
      {GATES.map((g, i) => {
        const state =
          i < index ? 'done' : i === index ? (alarm ? 'current-alarm' : 'current') : 'todo'
        return (
          <div className="step" key={g} data-state={state} style={{ flex: i === 0 ? 'none' : undefined }}>
            <span className="step-dot" aria-hidden="true" />
            <span className="step-label">
              {i === index && alarm ? '受阻' : g}
            </span>
            {i < GATES.length - 1 && <span className="step-line" data-done={i < index} />}
          </div>
        )
      })}
    </div>
  )
}

/* ── Evidence coverage ────────────────────────────────────────────────
   Segmented, not smooth: one segment per requested page. A gap in the
   meter is a real gap in the evidence, and it is always shown next to
   the conclusion it qualifies.                                        */

function Coverage({ task }: { task: OutreachTask }) {
  return (
    <div className="coverage">
      {task.coverage.folders.map((f) => (
        <div className="cov-row" key={f.folder}>
          <span className="cov-name">{f.folder}</span>
          <span
            className="cov-meter"
            role="img"
            aria-label={`${f.folder} 覆盖 ${f.pages}/${f.pagesTotal} 页，枚举 ${f.enumerated}/${f.declared} 条`}
          >
            {Array.from({ length: f.pagesTotal }, (_, i) => (
              <span className="cov-seg" key={i} data-filled={i < f.pages} />
            ))}
          </span>
          <span className="cov-num mono">
            {f.pages}/{f.pagesTotal} 页
          </span>
        </div>
      ))}
      {task.coverage.folders.some((f) => f.enumerated < f.declared) && (
        <div className="cov-row">
          <span className="cov-name" />
          <span className="cov-blind-item" style={{ gridColumn: '2 / span 2' }}>
            <Icon.alert />
            枚举 {task.coverage.folders.reduce((a, f) => a + f.enumerated, 0)} /{' '}
            {task.coverage.folders.reduce((a, f) => a + f.declared, 0)} 条
          </span>
        </div>
      )}
      {task.coverage.blindSpots.length > 0 && (
        <div className="cov-blind">
          {task.coverage.blindSpots.map((b) => (
            <span className="cov-blind-item" key={b}>
              <Icon.eye />
              {b}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

const duplicateCopy: Record<
  OutreachTask['duplicate'],
  { label: string; cls: string; note: string }
> = {
  unchecked: { label: '未查重', cls: 'pill-mute', note: '执行前必须运行查重' },
  no_duplicate_found: {
    label: '未发现重复',
    cls: 'pill-verified',
    note: '支持范围内未发现更多 — 非全邮箱证明',
  },
  duplicate_suspicion: {
    label: '疑似重复',
    cls: 'pill-amber',
    note: '待裁决，未裁决前不可授权',
  },
  ambiguous_match: {
    label: '歧义匹配',
    cls: 'pill-amber',
    note: '身份或覆盖不足，待人工裁决',
  },
  repeat_execution: {
    label: '重复执行',
    cls: 'pill-alarm',
    note: '硬阻断，禁止进入授权',
  },
  linked_follow_up: {
    label: '已关联跟进',
    cls: 'pill-cool',
    note: '非重复初邮，不按初邮口径查重',
  },
}

/* ── Attachment rows ────────────────────────────────────────────────── */

function AttachmentRow({
  a,
  onConfirm,
  onReplace,
}: {
  a: Attachment
  onConfirm?: () => void
  onReplace?: () => void
}) {
  if (a.state === 'missing') {
    return (
      <div className="attach" data-state="missing">
        <span className="attach-icon">
          <Icon.alert size={14} />
        </span>
        <span className="attach-body">
          <span className="attach-name">{a.name}</span>
          <span className="attach-meta">
            <span style={{ color: 'var(--alarm)' }}>缺失 · 阻断</span>
          </span>
        </span>
        <span className="attach-actions">
          <button className="btn btn-quiet" onClick={onReplace}>
            选择文件
          </button>
        </span>
      </div>
    )
  }
  return (
    <div className="attach">
      <span className="attach-icon">
        <Icon.paperclip size={14} />
      </span>
      <span className="attach-body">
        <span className="attach-name">{a.name}</span>
        <span className="attach-meta">
          <span>{Math.round(a.bytes / 1024)} KB</span>
          <span className="sha">sha {a.sha}</span>
          {a.state === 'advisory' && <span style={{ color: 'var(--amber)' }}>建议</span>}
          {a.state === 'confirmed' && <span style={{ color: 'var(--verified)' }}>已确认</span>}
        </span>
      </span>
      <span className="attach-actions">
        {a.state === 'advisory' && (
          <button className="btn btn-quiet" onClick={onConfirm}>
            确认
          </button>
        )}
        <button className="btn btn-quiet" onClick={onReplace}>
          替换
        </button>
      </span>
    </div>
  )
}

/* ── Blocker rows ───────────────────────────────────────────────────── */

function BlockerRow({ b, onResolve }: { b: Blocker; onResolve: () => void }) {
  return (
    <div className="blocker" data-tone="alarm">
      <span className="blocker-mark">
        <Icon.close size={14} />
      </span>
      <span className="blocker-body">
        <span className="blocker-text">{b.label}</span>
        <span className="blocker-kind">{b.kind.replace(/_/g, ' ')}</span>
        <span>
          <button className="btn btn-quiet" onClick={onResolve} style={{ paddingLeft: 0 }}>
            {b.action}
            <span className="kbd mono" style={{ marginLeft: 2 }}>
              {b.shortcut}
            </span>
          </button>
        </span>
      </span>
    </div>
  )
}

/* ── Empty inspector ──────────────────────────────────────────────────
   A keyboard sheet, never decorative art.                              */

const KEYBINDINGS: [string, string, string][] = [
  ['J', '下一个任务', 'board'],
  ['K', '上一个任务', 'board'],
  ['E', '就地修正阻断项', 'blocked'],
  ['C', '打开精确确认', 'ready'],
  ['R', '对账 / 裁决', 'verify'],
  ['A', '处理附件槽位', 'any'],
  ['/', '聚焦搜索', 'global'],
  ['⌘K', '命令面板', 'global'],
  ['↵', '暂停横幅主动作', 'paused'],
  ['Esc', '关闭弹层 / 取消选中', 'global'],
]

function EmptyInspector({ trackCount }: { trackCount: number }) {
  return (
    <div className="insp-empty">
      <div className="sect">
        <div className="sect-head">
          <span className="micro">态势 · situation</span>
        </div>
        <p style={{ fontSize: 'var(--t-body)', color: 'var(--ink-2)', lineHeight: 1.6 }}>
          共 <b className="mono" style={{ color: 'var(--ink-1)' }}>{trackCount}</b>{' '}
          个在制任务，按所处阶段自动归轨。位置即状态 —
          卡片所在的轨道就是它当前的阶段，无需再读状态徽章。
        </p>
        <p style={{ fontSize: 'var(--t-label)', color: 'var(--ink-3)', lineHeight: 1.6 }}>
          选中任意任务以在此展开它的全部证据与当前唯一可执行动作。
        </p>
      </div>
      <div className="sect">
        <div className="sect-head">
          <span className="micro">键盘 · keyboard</span>
        </div>
        <div className="keys">
          {KEYBINDINGS.map(([k, desc, scope]) => (
            <div className="key-row" key={k + desc}>
              <span className="kbd mono">{k}</span>
              <span className="key-desc">{desc}</span>
              <span className="key-scope">{scope}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="sect">
        <div className="sect-head">
          <span className="micro">诚实性 · honesty</span>
        </div>
        <ul style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {[
            '就绪不等于授权 — 两级视觉与两个不同 CTA',
            '结果未知永远是虚线空心，不判成功或失败',
            '「未发现重复」必须与覆盖度缺口同屏',
            '已发送记录不可变，无任何编辑入口',
          ].map((t) => (
            <li
              key={t}
              style={{
                display: 'flex',
                gap: 7,
                fontSize: 'var(--t-label)',
                color: 'var(--ink-3)',
                lineHeight: 1.5,
              }}
            >
              <span style={{ color: 'var(--ink-4)', flex: 'none', marginTop: 2 }}>
                <Icon.shield size={11} />
              </span>
              {t}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

/* ── Inspector ──────────────────────────────────────────────────────── */

export function Inspector({
  task,
  trackCount,
  onClose,
  onResolveBlocker,
  onConfirmSend,
  onReconcile,
  onAdjudicate,
  onConfirmAttachment,
  onPrimary,
  primaryDisabledReason,
}: {
  task: OutreachTask | null
  trackCount: number
  onClose: () => void
  onResolveBlocker: (taskId: string, blockerId: string) => void
  onConfirmSend: (taskId: string) => void
  onReconcile: (taskId: string) => void
  onAdjudicate: (taskId: string) => void
  onConfirmAttachment: (taskId: string, attachmentId: string) => void
  onPrimary: (taskId: string) => void
  primaryDisabledReason: string | null
}) {
  const [showInstitution, setShowInstitution] = useState(false)

  if (!task) {
    return (
      <aside className="inspector" aria-label="任务检查">
        <div className="insp-head">
          <span className="micro">任务检查 · inspector</span>
        </div>
        <EmptyInspector trackCount={trackCount} />
      </aside>
    )
  }

  const dup = duplicateCopy[task.duplicate]
  const hardBlocked = task.duplicate === 'repeat_execution'
  const blockerCount = task.blockers.length + (hardBlocked ? 1 : 0)

  /* The primary action changes with the stage — there is never a
     "ready means send" shortcut anywhere in the product. */
  let primary: { label: string; shortcut?: string; kind: 'primary' | 'ghost' | 'danger' }
  let onPrimaryClick = () => onPrimary(task.id)

  if (task.status === 'unknown_outcome') {
    primary = { label: '立即对账', shortcut: 'R', kind: 'primary' }
    onPrimaryClick = () => onReconcile(task.id)
  } else if (task.reply === 'ambiguous' || task.duplicate === 'ambiguous_match') {
    primary = { label: '裁决归属', shortcut: 'R', kind: 'primary' }
    onPrimaryClick = () => onAdjudicate(task.id)
  } else if (blockerCount > 0) {
    primary = { label: '确认发送', shortcut: 'C', kind: 'primary' }
    onPrimaryClick = () => onConfirmSend(task.id)
  } else if (task.stage === 'ready') {
    primary = { label: '确认发送', shortcut: 'C', kind: 'primary' }
    onPrimaryClick = () => onConfirmSend(task.id)
  } else if (task.stage === 'confirmed') {
    primary = { label: '加入执行批次', kind: 'primary' }
  } else if (task.stage === 'executing') {
    primary = { label: '查看三阶段证据', kind: 'ghost' }
  } else if (task.stage === 'sent') {
    primary = { label: '发起链接的跟进', kind: 'ghost' }
  } else if (task.followup.eligibility === 'due') {
    primary = { label: '制备跟进', shortcut: 'C', kind: 'primary' }
  } else {
    primary = { label: '查看许可', kind: 'ghost' }
  }

  const locked = blockerCount > 0 || !!primaryDisabledReason

  return (
    <aside className="inspector" aria-label={`任务检查 ${task.id}`}>
      <div className="insp-head">
        <span className="micro">任务检查 · inspector</span>
        <button className="icon-btn" onClick={onClose} aria-label="取消选中">
          <Icon.close size={14} />
        </button>
      </div>

      <div className="insp-scroll">
        {/* L0 — who is this task about */}
        <div>
          <div className="insp-id-row">
            <span className="insp-id mono">{task.id}</span>
            {task.status === 'unknown_outcome' ? (
              <span className="pill pill-unknown">unknown</span>
            ) : task.stage === 'sent' ? (
              <span className="pill pill-verified pill-solid">sent</span>
            ) : blockerCount > 0 ? (
              <span className="pill pill-alarm pill-solid">blocked</span>
            ) : task.readiness === 'confirmed' ? (
              <span className="pill pill-cool pill-diamond">confirmed</span>
            ) : (
              <span className="pill pill-amber pill-diamond">ready</span>
            )}
          </div>

          <div className="insp-parties">
            <span className="insp-student">{task.student}</span>
            <span className="insp-arrow-row">
              <Icon.arrowRight />
              <span>{task.supervisor}</span>
              {task.supervisorAliases.length > 1 && (
                <sup style={{ color: 'var(--ink-4)', fontSize: 9 }}>
                  {task.supervisorAliases.length}
                </sup>
              )}
              <button
                className="insp-sup-toggle"
                onClick={() => setShowInstitution((v) => !v)}
                aria-expanded={showInstitution}
              >
                {showInstitution ? '收起' : '院校与别名'}
              </button>
            </span>
            {showInstitution && (
              <div className="insp-sup-detail">
                <span>{task.institution || '未登记院校'}</span>
                {task.supervisorAliases.map((a) => (
                  <span className="mono" key={a} style={{ fontSize: 'var(--t-mini)' }}>
                    {a}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="insp-facts">
            <span>
              <span className="micro">邮箱</span> <b>{task.mailbox}</b>
            </span>
            <span>
              <span className="micro">动作</span>{' '}
              <b>{task.action === 'follow_up' ? '跟进' : '初次外联'}</b>
            </span>
            <span>
              <span className="micro">作用域</span> <b>Campaign 内</b>
            </span>
          </div>
        </div>

        {/* L2 — stage */}
        <div className="sect">
          <div className="sect-head">
            <span className="micro">阶段 · stage</span>
          </div>
          <Stepper task={task} />
        </div>

        {/* Attempt phases, inline — never a separate page for this */}
        {task.attempt && (
          <div className="sect">
            <div className="sect-head">
              <span className="micro">执行尝试 · attempt</span>
            </div>
            <div className="blocker" data-tone={task.status === 'unknown_outcome' ? 'mute' : 'amber'}>
              <span className="blocker-mark" style={{ color: 'var(--cool)' }}>
                <Icon.play size={14} />
              </span>
              <span className="blocker-body">
                <span className="blocker-text">
                  <b className="mono">{task.attempt.id}</b> · {task.attempt.note}
                </span>
                <span className="blocker-kind">
                  intent → {task.attempt.phase} → evidence
                </span>
              </span>
            </div>
          </div>
        )}

        {/* Blockers — resolvable in place */}
        {(task.blockers.length > 0 || hardBlocked) && (
          <div className="sect">
            <div className="sect-head">
              <span className="micro">待处理 · 必须先处置</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {hardBlocked && (
                <div className="blocker" data-tone="alarm">
                  <span className="blocker-mark">
                    <Icon.lock size={14} />
                  </span>
                  <span className="blocker-body">
                    <span className="blocker-text">
                      重复执行 · 已发箱存在同收件人同主题记录
                    </span>
                    <span className="blocker-kind">repeat execution · hard block</span>
                    <span>
                      <button
                        className="btn btn-quiet"
                        style={{ paddingLeft: 0 }}
                        onClick={() => onResolveBlocker(task.id, 'hard-duplicate')}
                      >
                        查看匹配证据
                        <span className="kbd mono" style={{ marginLeft: 2 }}>
                          R
                        </span>
                      </button>
                    </span>
                  </span>
                </div>
              )}
              {task.blockers.map((b) => (
                <BlockerRow
                  key={b.id}
                  b={b}
                  onResolve={() => onResolveBlocker(task.id, b.id)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Duplicate conclusion bound to its coverage qualifier */}
        <div className="sect">
          <div className="sect-head">
            <span className="micro">查重与覆盖 · duplicate</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span className={`pill pill-solid ${dup.cls}`}>{task.duplicate}</span>
            <span style={{ fontSize: 'var(--t-label)', color: 'var(--ink-3)' }}>
              {dup.note}
            </span>
          </div>
          <Coverage task={task} />
        </div>

        {/* Attachments */}
        <div className="sect">
          <div className="sect-head">
            <span className="micro">附件 · attachments</span>
          </div>
          {task.attachments.length === 0 ? (
            <span style={{ fontSize: 'var(--t-label)', color: 'var(--ink-4)' }}>
              无附件槽位
            </span>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {task.attachments.map((a) => (
                <AttachmentRow
                  key={a.id}
                  a={a}
                  onConfirm={() => onConfirmAttachment(task.id, a.id)}
                  onReplace={() => onConfirmAttachment(task.id, a.id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Frozen content */}
        <div className="sect">
          <div className="sect-head">
            <span className="micro">邮件内容 · preparation</span>
          </div>
          <div className="preview">
            <div className="field">
              <span className="field-label">发件人</span>
              <span className="field-value mono" data-mono="true">
                {task.sender}
              </span>
            </div>
            <div className="field">
              <span className="field-label">收件人</span>
              <span
                className="field-value mono"
                data-mono="true"
                style={
                  task.blockers.some((b) => b.kind === 'recipient_conflict')
                    ? { color: 'var(--alarm)' }
                    : undefined
                }
              >
                {task.recipient}
              </span>
            </div>
            <div className="field">
              <span className="field-label">主题</span>
              <span className="field-value" data-empty={!task.subject}>
                {task.subject || '（缺失 · 阻断）'}
              </span>
            </div>
            <div className="body-preview">{task.body}</div>
            <button className="btn btn-quiet" style={{ alignSelf: 'flex-start', paddingLeft: 0 }}>
              <Icon.file size={12} />
              打开全文预览
            </button>
          </div>
        </div>

        {/* Sent record — immutable */}
        {task.sentRecord && (
          <div className="sect">
            <div className="sect-head">
              <span className="micro">已发送记录 · frozen</span>
            </div>
            <div className="attach">
              <span className="attach-icon" style={{ color: 'var(--verified)' }}>
                <Icon.lock size={14} />
              </span>
              <span className="attach-body">
                <span className="attach-name mono">{task.sentRecord.id}</span>
                <span className="attach-meta">
                  <span>{task.sentRecord.canonicalId}</span>
                  <span className="sha">{task.sentRecord.sentAt}</span>
                </span>
              </span>
            </div>
          </div>
        )}

        {/* Follow-up timing */}
        <div className="sect">
          <div className="sect-head">
            <span className="micro">跟进 · follow-up</span>
          </div>
          <div className="kv">
            <span className="kv-label">资格</span>
            <span className="kv-value">{task.followup.eligibility}</span>
          </div>
          <div className="kv">
            <span className="kv-label">等待 / 间隔 / 上限</span>
            <span className="kv-value">
              {task.followup.waitedDays}d · {task.followup.intervalDays}d ·{' '}
              {task.followup.limit}
            </span>
          </div>
        </div>

        {/* Version record: this task's revisions. The global ledger is the dock. */}
        <div className="sect">
          <div className="sect-head">
            <span className="micro">版本记录 · revisions</span>
          </div>
          <div className="timeline">
            {task.versions.map((v, i) => (
              <div className="tl-item" key={`${v.at}-${i}`}>
                <span className="tl-at">{v.at}</span>
                <span className="tl-text">{v.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Sticky footer: the one action valid right now */}
      <div className="insp-foot">
        {locked ? (
          <span className="insp-lock-note">
            <Icon.lock size={11} />
            {primaryDisabledReason ??
              `锁定 · 先清除 ${blockerCount} 项待处理`}
          </span>
        ) : null}
        <button
          className={`btn ${primary.kind === 'primary' ? 'btn-primary' : primary.kind === 'danger' ? 'btn-danger' : 'btn-ghost'}`}
          disabled={locked}
          onClick={onPrimaryClick}
        >
          <span>{primary.label}</span>
          {primary.shortcut && <span className="kbd mono">{primary.shortcut}</span>}
        </button>
      </div>
    </aside>
  )
}

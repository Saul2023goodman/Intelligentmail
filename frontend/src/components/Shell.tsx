import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type {
  Campaign,
  ExecutionPause,
  MailboxLink,
  NavSection,
  RecordEntry,
} from '../domain'
import { Icon } from '../icons'

/* ── Popover: outside-click + Esc dismissal, focus returned to trigger ── */

export function Popover({
  open,
  onClose,
  children,
  align = 'left',
  width = 268,
}: {
  open: boolean
  onClose: () => void
  children: ReactNode
  align?: 'left' | 'right'
  width?: number
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey, true)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey, true)
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div
      ref={ref}
      className="pop"
      style={{ width, [align === 'right' ? 'right' : 'left']: 0 }}
      role="dialog"
    >
      {children}
    </div>
  )
}

/* ── Environment bar ────────────────────────────────────────────────── */

function Clock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])
  const utc = now.toISOString().slice(11, 19)
  const loc = now.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
  return (
    <div className="clock mono">
      <div className="clock-cell">
        <span className="clock-value">{utc}</span>
        <span className="micro">utc</span>
      </div>
      <div className="clock-cell">
        <span className="clock-value">{loc}</span>
        <span className="micro">local</span>
      </div>
    </div>
  )
}

const linkStateCopy: Record<
  MailboxLink['state'],
  { label: string; color: string; note: string }
> = {
  connected: {
    label: '已连接',
    color: 'var(--verified)',
    note: '标签页地址与登记一致',
  },
  needs_login: {
    label: '需要登录',
    color: 'var(--amber)',
    note: '未登录或需要验证码',
  },
  wrong_mailbox: {
    label: '账号不符',
    color: 'var(--alarm)',
    note: '零邮件行落库',
  },
  bridge_unavailable: {
    label: '桥接不可用',
    color: 'var(--ink-3)',
    note: 'Native Host 未响应',
  },
}

export function EnvironmentBar({
  campaigns,
  activeCampaignId,
  onSwitchCampaign,
  link,
  onSync,
  syncing,
  onOpenPalette,
  onImport,
  operator,
}: {
  campaigns: Campaign[]
  activeCampaignId: string
  onSwitchCampaign: (id: string) => void
  link: MailboxLink
  onSync: () => void
  syncing: boolean
  onOpenPalette: () => void
  onImport: () => void
  operator: { name: string; initials: string }
}) {
  const [scopeOpen, setScopeOpen] = useState(false)
  const [linkOpen, setLinkOpen] = useState(false)
  const [pendingSwitch, setPendingSwitch] = useState<string | null>(null)
  const active = campaigns.find((c) => c.id === activeCampaignId) ?? campaigns[0]
  const ls = linkStateCopy[link.state]

  return (
    <header className="env">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          <Icon.diamond />
        </span>
        <span className="brand-name">
          SmartMail <span>Console</span>
        </span>
      </div>

      {/* Campaign is the global scope. It is always explicit — never inferred
          from a filename, a directory, or the last operation. */}
      <div style={{ position: 'relative' }}>
        <button
          className="scope"
          onClick={() => {
            setScopeOpen((v) => !v)
            setPendingSwitch(null)
          }}
          aria-expanded={scopeOpen}
          aria-haspopup="dialog"
        >
          <span className="scope-text">
            <span className="scope-name">{active.name}</span>
            <span className="scope-meta">{active.meta}</span>
          </span>
          <Icon.chevronDown size={14} className="chev" />
        </button>
        <Popover open={scopeOpen} onClose={() => setScopeOpen(false)} width={300}>
          <div className="pop-head">
            <span className="micro">campaign · 全局作用域</span>
          </div>
          <div className="pop-list">
            {campaigns.map((c) => (
              <div key={c.id}>
                {pendingSwitch === c.id ? (
                  <div className="pop-confirm">
                    <p className="pop-confirm-text">
                      切换作用域至 <b>{c.name}</b>？当前筛选与选中任务将被清除，
                      本地制备不受影响。
                    </p>
                    <div className="pop-confirm-actions">
                      <button
                        className="btn btn-quiet"
                        onClick={() => setPendingSwitch(null)}
                      >
                        取消
                      </button>
                      <button
                        className="btn btn-quiet"
                        style={{ color: 'var(--amber-hi)' }}
                        onClick={() => {
                          onSwitchCampaign(c.id)
                          setScopeOpen(false)
                          setPendingSwitch(null)
                        }}
                      >
                        确认切换
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    className="pop-item"
                    data-active={c.id === activeCampaignId}
                    onClick={() =>
                      c.id === activeCampaignId
                        ? setScopeOpen(false)
                        : setPendingSwitch(c.id)
                    }
                  >
                    <span className="pop-item-main">
                      <span className="pop-item-title">{c.name}</span>
                      <span className="pop-item-sub">{c.meta}</span>
                    </span>
                    {c.id === activeCampaignId && (
                      <span className="micro" style={{ color: 'var(--amber)' }}>
                        active
                      </span>
                    )}
                  </button>
                )}
              </div>
            ))}
          </div>
        </Popover>
      </div>

      {/* Mailbox link — the environment, not a row attribute. Address is
          always shown so a wrong tab is never mistaken for the right one. */}
      <div style={{ position: 'relative' }}>
        <button
          className="link-pill"
          onClick={() => setLinkOpen((v) => !v)}
          aria-expanded={linkOpen}
          aria-haspopup="dialog"
          title={ls.note}
        >
          <span
            className={`beacon ${link.state === 'connected' ? 'beacon-live' : ''}`}
            style={{ color: ls.color }}
            aria-hidden="true"
          />
          <span className="link-pill-text">
            <span className="link-pill-addr">{link.address}</span>
            <span className="link-pill-state">
              {ls.label} · 同步 {link.lastSync}
            </span>
          </span>
        </button>
        <Popover open={linkOpen} onClose={() => setLinkOpen(false)} width={312}>
          <div className="pop-head">
            <span className="micro">mailbox · 连接与能力</span>
          </div>
          <div className="pop-body">
            <div className="pop-fact">
              <span className="micro">登记学生</span>
              <span className="pop-fact-value">{link.student}</span>
            </div>
            <div className="pop-fact">
              <span className="micro">标签页地址</span>
              <span className="pop-fact-value mono">{link.address}</span>
            </div>
            <div className="pop-fact">
              <span className="micro">状态</span>
              <span className="pop-fact-value" style={{ color: ls.color }}>
                {ls.label} · {ls.note}
              </span>
            </div>
          </div>
          <div className="pop-head" style={{ borderTop: '1px solid var(--line)' }}>
            <span className="micro">capability matrix</span>
          </div>
          <div className="pop-list">
            {link.capabilities.map((cap) => (
              <div className="cap-row" key={cap.id}>
                <span
                  className={`pill ${
                    cap.state === 'verified' ? 'pill-verified pill-solid' : 'pill-mute'
                  }`}
                  style={
                    cap.state === 'roadmap'
                      ? { borderStyle: 'dashed', color: 'var(--ink-4)' }
                      : undefined
                  }
                >
                  {cap.state === 'verified'
                    ? 'verified'
                    : cap.state === 'roadmap'
                      ? 'roadmap'
                      : 'disabled'}
                </span>
                <span className="cap-label">{cap.label}</span>
                <code className="cap-id mono">{cap.id}</code>
              </div>
            ))}
          </div>
          <div className="pop-foot">
            <Icon.compass size={12} />
            <span>
              标记 <b>roadmap</b> 的能力尚未验收，控件可见但不可点。
            </span>
          </div>
        </Popover>
      </div>

      <div className="env-sep" aria-hidden="true" />

      <button
        className="search-trigger"
        onClick={onOpenPalette}
        aria-label="搜索任务、学生、主管（打开命令面板）"
      >
        <Icon.search size={14} />
        <span className="search-trigger-text">搜索任务或收件人</span>
        <span className="kbd">⌘K</span>
      </button>

      <div className="env-spacer" />

      <Clock />

      <div className="env-sep" aria-hidden="true" />

      {/* The one sync entry point. Read-only: it can never change outbound state. */}
      <button
        className="btn btn-ghost"
        onClick={onSync}
        disabled={syncing}
        aria-label="同步邮箱观测（只读，不改变外发状态）"
      >
        <Icon.sync
          size={14}
          style={
            syncing
              ? { animation: 'spin 900ms linear infinite', color: 'var(--verified)' }
              : undefined
          }
        />
        {syncing ? '同步中' : '同步观测'}
      </button>

      <button className="btn btn-ghost" onClick={onImport} aria-label="导入新材料">
        <Icon.plus size={14} />
        导入
      </button>

      <div className="operator">
        <span className="operator-name">{operator.name}</span>
        <span className="avatar mono" aria-hidden="true">
          {operator.initials}
        </span>
      </div>
    </header>
  )
}

/* ── Rail navigation ────────────────────────────────────────────────── */

export function RailNav({
  sections,
  activeId,
  open,
  onToggle,
  onSelect,
}: {
  sections: NavSection[]
  activeId: string
  open: boolean
  onToggle: () => void
  onSelect: (id: string) => void
}) {
  return (
    <nav className="rail" data-open={open} aria-label="主导航">
      <ul className="rail-list">
        {sections.map((s) => {
          const Glyph = Icon[s.icon as keyof typeof Icon]
          const worst = s.lights?.[0]
          return (
            <li key={s.id}>
              <button
                className="rail-item"
                aria-current={s.id === activeId ? 'page' : undefined}
                onClick={() => onSelect(s.id)}
                title={open ? undefined : `${s.label} · ${s.canonical}`}
                style={worst ? { color: undefined } : undefined}
              >
                <span style={{ position: 'relative', display: 'grid' }}>
                  {Glyph && <Glyph size={17} />}
                  {worst && !open && (
                    <span
                      className="rail-dot"
                      style={{
                        color:
                          worst.tone === 'alarm'
                            ? 'var(--alarm)'
                            : worst.tone === 'amber'
                              ? 'var(--amber)'
                              : 'var(--cool)',
                      }}
                      aria-hidden="true"
                    />
                  )}
                </span>
                <span className="rail-label">
                  <span className="rail-label-cn">{s.label}</span>
                  <span className="rail-label-en">{s.canonical}</span>
                </span>
                {s.lights?.map((l) => (
                  <span
                    key={l.label}
                    className={`rail-lights light light-${l.tone}`}
                    title={l.label}
                  >
                    <span className="sr-only">{l.label} </span>
                    {l.value}
                  </span>
                ))}
              </button>
            </li>
          )
        })}
      </ul>
      <div className="rail-foot">
        <button
          className="rail-toggle"
          onClick={onToggle}
          aria-expanded={open}
          aria-label={open ? '折叠导航' : '展开导航'}
        >
          <Icon.collapse size={16} />
          <span className="rail-label">
            <span className="rail-label-cn">折叠</span>
          </span>
        </button>
      </div>
    </nav>
  )
}

/* ── Pause banner ─────────────────────────────────────────────────────
   Not dismissible. One reason yields exactly one valid primary action.  */

export function PauseBanner({
  pauses,
  index,
  onIndex,
  onPrimary,
  onSecondary,
}: {
  pauses: ExecutionPause[]
  index: number
  onIndex: (i: number) => void
  onPrimary: (p: ExecutionPause) => void
  onSecondary?: (p: ExecutionPause) => void
}) {
  if (pauses.length === 0) return null
  const p = pauses[Math.min(index, pauses.length - 1)]

  return (
    <div className="pause" role="alert" aria-live="assertive">
      <span className="pause-bar" aria-hidden="true" />
      <span className="pause-icon" aria-hidden="true">
        <Icon.alert size={14} />
      </span>
      <div className="pause-body">
        <span className="pause-reason">{p.reasonLabel}</span>
        <span className="pause-fact">
          执行已暂停 · 尝试 <b>{p.attempt}</b> · {p.fact}
        </span>
        <span className="pause-prevented">{p.prevented}</span>
      </div>
      <div className="pause-actions">
        {pauses.length > 1 && (
          <>
            <button
              className="btn btn-quiet"
              onClick={() => onIndex((index - 1 + pauses.length) % pauses.length)}
              aria-label="上一条暂停"
            >
              <Icon.chevronDown size={13} style={{ transform: 'rotate(90deg)' }} />
            </button>
            <span className="pause-index mono">
              {index + 1} / {pauses.length}
            </span>
            <button
              className="btn btn-quiet"
              onClick={() => onIndex((index + 1) % pauses.length)}
              aria-label="下一条暂停"
            >
              <Icon.chevronDown size={13} style={{ transform: 'rotate(-90deg)' }} />
            </button>
          </>
        )}
        {p.secondary && (
          <button className="btn btn-ghost" onClick={() => onSecondary?.(p)}>
            {p.secondary}
          </button>
        )}
        <button className="btn btn-primary" onClick={() => onPrimary(p)}>
          {p.primary}
          <span className="kbd" style={{ borderColor: 'rgba(23,17,10,.3)', color: '#17110a' }}>
            ↵
          </span>
        </button>
      </div>
    </div>
  )
}

/* ── Record dock ────────────────────────────────────────────────────── */

const channelLabel: Record<RecordEntry['channel'], string> = {
  observation: 'observation',
  execution: 'execution',
  preparation: 'preparation',
  confirmation: 'confirmation',
  import: 'import',
  reconciliation: 'reconcile',
  reply: 'reply',
}

export function RecordDock({
  records,
  open,
  onToggle,
  onOpenLink,
}: {
  records: RecordEntry[]
  open: boolean
  onToggle: () => void
  onOpenLink: (link: string) => void
}) {
  const latest = records[0]
  return (
    <footer className="dock" data-open={open}>
      <button
        className="dock-bar"
        onClick={onToggle}
        aria-expanded={open}
        aria-label={open ? '收起记录流' : '展开记录流'}
      >
        <span className="micro">记录流</span>
        {!open && latest && (
          <span className="dock-latest">
            <span className="dock-time">{latest.at}</span>
            <span className="dock-text">{latest.text}</span>
          </span>
        )}
        {open && <span className="dock-latest" />}
        <span className="dock-count">
          {records.length}
          <Icon.chevronDown size={12} />
        </span>
      </button>
      {open && (
        <div className="dock-list">
          {records.map((r) => (
            <button
              key={r.id}
              className="rec"
              data-tone={r.tone}
              onClick={() => r.link && onOpenLink(r.link)}
              title={r.link ? `打开 ${r.link}` : undefined}
            >
              <span className="rec-at">{r.at}</span>
              <span className="rec-ch">{channelLabel[r.channel]}</span>
              <span className="rec-text">{r.text}</span>
              <span className="rec-go">
                <Icon.chevronRight size={12} />
              </span>
            </button>
          ))}
        </div>
      )}
    </footer>
  )
}

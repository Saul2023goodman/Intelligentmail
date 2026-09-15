import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './console.css'
import './matrix.css'
import type { ExecutionPause, OutreachTask, RecordEntry, StageId } from './domain'
import {
  campaigns,
  executionPauses,
  mailboxLink,
  navSections,
  nextPlanSlot,
  operator,
  recordStream,
  stages,
  tasks as seedTasks,
} from './data'
import { EnvironmentBar, PauseBanner, RailNav, RecordDock } from './components/Shell'
import { FlowMatrix } from './components/FlowMatrix'
import { Inspector } from './components/Inspector'
import { CommandPalette, ConfirmDialog, Toasts } from './components/Overlays'
import type { Toast } from './components/Overlays'
import { Icon } from './icons'

/* Position is the status. A card's stage is always derived from its facts —
   never stored independently — so a card cannot disagree with its own track. */
function deriveStage(t: OutreachTask): StageId {
  if (t.status === 'unknown_outcome') return 'verify'
  if (t.reply === 'ambiguous' || t.duplicate === 'ambiguous_match') return 'verify'
  if (t.blockers.length > 0 || t.duplicate === 'repeat_execution') return 'blocked'
  if (t.sentRecord) return 'sent'
  if (t.attempt) return 'executing'
  if (t.readiness === 'confirmed') return 'confirmed'
  if (t.action === 'follow_up') return 'followup'
  return 'ready'
}

const withStage = (t: OutreachTask): OutreachTask => ({ ...t, stage: deriveStage(t) })

let recordSeq = 100
const nowHHMM = () =>
  new Date().toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

export default function App() {
  const [tasks, setTasks] = useState<OutreachTask[]>(() => seedTasks.map(withStage))
  const [selectedId, setSelectedTaskId] = useState<string | null>(() =>
    window.location.hash.match(/^#\/tasks\/(T-\d+)$/)?.[1] ?? null,
  )
  const boardScroll = useRef(0)
  const setSelectedId = useCallback((id: string | null) => {
    if (!window.location.hash.startsWith('#/tasks/')) boardScroll.current = window.scrollY
    const destination = id ? `#/tasks/${id}` : '#/'
    if (window.location.hash !== destination) window.history.pushState(null, '', destination)
    setSelectedTaskId(id)
    window.requestAnimationFrame(() => window.scrollTo(0, id ? 0 : boardScroll.current))
  }, [])
  useEffect(() => {
    const onPopState = () => setSelectedTaskId(window.location.hash.match(/^#\/tasks\/(T-\d+)$/)?.[1] ?? null)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])
  const [railOpen, setRailOpen] = useState(false)
  const [dockOpen, setDockOpen] = useState(false)
  const [sectionId, setSectionId] = useState('console')

  const [paletteOpen, setPaletteOpen] = useState(false)
  const [confirmQueue, setConfirmQueue] = useState<OutreachTask[]>([])
  const [confirmIndex, setConfirmIndex] = useState(0)

  const [pauses, setPauses] = useState<ExecutionPause[]>(executionPauses)
  const [pauseIndex, setPauseIndex] = useState(0)

  const [records, setRecords] = useState<RecordEntry[]>(recordStream)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [syncing, setSyncing] = useState(false)
  const [linkState, setLinkState] = useState(mailboxLink)

  const [campaignId, setCampaignId] = useState(campaigns[0].id)

  const toastSeq = useRef(0)
  const timers = useRef<number[]>([])

  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  const later = useCallback((fn: () => void, ms: number) => {
    timers.current.push(window.setTimeout(fn, ms))
  }, [])

  /* ── Feedback ─────────────────────────────────────────────────────── */

  const pushToast = useCallback(
    (text: string, tone: Toast['tone'] = 'verified', undo?: () => void) => {
      const id = ++toastSeq.current
      setToasts((prev) => [...prev.slice(-2), { id, text, tone, undo }])
      later(() => {
        setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)))
        later(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 240)
      }, 4200)
    },
    [later],
  )

  const pushRecord = useCallback((r: Omit<RecordEntry, 'id' | 'at'>) => {
    setRecords((prev) => [
      { ...r, id: `r${recordSeq++}`, at: nowHHMM() },
      ...prev,
    ])
  }, [])

  /* ── Derived views ────────────────────────────────────────────────── */

  const byStage = useMemo(() => {
    const map = new Map<StageId, OutreachTask[]>()
    for (const s of stages) map.set(s.id, [])
    for (const t of tasks) map.get(t.stage)?.push(t)
    return map
  }, [tasks])

  /* Flat order matches reading order: risk first, sent last. */
  const flatOrder = useMemo(
    () => stages.flatMap((s) => byStage.get(s.id) ?? []),
    [byStage],
  )

  const selected = tasks.find((t) => t.id === selectedId) ?? null

  /* ── Mutations ────────────────────────────────────────────────────── */

  const patchTask = useCallback(
    (id: string, patch: Partial<OutreachTask> | ((t: OutreachTask) => Partial<OutreachTask>)) => {
      setTasks((prev) =>
        prev.map((t) => {
          if (t.id !== id) return t
          const p = typeof patch === 'function' ? patch(t) : patch
          return withStage({ ...t, ...p })
        }),
      )
    },
    [],
  )

  const reject = useCallback(
    (_id: string, reason: string) => {

      pushToast(reason, 'alarm')
    },
    [pushToast],
  )

  /* Path 1 — clear a blocker. Saving revalidates the whole preparation and
     the card glides into the next track on its own. */
  const resolveBlocker = useCallback(
    (taskId: string, blockerId: string) => {
      const task = tasks.find((t) => t.id === taskId)
      if (!task) return

      if (blockerId === 'hard-duplicate') {
        reject(
          taskId,
          'repeat_execution 是硬阻断 · 条款：同一 Campaign 内同一学生与主管不得重复执行初邮',
        )
        return
      }
      if (task.duplicate === 'repeat_execution') {
        reject(taskId, '存在 repeat_execution 硬阻断 · 必须先裁决查重结论才能清除其他阻断')
        return
      }

      const blocker = task.blockers.find((b) => b.id === blockerId)
      const remaining = task.blockers.filter((b) => b.id !== blockerId)
      const becameReady = remaining.length === 0 && task.blockers.length > 0

      patchTask(taskId, {
        blockers: remaining,
        readiness: becameReady ? 'ready' : task.readiness,
        subject:
          blocker?.kind === 'subject_missing'
            ? `PhD supervision enquiry – ${task.student}`
            : task.subject,
        recipient:
          blocker?.kind === 'recipient_conflict'
            ? (task.supervisorAliases[0] ?? task.recipient)
            : task.recipient,
        attachments:
          blocker?.kind === 'attachment_missing'
            ? task.attachments.map((a) =>
                a.state === 'missing'
                  ? {
                      ...a,
                      state: 'confirmed' as const,
                      bytes: 288_540,
                      sha: '6b10ff…4e2a',
                    }
                  : a,
              )
            : task.attachments,
        versions: [
          ...task.versions,
          {
            at: nowHHMM(),
            text: blocker ? `${blocker.label} 已处置 · 整份制备重新校验` : '阻断项已处置',
          },
        ],
        annotation: becameReady ? undefined : task.annotation,
      })

      pushRecord({
        channel: 'preparation',
        text: `${taskId} ${blocker?.label ?? '阻断项'} 已处置${becameReady ? ' · 转为就绪' : ''}`,
        tone: becameReady ? 'verified' : 'neutral',
        link: `preparation/${taskId}`,
      })
      if (becameReady) {
        pushToast(
          `${taskId} 阻断清零 · 已滑入就绪待确认轨（就绪不等于授权）`,
          'verified',
          () => {
            patchTask(taskId, { blockers: task.blockers, readiness: 'blocked' })
            pushToast('已撤销 · 阻断项恢复', 'unknown')
          },
        )
      } else {
        pushToast(`${taskId} 已更新 · 剩余 ${remaining.length} 项待处理`, 'neutral')
      }
    },
    [tasks, patchTask, pushRecord, pushToast, reject],
  )

  const confirmAttachment = useCallback(
    (taskId: string, attachmentId: string) => {
      const task = tasks.find((t) => t.id === taskId)
      if (!task) return
      patchTask(taskId, {
        attachments: task.attachments.map((a) =>
          a.id === attachmentId
            ? a.state === 'missing'
              ? { ...a, state: 'confirmed' as const, bytes: 288_540, sha: '6b10ff…4e2a' }
              : { ...a, state: 'confirmed' as const }
            : a,
        ),
      })
      pushRecord({
        channel: 'preparation',
        text: `${taskId} 附件槽位已确认 · 指纹快照已冻结`,
        tone: 'neutral',
        link: `preparation/${taskId}`,
      })
      pushToast(`${taskId} 附件已确认`, 'neutral')
    },
    [tasks, patchTask, pushRecord, pushToast],
  )

  /* Path 2 — the readback gate. This is the only route to authorisation. */
  const openConfirm = useCallback(
    (ids: string[]) => {
      const queue = ids
        .map((id) => tasks.find((t) => t.id === id))
        .filter((t): t is OutreachTask => !!t)
      if (queue.length === 0) return
      const first = queue[0]
      if (first.blockers.length > 0 || first.duplicate === 'repeat_execution') {
        reject(first.id, `${first.id} 存在未清除的阻断项 · 就绪不等于授权，无法进入确认`)
        return
      }
      if (first.status === 'unknown_outcome') {
        reject(first.id, `${first.id} 结果未知 · 必须先对账，禁止盲重试`)
        return
      }
      setConfirmQueue(queue)
      setConfirmIndex(0)
    },
    [tasks, reject],
  )

  const doConfirm = useCallback(
    (task: OutreachTask, mode: 'immediate' | 'plan', expiresAt: string) => {
      patchTask(task.id, {
        readiness: 'confirmed',
        plannedAt: mode === 'plan' ? (task.plannedAt ?? nextPlanSlot.at) : task.plannedAt,
        versions: [
          ...task.versions,
          {
            at: nowHHMM(),
            text: `Confirmation 已绑定摘要 · ${mode === 'plan' ? '加入计划' : '立即发送'}${expiresAt ? ` · 有效期至 ${expiresAt}` : ''}`,
          },
        ],
        annotation: undefined,
      })

      pushRecord({
        channel: 'confirmation',
        text: `Confirmation 绑定摘要 · ${task.id} · ${mode === 'plan' ? '计划发送' : '立即发送'}`,
        tone: 'neutral',
        link: `execution/confirmations/${task.id}`,
      })
      pushToast(`${task.id} 已授权 · 本地未外发`, 'verified')

      setConfirmQueue((prev) => {
        const next = prev.filter((t) => t.id !== task.id)
        if (next.length === 0) return []
        return next
      })
      setConfirmIndex(0)
    },
    [patchTask, pushRecord, pushToast],
  )

  /* Path 3 — unknown outcome. Reconcile first; a blind retry is never offered. */
  const reconcile = useCallback(
    (taskId: string) => {
      const task = tasks.find((t) => t.id === taskId)
      if (!task) return
      patchTask(taskId, {
        status: 'sent',
        attempt: undefined,
        sentRecord: {
          id: `S-${900 + Math.floor(Math.random() * 80)}`,
          canonicalId: `163:${new Date().toISOString().slice(0, 10).replace(/-/g, '')}:${taskId.slice(2).toLowerCase()}`,
          sentAt: `${new Date().toISOString().slice(5, 10)} ${nowHHMM()}`,
        },
        followup: { ...task.followup, eligibility: 'waiting', waitedDays: 0 },
        versions: [
          ...task.versions,
          { at: nowHHMM(), text: '对账取得已发箱唯一匹配 · 判定 sent，冻结记录' },
        ],
        annotation: undefined,
      })
      setPauses((prev) => prev.filter((p) => p.taskId !== taskId))
      setPauseIndex(0)


      pushRecord({
        channel: 'reconciliation',
        text: `${taskId} 对账取得正向证据 · unknown_outcome → sent，Execution Flow 已恢复`,
        tone: 'verified',
        link: `mailbox/reconciliations/${taskId}`,
      })
      pushToast(`${taskId} 已对账 · 判定为 sent，暂停已解除`, 'verified')
    },
    [tasks, patchTask, pushRecord, pushToast],
  )

  const adjudicate = useCallback(
    (taskId: string) => {
      const task = tasks.find((t) => t.id === taskId)
      if (!task) return
      patchTask(taskId, {
        reply: 'associated',
        duplicate: task.duplicate === 'ambiguous_match' ? 'no_duplicate_found' : task.duplicate,
        followup: {
          ...task.followup,
          eligibility: 'ordinary_reply_received',
        },
        versions: [
          ...task.versions,
          { at: nowHHMM(), text: '回复已裁决为可靠关联 · 停止 no-reply 跟进资格' },
        ],
        annotation: undefined,
      })

      pushRecord({
        channel: 'reply',
        text: `${taskId} 歧义回复已裁决 · 关联至该任务`,
        tone: 'verified',
        link: `replies/${taskId}`,
      })
      pushToast(`${taskId} 已裁决 · 跟进资格转为 ordinary_reply_received`, 'verified')
    },
    [tasks, patchTask, pushRecord, pushToast],
  )

  /* Read-only sync: it can never change outbound state. */
  const runSync = useCallback(() => {
    if (syncing) return
    setSyncing(true)
    later(() => {
      setSyncing(false)
      setLinkState((l) => ({ ...l, lastSync: nowHHMM() }))
      pushRecord({
        channel: 'observation',
        text: '观测同步完成 · 只读，未改变任何外发状态',
        tone: 'neutral',
        link: 'mailbox/observations',
      })
      pushToast('观测同步完成 · 只读刷新', 'neutral')
    }, 1500)
  }, [syncing, later, pushRecord, pushToast])

  const pausePrimary = useCallback((p: ExecutionPause) => {
    setSelectedId(p.taskId)
  }, [setSelectedId])

  /* ── Selection & keyboard ─────────────────────────────────────────── */

  const moveSelection = useCallback(
    (delta: number) => {
      if (flatOrder.length === 0) return
      const i = flatOrder.findIndex((t) => t.id === selectedId)
      const next =
        i === -1
          ? flatOrder[delta > 0 ? 0 : flatOrder.length - 1]
          : flatOrder[Math.min(Math.max(i + delta, 0), flatOrder.length - 1)]
      setSelectedId(next.id)
    },
    [flatOrder, selectedId, setSelectedId],
  )

  const primaryFor = useCallback(
    (id: string) => {
      const t = tasks.find((x) => x.id === id)
      if (!t) return
      if (t.status === 'unknown_outcome') reconcile(id)
      else if (t.reply === 'ambiguous' || t.duplicate === 'ambiguous_match') adjudicate(id)
      else if (t.stage === 'ready' || t.stage === 'followup') openConfirm([id])
      else if (t.stage === 'blocked') {
        const first = t.blockers[0]
        if (first) resolveBlocker(id, first.id)
        else reject(id, `${id} 受 repeat_execution 硬阻断 · 请先裁决查重结论`)
      } else setSelectedId(id)
    },
    [tasks, reconcile, adjudicate, openConfirm, resolveBlocker, reject, setSelectedId],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      const typing =
        !!el &&
        (el.tagName === 'INPUT' ||
          el.tagName === 'TEXTAREA' ||
          el.isContentEditable)

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen((v) => !v)
        return
      }
      if (paletteOpen || confirmQueue.length > 0) return
      if (typing || el?.closest('button, select, a')) return

      if (e.key === 'Escape') {
        if (dockOpen) setDockOpen(false)
        else setSelectedId(null)
        return
      }
      if (e.key === '/') {
        e.preventDefault()
        setPaletteOpen(true)
        return
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return

      switch (e.key.toLowerCase()) {
        case 'j':
          e.preventDefault()
          moveSelection(1)
          break
        case 'k':
          e.preventDefault()
          moveSelection(-1)
          break
        case 'e':
          if (selectedId) {
            e.preventDefault()
            const t = tasks.find((x) => x.id === selectedId)
            const b = t?.blockers[0]
            if (t && b) resolveBlocker(selectedId, b.id)
            else if (t) reject(selectedId, `${selectedId} 当前无可就地修正的阻断项`)
          }
          break
        case 'c':
          if (selectedId) {
            e.preventDefault()
            primaryFor(selectedId)
          }
          break
        case 'r':
          if (selectedId) {
            e.preventDefault()
            const t = tasks.find((x) => x.id === selectedId)
            if (t?.status === 'unknown_outcome') reconcile(selectedId)
            else if (t && (t.reply === 'ambiguous' || t.duplicate === 'ambiguous_match'))
              adjudicate(selectedId)
            else reject(selectedId, `${selectedId} 不在待核实轨 · 无需对账或裁决`)
          }
          break
        case 'a':
          if (selectedId) {
            e.preventDefault()
            const t = tasks.find((x) => x.id === selectedId)
            const a = t?.attachments.find((x) => x.state !== 'confirmed')
            if (t && a) confirmAttachment(selectedId, a.id)
            else reject(selectedId, `${selectedId} 无待处理的附件槽位`)
          }
          break
        default:
          break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [
    paletteOpen,
    confirmQueue.length,
    dockOpen,
    pauses,
    pauseIndex,
    pausePrimary,
    moveSelection,
    selectedId,
    setSelectedId,
    tasks,
    resolveBlocker,
    confirmAttachment,
    reconcile,
    adjudicate,
    primaryFor,
    reject,
  ])

  /* ── Render ───────────────────────────────────────────────────────── */

  const selectedBlockers = selected?.blockers.length ?? 0
  const primaryLock =
    selected?.duplicate === 'repeat_execution'
      ? '锁定 · repeat_execution 硬阻断，禁止进入授权'
      : selectedBlockers > 0
        ? `锁定 · 先清除 ${selectedBlockers} 项待处理`
        : null

  return (
    <div className="app">
      <EnvironmentBar
        campaigns={campaigns}
        activeCampaignId={campaignId}
        onSwitchCampaign={(id) => {
          setCampaignId(id)
          setSelectedId(null)
          pushToast('作用域已切换 · 选中已清除，本地制备未受影响', 'neutral')
        }}
        link={linkState}
        onSync={runSync}
        syncing={syncing}
        onOpenPalette={() => setPaletteOpen(true)}
        onImport={() =>
          pushToast('导入需显式选择 Campaign 与学生 · 不提供默认猜测', 'neutral')
        }
        operator={operator}
      />

      <PauseBanner
        pauses={pauses}
        index={pauseIndex}
        onIndex={setPauseIndex}
        onPrimary={pausePrimary}
        onSecondary={(p) => {
          setSelectedId(p.taskId)
          pushToast(`已记录人工接管意图 · ${p.attempt} 需先对账才可继续`, 'unknown')
        }}
      />

      <div className="workspace">
        <RailNav
          sections={navSections}
          activeId={sectionId}
          open={railOpen}
          onToggle={() => setRailOpen((v) => !v)}
          onSelect={setSectionId}
        />

        <main className="board" hidden={!!selected}>
          <header className="matrix-title">
            <div><span className="micro">SMARTMAIL / OPERATIONS · 交互预览</span><h1>外联作业台 <span>CHECKPOINT WORKBENCH</span></h1></div>
            <div className="matrix-side">
              <span className="matrix-health"><span className="beacon" style={{ color: pauses.length ? 'var(--alarm)' : 'var(--verified)' }} /> {tasks.length} 个任务 · {pauses.length ? `${pauses.length} 项执行暂停` : '执行流正常'}</span>
              <span className="matrix-actions">
                {/* The dashboard shows the next slot only; the full timetable
                    lives on /plans. The same schedule is never shown twice. */}
                <span
                  className="mono matrix-slot"
                  title={nextPlanSlot.constraints}
                >
                  <Icon.clock size={12} />
                  下一时刻
                  <b>{nextPlanSlot.at}</b>
                  {nextPlanSlot.taskId}
                </span>
              </span>
            </div>
          </header>

          <FlowMatrix
            tasks={flatOrder}
            selectedId={selectedId}
            onOpen={setSelectedId}
            onPrimary={primaryFor}
            onBatchConfirm={(ids) => openConfirm(ids)}
          />
        </main>

        {selected && <main className="detail-page">
          <header className="detail-nav"><button className="btn btn-ghost" onClick={() => setSelectedId(null)}>← 返回作业台</button><span className="micro">任务 / {selected.id} / 详细操作</span></header>
        <Inspector
          key={selected.id}
          task={selected}
          trackCount={tasks.length}
          onClose={() => setSelectedId(null)}
          onResolveBlocker={resolveBlocker}
          onConfirmSend={(id) => openConfirm([id])}
          onReconcile={reconcile}
          onAdjudicate={adjudicate}
          onConfirmAttachment={confirmAttachment}
          onPrimary={primaryFor}
          primaryDisabledReason={primaryLock}
        />
        </main>}
      </div>

      <RecordDock
        records={records}
        open={dockOpen}
        onToggle={() => setDockOpen((v) => !v)}
        onOpenLink={(link) => pushToast(`深链 ${link} · 记录流是全局唯一流水`, 'neutral')}
      />

      {paletteOpen && (
        <CommandPalette
          tasks={tasks}
          onSelect={(id) => {
            setSelectedId(id)
            setPaletteOpen(false)
          }}
          onClose={() => setPaletteOpen(false)}
        />
      )}

      {confirmQueue.length > 0 && (
        <ConfirmDialog
          queue={confirmQueue}
          index={Math.min(confirmIndex, confirmQueue.length - 1)}
          onIndex={setConfirmIndex}
          onCancel={() => {
            setConfirmQueue([])
            setConfirmIndex(0)
          }}
          onConfirm={doConfirm}
        />
      )}

      <Toasts items={toasts} />
    </div>
  )
}

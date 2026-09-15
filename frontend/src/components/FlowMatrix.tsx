import { useState } from 'react'
import type { OutreachTask } from '../domain'
import { checkpoints, evaluate, evaluateMain, mainCheckpoints, stateLabels, stateMarks } from '../checkpoints'
import type { FilterId, CheckState } from '../checkpoints'
import '../workbench.css'

const compactLabels: Record<string, string> = { record:'入库', scope:'归属', content:'内容', attachments:'附件', identity:'对象', duplicate:'查重', followup:'跟进', timing:'时间', confirmation:'许可', receipt:'回执', archive:'留存' }

function executionLabel(t: OutreachTask) {
  if (t.status === 'unknown_outcome') return '结果未知'
  if (t.sentRecord) return '已发送'
  if (t.status === 'observed_failure') return '执行失败'
  if (t.status === 'externally_scheduled') return '外部已定时'
  if (t.attempt) return '执行中'
  return t.readiness === 'confirmed' ? '等待执行' : '本地制备'
}
function nextAction(t: OutreachTask) {
  if (t.status === 'unknown_outcome') return ['缺少发送回执', '查看对账']
  if (t.duplicate === 'repeat_execution') return ['同一行动已执行', '查看历史']
  if (t.reply === 'ambiguous') return ['回复归属待核实', '复核关联']
  if (t.duplicate === 'ambiguous_match' || t.duplicate === 'duplicate_suspicion') return ['历史匹配待复核', '复核查重']
  const blocker = t.blockers.find(b => b.kind !== 'attachment_missing')
  if (blocker) return [{ recipient_conflict: '收件地址不一致', identity_unconfirmed: '主管身份待确认', subject_missing: '缺少邮件主题', rewrite_required: '修订稿待重新制备', attachment_missing: '建议附件待选择' }[blocker.kind], '处理问题']
  if (t.sentRecord) return [t.reply === 'associated' ? '已收到普通回复' : t.sentRecord.sentAt, '查看记录']
  if (t.readiness === 'confirmed') return [t.plannedAt ?? '已确认，尚未外发', '查看许可']
  if (t.attachments.some(a => a.state !== 'confirmed')) return ['建议附件待选择', '核对附件']
  if (t.action === 'follow_up' && evaluate(t).followup.state !== 'pass') return ['跟进条件待复核', '查看资格']
  return ['等待内容复核与授权', '复核发送']
}
export function FlowMatrix({ tasks, selectedId, onOpen, onBatchConfirm }: {
  tasks: OutreachTask[]; selectedId: string | null; onOpen: (id: string) => void
  onPrimary: (id: string) => void; onBatchConfirm: (ids: string[]) => void
}) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FilterId | null>(null)
  const [state, setState] = useState<CheckState | 'attention'>('attention')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [detail, setDetail] = useState<{ task: string; check: FilterId } | null>(null)
  const [kind, setKind] = useState('all')
  const results = new Map(tasks.map(t => { const checks = evaluate(t); return [t.id, { ...checks, ...evaluateMain(checks) }] }))
  const labels = [...mainCheckpoints, ...checkpoints]
  const matches = (s: CheckState) => state === 'attention' ? s === 'fail' || s === 'pending' : s === state
  const rows = tasks.filter(t => (!query || `${t.id} ${t.student} ${t.supervisor} ${t.institution}`.toLowerCase().includes(query.toLowerCase())) &&
    (kind === 'all' || t.action === kind) && (!filter || matches(results.get(t.id)![filter].state)))
  const batch = rows.filter(t => selected.has(t.id) && !t.sentRecord && t.status !== 'unknown_outcome' && t.blockers.length === 0 &&
    ['ready', 'followup'].includes(t.stage) && results.get(t.id)!.duplicate.state === 'pass' &&
    (t.action !== 'follow_up' || results.get(t.id)!.followup.state === 'pass')).map(t => t.id)
  const toggle = (id: string) => setSelected(prev => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n })
  const all = rows.length > 0 && rows.every(t => selected.has(t.id))
  const activeTask = tasks.find(t => t.id === detail?.task)
  return <section className="wb" aria-label="任务检查工作台">
    <div className="wb-toolbar">
      <div className="wb-tabs" aria-label="行动类型">
        {[['all', '全部任务'], ['initial_outreach', '初次外联'], ['follow_up', '跟进']].map(([id, label]) =>
          <button key={id} aria-pressed={kind === id} onClick={() => setKind(id)}>{label}{id === 'all' && <b>{tasks.length}</b>}</button>)}
      </div>
      <label className="wb-search"><span aria-hidden="true">⌕</span><input aria-label="搜索任务" placeholder="搜索学生、主管或任务…" value={query} onChange={e => setQuery(e.target.value)} /></label>
    </div>
    <div className="wb-guide"><span><b>主 / 次检查点</b> <span className="wb-muted">一条轨道 · 主次有序</span></span>
      <div className="wb-legend">{(Object.keys(stateLabels) as CheckState[]).map(s => <span key={s}><i className={`wb-symbol ${s}`}>{stateMarks[s]}</i>{stateLabels[s]}</span>)}</div>
      <span className="wb-muted">点击主次标签筛选 · 点击节点查看依据</span>
    </div>
    {(filter || selected.size > 0) && <div className="wb-filterbar">
      {filter && <><button className="wb-chip" onClick={() => { setFilter(null); setState('attention') }}>{labels.find(c => c.id === filter)?.label} ×</button>
        <select aria-label="检查结果筛选" value={state} onChange={e => setState(e.target.value as typeof state)}><option value="attention">需处理：未通过 + 待核实</option>{(Object.keys(stateLabels) as CheckState[]).map(s => <option key={s} value={s}>{stateLabels[s]}</option>)}</select></>}
      <span className="wb-muted">{rows.length} 个匹配任务</span>
      {selected.size > 0 && <><button className="wb-chip" onClick={() => setSelected(new Set())}>已选 {selected.size} ×</button><button className="btn btn-primary btn-sm" disabled={!batch.length} onClick={() => onBatchConfirm(batch)}>批量复核 {batch.length}</button></>}
    </div>}
    <div className="wb-scroll">
      <table className="wb-table">
        <colgroup><col className="wb-select-col"/><col className="wb-person-col"/>{mainCheckpoints.map(c => <col className="wb-main-col" key={c.id}/>)}<col className="wb-status-col"/><col className="wb-issue-col"/><col className="wb-action-col"/></colgroup>
        <thead><tr className="wb-main-header">
          <th><input type="checkbox" aria-label="全选可见任务" checked={all} ref={el => { if (el) el.indeterminate = !all && rows.some(t => selected.has(t.id)) }} onChange={() => setSelected(prev => { const n = new Set(prev); rows.forEach(t => all ? n.delete(t.id) : n.add(t.id)); return n })}/></th>
          <th className="wb-person-head">外联任务 <small>OUTREACH</small></th>
          {mainCheckpoints.map(main => <th key={main.id} scope="col">
            <div className="wb-linear-labels" style={{gridTemplateColumns:`60px repeat(${main.ids.length}, minmax(0, 1fr))`}}>
              <button className="wb-main-label" aria-pressed={filter === main.id} onClick={() => { setFilter(filter === main.id ? null : main.id); setState('attention') }}>{main.label}</button>
              {main.ids.map(id => { const c = checkpoints.find(c => c.id === id)!; return <button className="wb-sub-label" key={id} title={c.hint} aria-label={c.label} aria-pressed={filter === id} onClick={() => { setFilter(filter === id ? null : id); setState('attention') }}>{compactLabels[id]}</button> })}
            </div>
          </th>)}
          <th className="wb-outcome-head">执行状态</th><th>当前事项</th><th>下一步</th>
        </tr></thead>
        <tbody>{rows.map(t => { const checks = results.get(t.id)!; const [issue, action] = nextAction(t); return <tr key={t.id} data-selected={selected.has(t.id) || selectedId === t.id}>
          <td><input type="checkbox" aria-label={`选择 ${t.id}`} checked={selected.has(t.id)} onChange={() => toggle(t.id)}/></td>
          <td><button className="wb-person" onClick={() => onOpen(t.id)}><span><b>{t.student}</b><i>→</i>{t.supervisor}</span><small><span className="mono">{t.id}</span><em>{t.action === 'follow_up' ? `跟进 ${t.followup.round}` : '初邮'}</em><span title={t.institution}>{t.institution}</span></small></button></td>
          {mainCheckpoints.map(main => <td className="wb-milestone-cell" key={main.id}>
            <div className="wb-linear-rail" style={{gridTemplateColumns:`60px repeat(${main.ids.length}, minmax(0, 1fr))`}}><button className={`wb-node wb-major-node ${checks[main.id].state}`} aria-label={`${t.id} ${main.label}：${stateLabels[checks[main.id].state]}`} aria-expanded={detail?.task === t.id && detail.check === main.id} title={checks[main.id].detail} onClick={() => setDetail(detail?.task === t.id && detail.check === main.id ? null : {task:t.id, check:main.id})}>{stateMarks[checks[main.id].state]}</button>
            {main.ids.map(id => <button key={id} className={`wb-node wb-minor-node ${checks[id].state}`} aria-label={`${t.id} ${checkpoints.find(c => c.id === id)!.label}：${stateLabels[checks[id].state]}`} aria-expanded={detail?.task === t.id && detail.check === id} title={`${checkpoints.find(c => c.id === id)!.label} · ${stateLabels[checks[id].state]}\n${checks[id].detail}`} onClick={() => setDetail(detail?.task === t.id && detail.check === id ? null : {task:t.id, check:id})}>{stateMarks[checks[id].state]}</button>)}</div>
          </td>)}
          <td className="wb-outcome"><span data-status={t.status}>{executionLabel(t)}</span></td>
          <td className="wb-issue"><span title={issue}>{issue}</span>{t.blockers.filter(b => b.kind !== 'attachment_missing').length > 1 && <small>+{t.blockers.length - 1}</small>}</td>
          <td><button className="wb-next" onClick={() => onOpen(t.id)}>{action}<span>↗</span></button></td>
        </tr> })}</tbody>
      </table>
      {!rows.length && <div className="wb-empty">没有符合条件的任务。<button onClick={() => { setQuery(''); setFilter(null); setKind('all') }}>清除筛选</button></div>}
    </div>
    {detail && activeTask && <aside className="wb-evidence" aria-label="检查依据"><i className={`wb-symbol ${results.get(activeTask.id)![detail.check].state}`}>{stateMarks[results.get(activeTask.id)![detail.check].state]}</i><div><b>{activeTask.id} · {labels.find(c => c.id === detail.check)?.label} <span>{stateLabels[results.get(activeTask.id)![detail.check].state]}</span></b><p>{results.get(activeTask.id)![detail.check].detail}</p></div><button onClick={() => onOpen(activeTask.id)}>查看任务依据 ↗</button><button aria-label="关闭检查依据" onClick={() => setDetail(null)}>×</button></aside>}
    <footer className="wb-footer"><span>{rows.length} / {tasks.length} 个任务<span className="wb-divider">/</span>每行一个任务 · 各检查项独立更新</span><span>演示数据 · 操作仅在本地预览生效</span></footer>
  </section>
}


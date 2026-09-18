import { useEffect, useRef, useState, type ReactNode } from 'react';
import { AppShell, Topbar } from '../../app/shell';
import { PageHeader } from '../../app/page-header';
import { useWorkspaceScope } from '../../app/scope';
import { useCoreQuery } from '../../core/data';
import { core, human, type ComparisonRow } from '../../core';
import Icon from '../../shared/Icon';
import { kindOf, statusOf, statuses, type Status } from './presentation';
import './Mailbox.css';

const date = (value?: string) => value ? new Date(value).toLocaleString() : 'Not observed';
function Dialog({ title, close, children }: { title: string; close: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const el = ref.current; el?.showModal(); return () => el?.close(); }, []);
  return <dialog className="mb-dialog" ref={ref} onCancel={close} onClick={e => { if (e.target === e.currentTarget) close(); }}>
    <header><div><span className="mb-eyebrow">RECONCILIATION EVIDENCE</span><h2>{title}</h2></div><button autoFocus aria-label="Close evidence" onClick={close}><Icon name="close" /></button></header>
    <div className="mb-dialog-body">{children}</div>
  </dialog>;
}
export default function MailboxPage() {
  const { scope } = useWorkspaceScope();
  const campaign = scope?.campaignId ?? '';
  const student = scope?.studentId ?? '';
  const workspaceQuery = useCoreQuery('workspace', { campaign_id: campaign }, { enabled: Boolean(campaign) });
  const mailboxQuery = useCoreQuery('mailbox_workspace', { campaign_id: campaign, student_id: student }, { enabled: Boolean(campaign && student) });
  const workspace = workspaceQuery.data;
  const data = mailboxQuery.data;
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<Status | 'all'>('all');
  const [kind, setKind] = useState('all');
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [selected, setSelected] = useState<ComparisonRow | null>(null);
  const [history, setHistory] = useState(false);
  const loading = workspaceQuery.isLoading || mailboxQuery.isLoading;
  const displayError = error || workspaceQuery.error?.message || mailboxQuery.error?.message || '';
  async function refresh() {
    setRefreshing(true); setError(''); setNotice('');
    try {
      const result = await core('refresh_mailbox', { student_id: student });
      setNotice(`Observation ${human(result.observation.status)}. ${result.observation.detail || 'Reconciliation evidence updated.'}`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setRefreshing(false); }
  }
  const rows = data?.rows ?? [];
  const filtered = rows.filter(row => (status === 'all' || statusOf(row) === status) && (kind === 'all' || kindOf(row) === kind) &&
    `${row.local?.subject ?? ''} ${row.local?.supervisor ?? ''} ${row.local?.recipient ?? ''} ${row.observed?.subject ?? ''} ${row.observed?.counterpart ?? ''} ${row.findings.map(f => `${f.finding} ${f.detail}`).join(' ')}`.toLowerCase().includes(query.toLowerCase()));
  const mailbox = workspace?.mailboxes.find(m => m.student_id === student);
  const observation = data?.observation;
  const canRead = workspace?.mailbox_capabilities.capabilities.read_history.available;
  const count = (key: Status) => rows.filter(row => statusOf(row) === key).length;
  return <AppShell className="mailbox-page" activeRoute="mailbox">
    <div className="workspace">
      <Topbar breadcrumb="Mailbox" homeHref="#workflow"><span className="mb-top-note"><Icon name="shield" size={15} /> Observation & reconciliation</span></Topbar>
      <PageHeader
        eyebrow="Communication operations"
        title="Mailbox reconciliation"
        meta={<div className="mb-observed-at" aria-label="Mailbox evidence status"><i className={observation?.status === 'complete' ? 'complete' : ''} /><span>{observation ? `Last observation · ${date(observation.observed_at)}` : 'No mailbox observation yet'}</span><small>{canRead ? 'Read-only observation available' : 'Connect the dedicated 163 extension to refresh'}</small></div>}
        actions={<><button className="mb-button" onClick={() => setHistory(true)}><Icon name="clock" size={15} /> Observation history</button><button className="mb-button mb-primary" disabled={!student || !campaign || !canRead || loading || refreshing} onClick={refresh}><Icon name="refresh" size={15} />{refreshing ? 'Observing mailbox…' : 'Refresh evidence'}</button></>}
      />
      <section className="mb-stats" aria-label="Reconciliation filters">{(['all', 'matched', 'discrepancy', 'unknown', 'external', 'reply'] as const).map(key => <button key={key} aria-pressed={status === key} className={`mb-stat ${key} ${status === key ? 'selected' : ''}`} onClick={() => setStatus(key)}><span>{key === 'all' ? 'All comparisons' : statuses[key].label}</span><strong>{loading ? '—' : key === 'all' ? rows.length : count(key)}</strong><small>{key === 'all' ? 'Current evidence' : key === 'matched' ? 'Established by Core' : key === 'discrepancy' ? 'External change detected' : key === 'unknown' ? 'Needs more evidence' : key === 'external' ? 'No local association' : 'Associated & unassociated'}</small></button>)}</section>
      {displayError && <div className="mb-notice mb-error" role="alert"><Icon name="warning" size={16} /><span>{displayError}</span><button onClick={() => { void workspaceQuery.refresh(); void mailboxQuery.refresh(); }}>Retry loading</button></div>}
      {notice && <div className="mb-notice" role="status">{notice}</div>}
      <main className="mb-main">
        <div className="mb-toolbar"><div className="mb-tabs" aria-label="Record type">{['all', 'sent', 'schedules', 'replies'].map(k => <button aria-pressed={kind === k} className={kind === k ? 'active' : ''} key={k} onClick={() => setKind(k)}>{k === 'all' ? 'All records' : k[0].toUpperCase() + k.slice(1)}</button>)}</div><label className="mb-search"><Icon name="search" size={16} /><input aria-label="Search comparisons" placeholder="Search subject, supervisor, evidence…" value={query} onChange={e => setQuery(e.target.value)} /></label><select aria-label="Comparison status" value={status} onChange={e => setStatus(e.target.value as Status | 'all')}><option value="all">All statuses</option>{Object.entries(statuses).map(([key, value]) => <option value={key} key={key}>{value.label}</option>)}</select></div>
        <div className="mb-column-head"><div><span className="mb-system-icon"><Icon name="database" size={22} /></span><span><strong>SmartMail</strong><small>Expected state · local system of record</small></span><span className="mb-source-label">LOCAL</span></div><span className="mb-compare-icon"><Icon name="refresh" /></span><div><span className="mb-system-icon external"><Icon name="mail" size={22} /></span><span><strong>External mailbox</strong><small>{mailbox?.address || 'Observed state · select a mailbox'}</small></span><span className="mb-source-label">OBSERVED</span></div></div>
        <div className="mb-comparisons" aria-label="Expected and observed comparisons" aria-busy={loading || refreshing}>
          {loading ? <div className="mb-empty"><Icon name="refresh" size={30} /><h2>Loading reconciliation evidence</h2><p>Reading retained SmartMail records.</p></div> : filtered.length === 0 ? <div className="mb-empty"><span className="mb-empty-icon"><Icon name="branch" size={36} /></span><h2>{rows.length ? 'No comparisons match these filters' : !campaign || !student ? 'Choose a Student workspace' : 'A clear view starts with evidence'}</h2><p>{rows.length ? 'Try a different status or search term.' : 'Local work appears here alongside retained mailbox observations. Refresh evidence after connecting the dedicated extension.'}</p>{rows.length > 0 && <button className="mb-button" onClick={() => { setQuery(''); setStatus('all'); setKind('all'); }}>Clear filters</button>}</div> : filtered.map(row => {
            const state = statusOf(row); const local = row.local; const observed = row.observed;
            return <button key={row.id} className={`mb-comparison ${state}`} onClick={() => setSelected(row)} aria-label={`Inspect ${local?.subject || observed?.subject || 'evidence'}: ${statuses[state].label}`}>
              <div className={`mb-record ${!local ? 'absent' : ''}`}><span className="mb-record-icon"><Icon name={local?.kind === 'external_schedule' ? 'clock' : local?.kind === 'sent_record' ? 'send' : local?.kind === 'reply_association' ? 'reply' : 'file'} size={19} /></span><div className="mb-record-text"><strong>{local?.subject || (local?.kind === 'reply_association' ? local.supervisor : local ? 'Untitled preparation' : 'No local association')}</strong><small>{local ? `${local.supervisor} · ${local.institution}` : 'Mailbox-wide evidence · campaign unassigned'}</small><span>{local?.recipient || (local ? human(local.kind) : 'Retained for operator inspection')}</span></div><span className="mb-state">{local ? human(local.state) : 'External only'}{local?.time && <small>{date(local.time)}</small>}</span></div>
              <div className="mb-link"><span>{statuses[state].symbol}</span><small>{statuses[state].label}</small></div>
              <div className={`mb-record observed ${!observed ? 'absent' : ''}`}><span className="mb-record-icon"><Icon name={observed?.direction === 'inbound' ? 'reply' : observed?.status === 'scheduled' ? 'clock' : 'mail'} size={19} /></span><div className="mb-record-text"><strong>{observed?.subject || (observed ? 'No subject observed' : 'No linked observation')}</strong><small>{observed?.counterpart || 'Available evidence does not establish a match'}</small><span>{observed ? `${observed.folder} · ${observed.observed_time || 'Time unavailable'}` : 'Absence of evidence does not establish failure'}</span></div><span className="mb-state">{observed ? human(observed.status) : 'Not established'}<Icon name="chevron" size={13} /></span></div>
            </button>;
          })}
        </div>
        <div className="mb-coverage"><Icon name="shield" size={15} /><span><strong>Evidence coverage: {observation ? observation.evidence_coverage.complete ? 'complete within reported scope' : 'partial / limited' : 'not available'}</strong><span>{observation ? ` · ${human(observation.status)} · ${observation.messages.length} observed messages` : ' · No conclusions drawn without mailbox evidence'}</span></span><button onClick={() => setHistory(true)}>View coverage <Icon name="arrow" size={13} /></button></div>
      </main>
      <footer className="mb-footer"><span>{filtered.length} of {rows.length} comparisons · Select a row to inspect evidence</span><span>Observations do not grant sending authority</span></footer>
    </div>
    {selected && <Dialog title="Comparison details" close={() => setSelected(null)}><div className={`mb-detail-status ${statusOf(selected)}`}>{statuses[statusOf(selected)].label}</div><p>Local records are compared with the latest retained observation. A match establishes only the finding below, not delivery or reading.</p>{selected.findings.length ? selected.findings.map(f => <section className="mb-finding" key={f.id}><h3>{human(f.finding)}</h3><p>{f.detail || 'Core recorded this association from the available evidence.'}</p><dl><dt>Matching basis</dt><dd>{human(f.basis) || 'Not established'}</dd><dt>Finding ID</dt><dd>{f.id}</dd></dl></section>) : <p>No finding links this local record to the latest observation. This is not proof of failure.</p>}<div className="mb-evidence-pair"><section><h3>SmartMail expected state</h3><dl><dt>Subject</dt><dd>{selected.local?.subject || 'Not available'}</dd><dt>State</dt><dd>{human(selected.local?.state || 'No local association')}</dd><dt>Confirmed schedule</dt><dd>{selected.local?.time ? date(selected.local.time) : 'Not applicable'}</dd><dt>Record ID</dt><dd>{selected.local?.id || 'None'}</dd></dl></section><section><h3>Observed external state</h3><dl><dt>Subject</dt><dd>{selected.observed?.subject || 'Not available'}</dd><dt>State / folder</dt><dd>{selected.observed ? `${selected.observed.status} / ${selected.observed.folder}` : 'Not established'}</dd><dt>Observed time</dt><dd>{selected.observed?.observed_time || 'Not available'}</dd><dt>Platform reference</dt><dd>{selected.observed?.platform_reference || 'Not available'}</dd></dl></section></div><p className="mb-evidence-note">Unknown outcomes require reconciliation before another attempt. External edits do not inherit Confirmation. Sent Records remain immutable.</p><details><summary>Retained record and observation evidence</summary><pre>{JSON.stringify({ local: selected.local?.evidence, observed: selected.observed, observation: { id: observation?.id, observed_at: observation?.observed_at, coverage: observation?.evidence_coverage } }, null, 2)}</pre></details></Dialog>}
    {history && <Dialog title="Observation history & coverage" close={() => setHistory(false)}><p>Comparisons use the latest retained observation. Earlier observations remain evidence; they are not a live mailbox mirror.</p>{data?.history.length ? data.history.map(item => <section className="mb-finding" key={item.id}><h3>{date(item.observed_at)} <span>{human(item.status)}</span></h3><p>{item.detail || 'Retained mailbox observation'}</p><details open><summary>Evidence coverage</summary><pre>{JSON.stringify(item.evidence_coverage, null, 2)}</pre></details><small>{item.id}</small></section>) : <p>No retained observations for this mailbox.</p>}</Dialog>}
  </AppShell>;
}

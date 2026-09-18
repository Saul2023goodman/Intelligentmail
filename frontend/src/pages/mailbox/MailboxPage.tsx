import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { AppShell, Topbar } from "../../app/shell";
import { PageHeader } from "../../app/page-header";
import { navigate } from "../../app/routes";
import { useWorkspaceScope } from "../../app/scope";
import { core, human, type FollowUpStatus } from "../../core";
import { useCoreQuery } from "../../core/data";
import Icon from "../../shared/Icon";
import "./MailboxMonitor.css";

const ZONES = [
  "Asia/Shanghai", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney",
  "Europe/London", "Europe/Berlin", "America/New_York", "America/Los_Angeles", "UTC",
];

const STATE_LABEL: Record<string, string> = {
  rule_not_configured: "未配置",
  no_initial_send: "等待首封",
  ordinary_reply_received: "已有普通回复",
  reply_review_required: "回复待核对",
  follow_up_open: "已进入 Ready Pool",
  maximum_reached: "已达上限",
  due: "触发到期",
  waiting: "等待触发",
};
const STATE_TONE: Record<string, string> = {
  due: "amber",
  waiting: "blue",
  follow_up_open: "violet",
  ordinary_reply_received: "green",
  reply_review_required: "rose",
  maximum_reached: "gray",
  no_initial_send: "gray",
  rule_not_configured: "gray",
};

const formatTime = (value?: string) => value
  ? new Date(value).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    })
  : "—";

function StatusRow({ item }: { item: FollowUpStatus }) {
  const tone = STATE_TONE[item.state] ?? "gray";
  return (
    <article className="fu-task-row">
      <span className={`fu-state-dot is-${tone}`} />
      <span className="fu-task-copy">
        <strong>{item.supervisor_name}</strong>
        <small>{item.institution_name} · {item.recipient_addresses[0] || "未记录收件地址"}</small>
      </span>
      <span className="fu-task-time">
        <strong>{STATE_LABEL[item.state] ?? human(item.state)}</strong>
        <small>{item.due_at ? formatTime(item.due_at) : `第 ${item.next_sequence} 次`}</small>
      </span>
    </article>
  );
}

function ConfigDialog({ close, children }: { close: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = ref.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return (
    <dialog className="mm-config-dialog" ref={ref} onCancel={close} onClick={(event) => {
      if (event.target === event.currentTarget) close();
    }}>
      {children}
    </dialog>
  );
}

export default function MailboxPage() {
  const { scope } = useWorkspaceScope();
  const campaignId = scope?.campaignId ?? "";
  const studentId = scope?.studentId ?? "";
  const query = useCoreQuery(
    "followup_workspace",
    { campaign_id: campaignId },
    { enabled: Boolean(campaignId), refetchInterval: 30_000 },
  );
  const workspaceQuery = useCoreQuery(
    "workspace",
    { campaign_id: campaignId },
    { enabled: Boolean(campaignId), refetchInterval: 30_000 },
  );
  const mailboxQuery = useCoreQuery(
    "mailbox_workspace",
    { campaign_id: campaignId, student_id: studentId },
    { enabled: Boolean(campaignId && studentId), refetchInterval: 30_000 },
  );
  const data = query.data;
  const mailboxData = mailboxQuery.data;
  const mailboxSummary = workspaceQuery.data?.mailboxes.find((item) => item.student_id === studentId);
  const observation = mailboxData?.observation;
  const canRead = workspaceQuery.data?.mailbox_capabilities.capabilities.read_history.available ?? false;
  const rule = data?.rule;
  const [enabled, setEnabled] = useState(false);
  const [delay, setDelay] = useState("3");
  const [maximum, setMaximum] = useState("2");
  const [timezone, setTimezone] = useState("Asia/Shanghai");
  const [sendTime, setSendTime] = useState("09:00");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [hydratedRevision, setHydratedRevision] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const revision = rule?.revision ?? 0;
    if (hydratedRevision === revision) return;
    // oxlint-disable-next-line react/set-state-in-effect -- Rehydrate only when Core publishes a new confirmed policy revision.
    setEnabled(rule?.enabled ?? false);
    setDelay(String(rule?.delay_days ?? 3));
    setMaximum(String(rule?.maximum_count ?? 2));
    setTimezone(rule?.timezone || "Asia/Shanghai");
    setSendTime(rule?.send_time || "09:00");
    setSubject(rule?.subject_template ?? "");
    setBody(rule?.body_template ?? "");
    setHydratedRevision(revision);
  }, [hydratedRevision, rule]);

  const sortedStatuses = useMemo(() => [...(data?.statuses ?? [])].sort((a, b) => {
    const order = ["due", "reply_review_required", "follow_up_open", "waiting"];
    return (order.indexOf(a.state) < 0 ? 99 : order.indexOf(a.state))
      - (order.indexOf(b.state) < 0 ? 99 : order.indexOf(b.state));
  }), [data?.statuses]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!campaignId || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const configured = await core("followup_configure", {
        campaign_id: campaignId,
        delay_days: Number(delay),
        maximum_count: Number(maximum),
        subject_template: subject,
        body_template: body,
        enabled,
        timezone,
        send_time: sendTime,
      });
      setHydratedRevision(configured.rule.revision);
      if (configured.rule.enabled) {
        const processed = await core("followup_process", { campaign_id: campaignId });
        query.setData(processed.workspace);
        setNotice(
          processed.state === "ready_pool"
            ? `触发策略已确认；${processed.ready_preparation_ids.length} 个动作已进入 Batch execution 的 Ready Pool。`
            : "触发策略已确认，系统已完成一次到期检查。",
        );
      } else {
        query.setData(configured.workspace);
        setNotice("自动 Follow-up 已停用；不会派生新的动作。 ");
      }
      setConfigOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function refreshMailbox() {
    if (!studentId || refreshing) return;
    setRefreshing(true);
    setError("");
    setNotice("");
    try {
      const result = await core("refresh_mailbox", { student_id: studentId });
      const processed = await core("followup_process", { campaign_id: campaignId });
      query.setData(processed.workspace);
      await Promise.all([workspaceQuery.refresh(), mailboxQuery.refresh()]);
      setNotice(
        `邮箱监测已更新：${human(result.observation.status)}。新回复已参与 Follow-up 触发判断。`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRefreshing(false);
    }
  }

  const loading = query.isLoading || workspaceQuery.isLoading || mailboxQuery.isLoading;
  const queryError = query.error?.message || workspaceQuery.error?.message || mailboxQuery.error?.message || "";
  const displayError = error || queryError;

  const openActions = (data?.actions ?? []).filter((action) => action.status !== "sent");
  return (
    <AppShell className="followup-page mailbox-monitor-page" activeRoute="mailbox">
      <div className="workspace">
        <Topbar breadcrumb="Mailbox monitor" homeHref="#workflow">
          <span className={`fu-live ${observation ? "is-on" : ""}`}>
            <i /> {observation ? `Observed ${formatTime(observation.observed_at)}` : "Awaiting mailbox evidence"}
          </span>
        </Topbar>
        <PageHeader
          eyebrow="Signal monitoring"
          title="Mailbox monitor"
          subtitle="Mailbox evidence drives one Follow-up trigger; Batch execution owns every send."
          badge={rule?.enabled ? `Trigger v${rule.revision}` : "Trigger off"}
          actions={<>
            <button className="fu-button" onClick={() => setConfigOpen(true)}><Icon name="filter" size={15} /> 配置 Follow-up 触发</button>
            <button className="fu-button" onClick={() => navigate("records")}><Icon name="book" size={15} /> 历史证据</button>
            <button className="fu-button fu-primary" disabled={loading || refreshing || !canRead} onClick={refreshMailbox}>
              <Icon name="refresh" size={15} /> {refreshing ? "监测中…" : "刷新邮箱"}
            </button>
          </>}
        />
        {(displayError || notice) && (
          <div className={`fu-banner ${displayError ? "is-error" : ""}`} role={displayError ? "alert" : "status"}>
            <span>{displayError || notice}</span>
            <button aria-label="Dismiss" onClick={() => { setError(""); setNotice(""); }}><Icon name="close" size={14} /></button>
          </div>
        )}
        <main className="mm-main" aria-busy={loading || busy}>
          <section className="mm-flow" aria-label="Mailbox to execution flow">
            <article className="is-current"><span>01</span><Icon name="mail" size={18} /><div><strong>Mailbox signal</strong><small>read-only observation</small></div></article>
            <i><Icon name="arrow" size={14} /></i>
            <article className={rule?.enabled ? "is-current" : ""}><span>02</span><Icon name="reply" size={18} /><div><strong>Follow-up trigger</strong><small>evaluate and prepare once</small></div></article>
            <i><Icon name="arrow" size={14} /></i>
            <article><span>03</span><Icon name="database" size={18} /><div><strong>Global Ready Pool</strong><small>owned by Batch execution</small></div></article>
          </section>

          <section className="mm-dashboard">
            <section className="mm-card mm-monitor">
              <header><span><Icon name="mail" size={18} /></span><div><h2>Current mailbox signal</h2><p>{scope?.mailbox || "No Student mailbox selected"}</p></div><b className={canRead ? "is-on" : ""}>{canRead ? "READABLE" : "OFFLINE"}</b></header>
              <div className="mm-monitor-body">
                <div className="mm-signal">
                  <span className={observation?.status === "complete" ? "is-complete" : ""}><Icon name="refresh" size={21} /></span>
                  <div><strong>{observation ? human(observation.status) : "No observation"}</strong><small>{observation ? formatTime(observation.observed_at) : "Connect the dedicated extension"}</small></div>
                </div>
                <dl className="mm-facts">
                  <div><dt>Monitoring runs</dt><dd>{mailboxSummary?.observation_count ?? 0}</dd></div>
                  <div><dt>Observed messages</dt><dd>{mailboxSummary?.message_count ?? 0}</dd></div>
                  <div><dt>Latest batch</dt><dd>{observation?.messages.length ?? 0}</dd></div>
                  <div><dt>Coverage</dt><dd>{observation ? observation.evidence_coverage.complete ? "reported scope complete" : "limited" : "none"}</dd></div>
                </dl>
                <p className="mm-boundary"><Icon name="shield" size={13} /> Observation changes eligibility only. It never sends and never grants sending authority.</p>
              </div>
              <footer><button onClick={() => navigate("records")}>Inspect observations & reconciliation <Icon name="arrow" size={12} /></button></footer>
            </section>

            <section className="mm-card mm-trigger">
              <header><span><Icon name="reply" size={18} /></span><div><h2>Follow-up trigger</h2><p>One due Task creates one Ready Preparation</p></div><b className={rule?.enabled ? "is-on" : ""}>{rule?.enabled ? "ACTIVE" : "OFF"}</b></header>
              <div className="mm-policy">
                <div><span>Delay</span><strong>{rule ? `${rule.delay_days} days` : "—"}</strong></div>
                <div><span>Trigger time</span><strong>{rule?.send_time || "—"}</strong></div>
                <div><span>Maximum</span><strong>{rule ? rule.maximum_count : "—"}</strong></div>
                <div><span>Waiting</span><strong>{data?.summary.waiting ?? 0}</strong></div>
                <button onClick={() => setConfigOpen(true)}>Edit trigger policy</button>
              </div>
              <div className="mm-trigger-list">
                {sortedStatuses.map((item) => <StatusRow key={item.task_id} item={item} />)}
                {!sortedStatuses.length && <div className="fu-empty"><Icon name="reply" /> No Outreach Tasks in this Campaign</div>}
              </div>
            </section>
          </section>

          <section className="mm-ready">
            <header><span><Icon name="database" size={16} /></span><div><h2>Ready Pool handoff</h2><p>Follow-up stops here. Selection, scheduling, exact Confirmation and send live in Batch execution.</p></div><b>{openActions.filter((action) => action.preparation?.ready).length} ready</b><button className="fu-button fu-primary" onClick={() => navigate("execution")}>Open Batch execution <Icon name="arrow" size={13} /></button></header>
            <div className="mm-ready-list">
              {openActions.slice().reverse().map((action) => (
                <article key={action.id}>
                  <span className={`fu-state-dot is-${action.preparation?.ready ? "green" : "amber"}`} />
                  <div><strong>{action.preparation?.subject || `Follow-up #${action.sequence}`}</strong><small>{formatTime(action.due_at)} · trigger policy v{action.rule_revision}</small></div>
                  <em>{action.preparation?.ready ? "READY POOL" : "PREPARATION REQUIRED"}</em>
                </article>
              ))}
              {!openActions.length && <p>No triggered Follow-up Action is waiting in the Ready Pool.</p>}
            </div>
          </section>
        </main>
        <footer className="fu-footer"><span><Icon name="shield" size={13} /> One module, one transition: Mailbox observes · Follow-up triggers · Batch execution confirms and sends</span><span>{rule?.confirmed_at ? `Trigger confirmed ${formatTime(rule.confirmed_at)}` : "No trigger policy"}</span></footer>
      </div>

      {configOpen && (
        <ConfigDialog close={() => !busy && setConfigOpen(false)}>
          <form className="fu-config" onSubmit={save}>
            <header className="mm-dialog-head"><div><span>FOLLOW-UP TRIGGER</span><h2>Configure deterministic handoff</h2><p>Saving confirms trigger creation only; it never confirms a send.</p></div><button type="button" aria-label="Close trigger configuration" onClick={() => setConfigOpen(false)}><Icon name="close" /></button></header>
            <div className="fu-config-scroll">
              <section className="fu-section mm-enable-row"><div><h3>Trigger automation</h3><p>Evaluate on mailbox refresh and background scheduler ticks.</p></div><label className="fu-switch"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /><span />{enabled ? "启用" : "停用"}</label></section>
              <section className="fu-section"><h3>Eligibility and timing</h3><div className="fu-fixed-rules"><span><Icon name="check" size={13} /> 无普通回复</span><span><Icon name="check" size={13} /> 自动回复不阻断</span><span><Icon name="check" size={13} /> 歧义回复暂停</span></div><div className="fu-fields two"><label>上次发送后<span className="fu-suffix"><input type="number" min="0" required value={delay} onChange={(e) => setDelay(e.target.value)} /> 天</span></label><label>最多 Follow-up<span className="fu-suffix"><input type="number" min="1" required value={maximum} onChange={(e) => setMaximum(e.target.value)} /> 次</span></label><label>触发时间<input type="time" required value={sendTime} onChange={(e) => setSendTime(e.target.value)} /></label><label>时区<select value={timezone} onChange={(e) => setTimezone(e.target.value)}>{ZONES.map((zone) => <option key={zone}>{zone}</option>)}</select></label></div></section>
              <section className="fu-section fu-template"><h3>Ready Preparation template</h3><p>允许字段：supervisor_name、student_name、institution、original_subject</p><label>主题模板<input required={enabled} value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Re: {original_subject}" /></label><label>正文模板<textarea required={enabled} rows={6} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Dear {supervisor_name}, …" /></label></section>
            </div>
            <footer className="fu-config-foot"><span><Icon name="database" size={13} /> Triggered content enters Batch execution as Ready, never directly Sent</span><button className="fu-button fu-primary" disabled={busy || !campaignId}>{busy ? "保存中…" : enabled ? "保存并确认触发策略" : "保存停用状态"}</button></footer>
          </form>
        </ConfigDialog>
      )}
    </AppShell>
  );
}

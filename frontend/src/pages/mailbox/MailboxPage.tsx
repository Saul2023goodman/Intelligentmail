import { useEffect, useMemo, useState, type FormEvent } from "react";
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
  follow_up_open: "已进入执行",
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
          processed.state === "awaiting_mailbox"
            ? "配置已确认；已到期动作已进入队列，等待邮箱执行能力。"
            : "配置已确认，系统已完成一次触发检查。",
        );
      } else {
        query.setData(configured.workspace);
        setNotice("自动 Follow-up 已停用；不会派生新的动作。 ");
      }
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

  return (
    <AppShell className="followup-page mailbox-monitor-page" activeRoute="mailbox">
      <div className="workspace">
        <Topbar breadcrumb="Mailbox monitoring" homeHref="#workflow">
          <span className={`fu-live ${rule?.enabled ? "is-on" : ""}`}>
            <i /> {observation ? `Observed ${formatTime(observation.observed_at)}` : "No observation"}
          </span>
        </Topbar>
        <PageHeader
          eyebrow="Mailbox monitoring"
          title="Mailbox & Follow-up"
          subtitle="Observe replies, evaluate triggers, and hand confirmed actions to Execution."
          badge={rule?.enabled ? `Automation v${rule.revision}` : "Automation off"}
          actions={
            <>
              <button className="fu-button" onClick={() => navigate("records")}>
                <Icon name="book" size={15} /> 对账与历史证据
              </button>
              <button
                className="fu-button fu-primary"
                disabled={loading || busy || refreshing || !canRead}
                onClick={refreshMailbox}
              >
                <Icon name="refresh" size={15} /> {refreshing ? "正在监测…" : "刷新邮箱监测"}
              </button>
            </>
          }
        />
        {(displayError || notice) && (
          <div className={`fu-banner ${displayError ? "is-error" : ""}`} role={displayError ? "alert" : "status"}>
            <span>{displayError || notice}</span>
            <button aria-label="Dismiss" onClick={() => { setError(""); setNotice(""); }}>
              <Icon name="close" size={14} />
            </button>
          </div>
        )}
        <main className="fu-main" aria-busy={loading || busy}>
          <form className="fu-panel fu-config" onSubmit={save}>
            <header className="fu-panel-head">
              <span><Icon name="shield" size={17} /></span>
              <div>
                <h2>触发与授权配置</h2>
                <p>保存并启用即构成持续 Confirmation</p>
              </div>
              <label className="fu-switch">
                <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
                <span />
                {enabled ? "启用" : "停用"}
              </label>
            </header>
            <div className="fu-config-scroll">
              <section className="fu-section">
                <h3>触发条件</h3>
                <div className="fu-fixed-rules">
                  <span><Icon name="check" size={13} /> 无普通回复</span>
                  <span><Icon name="check" size={13} /> 自动回复不阻断</span>
                  <span><Icon name="check" size={13} /> 歧义回复暂停</span>
                </div>
                <div className="fu-fields two">
                  <label>首次 / 上次发送后
                    <span className="fu-suffix"><input type="number" min="0" required value={delay} onChange={(e) => setDelay(e.target.value)} /> 天</span>
                  </label>
                  <label>最多 Follow-up
                    <span className="fu-suffix"><input type="number" min="1" required value={maximum} onChange={(e) => setMaximum(e.target.value)} /> 次</span>
                  </label>
                </div>
              </section>
              <section className="fu-section">
                <h3>执行时间</h3>
                <div className="fu-fields two">
                  <label>本地时间<input type="time" required value={sendTime} onChange={(e) => setSendTime(e.target.value)} /></label>
                  <label>时区
                    <select value={timezone} onChange={(e) => setTimezone(e.target.value)}>
                      {ZONES.map((zone) => <option key={zone}>{zone}</option>)}
                    </select>
                  </label>
                </div>
              </section>
              <section className="fu-section fu-template">
                <h3>确定性内容模板</h3>
                <p>允许字段：supervisor_name、student_name、institution、original_subject</p>
                <label>主题模板<input required={enabled} value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Re: {original_subject}" /></label>
                <label>正文模板<textarea required={enabled} rows={6} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Dear {supervisor_name}, …" /></label>
              </section>
            </div>
            <footer className="fu-config-foot">
              <span><Icon name="shield" size={13} /> 内容或时间变更会生成新授权版本</span>
              <button className="fu-button fu-primary" disabled={busy || !campaignId}>
                {busy ? "正在保存…" : enabled ? "保存并确认自动跟进" : "保存停用状态"}
              </button>
            </footer>
          </form>

          <section className="fu-operations">
            <div className="fu-overview">
              <div className="fu-metrics">
                <article><span>监测批次</span><strong>{mailboxSummary?.observation_count ?? 0}</strong><small>保留在 Records</small></article>
                <article><span>观察邮件</span><strong>{mailboxSummary?.message_count ?? 0}</strong><small>只读邮箱证据</small></article>
                <article><span>等待触发</span><strong>{data?.summary.waiting ?? 0}</strong><small>按已确认时间计算</small></article>
                <article><span>开放动作</span><strong>{data?.summary.open_actions ?? 0}</strong><small>已交给 Execution</small></article>
              </div>
              <div className={`fu-mailbox-strip ${canRead ? "is-ready" : ""}`}>
                <span className="fu-mailbox-icon"><Icon name="mail" size={17} /></span>
                <span>
                  <strong>{scope?.mailbox || "未选择学生邮箱"}</strong>
                  <small>
                    {observation
                      ? `${human(observation.status)} · ${observation.messages.length} messages · coverage ${observation.evidence_coverage.complete ? "complete in reported scope" : "limited"}`
                      : canRead ? "网关可读，尚无保留监测批次" : "连接当前学生的 163 邮箱扩展后才能刷新"}
                  </small>
                </span>
                <button onClick={() => navigate("records")}>查看证据链 <Icon name="arrow" size={12} /></button>
              </div>
            </div>

            <section className="fu-panel fu-status-panel">
              <header className="fu-panel-head">
                <span><Icon name="clock" size={17} /></span>
                <div><h2>邮箱驱动的触发监视</h2><p>{data?.summary.tasks ?? 0} 个 Outreach Task · 普通回复会停止 Follow-up</p></div>
                <span className={`fu-capability ${data?.availability.available ? "is-ready" : ""}`}>
                  {data?.flow.state === "paused" ? "执行已暂停" : data?.availability.available ? "邮箱可执行" : "等待邮箱"}
                </span>
              </header>
              <div className="fu-list">
                {sortedStatuses.map((item) => <StatusRow key={item.task_id} item={item} />)}
                {!sortedStatuses.length && <div className="fu-empty"><Icon name="reply" /> 当前 Campaign 尚无 Outreach Task</div>}
              </div>
            </section>

            <section className="fu-panel fu-audit-panel">
              <header className="fu-panel-head">
                <span><Icon name="book" size={17} /></span>
                <div><h2>进入 Execution</h2><p>策略 Confirmation → 精确 Confirmation → Attempt；完整证据在 Records</p></div>
              </header>
              <div className="fu-audit-list">
                {(data?.actions ?? []).slice().reverse().map((action) => (
                  <article key={action.id}>
                    <span className={`fu-state-dot is-${action.status === "sent" ? "green" : action.attempt ? "amber" : "violet"}`} />
                    <div>
                      <strong>Follow-up #{action.sequence} · {human(action.status)}</strong>
                      <small>{action.preparation?.subject || action.detail || "等待生成确定内容"}</small>
                    </div>
                    <dl>
                      <dt>触发</dt><dd>{formatTime(action.due_at)}</dd>
                      <dt>授权</dt><dd>{action.confirmation ? `v${action.rule_revision}` : "—"}</dd>
                      <dt>结果</dt><dd>{action.attempt ? human(action.attempt.state) : "未尝试"}</dd>
                    </dl>
                  </article>
                ))}
                {!data?.actions.length && <div className="fu-empty"><Icon name="book" /> 尚未触发 Follow-up Action</div>}
              </div>
            </section>
          </section>
        </main>
        <footer className="fu-footer">
          <span><Icon name="shield" size={13} /> Mailbox only observes and triggers; every external action still uses the Execution Flow</span>
          <span>{rule?.confirmed_at ? `Automation confirmed ${formatTime(rule.confirmed_at)}` : "No standing Confirmation"}</span>
        </footer>
      </div>
    </AppShell>
  );
}

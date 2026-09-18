import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { core } from "../../core";
import { gatewayHealth } from "../../core/gateway";
import { useCoreQuery } from "../../core/data";
import { fitScale } from "./workflow-model";
import Workflow from "./Workflow";
import Icon from "../../shared/Icon";
import { AppShell, Topbar } from "../../app/shell";
import { StudentDialog } from "../../app/student-dialog";
import { navigate, type Route } from "../../app/routes";
import { useWorkspaceScope } from "../../app/scope";
import "./Workspace.css";

const GATEWAY_STATE_LABEL: Record<string, string> = {
  connected: "已连接",
  disconnected: "未连接",
  mismatch: "连接作用域不符",
  unavailable: "网关未启用",
};
const formatTime = (value: null | string) =>
  value ? new Date(value).toLocaleString() : "尚未观察";

export default function WorkspacePage({ route }: { route: Route }) {
  const { scope, setScope } = useWorkspaceScope();
  const studentId = scope?.studentId ?? "";
  const campaignId = scope?.campaignId ?? "";
  const workspaceQuery = useCoreQuery(
    "workspace",
    campaignId ? { campaign_id: campaignId } : {},
  );
  const gatewayQuery = useCoreQuery(
    "gateway_status",
    {},
    { maxAge: 1_000, refetchInterval: route === "workflow" ? 2_000 : 0 },
  );
  const data = workspaceQuery.data;
  const [selected, setSelected] = useState("mailbox");
  const [scale, setScale] = useState(1);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [newStudent, setNewStudent] = useState(false);
  const [gatewayPanel, setGatewayPanel] = useState(false);
  const [observing, setObserving] = useState(false);
  const view = route;
  const frame = useRef<HTMLDivElement>(null);
  const studentMailbox =
    data?.mailboxes.find((mailbox) => mailbox.student_id === studentId) ??
    null;
  const gateway = useMemo(
    () => gatewayHealth(gatewayQuery.data ?? data?.mailbox_capabilities.gateway, studentMailbox),
    [data?.mailbox_capabilities.gateway, gatewayQuery.data, studentMailbox],
  );
  const refreshWorkspace = workspaceQuery.refresh;
  const refreshGateway = gatewayQuery.refresh;
  // The scope is written only by the global switcher and by first-run
  // selection; this effect never re-points an operator's chosen Student.
  useEffect(() => {
    if (!data || scope) return;
    const first = data.mailboxes[0];
    if (!first) return;
    // oxlint-disable-next-line react/set-state-in-effect -- Pick the initial Student once the Core mailbox list arrives.
    setScope({
      studentId: first.student_id,
      studentName: first.student_name,
      mailbox: first.address,
      campaignId: first.campaign_id,
      campaignName:
        data.campaigns.find((campaign) => campaign.id === first.campaign_id)
          ?.name ?? "",
    });
  }, [data, scope, setScope]);
  // Keep the scope's descriptive labels aligned with Core's own records.
  useEffect(() => {
    if (!data || !studentId) return;
    const mailbox = data.mailboxes.find((item) => item.student_id === studentId);
    if (!mailbox) return;
    const campaignName =
      data.campaigns.find((campaign) => campaign.id === mailbox.campaign_id)
        ?.name ?? "";
    if (
      mailbox.address === scope?.mailbox &&
      mailbox.student_name === scope?.studentName &&
      mailbox.campaign_id === scope?.campaignId &&
      campaignName === scope?.campaignName
    )
      return;
    // oxlint-disable-next-line react/set-state-in-effect -- Reflect renamed Core records in the shared scope label.
    setScope({
      studentId,
      studentName: mailbox.student_name,
      mailbox: mailbox.address,
      campaignId: mailbox.campaign_id,
      campaignName,
    });
  }, [data, scope, setScope, studentId]);
  const reload = useCallback(
    () => Promise.all([refreshWorkspace(), refreshGateway()]),
    [refreshGateway, refreshWorkspace],
  );
  const busy = observing;
  const displayError = error || workspaceQuery.error?.message || "";
  const openGateway = useCallback(() => {
    setError("");
    setGatewayPanel(true);
  }, []);
  useEffect(() => {
    if (!gatewayPanel) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setGatewayPanel(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [gatewayPanel]);
  // Read-only observation through the connected gateway. Evidence is persisted
  // and reconciled by Core; the gateway state is reloaded afterwards.
  const observeMailbox = useCallback(async () => {
    if (!studentId || !gateway.canObserve) return;
    setObserving(true);
    setError("");
    try {
      const result = await core("refresh_mailbox", { student_id: studentId });
      await reload();
      const count = result.observation.messages?.length ?? 0;
      setNotice(
        `邮箱证据已更新（${result.observation.status}，${count} 封邮件观察）。可在 Mailbox 对账工作区查看。`,
      );
      setGatewayPanel(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setObserving(false);
    }
  }, [studentId, gateway.canObserve, reload]);
  const hasMailboxes = !!data?.mailboxes.length;
  useEffect(() => {
    const el = frame.current;
    if (!el || !hasMailboxes) return;
    const update = () => setScale(fitScale(el.clientWidth, el.clientHeight));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMailboxes]);
  // Remain mounted while other pages are active, preserving scope state.
  if (view !== "workflow") return null;
  const banners = (
    <>
      {displayError && (
        <div role="alert" className="banner error">
          {displayError}
          <button onClick={reload}>Retry connection</button>
        </div>
      )}
      {notice && !displayError && (
        <div role="status" className="banner">
          {notice}
          <button
            aria-label="Dismiss notification"
            onClick={() => setNotice("")}
          >
            <Icon name="close" size={14} />
          </button>
        </div>
      )}
    </>
  );
  return (
    <AppShell
      className="workspace-page"
      activeRoute="workflow"
    >
      <div className="workspace">
        <Topbar breadcrumb="Workflow" homeHref="/">
          <span className={`connection ${displayError ? "offline" : ""}`}>
            <i />
            {displayError
              ? "Connection needs attention"
              : data
                ? "Core connected"
                : "Connecting to Core"}
          </span>
          <button
            className="icon-button"
            title="Refresh Core data"
            aria-label="Refresh Core data"
            onClick={reload}
            disabled={busy || workspaceQuery.isFetching}
          >
            <Icon name="refresh" size={18} />
          </button>
        </Topbar>
        <main className="workflow-stage" aria-label="Outreach workflow">
          <div className="workspace-context">
            {studentMailbox ? (
              <>
                <span className="context-campaign">
                  {scope?.campaignName || "Campaign"}
                </span>
                <span className="context-sep" aria-hidden="true">
                  ·
                </span>
                <span>{studentMailbox.address}</span>
                <span className="context-sep" aria-hidden="true">
                  ·
                </span>
                <span>{studentMailbox.observation_count} 次邮箱读取</span>
                <span className="context-sep" aria-hidden="true">
                  ·
                </span>
                <span>{data?.report?.counts.tasks ?? 0} outreach tasks</span>
                <button
                  type="button"
                  className={`gateway-pill ${gateway.state}`}
                  onClick={openGateway}
                  title="管理邮箱网关连接"
                >
                  <i className={gateway.state === "disconnected" ? "pulse" : ""} />
                  {gateway.state === "connected"
                    ? "网关已连接"
                    : gateway.state === "mismatch"
                      ? "网关作用域不符"
                      : gateway.state === "disconnected"
                        ? "连接邮箱"
                        : "邮箱网关"}
                  <Icon name="chevron" size={11} />
                </button>
              </>
            ) : (
              <span className="context-empty">
                在右上角的学生工作区切换器中选择或新增学生
              </span>
            )}
          </div>
          {banners}
          <div className="workflow-frame" ref={frame}>
            {hasMailboxes ? (
              <Workflow
                data={data}
                selected={selected}
                onSelect={setSelected}
                onManageGateway={openGateway}
                gateway={gateway}
                scale={scale}
              />
            ) : (
              <div className="workflow-empty">
                <span className="workflow-empty-icon">
                  <Icon name="mail" size={28} />
                </span>
                <h2>设定第一位学生</h2>
                <p>
                  学生即本页的工作流空间（Campaign）。添加学生姓名与其 163
                  邮箱后，在工作流起点的<strong>邮箱网关</strong>连接专用扩展，
                  即可只读观察邮箱证据并导入来源材料；网关是外部执行基础设施，不单独占用设置页。
                </p>
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() => setNewStudent(true)}
                >
                  <Icon name="plus" size={17} /> 新增学生
                </button>
              </div>
            )}
            <div className="canvas-legend">
              <span>
                <i className="green-dot" />
                Preparation
              </span>
              <span>
                <i className="rose-dot" />
                Operator review
              </span>
              <span>
                <i className="purple-dot" />
                Follow-up
              </span>
            </div>
          </div>
        </main>
        <StudentDialog
          open={newStudent}
          onClose={() => setNewStudent(false)}
          onCreated={(value) =>
            setNotice(
              `已添加学生 ${value.name}（${value.mailbox}）。通过 Core CLI 导入来源材料后，任务将出现在工作流中。`,
            )
          }
        />
        {gatewayPanel && (
          <div
            className="modal-backdrop"
            onClick={(e) => {
              if (e.target === e.currentTarget) setGatewayPanel(false);
            }}
          >
            <section
              role="dialog"
              aria-modal="true"
              aria-labelledby="gateway-title"
              className="modal gateway-modal"
              onKeyDown={(e) => {
                if (e.key === "Escape") setGatewayPanel(false);
              }}
            >
              <button
                className="modal-close icon-button"
                aria-label="Close gateway panel"
                onClick={() => setGatewayPanel(false)}
              >
                <Icon name="close" />
              </button>
              <div className="eyebrow">EXTERNAL EXECUTION INFRASTRUCTURE</div>
              <h2 id="gateway-title">
                邮箱网关 <span>Mailbox Gateway</span>
              </h2>
              <p>
                网关是 SmartMail 观察邮箱与执行已确认操作的唯一通道。它连接一个已登录的
                163 邮箱标签页；观察始终只读，读取不会授权发送。
              </p>

              <div className={`gateway-status ${gateway.state}`}>
                <i className={gateway.state === "disconnected" || gateway.state === "mismatch" ? "pulse" : ""} />
                <div>
                  <strong>{GATEWAY_STATE_LABEL[gateway.state]}</strong>
                  <small>
                    {gateway.state === "connected"
                      ? `已连接 ${gateway.connectedAddress}`
                      : gateway.state === "mismatch"
                        ? `当前连接 ${gateway.connectedAddress || "—"}，与学生邮箱不一致`
                        : gateway.state === "disconnected"
                          ? "扩展未连接邮箱标签页"
                          : "未启用 163 邮箱扩展适配器"}
                  </small>
                </div>
              </div>

              <dl className="gateway-facts">
                <div>
                  <dt>适配器</dt>
                  <dd>{data?.mailbox_capabilities.adapter || "unavailable"}</dd>
                </div>
                <div>
                  <dt>桥接协议</dt>
                  <dd>
                    v{(gatewayQuery.data ?? data?.mailbox_capabilities.gateway)?.protocol ?? 0}
                  </dd>
                </div>
                <div>
                  <dt>已连接邮箱</dt>
                  <dd>{gateway.connectedAddress || "—"}</dd>
                </div>
                <div>
                  <dt>当前学生邮箱</dt>
                  <dd>{gateway.studentAddress || "尚未选择学生"}</dd>
                </div>
                <div>
                  <dt>最近观察</dt>
                  <dd>
                    {studentMailbox?.latest
                      ? `${formatTime(studentMailbox.latest.observed_at)} · ${studentMailbox.latest.status}`
                      : "尚未观察"}
                  </dd>
                </div>
                <div>
                  <dt>观察批次 / 邮件</dt>
                  <dd>
                    {studentMailbox
                      ? `${studentMailbox.observation_count} · ${studentMailbox.message_count}`
                      : "—"}
                  </dd>
                </div>
              </dl>

              {gateway.state === "disconnected" && (
                <ol className="gateway-steps">
                  <li>在浏览器中登录目标 163 邮箱并进入邮箱主页。</li>
                  <li>扩展会自动发现并连接；页面刷新或桥接抖动后也会自动恢复。</li>
                  <li>只有同时打开多个邮箱页时，才需在目标页面点扩展图标选择。</li>
                </ol>
              )}
              {gateway.state === "mismatch" && (
                <p className="gateway-note">
                  扩展同时只能连接一个标签页。请在扩展中断开当前邮箱，重新连接
                  <strong> {gateway.studentAddress || "该学生的邮箱"} </strong>
                  后再读取。
                </p>
              )}
              {gateway.state === "unavailable" && (
                <p className="gateway-note">
                  Core 未启用专用扩展适配器。安装并注册扩展、连接邮箱标签页后，网关会变为可用。
                </p>
              )}

              <div className="gateway-actions">
                <button
                  type="button"
                  className="primary"
                  disabled={!gateway.canObserve || observing}
                  onClick={observeMailbox}
                  title={gateway.canObserve ? "只读观察邮箱并由 Core 保存对账" : "需要连接到当前学生的邮箱"}
                >
                  <Icon name="refresh" size={15} />
                  {observing ? "正在观察邮箱…" : "刷新邮箱证据"}
                </button>
                <button
                  type="button"
                  className="gateway-secondary"
                  disabled={observing}
                  onClick={() => {
                    setGatewayPanel(false);
                    navigate("mailbox");
                  }}
                >
                  管理对账 <Icon name="arrow" size={14} />
                </button>
                <button
                  type="button"
                  className="gateway-secondary"
                  disabled={observing || busy}
                  onClick={reload}
                >
                  立即检查状态
                </button>
              </div>
              <p className="gateway-foot">
                <Icon name="shield" size={13} />
                每次观察经 Core 持久化并对账；观察不创建任务、不授权发送。
              </p>
            </section>
          </div>
        )}
      </div>
    </AppShell>
  );
}

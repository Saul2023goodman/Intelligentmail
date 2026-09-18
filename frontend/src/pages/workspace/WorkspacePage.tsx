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
  connected: "Connected",
  disconnected: "Not connected",
  mismatch: "Connection scope mismatch",
  unavailable: "Gateway not enabled",
};
const formatTime = (value: null | string) =>
  value ? new Date(value).toLocaleString() : "Not yet observed";

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
        `Mailbox evidence refreshed (${result.observation.status}, ${count} messages observed). View it in the Mailbox reconciliation workspace.`,
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
                <span>{studentMailbox.observation_count} mailbox observations</span>
                <span className="context-sep" aria-hidden="true">
                  ·
                </span>
                <span>{data?.report?.counts.tasks ?? 0} outreach tasks</span>
                <button
                  type="button"
                  className={`gateway-pill ${gateway.state}`}
                  onClick={openGateway}
                  title="Manage mailbox gateway connection"
                >
                  <i className={gateway.state === "disconnected" ? "pulse" : ""} />
                  {gateway.state === "connected"
                    ? "Gateway connected"
                    : gateway.state === "mismatch"
                      ? "Gateway scope mismatch"
                      : gateway.state === "disconnected"
                        ? "Connect mailbox"
                        : "Mailbox gateway"}
                  <Icon name="chevron" size={11} />
                </button>
              </>
            ) : (
              <span className="context-empty">
                Select or add a student in the student workspace switcher at the top right
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
                <h2>Set up your first student</h2>
                <p>
                  Each student is this page's workflow space (Campaign). After adding the
                  student's name and their 163 mailbox, connect the dedicated extension at the
                  <strong> Mailbox gateway</strong> at the start of the workflow to observe
                  mailbox evidence read-only and import source materials; the gateway is external
                  execution infrastructure and does not have its own settings page.
                </p>
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() => setNewStudent(true)}
                >
                  <Icon name="plus" size={17} /> Add student
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
              `Added student ${value.name} (${value.mailbox}). After importing source materials via the Core CLI, tasks will appear in the workflow.`,
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
                Mailbox gateway <span>Mailbox Gateway</span>
              </h2>
              <p>
                The gateway is SmartMail's only channel for observing mailboxes and executing
                confirmed actions. It connects one signed-in 163 mailbox tab; observation is
                always read-only, and reading never authorizes sending.
              </p>

              <div className={`gateway-status ${gateway.state}`}>
                <i className={gateway.state === "disconnected" || gateway.state === "mismatch" ? "pulse" : ""} />
                <div>
                  <strong>{GATEWAY_STATE_LABEL[gateway.state]}</strong>
                  <small>
                    {gateway.state === "connected"
                      ? `Connected to ${gateway.connectedAddress}`
                      : gateway.state === "mismatch"
                        ? `Currently connected to ${gateway.connectedAddress || "—"}, which does not match the student mailbox`
                        : gateway.state === "disconnected"
                          ? "The extension is not connected to a mailbox tab"
                          : "The 163 mailbox extension adapter is not enabled"}
                  </small>
                </div>
              </div>

              <dl className="gateway-facts">
                <div>
                  <dt>Adapter</dt>
                  <dd>{data?.mailbox_capabilities.adapter || "unavailable"}</dd>
                </div>
                <div>
                  <dt>Bridge protocol</dt>
                  <dd>
                    v{(gatewayQuery.data ?? data?.mailbox_capabilities.gateway)?.protocol ?? 0}
                  </dd>
                </div>
                <div>
                  <dt>Connected mailbox</dt>
                  <dd>{gateway.connectedAddress || "—"}</dd>
                </div>
                <div>
                  <dt>Current student mailbox</dt>
                  <dd>{gateway.studentAddress || "No student selected"}</dd>
                </div>
                <div>
                  <dt>Latest observation</dt>
                  <dd>
                    {studentMailbox?.latest
                      ? `${formatTime(studentMailbox.latest.observed_at)} · ${studentMailbox.latest.status}`
                      : "Not yet observed"}
                  </dd>
                </div>
                <div>
                  <dt>Observation batches / messages</dt>
                  <dd>
                    {studentMailbox
                      ? `${studentMailbox.observation_count} · ${studentMailbox.message_count}`
                      : "—"}
                  </dd>
                </div>
              </dl>

              {gateway.state === "disconnected" && (
                <ol className="gateway-steps">
                  <li>Sign in to the target 163 mailbox in the browser and open the mailbox home.</li>
                  <li>The extension discovers and connects automatically; it also recovers after page refreshes or bridge jitter.</li>
                  <li>Only when several mailbox pages are open at once do you need to pick the target page via the extension icon.</li>
                </ol>
              )}
              {gateway.state === "mismatch" && (
                <p className="gateway-note">
                  The extension can only connect one tab at a time. Disconnect the current mailbox
                  in the extension and reconnect
                  <strong> {gateway.studentAddress || "this student's mailbox"} </strong>
                  before reading.
                </p>
              )}
              {gateway.state === "unavailable" && (
                <p className="gateway-note">
                  Core has not enabled the dedicated extension adapter. The gateway becomes available
                  once the extension is installed, registered, and connected to a mailbox tab.
                </p>
              )}

              <div className="gateway-actions">
                <button
                  type="button"
                  className="primary"
                  disabled={!gateway.canObserve || observing}
                  onClick={observeMailbox}
                  title={gateway.canObserve ? "Observe the mailbox read-only and let Core persist and reconcile" : "Requires a connection to the current student's mailbox"}
                >
                  <Icon name="refresh" size={15} />
                  {observing ? "Observing mailbox…" : "Refresh mailbox evidence"}
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
                  Manage reconciliation <Icon name="arrow" size={14} />
                </button>
                <button
                  type="button"
                  className="gateway-secondary"
                  disabled={observing || busy}
                  onClick={reload}
                >
                  Check status now
                </button>
              </div>
              <p className="gateway-foot">
                <Icon name="shield" size={13} />
                Every observation is persisted and reconciled by Core; observation creates no tasks and grants no sending authority.
              </p>
            </section>
          </div>
        )}
      </div>
    </AppShell>
  );
}

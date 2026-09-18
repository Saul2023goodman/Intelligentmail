import {
  Fragment,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AppShell, Topbar } from "../../app/shell";
import { PageHeader } from "../../app/page-header";
import { useWorkspaceScope } from "../../app/scope";
import { useCoreQuery } from "../../core/data";
import {
  core,
  human,
  type ExecutionWorkspace,
  type ExecutionRun,
  type QueueRow,
  type PreparationReview,
  type SendingPlan,
  type PlanConfiguration,
  type ReviewRequest,
  type ReviewResult,
  type OperationReview,
  type Confirmation,
  type ExternalSchedule,
} from "../../core";
import Icon, { type IconName } from "../../shared/Icon";
import "./Execution.css";

type DialogState =
  | { type: "rules" }
  | {
      type: "review";
      request: ReviewRequest;
      result: ReviewResult;
      runAfter: boolean;
    }
  | {
      type: "adjust";
      preparation: string;
      at: string;
      timezone: string;
      plan: string;
    }
  | { type: "replace"; schedule: ExternalSchedule }
  | { type: "run"; confirmation: Confirmation }
  | { type: "result"; run: ExecutionRun };
const phases = [
  "Execution queue",
  "Proposed slots",
  "Awaiting execution",
  "Execution",
  "Authorize and run",
  "Timeline",
];
/** Batch outcomes an operator reads after a run, in the order they matter. */
const OUTCOME_LABELS: [string, string][] = [
  ["sent", "Sent"],
  ["externally_scheduled", "Scheduled"],
  ["cancelled", "Cancelled"],
  ["replaced", "Replaced"],
  ["observed_failure", "Failed"],
  ["unknown_outcome", "Unknown"],
  ["refused", "Refused"],
  ["not_reached", "Not reached"],
];
const QUEUE_TONE: Record<string, string> = {
  ready_to_authorize: "blue",
  awaiting_execution: "green",
  externally_scheduled: "amber",
  already_sent: "gray",
  not_ready: "red",
};
/** Success is green only when the mailbox actually carried the action out. */
const OUTCOME_TONE: Record<string, string> = {
  sent: "green",
  externally_scheduled: "blue",
  cancelled: "blue",
  replaced: "blue",
  observed_failure: "red",
  unknown_outcome: "amber",
  refused: "red",
  not_reached: "gray",
};
const date = (value?: string) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Immediate";
const capabilityFor = (kind: string) =>
  ({
    immediate: "immediate_send",
    scheduled: "native_scheduling",
    cancellation: "schedule_cancellation",
    replacement: "schedule_cancellation",
  })[kind];

type TimelineEvent = {
  key: string;
  at: string;
  preparationIds: string[];
  icon: IconName;
  tone: "blue" | "green" | "amber" | "red";
  title: string;
  detail: string;
};
const time = (value: string) =>
  new Date(value).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
const dayKey = (value: string) => new Date(value).toDateString();
const dayLabel = (value: string) => {
  const day = new Date(value);
  return day.toDateString() === new Date().toDateString()
    ? "Today"
    : day.toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
      });
};
function buildEvents(
  data: ExecutionWorkspace | null,
  taskName: (id: string) => string,
): TimelineEvent[] {
  if (!data) return [];
  const events: TimelineEvent[] = [];
  for (const plan of data.plans)
    events.push({
      key: `plan-${plan.id}`,
      at: plan.created_at,
      preparationIds: plan.proposals.map((p) => p.preparation_id),
      icon: "source",
      tone: "blue",
      title: `Sending plan ${human(plan.status)}`,
      detail: `${plan.proposals.length} proposed slots · ${
        plan.impossible.length + plan.unavailable.length
      } excluded`,
    });
  for (const c of data.confirmations)
    events.push({
      key: `confirmation-${c.id}`,
      at: c.confirmed_at,
      preparationIds: [c.preparation_id],
      icon: "shield",
      tone: "green",
      title: `Confirmed ${human(c.execution.kind)}`,
      detail: `${taskName(c.task_id)} · ${date(
        c.execution.scheduled_at || c.execution.scheduled_utc,
      )}`,
    });
  for (const s of data.schedules)
    events.push({
      key: `schedule-${s.id}`,
      at: s.scheduled_utc,
      preparationIds: [s.preparation_id],
      icon: "clock",
      tone: s.state.includes("unknown") ? "amber" : "blue",
      title: human(s.state),
      detail: `${taskName(s.task_id)} · ${s.mailbox_address}`,
    });
  for (const r of data.runs ?? [])
    events.push({
      key: `run-${r.id}`,
      at: r.finished_at || r.started_at,
      preparationIds: r.items
        .map((entry) => entry.preparation_id)
        .filter((id): id is string => Boolean(id)),
      icon: r.state === "completed" ? "check" : "stop",
      tone: r.state === "completed" ? "green" : r.state === "running" ? "amber" : "red",
      title: `${human(r.kind)} run ${human(r.state)}`,
      detail: `${r.executed_count} of ${r.requested_count} reached · ${r.not_reached_count} not reached`,
    });
  for (const a of data.attempts)
    events.push({
      key: `attempt-${a.id}`,
      at: a.updated_at,
      preparationIds: [a.preparation_id],
      icon: a.state === "sent" ? "check" : "send",
      tone:
        a.state === "sent"
          ? "green"
          : ["failed", "cancel_failed"].includes(a.state)
            ? "red"
            : "amber",
      title: human(a.state),
      detail: `${taskName(a.task_id)} · ${a.request.recipient}`,
    });
  return events.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
}

function Empty({
  icon = "mail",
  children,
}: {
  icon?: IconName;
  children: ReactNode;
}) {
  return (
    <div className="ex-empty">
      <Icon name={icon} size={28} />
      <p>{children}</p>
    </div>
  );
}
function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = ref.current!;
    element.showModal();
    return () => element.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="ex-dialog"
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
    >
      <header>
        <h2>{title}</h2>
        <button aria-label="Close dialog" onClick={close}>
          <Icon name="close" />
        </button>
      </header>
      {children}
    </dialog>
  );
}
function Message({
  item,
}: {
  item: PreparationReview | SendingPlan["proposals"][number];
}) {
  return (
    <article className="ex-message">
      <h3>{item.subject || "Untitled preparation"}</h3>
      <dl>
        <dt>From</dt>
        <dd>{item.sender}</dd>
        <dt>To</dt>
        <dd>{item.recipient}</dd>
        {"scheduled_at" in item && (
          <>
            <dt>Send at</dt>
            <dd>
              {item.scheduled_at} · {item.timezone}
            </dd>
          </>
        )}
      </dl>
      <pre>{"body" in item ? item.body : item.message}</pre>
      <div className="ex-attachments">
        {item.attachments.length
          ? item.attachments.map((a) => (
              <span key={a.id}>
                <Icon name="clip" size={14} />
                {a.name} · {a.size.toLocaleString()} bytes
              </span>
            ))
          : "No attachments"}
      </div>
    </article>
  );
}

export default function ExecutionPage() {
  const { scope } = useWorkspaceScope();
  const campaign = scope?.campaignId ?? "";
  const workspaceQuery = useCoreQuery("workspace", { campaign_id: campaign }, { enabled: Boolean(campaign) });
  const executionQuery = useCoreQuery("execution_workspace", { campaign_id: campaign }, { enabled: Boolean(campaign) });
  const workspace = workspaceQuery.data;
  const data = executionQuery.data;
  const [search, setSearch] = useState("");
  // ``null`` means the Core-computed default: everything that may be authorized.
  // The normal path is subtraction, not building a selection from empty.
  const [override, setOverride] = useState<string[] | null>(null);
  const [progress, setProgress] = useState("");
  const [run, setRun] = useState<ExecutionRun | null>(null);
  const [inspected, setInspected] = useState("");
  const [tab, setTab] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dialog, setDialog] = useState<DialogState | null>(null);
  const [replacement, setReplacement] = useState("");
  const actionLock = useRef(false);

  async function refresh() {
    if (!campaign) return;
    await Promise.all([workspaceQuery.refresh(), executionQuery.refresh()]);
  }
  const loading = workspaceQuery.isLoading || executionQuery.isLoading;
  const queryError = workspaceQuery.error?.message || executionQuery.error?.message || "";
  const displayError = error || queryError;

  async function perform(
    action: () => Promise<unknown>,
    message = "",
    reload = true,
  ) {
    if (actionLock.current) return;
    actionLock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(message);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      if (reload) await Promise.resolve();
    } finally {
      actionLock.current = false;
      setBusy(false);
    }
  }
  const queue: QueueRow[] = data?.queue ?? [];
  const authorizable = queue.filter((row) => row.state === "ready_to_authorize");
  const selected =
    override ?? authorizable.map((row) => row.preparation_id);
  const review = (request: ReviewRequest, runAfter: boolean) =>
    perform(
      async () => {
        const result = await core("execution_review", request);
        setDialog({ type: "review", request, result, runAfter });
      },
      "",
      false,
    );
  const plans = data?.plans.filter((p) => p.status !== "superseded") ?? [];
  const plan = plans.at(-1);
  const awaiting = queue.filter((row) => row.state === "awaiting_execution");
  const awaitingOf = (kind: string) =>
    awaiting.filter((row) => row.confirmation_kind === kind && row.confirmation_id);
  const visible = authorizable.filter((row) =>
    `${row.subject} ${row.recipient} ${taskName(row.task_id)}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  const picked = authorizable.filter((row) => selected.includes(row.preparation_id));
  const item = data?.reviews.find((r) => r.preparation_id === inspected);
  const events = buildEvents(data, taskName);
  const focus = item
    ? events.filter((e) => e.preparationIds.includes(item.preparation_id))
    : events;
  const days: [string, TimelineEvent[]][] = [];
  for (const event of focus) {
    const key = dayKey(event.at);
    const last = days.at(-1);
    if (last && last[0] === key) last[1].push(event);
    else days.push([key, [event]]);
  }
  const confirmations = data?.confirmations ?? [];
  const operations = confirmations.filter((c) =>
    ["cancellation", "replacement"].includes(c.execution.kind),
  );
  const paused = workspace?.report?.flow.state === "paused";
  const runs = data?.runs ?? [];
  const latest = run ?? runs[0] ?? null;
  const availability = data?.availability ?? {};
  const available = (kind: string) => !!availability[kind]?.available;
  const basis = (kind: string) =>
    availability[kind]?.basis || "This operation is disabled for the connected mailbox.";

  async function runConfirmations(identifiers: string[]) {
    setProgress(`Running ${identifiers.length} authorized action(s)…`);
    const result = await core("execution_run", { confirmation_ids: identifiers });
    setRun(result);
    setOverride(null);
    setDialog({ type: "result", run: result });
    return result;
  }
  async function confirmThen(request: ReviewRequest, token: string, runAfter: boolean) {
    setProgress("Authorizing…");
    const confirmed = await core("execution_confirm", { ...request, token });
    const created: Confirmation[] = Array.isArray(confirmed)
      ? confirmed
      : ((confirmed as { confirmations?: Confirmation[] }).confirmations ?? []);
    if (!runAfter) {
      setDialog(null);
      setNotice(
        `Authorized ${created.length} action(s). They appear under awaiting execution and can be run without selecting them again.`,
      );
      return;
    }
    if (!created.length) {
      setDialog(null);
      setNotice("No Confirmation was created; nothing was executed.");
      return;
    }
    await runConfirmations(created.map((c) => c.id));
  }
  function taskName(id: string) {
    return (
      workspace?.report?.tasks.find((t) => t.task_id === id)?.supervisor_name ||
      "Outreach task"
    );
  }
  function toggle(id: string) {
    setOverride(
      selected.includes(id)
        ? selected.filter((p) => p !== id)
        : [...selected, id],
    );
  }
  const disabled = busy || loading;
  const inspect = (id: string) => {
    setInspected(id);
    setTab(5);
  };
  const panel = (
    index: number,
    icon: IconName,
    count: number | string,
    children: ReactNode,
    action?: ReactNode,
  ) => (
    <section
      className={`ex-panel ex-panel-${index} ${tab === index ? "ex-mobile-active" : ""}`}
      aria-label={phases[index]}
    >
      <header className="ex-panel-heading">
        <span className={`ex-stage ex-stage-${index}`}>
          <Icon name={icon} />
        </span>
        <h2>{phases[index]}</h2>
        <span className="ex-count">{count}</span>
        {action}
      </header>
      {children}
    </section>
  );

  return (
    <AppShell
      className="execution-page"
      activeRoute="execution"
    >
      <div className="workspace">
        <Topbar breadcrumb="Batch execution" homeHref="#workflow">
          <span className="ex-connection">
            <i />
            {loading
              ? "Loading Core…"
              : workspace
                ? "Connected to Core"
                : "Core unavailable"}
          </span>
        </Topbar>
        <PageHeader
          className="ex-heading"
          eyebrow="Outreach operations / 04"
          title="Batch execution"
          subtitle="From ready to sent, with you in control."
          actions={
            <button
              className="ex-button"
              disabled={disabled}
              onClick={() =>
                perform(() => refresh(), "Workspace refreshed", false)
              }
            >
              <Icon name="refresh" size={15} />
              Refresh
            </button>
          }
        />
        <div className="ex-toolbar">
          <label className="ex-search">
            <Icon name="search" size={16} />
            <input
              placeholder="Search ready tasks…"
              aria-label="Search ready tasks"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <button
            className="ex-button"
            disabled={disabled || !data}
            onClick={() => {
              setError("");
              setDialog({ type: "rules" });
            }}
          >
            <Icon name="filter" size={16} />
            Scheduling rules
          </button>
          <span className="ex-timezone">
            {data?.configuration.timezone || "UTC"}
          </span>
        </div>
        {(displayError || notice) && (
          <div
            className={`ex-banner ${displayError ? "ex-error" : ""}`}
            role={displayError ? "alert" : "status"}
          >
            <span>{displayError || notice}</span>
            <button
              aria-label="Dismiss notification"
              onClick={() => {
                setError("");
                setNotice("");
              }}
            >
              <Icon name="close" size={14} />
            </button>
          </div>
        )}
        {paused && (
          <div className="ex-banner ex-error">
            Execution paused ·{" "}
            {human(
              workspace?.report?.flow.reason ||
                "operator intervention required",
            )}
            . Reconcile mailbox evidence and resolve the flow in Core before
            continuing.
          </div>
        )}
        <div className="ex-tabs" role="tablist" aria-label="Workspace regions">
          {phases.map((p, i) => (
            <button
              key={p}
              role="tab"
              aria-selected={tab === i}
              onClick={() => setTab(i)}
            >
              {p}
            </button>
          ))}
        </div>
        <main className="ex-main" aria-busy={disabled}>
          <div className="ex-board">
            {panel(
              0,
              "database",
              queue.length,
              <>
                <div className="ex-panel-sub">
                  <span>Core-computed authorization state</span>
                  <button
                    disabled={!visible.length || disabled}
                    onClick={() =>
                      setOverride(
                        visible.every((r) => selected.includes(r.preparation_id))
                          ? selected.filter(
                              (id) =>
                                !visible.some((r) => r.preparation_id === id),
                            )
                          : [
                              ...new Set([
                                ...selected,
                                ...visible.map((r) => r.preparation_id),
                              ]),
                            ],
                      )
                    }
                  >
                    {visible.length &&
                    visible.every((r) => selected.includes(r.preparation_id))
                      ? "Clear visible"
                      : "Select visible"}
                  </button>
                </div>
                <div className="ex-scroll">
                  {queue.length ? (
                    queue
                      .filter(
                        (row) =>
                          `${row.subject} ${row.recipient} ${taskName(row.task_id)}`
                            .toLowerCase()
                            .includes(search.toLowerCase()),
                      )
                      .map((row, i) => (
                        <div
                          key={row.preparation_id}
                          className={`ex-task ${selected.includes(row.preparation_id) ? "is-selected" : ""}`}
                        >
                          <input
                            type="checkbox"
                            aria-label={`Select ${row.recipient}`}
                            checked={selected.includes(row.preparation_id)}
                            disabled={
                              disabled || row.state !== "ready_to_authorize"
                            }
                            onChange={() => toggle(row.preparation_id)}
                          />
                          <button
                            className="ex-task-content"
                            onClick={() => inspect(row.preparation_id)}
                          >
                            <span className={`ex-monogram ex-color-${i % 4}`}>
                              {taskName(row.task_id).slice(0, 2).toUpperCase()}
                            </span>
                            <span>
                              <strong>{taskName(row.task_id)}</strong>
                              <small>{row.recipient}</small>
                            </span>
                            <span
                              className={`ex-chip ex-chip-${QUEUE_TONE[row.state] ?? "gray"}`}
                              title={
                                row.blocking_codes.length
                                  ? row.blocking_codes.join(", ")
                                  : undefined
                              }
                            >
                              {human(row.state)}
                            </span>
                          </button>
                        </div>
                      ))
                  ) : (
                    <Empty icon="database">
                      {loading
                        ? "Loading preparations…"
                        : "Active Preparations and their authorization state appear here."}
                    </Empty>
                  )}
                </div>
                <div className="ex-panel-foot">
                  {picked.length} selected{" "}
                  <span>Readiness is never authorization</span>
                </div>
              </>,
            )}
            {panel(
              1,
              "clock",
              plan?.proposals.length ?? 0,
              <>
                <div className="ex-panel-sub">
                  <span>
                    {plan ? human(plan.status) : "Campaign sending plan"}
                  </span>
                  <button
                    disabled={disabled || !campaign}
                    onClick={() =>
                      perform(
                        () =>
                          core("execution_propose", { campaign_id: campaign }),
                        "Campaign sending plan proposed. Review exact times before confirming.",
                      )
                    }
                  >
                    Propose slots <Icon name="plus" size={14} />
                  </button>
                </div>
                <div className="ex-scroll">
                  {plan?.proposals.length ? (
                    plan.proposals.map((p) => (
                      <article
                        className="ex-card ex-slot"
                        key={p.preparation_id}
                      >
                        <div className="ex-card-top">
                          <Icon name="clock" size={17} />
                          <strong>{p.scheduled_at.slice(11, 16)}</strong>
                          <span>{p.scheduled_at.slice(0, 10)}</span>
                        </div>
                        <button
                          className="ex-card-title"
                          onClick={() => inspect(p.preparation_id)}
                        >
                          {taskName(p.task_id)}
                        </button>
                        <p>{p.subject}</p>
                        <div className="ex-card-bottom">
                          <span>{p.timezone}</span>
                          <button
                            disabled={disabled}
                            onClick={() => {
                              setError("");
                              setDialog({
                                type: "adjust",
                                preparation: p.preparation_id,
                                at: p.scheduled_at.slice(0, 16),
                                timezone: p.timezone,
                                plan: plan.id,
                              });
                            }}
                          >
                            Adjust time
                          </button>
                        </div>
                      </article>
                    ))
                  ) : (
                    <Empty icon="clock">
                      Propose time slots for the campaign using its allowed
                      windows, spacing, and daily limit.
                    </Empty>
                  )}
                  {plan &&
                    [...plan.impossible, ...plan.unavailable].map((p) => (
                      <article
                        className="ex-card ex-excluded"
                        key={p.preparation_id}
                      >
                        <strong>{taskName(p.task_id)}</strong>
                        <p>{p.detail}</p>
                        <small>{human(p.status)}</small>
                      </article>
                    ))}
                </div>
                <div className="ex-panel-foot">
                  <span>
                    {data?.configuration.spacing_minutes ?? 15} min spacing
                  </span>
                  <span>{data?.configuration.daily_limit ?? 20} / day</span>
                </div>
              </>,
            )}
            {panel(
              2,
              "shield",
              awaiting.length + operations.length,
              <>
                <div className="ex-panel-sub">
                  <span>Authorized · not yet carried out</span>
                </div>
                <div className="ex-scroll">
                  {[
                    { kind: "immediate", rows: awaitingOf("immediate") },
                    { kind: "scheduled", rows: awaitingOf("scheduled") },
                  ].map((group) => (
                    <section className="ex-group" key={group.kind}>
                      <h3>
                        {group.kind === "immediate" ? "Send now" : "Place schedule"}{" "}
                        <span>{group.rows.length}</span>
                      </h3>
                      {!available(group.kind) && (
                        <p className="ex-banner">{basis(group.kind)}</p>
                      )}
                      <button
                        className="ex-button ex-primary"
                        disabled={
                          disabled ||
                          paused ||
                          !available(group.kind) ||
                          !group.rows.length
                        }
                        onClick={() =>
                          perform(async () => {
                            await runConfirmations(
                              group.rows.map((row) => row.confirmation_id!),
                            );
                          }, "")
                        }
                      >
                        <Icon name="send" size={15} />
                        {group.kind === "immediate"
                          ? `Send ${group.rows.length} authorized`
                          : `Place ${group.rows.length} schedule(s)`}
                      </button>
                      {group.rows.map((row) => (
                        <button
                          className="ex-batch-row"
                          key={row.preparation_id}
                          onClick={() => inspect(row.preparation_id)}
                        >
                          <span className="ex-check">
                            <Icon name="check" size={12} />
                          </span>
                          {taskName(row.task_id)}
                          <span>{row.subject}</span>
                        </button>
                      ))}
                    </section>
                  ))}
                  {operations.length > 0 && (
                    <section className="ex-group">
                      <h3>
                        Cancellation and replacement <span>{operations.length}</span>
                      </h3>
                      {!available("cancellation") && (
                        <p className="ex-banner">{basis("cancellation")}</p>
                      )}
                      {operations.map((c) => (
                        <article className="ex-card ex-confirmed" key={c.id}>
                          <div className="ex-card-top">
                            <span className="ex-check">
                              <Icon name="check" size={13} />
                            </span>
                            <strong>{human(c.execution.kind)}</strong>
                          </div>
                          <button
                            className="ex-card-title"
                            onClick={() => inspect(c.preparation_id)}
                          >
                            {taskName(c.task_id)}
                          </button>
                          <div className="ex-card-bottom">
                            <span>{date(c.confirmed_at)}</span>
                            <button
                              disabled={
                                disabled ||
                                paused ||
                                !available(c.execution.kind)
                              }
                              onClick={() => {
                                setError("");
                                setDialog({ type: "run", confirmation: c });
                              }}
                            >
                              Review execution <Icon name="arrow" size={14} />
                            </button>
                          </div>
                        </article>
                      ))}
                    </section>
                  )}
                  {!awaiting.length && !operations.length && (
                    <Empty icon="shield">
                      Authorized actions appear here until a run carries them
                      out. Authorization and execution stay separate decisions.
                    </Empty>
                  )}
                </div>
                <div className="ex-panel-foot">
                  <Icon name="shield" size={14} />
                  <span>Core rechecks every action</span>
                </div>
              </>,
            )}
            {panel(
              3,
              "send",
              data?.attempts.length ?? 0,
              <>
                <div className="ex-panel-sub">
                  <span>Mailbox evidence & outcomes</span>
                </div>
                <div className="ex-scroll">
                  {latest && (
                    <article
                      className={`ex-card ex-outcome ${latest.state === "stopped" ? "ex-excluded" : ""}`}
                    >
                      <div className="ex-card-top">
                        <Icon name="send" size={16} />
                        <strong>{human(latest.kind)} run {human(latest.state)}</strong>
                        <span>{date(latest.started_at)}</span>
                      </div>
                      <RunSummary run={latest} />
                      {latest.state === "stopped" && (
                        <p className="ex-hint">
                          Stopped after {latest.executed_count} of{" "}
                          {latest.requested_count} · {latest.not_reached_count}{" "}
                          never reached
                          {workspace?.report?.flow.reason
                            ? ` · ${human(workspace.report.flow.reason)}`
                            : ""}
                          . Resolve it in the{" "}
                          <a href="#records">execution ledger</a>, then run the
                          remaining actions explicitly.
                        </p>
                      )}
                      <details>
                        <summary>Run items</summary>
                        <pre>{JSON.stringify(latest.items, null, 2)}</pre>
                      </details>
                    </article>
                  )}
                  {!data?.attempts.length && !data?.schedules.length && !latest && (
                    <Empty icon="send">
                      Execution outcomes appear here after an attempt. A
                      scheduled time passing never means sent.
                    </Empty>
                  )}
                  {data?.schedules.map((s) => (
                    <article
                      className={`ex-card ex-outcome ${s.state.includes("unknown") ? "ex-excluded" : ""}`}
                      key={s.id}
                    >
                      <div className="ex-card-top">
                        <Icon name="clock" size={16} />
                        <strong>{human(s.state)}</strong>
                      </div>
                      <button
                        className="ex-card-title"
                        onClick={() => inspect(s.preparation_id)}
                      >
                        {taskName(s.task_id)}
                      </button>
                      <p>{date(s.scheduled_utc)}</p>
                      <small>{s.mailbox_address}</small>
                      <div className="ex-card-bottom">
                        <button
                          disabled={
                            disabled || s.state !== "externally_scheduled"
                          }
                          onClick={() =>
                            review(
                              { kind: "cancellation", schedule_id: s.id },
                              false,
                            )
                          }
                        >
                          Cancel schedule
                        </button>
                        <button
                          disabled={
                            disabled || s.state !== "externally_scheduled"
                          }
                          onClick={() => {
                            setReplacement("");
                            setError("");
                            setDialog({ type: "replace", schedule: s });
                          }}
                        >
                          Replace
                        </button>
                      </div>
                    </article>
                  ))}
                  {data?.attempts
                    .slice()
                    .reverse()
                    .map((a) => (
                      <article
                        className={`ex-card ex-outcome ${["unknown", "failed", "cancel_unknown"].includes(a.state) ? "ex-excluded" : ""}`}
                        key={a.id}
                      >
                        <div className="ex-card-top">
                          <Icon
                            name={a.state === "sent" ? "check" : "send"}
                            size={16}
                          />
                          <strong>{human(a.state)}</strong>
                          <span>{date(a.updated_at)}</span>
                        </div>
                        <button
                          className="ex-card-title"
                          onClick={() => inspect(a.preparation_id)}
                        >
                          {a.request.subject || taskName(a.task_id)}
                        </button>
                        <p>{a.request.recipient}</p>
                        <small>{human(a.phase)}</small>
                        <details>
                          <summary>Evidence</summary>
                          <pre>{JSON.stringify(a.evidence, null, 2)}</pre>
                        </details>
                      </article>
                    ))}
                </div>
                <div className="ex-panel-foot">
                  <span className="ex-dot" />
                  <span>Observed outcomes only</span>
                </div>
              </>,
            )}
          </div>
          <div className="ex-bottom">
            {panel(
              4,
              "source",
              picked.length,
              <>
                {/* Two distinct regions, each stating its own scope: a Campaign-wide
                    plan can no longer be mistaken for the current selection. */}
                <div className="ex-scroll ex-authorize">
                  <section className="ex-group">
                    <h3>
                      Send now <span>{picked.length}</span>
                    </h3>
                    <p className="ex-scope">
                      Scope: the {picked.length} Preparation
                      {picked.length === 1 ? "" : "s"} selected above. One review,
                      one authorization, then one run.
                    </p>
                    {!available("immediate") && (
                      <p className="ex-banner">{basis("immediate")}</p>
                    )}
                    <div className="ex-batch-actions">
                      <button
                        className="ex-button ex-primary"
                        disabled={
                          disabled ||
                          paused ||
                          !picked.length ||
                          !available("immediate")
                        }
                        onClick={() =>
                          review(
                            {
                              kind: "immediate",
                              preparation_ids: picked.map((row) => row.preparation_id),
                            },
                            true,
                          )
                        }
                      >
                        <Icon name="send" size={15} />
                        Review and send {picked.length}
                      </button>
                      <button
                        className="ex-button"
                        disabled={
                          disabled || !picked.length || !available("immediate")
                        }
                        onClick={() =>
                          review(
                            {
                              kind: "immediate",
                              preparation_ids: picked.map((row) => row.preparation_id),
                            },
                            false,
                          )
                        }
                      >
                        <Icon name="shield" size={15} />
                        Authorize only
                      </button>
                    </div>
                    {picked.length ? (
                      picked.map((row) => (
                        <div className="ex-batch-row" key={row.preparation_id}>
                          <span className="ex-check">
                            <Icon name="check" size={12} />
                          </span>
                          <button onClick={() => inspect(row.preparation_id)}>
                            {taskName(row.task_id)}
                          </button>
                          <span>{row.subject}</span>
                          <button
                            aria-label={`Remove ${row.recipient} from batch`}
                            disabled={disabled}
                            onClick={() => toggle(row.preparation_id)}
                          >
                            <Icon name="close" size={14} />
                          </button>
                        </div>
                      ))
                    ) : (
                      <p className="ex-hint">
                        Nothing selected. Every Preparation that may be
                        authorized is selected by default — deselect the ones to
                        hold back.
                      </p>
                    )}
                  </section>
                  <section className="ex-group">
                    <h3>
                      Place schedules <span>{plan?.proposals.length ?? 0}</span>
                    </h3>
                    <p className="ex-scope">
                      Scope: every proposed slot of the current campaign plan,
                      not the selection above.
                    </p>
                    {!available("scheduled") && (
                      <p className="ex-banner">{basis("scheduled")}</p>
                    )}
                    <div className="ex-batch-actions">
                      <button
                        className="ex-button ex-primary"
                        disabled={
                          disabled ||
                          paused ||
                          !plan?.proposals.length ||
                          !available("scheduled")
                        }
                        onClick={() =>
                          plan && review({ kind: "plan", plan_id: plan.id }, true)
                        }
                      >
                        <Icon name="clock" size={15} />
                        Review and place {plan?.proposals.length ?? 0}
                      </button>
                      <button
                        className="ex-button"
                        disabled={
                          disabled ||
                          !plan?.proposals.length ||
                          !available("scheduled")
                        }
                        onClick={() =>
                          plan && review({ kind: "plan", plan_id: plan.id }, false)
                        }
                      >
                        <Icon name="shield" size={15} />
                        Authorize plan only
                      </button>
                    </div>
                    <p className="ex-hint">
                      A confirmed plan produces scheduled Confirmations that
                      appear under awaiting execution. They are never sent
                      immediately.
                    </p>
                  </section>
                </div>
                <div className="ex-panel-foot">
                  {progress ? (
                    <span className="ex-progress">{progress}</span>
                  ) : (
                    <span>Authorization and execution stay separate</span>
                  )}
                </div>
              </>,
            )}
            {panel(
              5,
              "clock",
              focus.length,
              <>
                <div className="ex-panel-sub">
                  <span className="ex-sub-label">
                    {item
                      ? `Focused · ${item.subject || "Untitled preparation"}`
                      : "Campaign execution ledger"}
                  </span>
                  {item && (
                    <button
                      disabled={disabled}
                      onClick={() => setInspected("")}
                    >
                      Show all <Icon name="close" size={12} />
                    </button>
                  )}
                </div>
                <div className="ex-scroll ex-timeline">
                  {days.length ? (
                    days.map(([day, items]) => (
                      <Fragment key={day}>
                        <div className="ex-timeline-day">{dayLabel(day)}</div>
                        {items.map((event) => (
                          <div className="ex-timeline-row" key={event.key}>
                            <span
                              className={`ex-timeline-node ex-tone-${event.tone}`}
                            >
                              <Icon name={event.icon} size={13} />
                            </span>
                            <span className="ex-timeline-body">
                              <strong>{event.title}</strong>
                              <small>{event.detail}</small>
                            </span>
                            <time className="ex-timeline-time">
                              {time(event.at)}
                            </time>
                          </div>
                        ))}
                      </Fragment>
                    ))
                  ) : (
                    <Empty icon="clock">
                      {loading
                        ? "Loading the execution ledger…"
                        : "Proposed plans, confirmations, external schedules, and observed outcomes appear here in order."}
                    </Empty>
                  )}
                </div>
                <div className="ex-panel-foot">
                  <Icon name="shield" size={14} />
                  <span>Observed evidence only · newest first</span>
                </div>
              </>,
            )}
          </div>
        </main>
        <footer className="ex-footer">
          <span>
            <Icon name="shield" size={13} />
            Operator-confirmed execution
          </span>
          <span>
            {workspace?.report?.campaign.name || "Choose a campaign"} ·{" "}
            {data?.reviews.length ?? 0} preparations
          </span>
        </footer>
      </div>
      {dialog && (
        <Modal
          title={
            dialog.type === "result"
              ? `Execution run ${human(dialog.run.state)}`
              : dialog.type === "rules"
                ? "Scheduling rules"
                : dialog.type === "adjust"
                  ? "Adjust proposed time"
                  : dialog.type === "replace"
                    ? "Replace scheduled draft"
                    : dialog.type === "run"
                      ? "Review external execution"
                      : `Confirm ${dialog.request.kind === "plan" ? "sending plan" : dialog.request.kind}`
          }
          close={() => {
            if (!busy) {
              setDialog(null);
              setError("");
            }
          }}
        >
          {error && (
            <div className="ex-banner ex-error" role="alert">
              {error}
            </div>
          )}
          {dialog.type === "result" && (
            <>
              <div className="ex-dialog-body">
                <p>
                  {human(dialog.run.kind)} run {human(dialog.run.state)} ·{" "}
                  {dialog.run.executed_count} of {dialog.run.requested_count}{" "}
                  reached. Completion alone never claims success: read the
                  observed outcomes.
                </p>
                <RunSummary run={dialog.run} />
                {dialog.run.state === "stopped" && (
                  <div className="ex-banner ex-error">
                    <p>
                      The run stopped after {dialog.run.executed_count} of{" "}
                      {dialog.run.requested_count}; {dialog.run.not_reached_count}{" "}
                      action(s) were never reached and stay eligible for a later,
                      explicitly requested run.
                    </p>
                    {workspace?.report?.flow.reason && (
                      <p>
                        Pause reason: {human(workspace.report.flow.reason)}.
                        Resolve it in the{" "}
                        <a href="#records">execution ledger</a>, then run the
                        remaining actions explicitly.
                      </p>
                    )}
                  </div>
                )}
                <ol className="ex-run-items">
                  {dialog.run.items.map((entry) => (
                    <li key={entry.id}>
                      <span
                        className={`ex-chip ex-chip-${OUTCOME_TONE[entry.outcome] ?? "gray"}`}
                      >
                        {human(entry.outcome)}
                      </span>
                      <span>
                        {entry.task_id ? taskName(entry.task_id) : "Action"}
                      </span>
                      {entry.detail && <small>{entry.detail}</small>}
                    </li>
                  ))}
                </ol>
              </div>
              <div className="ex-dialog-actions">
                <button
                  className="ex-button ex-primary"
                  onClick={() => setDialog(null)}
                >
                  Close
                </button>
              </div>
            </>
          )}
          {dialog.type === "rules" && data && (
            <Rules
              configuration={data.configuration}
              busy={busy}
              save={(rules) =>
                perform(async () => {
                  await core("execution_configure", {
                    campaign_id: campaign,
                    ...rules,
                  });
                  setDialog(null);
                }, "Scheduling rules saved. Propose a new plan to apply them; existing plan times are unchanged.")
              }
            />
          )}
          {dialog.type === "adjust" && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const values = new FormData(e.currentTarget);
                perform(async () => {
                  await core("execution_adjust", {
                    plan_id: dialog.plan,
                    preparation_id: dialog.preparation,
                    scheduled_at: String(values.get("at")),
                  });
                  setDialog(null);
                }, "Proposed time updated. Any confirmation for the old time was invalidated.");
              }}
            >
              <div className="ex-dialog-body">
                <p>
                  Local time in <strong>{dialog.timezone}</strong>. Core checks
                  allowed windows, spacing, and daily limits.
                </p>
                <label>
                  Proposed time
                  <input
                    type="datetime-local"
                    name="at"
                    required
                    defaultValue={dialog.at}
                  />
                </label>
                <p>Changing a confirmed time invalidates its confirmation.</p>
              </div>
              <div className="ex-dialog-actions">
                <button className="ex-button ex-primary" disabled={busy}>
                  Save proposed time
                </button>
              </div>
            </form>
          )}
          {dialog.type === "replace" && (
            <>
              <div className="ex-dialog-body">
                <p>
                  Replace the external draft for{" "}
                  <strong>{taskName(dialog.schedule.task_id)}</strong>,
                  scheduled {date(dialog.schedule.scheduled_utc)}.
                </p>
                <p>
                  Choose a fresh preparation with its own scheduled
                  confirmation. Core verifies removal of the original before
                  submitting the replacement.
                </p>
                <label>
                  Replacement confirmation
                  <select
                    value={replacement}
                    onChange={(e) => setReplacement(e.target.value)}
                  >
                    <option value="">Choose a confirmed replacement</option>
                    {confirmations
                      .filter(
                        (c) =>
                          c.task_id === dialog.schedule.task_id &&
                          c.preparation_id !== dialog.schedule.preparation_id &&
                          c.execution.kind === "scheduled",
                      )
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {data?.reviews.find(
                            (r) => r.preparation_id === c.preparation_id,
                          )?.subject || c.preparation_id}{" "}
                          ·{" "}
                          {date(
                            c.execution.scheduled_at ||
                              c.execution.scheduled_utc,
                          )}
                        </option>
                      ))}
                  </select>
                </label>
                <p className="ex-hint">
                  If none are available, create a fresh preparation through
                  Core’s Rewrite flow and confirm its schedule first.
                </p>
              </div>
              <div className="ex-dialog-actions">
                <button
                  className="ex-button ex-primary"
                  disabled={busy || !replacement}
                  onClick={() =>
                    review(
                      {
                        kind: "replacement",
                        schedule_id: dialog.schedule.id,
                        replacement_confirmation_id: replacement,
                      },
                      false,
                    )
                  }
                >
                  Review replacement
                </button>
              </div>
            </>
          )}
          {dialog.type === "review" && (
            <>
              <div className="ex-dialog-body">
                <p>
                  Review every message and the exact execution details below.
                  Confirmation authorizes these details; execution is a separate
                  action.
                </p>
                {Array.isArray(dialog.result.value) ? (
                  dialog.result.value.map((r) => (
                    <Message key={r.preparation_id} item={r} />
                  ))
                ) : "proposals" in dialog.result.value ? (
                  <>
                    <p>
                      <strong>
                        {dialog.result.value.proposals.length} actions
                      </strong>{" "}
                      · {dialog.result.value.configuration.timezone} ·{" "}
                      {dialog.result.value.impossible.length +
                        dialog.result.value.unavailable.length}{" "}
                      excluded
                    </p>
                    {dialog.result.value.proposals.map((p) => (
                      <Message key={p.preparation_id} item={p} />
                    ))}
                  </>
                ) : (
                  <OperationDetails value={dialog.result.value} />
                )}
              </div>
              <div className="ex-dialog-actions">
                <span>
                  {dialog.runAfter
                    ? "Authorizing, then carrying the run out in order"
                    : "No external action occurs yet"}
                </span>
                <button
                  className="ex-button ex-primary"
                  disabled={busy}
                  onClick={() =>
                    perform(
                      async () => {
                        await confirmThen(
                          dialog.request,
                          dialog.result.token,
                          dialog.runAfter,
                        );
                        setProgress("");
                      },
                      dialog.runAfter
                        ? ""
                        : "Confirmation recorded. Authorized actions appear under awaiting execution.",
                    )
                  }
                >
                  {busy
                    ? progress || "Working…"
                    : dialog.runAfter
                      ? "Authorize and run"
                      : "Confirm exact details"}
                </button>
              </div>
            </>
          )}
          {dialog.type === "run" && (
            <>
              <div className="ex-dialog-body">
                <p>
                  <strong>{human(dialog.confirmation.execution.kind)}</strong> ·{" "}
                  {taskName(dialog.confirmation.task_id)}
                </p>
                <p>
                  Confirmed time:{" "}
                  {date(
                    dialog.confirmation.execution.scheduled_at ||
                      dialog.confirmation.execution.scheduled_utc,
                  )}
                </p>
                {data?.reviews
                  .filter(
                    (r) =>
                      r.preparation_id === dialog.confirmation.preparation_id,
                  )
                  .map((r) => (
                    <Message key={r.preparation_id} item={r} />
                  ))}
                {dialog.confirmation.execution.schedule_id && (
                  <p>
                    External schedule:{" "}
                    {dialog.confirmation.execution.schedule_id}
                  </p>
                )}
                <p>
                  Core rechecks the persisted confirmation, content, and
                  execution conditions before submitting. Unknown outcomes
                  require reconciliation.
                </p>
                {!available(dialog.confirmation.execution.kind) && (
                  <div className="ex-banner">
                    {workspace?.mailbox_capabilities.capabilities[
                      capabilityFor(dialog.confirmation.execution.kind) || ""
                    ]?.basis ||
                      "This operation is disabled for the connected mailbox."}
                  </div>
                )}
                {paused && (
                  <div className="ex-banner ex-error">
                    Execution flow is paused.
                  </div>
                )}
              </div>
              <div className="ex-dialog-actions">
                <button
                  className="ex-button ex-primary"
                  disabled={
                    busy ||
                    !available(dialog.confirmation.execution.kind) ||
                    paused
                  }
                  onClick={() =>
                    perform(async () => {
                      await core("execution_run", {
                        confirmation_id: dialog.confirmation.id,
                      });
                      setDialog(null);
                    }, "Execution request completed. Inspect the recorded outcome; completion alone does not establish success.")
                  }
                >
                  {busy
                    ? "Executing…"
                    : dialog.confirmation.execution.kind === "immediate"
                      ? "Send now"
                      : dialog.confirmation.execution.kind === "scheduled"
                        ? "Place scheduled send"
                        : dialog.confirmation.execution.kind === "cancellation"
                          ? "Execute cancellation"
                          : "Execute replacement"}
                </button>
              </div>
            </>
          )}
        </Modal>
      )}
    </AppShell>
  );
}

function RunSummary({ run }: { run: ExecutionRun }) {
  return (
    <div className="ex-run-summary">
      {OUTCOME_LABELS.filter(([key]) => (run.summary?.[key] ?? 0) > 0).map(
        ([key, label]) => (
          <span
            className={`ex-chip ex-chip-${OUTCOME_TONE[key] ?? "gray"}`}
            key={key}
          >
            {label} {run.summary[key]}
          </span>
        ),
      )}
      {run.state === "completed" && (
        <span className="ex-chip ex-chip-gray">
          {run.requested_count} requested
        </span>
      )}
    </div>
  );
}
function OperationDetails({ value }: { value: OperationReview }) {
  return (
    <>
      <dl>
        <dt>Mailbox</dt>
        <dd>{value.schedule.mailbox_address}</dd>
        <dt>External draft</dt>
        <dd>{value.schedule.external_id}</dd>
        <dt>Send time</dt>
        <dd>{value.schedule.scheduled_utc}</dd>
        <dt>State</dt>
        <dd>{human(value.schedule.state)}</dd>
      </dl>
      <p>{value.note}</p>
      {value.replacement && (
        <>
          <h3>Replacement preparation</h3>
          <p>
            {value.replacement_confirmation?.execution.scheduled_at ||
              value.replacement_confirmation?.execution.scheduled_utc}
          </p>
          <Message item={value.replacement} />
        </>
      )}
    </>
  );
}
function Rules({
  configuration,
  busy,
  save,
}: {
  configuration: PlanConfiguration;
  busy: boolean;
  save: (configuration: PlanConfiguration) => void;
}) {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        const values = new FormData(event.currentTarget);
        save({
          timezone: String(values.get("timezone")),
          spacing_minutes: Number(values.get("spacing")),
          daily_limit: Number(values.get("limit")),
          horizon_days: Number(values.get("horizon")),
          windows: String(values.get("windows"))
            .split("\n")
            .filter((line) => line.trim())
            .map((line) => {
              const parts = line.trim().split(/\s+/);
              const [start, end] = parts.pop()!.split("-");
              return { days: parts.join(" ").split(/[ ,]+/), start, end };
            }),
        });
      }}
    >
      <div className="ex-dialog-body ex-rules">
        <p>
          Rules apply to the whole campaign. Core generates slots and validates
          every adjustment.
        </p>
        <label>
          Timezone (IANA)
          <input
            name="timezone"
            required
            defaultValue={configuration.timezone}
            placeholder="Asia/Shanghai"
          />
        </label>
        <label>
          Allowed windows · one per line
          <textarea
            name="windows"
            required
            rows={4}
            defaultValue={configuration.windows
              .map((w) => `${w.days.join(",")} ${w.start}-${w.end}`)
              .join("\n")}
          />
          <small>Example: MON-FRI 09:00-17:00</small>
        </label>
        <div className="ex-rule-numbers">
          <label>
            Spacing (minutes)
            <input
              name="spacing"
              type="number"
              min="1"
              required
              defaultValue={configuration.spacing_minutes}
            />
          </label>
          <label>
            Daily limit
            <input
              name="limit"
              type="number"
              min="1"
              required
              defaultValue={configuration.daily_limit}
            />
          </label>
          <label>
            Horizon (days)
            <input
              name="horizon"
              type="number"
              min="1"
              required
              defaultValue={configuration.horizon_days}
            />
          </label>
        </div>
        <p className="ex-hint">
          Saving rules does not change or authorize an existing plan. Propose
          new slots afterward.
        </p>
      </div>
      <div className="ex-dialog-actions">
        <button className="ex-button ex-primary" disabled={busy}>
          {busy ? "Saving…" : "Save rules"}
        </button>
      </div>
    </form>
  );
}

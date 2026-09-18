import {
  Fragment,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AppShell, Topbar } from "../../app/shell";
import { useWorkspaceScope } from "../../app/scope";
import {
  core,
  human,
  type Workspace,
  type ExecutionWorkspace,
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
  | { type: "batch-run"; confirmations: Confirmation[] }
  | { type: "rules" }
  | { type: "review"; request: ReviewRequest; result: ReviewResult }
  | {
      type: "adjust";
      preparation: string;
      at: string;
      timezone: string;
      plan: string;
    }
  | { type: "replace"; schedule: ExternalSchedule }
  | { type: "run"; confirmation: Confirmation };
const phases = [
  "Ready tasks",
  "Proposed slots",
  "Confirmation",
  "Execution",
  "Batch",
  "Timeline",
];
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
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [data, setData] = useState<ExecutionWorkspace | null>(null);
  const campaign = scope?.campaignId ?? "";
  const [search, setSearch] = useState("");
  const [executionSelection, setExecutionSelection] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [inspected, setInspected] = useState("");
  const [tab, setTab] = useState(0);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dialog, setDialog] = useState<DialogState | null>(null);
  const [replacement, setReplacement] = useState("");
  const version = useRef(0);
  const actionLock = useRef(false);

  async function refresh(scope = campaign) {
    const current = ++version.current;
    setLoading(true);
    try {
      if (!scope) {
        setWorkspace(null);
        setData(null);
        return;
      }
      const next = await core("workspace", { campaign_id: scope });
      const id = scope;
      const execution = id
        ? await core("execution_workspace", { campaign_id: id })
        : null;
      if (current !== version.current) return;
      setWorkspace(next);
      setData(execution);
      setSelected((previous) =>
        previous.filter((p) =>
          execution?.reviews.some(
            (r) => r.preparation_id === p && r.ready && !r.already_sent,
          ),
        ),
      );
    } finally {
      if (current === version.current) setLoading(false);
    }
  }
  useEffect(() => {
    setSelected([]);
    setExecutionSelection([]);
    setInspected("");
    refresh().catch((e) => setError(String(e.message || e)));
    const generation = version;
    return () => {
      generation.current++;
    };
    // The Workflow owns the global Student/Campaign scope.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaign]);

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
      if (reload) await refresh();
      setNotice(message);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      if (reload) await refresh().catch(() => {});
    } finally {
      actionLock.current = false;
      setBusy(false);
    }
  }
  const review = (request: ReviewRequest) =>
    perform(
      async () => {
        const result = await core("execution_review", request);
        setDialog({ type: "review", request, result });
      },
      "",
      false,
    );
  const plans = data?.plans.filter((p) => p.status !== "superseded") ?? [];
  const plan = plans.at(-1);
  const ready =
    data?.reviews.filter(
      (r) =>
        r.ready &&
        !r.already_sent &&
        r.status === "active" &&
        !data.schedules.some(
          (s) =>
            s.preparation_id === r.preparation_id &&
            [
              "externally_scheduled",
              "placement_unknown",
              "cancel_unknown",
            ].includes(s.state),
        ),
    ) ?? [];
  const visible = ready.filter(
    (r) =>
      `${r.subject} ${r.sender} ${r.recipient} ${taskName(r.task_id)}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const picked = ready.filter((r) => selected.includes(r.preparation_id));
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
  const paused = workspace?.report?.flow.state === "paused";
  const available = (kind: string) => {
    const key = capabilityFor(kind);
    return (
      !!key &&
      !!workspace?.mailbox_capabilities.capabilities[key]?.available &&
      (kind !== "replacement" ||
        !!workspace?.mailbox_capabilities.capabilities.native_scheduling
          ?.available)
    );
  };
  const used = (c: Confirmation) =>
    data?.schedules.some((s) => s.confirmation_id === c.id) ||
    data?.attempts.some(
      (a) => a.confirmation_id === c.id && !["not_attempted"].includes(a.state),
    );
  function taskName(id: string) {
    return (
      workspace?.report?.tasks.find((t) => t.task_id === id)?.supervisor_name ||
      "Outreach task"
    );
  }
  function toggle(id: string) {
    setSelected((old) =>
      old.includes(id) ? old.filter((p) => p !== id) : [...old, id],
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
        <div className="ex-heading">
          <div>
            <div className="ex-eyebrow">OUTREACH OPERATIONS / 04</div>
            <h1>
              Batch execution
              <span>From ready to sent, with you in control.</span>
            </h1>
          </div>
          <button
            className="ex-button"
            disabled={disabled}
            onClick={() =>
              perform(() => refresh(), "Workspace refreshed", false)
            }
          >
            <Icon name="refresh" size={16} />
            Refresh
          </button>
        </div>
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
        {(error || notice) && (
          <div
            className={`ex-banner ${error ? "ex-error" : ""}`}
            role={error ? "alert" : "status"}
          >
            <span>{error || notice}</span>
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
              ready.length,
              <>
                <div className="ex-panel-sub">
                  <span>Validated preparations</span>
                  <button
                    disabled={!visible.length || disabled}
                    onClick={() =>
                      setSelected((old) =>
                        visible.every((r) => old.includes(r.preparation_id))
                          ? old.filter(
                              (id) =>
                                !visible.some((r) => r.preparation_id === id),
                            )
                          : [
                              ...new Set([
                                ...old,
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
                  {visible.length ? (
                    visible.map((r, i) => (
                      <div
                        key={r.preparation_id}
                        className={`ex-task ${selected.includes(r.preparation_id) ? "is-selected" : ""}`}
                      >
                        <input
                          type="checkbox"
                          aria-label={`Select ${r.recipient}`}
                          checked={selected.includes(r.preparation_id)}
                          disabled={disabled}
                          onChange={() => toggle(r.preparation_id)}
                        />
                        <button
                          className="ex-task-content"
                          onClick={() => inspect(r.preparation_id)}
                        >
                          <span className={`ex-monogram ex-color-${i % 4}`}>
                            {taskName(r.task_id).slice(0, 2).toUpperCase()}
                          </span>
                          <span>
                            <strong>{taskName(r.task_id)}</strong>
                            <small>{r.recipient}</small>
                          </span>
                          <span className="ex-dot" title="Ready preparation" />
                        </button>
                      </div>
                    ))
                  ) : (
                    <Empty icon="database">
                      {loading
                        ? "Loading preparations…"
                        : search
                          ? "No ready tasks match these filters."
                          : "Ready preparations appear here after validation in Core."}
                    </Empty>
                  )}
                </div>
                <div className="ex-panel-foot">
                  {picked.length} selected{" "}
                  <span>Readiness is not authorization</span>
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
              confirmations.length,
              <>
                <div className="ex-panel-sub">
                  <span>Exact content · exact intent</span>
                  <button
                    disabled={disabled || !executionSelection.length}
                    onClick={() => {
                      setError("");
                      setDialog({
                        type: "batch-run",
                        confirmations: confirmations.filter(
                          (c) => executionSelection.includes(c.id) && !used(c),
                        ),
                      });
                    }}
                  >
                    Run selected ({executionSelection.length})
                  </button>
                </div>
                <div className="ex-scroll">
                  {confirmations.length ? (
                    confirmations.map((c) => (
                      <article
                        key={c.id}
                        className={`ex-card ex-confirmed ${used(c) ? "ex-muted" : ""}`}
                      >
                        <div className="ex-card-top">
                          <input
                            type="checkbox"
                            aria-label={`Execute ${taskName(c.task_id)} ${c.execution.kind}`}
                            checked={executionSelection.includes(c.id)}
                            disabled={disabled || !!used(c)}
                            onChange={() =>
                              setExecutionSelection((old) =>
                                old.includes(c.id)
                                  ? old.filter((id) => id !== c.id)
                                  : [...old, c.id],
                              )
                            }
                          />
                          <span className="ex-check">
                            <Icon name="check" size={13} />
                          </span>
                          <strong>{human(c.execution.kind)}</strong>
                          <span>
                            {used(c) ? "Attempt recorded" : "Confirmed"}
                          </span>
                        </div>
                        <button
                          className="ex-card-title"
                          onClick={() => inspect(c.preparation_id)}
                        >
                          {taskName(c.task_id)}
                        </button>
                        <p>
                          {date(
                            c.execution.scheduled_at ||
                              c.execution.scheduled_utc,
                          )}
                        </p>
                        <div className="ex-card-bottom">
                          <span>{date(c.confirmed_at)}</span>
                          <button
                            disabled={disabled || !!used(c)}
                            onClick={() => {
                              setError("");
                              setDialog({ type: "run", confirmation: c });
                            }}
                          >
                            Review execution <Icon name="arrow" size={14} />
                          </button>
                        </div>
                      </article>
                    ))
                  ) : (
                    <Empty icon="shield">
                      Review a proposed plan or selected ready tasks, then
                      explicitly confirm the batch.
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
                  {!data?.attempts.length && !data?.schedules.length && (
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
                            review({ kind: "cancellation", schedule_id: s.id })
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
                <div className="ex-batch-actions">
                  <button
                    className="ex-button ex-primary"
                    disabled={disabled || !picked.length}
                    onClick={() =>
                      review({
                        kind: "immediate",
                        preparation_ids: picked.map((p) => p.preparation_id),
                      })
                    }
                  >
                    <Icon name="send" size={15} />
                    Confirm immediate
                  </button>
                  <button
                    className="ex-button"
                    disabled={disabled || !plan?.proposals.length}
                    onClick={() =>
                      plan && review({ kind: "plan", plan_id: plan.id })
                    }
                  >
                    <Icon name="clock" size={15} />
                    Confirm plan ({plan?.proposals.length ?? 0})
                  </button>
                  <button
                    className="ex-button"
                    disabled={!selected.length || disabled}
                    onClick={() => setSelected([])}
                  >
                    Clear selection
                  </button>
                </div>
                <div className="ex-scroll ex-batch-list">
                  {picked.length ? (
                    picked.map((r) => (
                      <div className="ex-batch-row" key={r.preparation_id}>
                        <span className="ex-check">
                          <Icon name="check" size={12} />
                        </span>
                        <button onClick={() => inspect(r.preparation_id)}>
                          {taskName(r.task_id)}
                        </button>
                        <span>{r.subject}</span>
                        <small>{r.sender}</small>
                        <button
                          aria-label={`Remove ${r.recipient} from batch`}
                          disabled={disabled}
                          onClick={() => toggle(r.preparation_id)}
                        >
                          <Icon name="close" size={14} />
                        </button>
                      </div>
                    ))
                  ) : (
                    <p className="ex-hint">
                      Select ready tasks for immediate confirmation. Plan
                      confirmation covers every proposed slot in the campaign.
                    </p>
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
            dialog.type === "batch-run"
              ? "Review batch execution"
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
          {dialog.type === "batch-run" && (
            <>
              <div className="ex-dialog-body">
                <p>
                  Execute these {dialog.confirmations.length} confirmed
                  operations in order. The batch stops on an error or a paused
                  execution flow.
                </p>
                {dialog.confirmations.map((c) => (
                  <section key={c.id}>
                    <h3>
                      {taskName(c.task_id)} · {human(c.execution.kind)}
                    </h3>
                    <p>
                      {date(
                        c.execution.scheduled_at || c.execution.scheduled_utc,
                      )}
                    </p>
                    {data?.reviews
                      .filter((r) => r.preparation_id === c.preparation_id)
                      .map((r) => (
                        <Message key={r.preparation_id} item={r} />
                      ))}
                    {!available(c.execution.kind) && (
                      <p className="ex-banner">
                        {human(c.execution.kind)} capability is disabled.
                      </p>
                    )}
                  </section>
                ))}
              </div>
              <div className="ex-dialog-actions">
                <button
                  className="ex-button ex-primary"
                  disabled={
                    busy ||
                    paused ||
                    !dialog.confirmations.length ||
                    dialog.confirmations.some(
                      (c) => !available(c.execution.kind),
                    )
                  }
                  onClick={() =>
                    perform(async () => {
                      for (const c of dialog.confirmations) {
                        const result = await core("execution_run", {
                          confirmation_id: c.id,
                        });
                        setExecutionSelection((old) =>
                          old.filter((id) => id !== c.id),
                        );
                        if (result.paused || result.flow?.state === "paused") {
                          setDialog(null);
                          throw new Error(
                            "Batch stopped: execution flow is paused. Inspect recorded evidence before continuing.",
                          );
                        }
                      }
                      setDialog(null);
                    }, "Batch requests completed. Inspect the observed outcomes in the execution ledger.")
                  }
                >
                  {busy ? "Executing batch…" : "Execute confirmed batch"}
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
                    review({
                      kind: "replacement",
                      schedule_id: dialog.schedule.id,
                      replacement_confirmation_id: replacement,
                    })
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
                <span>No external action occurs yet</span>
                <button
                  className="ex-button ex-primary"
                  disabled={busy}
                  onClick={() =>
                    perform(async () => {
                      await core("execution_confirm", {
                        ...dialog.request,
                        token: dialog.result.token,
                      });
                      setDialog(null);
                    }, "Confirmation recorded. Review execution when ready.")
                  }
                >
                  {busy ? "Confirming…" : "Confirm exact details"}
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

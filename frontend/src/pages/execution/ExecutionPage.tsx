import {
  useEffect,
  useMemo,
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
  type Workspace,
  type Attempt,
} from "../../core";
import Icon, { type IconName } from "../../shared/Icon";
import Timetable from "./Timetable";
import {
  autoDensity,
  buildIndex,
  buildRows,
  buildSessions,
  buildSlots,
  DAY_LABEL,
  DENSITIES,
  SLOT_LABEL,
  WEEKDAY_TOKEN,
  zoned,
  type Density,
  type Slot,
  type Tone,
} from "./timetable-model";
import "./Execution.css";

const REGIONS = ["Ready pool", "Send timeline", "Execution monitor"];
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
/** Legend order: what the operator needs to read about the whole horizon, in sequence. */
const LEGEND_ORDER: Tone[] = [
  "proposed", "queued", "placed", "sent", "failed", "unknown", "expired",
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
const DAY_TOKENS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
const DAY_SHORT: Record<string, string> = {
  SUN: "日", MON: "一", TUE: "二", WED: "三", THU: "四", FRI: "五", SAT: "六",
};
const COMMON_ZONES = [
  "Asia/Shanghai", "Asia/Tokyo", "Asia/Singapore", "Australia/Sydney",
  "Europe/London", "Europe/Berlin", "Europe/Paris",
  "America/New_York", "America/Chicago", "America/Los_Angeles", "UTC",
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
/** What a configuration would actually produce, shown before it is saved. */
function project(
  configuration: PlanConfiguration,
  institutions: { name: string; count: number }[],
  now: Date,
) {
  const sessions: { date: string; weekday: string }[] = [];
  for (let offset = 0; offset < configuration.horizon_days; offset += 1) {
    const instant = new Date(now.getTime() + offset * 86400000);
    const weekday = WEEKDAY_TOKEN[
      zoned(instant, configuration.timezone, { weekday: "short" }, "en-US")
    ] ?? "";
    for (const window of configuration.windows)
      if (window.days.includes(weekday))
        sessions.push({
          date: zoned(instant, configuration.timezone, {
            year: "numeric", month: "2-digit", day: "2-digit",
          }),
          weekday,
        });
  }
  const limit = Math.max(1, configuration.institution_limit || 1);
  const wanted = sessions.map((_, index) =>
    institutions.filter((item) => item.count > index * limit).length);
  return {
    sessions,
    wanted,
    placed: sessions.map((_, index) => Math.min(wanted[index], configuration.daily_limit)),
    crowded: wanted.some((count) => count > configuration.daily_limit),
    total: institutions.reduce((sum, item) => sum + item.count, 0),
    needed: institutions.reduce(
      (worst, item) => Math.max(worst, Math.ceil(item.count / limit)), 0),
    grid: institutions.map((item) => ({
      institution: item.name,
      filled: sessions.map((_, index) => item.count > index * limit),
    })),
    finish: (count: number) => sessions[Math.min(count, sessions.length) - 1]?.date ?? "",
  };
}
function countdown(epoch: number, now: number) {
  const minutes = Math.round((epoch - now) / 60000);
  if (minutes <= 0) return "已到";
  if (minutes < 60) return `${minutes} 分钟后`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时后`;
  return `${Math.round(minutes / 1440)} 天后`;
}

function Empty({ icon = "mail", children }: { icon?: IconName; children: ReactNode }) {
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
  wide,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  wide?: boolean;
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
      className={`ex-dialog${wide ? " ex-dialog-wide" : ""}`}
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

type WindowDraft = { days: string[]; start: string; end: string };

/** The scheduled-send rules: timezone, repeatable windows, pacing and institution rhythm. */
function PlanSettings({
  configuration,
  institutions,
  busy,
  save,
}: {
  configuration: PlanConfiguration;
  institutions: { name: string; count: number }[];
  busy: boolean;
  save: (value: PlanConfiguration) => void;
}) {
  const [timezone, setTimezone] = useState(configuration.timezone);
  const [windows, setWindows] = useState<WindowDraft[]>(
    configuration.windows.map((w) => ({ days: [...w.days], start: w.start, end: w.end })),
  );
  const [spacing, setSpacing] = useState(String(configuration.spacing_minutes));
  const [daily, setDaily] = useState(String(configuration.daily_limit));
  const [horizon, setHorizon] = useState(String(configuration.horizon_days));
  const [limit, setLimit] = useState(String(configuration.institution_limit ?? 1));
  const [problem, setProblem] = useState("");

  const draft: PlanConfiguration = {
    timezone: timezone.trim() || "UTC",
    windows: windows.map((w) => ({ days: w.days, start: w.start, end: w.end })),
    spacing_minutes: Number(spacing),
    daily_limit: Number(daily),
    horizon_days: Number(horizon),
    institution_limit: Number(limit),
  };
  const preview = project(draft, institutions, new Date());
  const sessionsNeeded = preview.needed;

  function addWindow(preset: string[]) {
    setWindows([...windows, { days: preset, start: "09:00", end: "12:00" }]);
  }
  function submit() {
    if (!windows.length) return setProblem("At least one allowed window is required.");
    for (const window of windows) {
      if (!window.days.length) return setProblem("Every window needs at least one day.");
      if (window.end <= window.start)
        return setProblem(`The window end must be after its start (${window.start}-${window.end}).`);
    }
    for (const [label, value] of [
      ["Spacing", draft.spacing_minutes],
      ["Daily limit", draft.daily_limit],
      ["Horizon", draft.horizon_days],
      ["Institution limit", draft.institution_limit],
    ] as [string, number][])
      if (!Number.isInteger(value) || value < 1)
        return setProblem(`${label} must be a positive whole number.`);
    setProblem("");
    save(draft);
  }
  return (
    <div className="ex-settings">
      <div className="ex-settings-rules">
        <label>
          时区（IANA）
          <input
            list="ex-zones"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            placeholder="Asia/Shanghai"
          />
        </label>
        <datalist id="ex-zones">
          {COMMON_ZONES.map((zone) => <option key={zone} value={zone} />)}
        </datalist>

        <div className="ex-field">
          <span>允许窗口 · 每个窗口在某个星期几出现一次，就是一个档期</span>
          {windows.map((window, index) => (
            <div className="ex-window" key={index}>
              <div className="ex-days">
                {DAY_TOKENS.map((token) => {
                  const on = window.days.includes(token);
                  return (
                    <button
                      type="button"
                      key={token}
                      className={`ex-day${on ? " is-on" : ""}`}
                      aria-pressed={on}
                      onClick={() => setWindows(windows.map((w, i) => i === index ? {
                        ...w,
                        days: on ? w.days.filter((d) => d !== token) : [...w.days, token],
                      } : w))}
                    >
                      {DAY_SHORT[token]}
                    </button>
                  );
                })}
              </div>
              <input
                type="time"
                aria-label="Window start"
                value={window.start}
                onChange={(e) => setWindows(windows.map((w, i) =>
                  i === index ? { ...w, start: e.target.value } : w))}
              />
              <span className="ex-dash">–</span>
              <input
                type="time"
                aria-label="Window end"
                value={window.end}
                onChange={(e) => setWindows(windows.map((w, i) =>
                  i === index ? { ...w, end: e.target.value } : w))}
              />
              <button
                type="button"
                className="ex-icon-button"
                aria-label="Remove window"
                disabled={windows.length === 1}
                onClick={() => setWindows(windows.filter((_, i) => i !== index))}
              >
                <Icon name="close" size={14} />
              </button>
            </div>
          ))}
          <div className="ex-window-add">
            <button type="button" className="ex-button" onClick={() => addWindow(["MON"])}>
              <Icon name="plus" size={14} /> 添加窗口
            </button>
            <button
              type="button"
              className="ex-button"
              onClick={() => addWindow(DAY_TOKENS.slice(1, 6))}
            >
              工作日
            </button>
            <button type="button" className="ex-button" onClick={() => addWindow(DAY_TOKENS)}>
              每天
            </button>
            <button
              type="button"
              className="ex-button"
              onClick={() => addWindow(["SAT", "SUN"])}
            >
              周末
            </button>
          </div>
        </div>

        <div className="ex-rule-numbers">
          <label>
            间隔（分钟）
            <input type="number" min="1" value={spacing}
              onChange={(e) => setSpacing(e.target.value)} />
          </label>
          <label>
            每日上限
            <input type="number" min="1" value={daily}
              onChange={(e) => setDaily(e.target.value)} />
          </label>
          <label>
            视野（天）
            <input type="number" min="1" value={horizon}
              onChange={(e) => setHorizon(e.target.value)} />
          </label>
        </div>

        <div className="ex-field ex-pace">
          <span>同校节奏</span>
          <p>
            同一所院校的导师会互相交流。把间隔设得再大，也挡不住同一档期里出现两位同校导师——
            只有这条规则能。
          </p>
          <div className="ex-pace-row">
            <span>同一档期内同一院校最多</span>
            <select value={limit} onChange={(e) => setLimit(e.target.value)}>
              <option value="1">1 位导师（最安全）</option>
              <option value="2">2 位导师</option>
              <option value="3">3 位导师</option>
            </select>
          </div>
        </div>
        {problem && <p className="ex-banner ex-error" role="alert">{problem}</p>}
      </div>

      <div className="ex-settings-preview">
        <h3>这套规则会排出什么</h3>
        <dl className="ex-projection">
          <dt>视野内档期</dt>
          <dd>{preview.sessions.length} 个</dd>
          <dt>排完需要</dt>
          <dd>{sessionsNeeded} 个档期</dd>
          <dt>就绪动作</dt>
          <dd>{preview.total} 位导师</dd>
          <dt>最后一批</dt>
          <dd>{sessionsNeeded ? preview.finish(sessionsNeeded) : "—"}</dd>
        </dl>
        {sessionsNeeded > preview.sessions.length ? (
          <p className="ex-banner ex-error">
            视野内只有 {preview.sessions.length} 个档期，排完需要 {sessionsNeeded} 个：
            有 {preview.total - preview.placed.reduce((s, n) => s + n, 0)} 位排不下。
            加大视野天数、增加窗口，或放宽同校节奏。
          </p>
        ) : (
          <p className="ex-banner">
            这套规则能在视野内排下全部 {preview.total} 位导师，
            且不会有两个同校导师落在同一档期。
          </p>
        )}
        {preview.crowded && (
          <p className="ex-banner ex-error">
            每日上限 {draft.daily_limit} 小于某个档期想容纳的院校数，多出来的会顺延到下一档期。
          </p>
        )}
        <div className="ex-mini">
          <div className="ex-mini-grid" style={{
            gridTemplateColumns: `72px repeat(${Math.min(preview.sessions.length, 8)}, 1fr)`,
          }}>
            <span />
            {preview.sessions.slice(0, 8).map((session, index) => (
              <span key={index} className="ex-mini-head">
                {session.date.slice(5)}
                <small>{DAY_LABEL[session.weekday] ?? ""}</small>
              </span>
            ))}
            {preview.grid.slice(0, 6).map((row) => (
              <MiniRow key={row.institution} row={row} />
            ))}
          </div>
          {preview.sessions.length > 8 && (
            <small>仅预览前 8 个档期</small>
          )}
        </div>
        <p className="ex-hint">
          保存规则不会改动已经生成的排期。保存后重新生成排期才会应用；
          改期一个已确认的时间会让那次确认失效。
        </p>
      </div>
      <div className="ex-dialog-actions ex-settings-actions">
        <span>Core 会校验每一项约束，拒绝时指名具体约束</span>
        <button className="ex-button ex-primary" disabled={busy} onClick={submit}>
          {busy ? "Saving…" : "保存规则"}
        </button>
      </div>
    </div>
  );
}
function MiniRow({ row }: { row: { institution: string; filled: boolean[] } }) {
  return (
    <>
      <span className="ex-mini-name" title={row.institution}>{row.institution}</span>
      {row.filled.slice(0, 8).map((on, index) => (
        <span key={index} className={`ex-mini-cell${on ? " is-on" : ""}`}>
          {on ? <i /> : null}
        </span>
      ))}
    </>
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
  const [override, setOverride] = useState<string[] | null>(null);
  const [progress, setProgress] = useState("");
  const [run, setRun] = useState<ExecutionRun | null>(null);
  const [tab, setTab] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dialog, setDialog] = useState<DialogState | null>(null);
  const [replacement, setReplacement] = useState("");
  const [tick, setTick] = useState(() => Date.now());
  /** Grid density; ``null`` follows the size of the plan, an explicit pick sticks. */
  const [density, setDensity] = useState<Density | null>(null);
  const [focused, setFocused] = useState(false);
  const actionLock = useRef(false);

  useEffect(() => {
    const timer = setInterval(() => setTick(Date.now()), 30000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!focused) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFocused(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focused]);

  async function refresh() {
    if (!campaign) return;
    await Promise.all([workspaceQuery.refresh(), executionQuery.refresh()]);
  }
  const loading = workspaceQuery.isLoading || executionQuery.isLoading;
  const queryError = workspaceQuery.error?.message || executionQuery.error?.message || "";
  const displayError = error || queryError;

  async function perform(action: () => Promise<unknown>, message = "") {
    if (actionLock.current) return;
    actionLock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(message);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      actionLock.current = false;
      setBusy(false);
      setProgress("");
    }
  }
  const configuration = data?.configuration;
  const queue: QueueRow[] = data?.queue ?? [];
  const authorizable = queue.filter((row) => row.state === "ready_to_authorize");
  const selected = override ?? authorizable.map((row) => row.preparation_id);
  const plans = data?.plans.filter((p) => p.status !== "superseded") ?? [];
  const plan = plans.at(-1);
  const slots = useMemo(() => buildSlots(plan), [plan]);
  const queueById = useMemo(
    () => new Map((data?.queue ?? []).map((row) => [row.preparation_id, row])),
    [data?.queue]);
  /** The newest attempt per Preparation; the mailbox is the only source of an outcome. */
  const attemptById = useMemo(() => {
    const found = new Map<string, Attempt>();
    for (const attempt of data?.attempts ?? []) {
      const existing = found.get(attempt.preparation_id);
      if (!existing || attempt.updated_at > existing.updated_at) {
        found.set(attempt.preparation_id, attempt);
      }
    }
    return found;
  }, [data?.attempts]);
  const toneOf = useMemo(() => (slot: Slot): Tone => {
    const row = queueById.get(slot.proposal.preparation_id);
    const attempt = attemptById.get(slot.proposal.preparation_id);
    if (row?.state === "already_sent") return "sent";
    if (attempt?.state === "sent") return "sent";
    if (attempt?.state === "failed") return "failed";
    if (attempt?.state === "unknown") return "unknown";
    if (row?.state === "externally_scheduled") return "placed";
    if (row?.state === "awaiting_execution") return "queued";
    // A planned time that passed before it was ever confirmed needs a new time, not a send.
    return slot.epoch <= tick ? "expired" : "proposed";
  }, [queueById, attemptById, tick]);
  const sessions = useMemo(
    () => (configuration ? buildSessions(slots, configuration) : []), [slots, configuration]);
  const rows = useMemo(() => buildRows(slots, toneOf), [slots, toneOf]);
  const index = useMemo(() => buildIndex(slots), [slots]);
  const toneCounts = useMemo(() => {
    const counts: Record<Tone, number> = {
      proposed: 0, queued: 0, placed: 0, sending: 0,
      sent: 0, failed: 0, unknown: 0, expired: 0,
    };
    for (const slot of slots) counts[toneOf(slot)] += 1;
    return counts;
  }, [slots, toneOf]);
  const timezone = configuration?.timezone ?? "";
  const today = useMemo(
    () => (timezone
      ? zoned(new Date(tick), timezone, { year: "numeric", month: "2-digit", day: "2-digit" })
      : ""),
    [timezone, tick],
  );
  /** The first session still ahead of now; its left edge is the "now" line. */
  const nowKey = useMemo(
    () => sessions.find((session) => session.epoch > tick)?.key ?? null,
    [sessions, tick],
  );
  const gridDensity = density ?? autoDensity(sessions.length, rows.length);
  const confirmationById = new Map(
    (data?.confirmations ?? []).map((c) => [c.id, c]));
  const reviewById = new Map((data?.reviews ?? []).map((r) => [r.preparation_id, r]));
  const institutions = institutionCounts(authorizable, workspace);
  const picked = authorizable.filter((row) => selected.includes(row.preparation_id));
  const visible = authorizable.filter((row) =>
    `${row.subject} ${row.recipient} ${taskName(row.task_id)}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  const awaiting = queue.filter((row) => row.state === "awaiting_execution" && row.confirmation_id);
  const dueOf = (kind: string) => awaiting.filter((row) => {
    const confirmation = confirmationById.get(row.confirmation_id!);
    if (!confirmation || confirmation.execution.kind !== kind) return false;
    const at = confirmation.execution.scheduled_at || confirmation.execution.scheduled_utc;
    return !at || new Date(at).getTime() <= tick;
  });
  const scheduledDue = dueOf("scheduled");
  const immediateDue = dueOf("immediate");
  const runs = data?.runs ?? [];
  const latest = run ?? runs[0] ?? null;
  const availability = data?.availability ?? {};
  const available = (kind: string) => !!availability[kind]?.available;
  const basis = (kind: string) =>
    availability[kind]?.basis || "This operation is disabled for the connected mailbox.";
  const paused = workspace?.report?.flow.state === "paused";
  const disabled = busy || loading;
  const excluded = plan ? [...plan.impossible, ...plan.unavailable] : [];

  const review = (request: ReviewRequest, runAfter: boolean) =>
    perform(async () => {
      const result = await core("execution_review", request);
      setDialog({ type: "review", request, result, runAfter });
    });
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
        `Authorized ${created.length} action(s). They are now in the sending queue and can be run without selecting them again.`,
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
      selected.includes(id) ? selected.filter((p) => p !== id) : [...selected, id],
    );
  }
  const panel = (
    index: number,
    icon: IconName,
    count: number | string,
    children: ReactNode,
    action?: ReactNode,
  ) => (
    <section
      className={`ex-panel ex-panel-${index} ${tab === index ? "ex-mobile-active" : ""}`}
      aria-label={REGIONS[index]}
    >
      <header className="ex-panel-heading">
        <span className={`ex-stage ex-stage-${index + 1}`}>
          <Icon name={icon} />
        </span>
        <h2>{REGIONS[index]}</h2>
        <span className="ex-count">{count}</span>
        {action}
      </header>
      {children}
    </section>
  );

  return (
    <AppShell className="execution-page" activeRoute="execution">
      <div className="workspace">
        <Topbar breadcrumb="Batch execution" homeHref="#workflow">
          <span className="ex-connection">
            <i />
            {loading ? "Loading Core…" : workspace ? "Connected to Core" : "Core unavailable"}
          </span>
        </Topbar>
        <PageHeader
          className="ex-heading"
          eyebrow="Outreach operations / 04"
          title="Batch execution"
          subtitle="From ready to sent, with you in control."
          actions={
            <button className="ex-button" disabled={disabled} onClick={() => refresh()}>
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
            disabled={disabled || !configuration}
            onClick={() => {
              setError("");
              setDialog({ type: "rules" });
            }}
          >
            <Icon name="filter" size={16} />
            排期设置
          </button>
          {configuration && (
            <span className="ex-timezone">
              {configuration.timezone} · 间隔 {configuration.spacing_minutes} 分钟 ·
              每日 {configuration.daily_limit} · 同校每档期 {configuration.institution_limit} 位
            </span>
          )}
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
            {human(workspace?.report?.flow.reason || "operator intervention required")}.
            Reconcile mailbox evidence and resolve the flow in Core before continuing.
          </div>
        )}
        <div className="ex-tabs" role="tablist" aria-label="Workspace regions">
          {REGIONS.map((name, i) => (
            <button
              key={name}
              role="tab"
              aria-selected={tab === i}
              onClick={() => setTab(i)}
            >
              {name}
            </button>
          ))}
        </div>
        <main className={`ex-main${focused ? " is-focused" : ""}`} aria-busy={disabled}>
          {panel(
            0,
            "database",
            authorizable.length,
            <>
              <div className="ex-panel-sub">
                <span>Only Ready actions may enter the queue</span>
                <button
                  disabled={!visible.length || disabled}
                  onClick={() =>
                    setOverride(
                      visible.every((r) => selected.includes(r.preparation_id))
                        ? selected.filter(
                            (id) => !visible.some((r) => r.preparation_id === id))
                        : [...new Set([...selected, ...visible.map((r) => r.preparation_id)])],
                    )
                  }
                >
                  {visible.length && visible.every((r) => selected.includes(r.preparation_id))
                    ? "Clear visible"
                    : "Select visible"}
                </button>
              </div>
              <div className="ex-scroll">
                {rowsOf(visible, workspace).map(([institution, group]) => (
                  <section className="ex-pool-group" key={institution}>
                    <h3>
                      {institution} <span>{group.length}</span>
                    </h3>
                    {group.map((row) => (
                      <div
                        key={row.preparation_id}
                        className={`ex-task ${selected.includes(row.preparation_id) ? "is-selected" : ""}`}
                      >
                        <input
                          type="checkbox"
                          aria-label={`Select ${row.recipient}`}
                          checked={selected.includes(row.preparation_id)}
                          disabled={disabled}
                          onChange={() => toggle(row.preparation_id)}
                        />
                        <span className="ex-task-content">
                          <span className="ex-monogram">
                            {taskName(row.task_id).slice(0, 2).toUpperCase()}
                          </span>
                          <span>
                            <strong>{taskName(row.task_id)}</strong>
                            <small>{row.recipient}</small>
                          </span>
                        </span>
                      </div>
                    ))}
                  </section>
                ))}
                {!visible.length && (
                  <Empty icon="database">
                    {loading
                      ? "Loading preparations…"
                      : "Ready Preparations appear here. Readiness is the only way into the queue."}
                  </Empty>
                )}
                {blocked(queue).length > 0 && (
                  <section className="ex-pool-group ex-pool-blocked">
                    <h3>未就绪 · 不进队列 <span>{blocked(queue).length}</span></h3>
                    {blocked(queue).map((row) => (
                      <div className="ex-task is-blocked" key={row.preparation_id}>
                        <span className="ex-task-content">
                          <span className="ex-monogram ex-blocked-mark">!</span>
                          <span>
                            <strong>{taskName(row.task_id)}</strong>
                            <small>{row.blocking_codes.join(", ") || "not_ready"}</small>
                          </span>
                        </span>
                      </div>
                    ))}
                  </section>
                )}
              </div>
              <div className="ex-panel-foot">
                <span>{picked.length} selected</span>
                <button
                  className="ex-button ex-primary"
                  disabled={disabled || paused || !picked.length || !available("immediate")}
                  onClick={() => review({
                    kind: "immediate",
                    preparation_ids: picked.map((row) => row.preparation_id),
                  }, true)}
                >
                  <Icon name="send" size={14} />
                  立即发送 {picked.length}
                </button>
              </div>
            </>,
          )}
          {panel(
            1,
            "clock",
            slots.length,
            <>
              <div className="ex-panel-sub ex-timeline-sub">
                <span className="ex-scale">
                  {rows.length} 校 × {sessions.length} 档期 · {plan ? human(plan.status) : "无排期"}
                </span>
                <span className="ex-sub-tools">
                  <span className="ex-legend">
                    {LEGEND_ORDER.filter((tone) => toneCounts[tone] > 0).map((tone) => (
                      <span className={`ex-swatch is-${tone}`} key={tone} title={SLOT_LABEL[tone]}>
                        <i />
                        {SLOT_LABEL[tone]} {toneCounts[tone]}
                      </span>
                    ))}
                  </span>
                  <span className="ex-density" role="group" aria-label="网格密度">
                    {DENSITIES.map((option) => (
                      <button
                        key={option.key}
                        type="button"
                        title={option.hint}
                        aria-pressed={gridDensity === option.key}
                        className={gridDensity === option.key ? "is-active" : ""}
                        onClick={() => setDensity(option.key)}
                      >
                        {option.label}
                      </button>
                    ))}
                  </span>
                </span>
              </div>
              {slots.length ? (
                <Timetable
                  sessions={sessions}
                  rows={rows}
                  index={index}
                  tick={tick}
                  today={today}
                  nowKey={nowKey}
                  density={gridDensity}
                  toneOf={toneOf}
                  onPick={(slot) => plan && setDialog({
                    type: "slot", slot, plan: plan.id,
                    timezone: plan.configuration.timezone,
                  })}
                />
              ) : (
                <div className="ex-grid-wrap ex-grid-blank">
                  <Empty icon="clock">
                    {loading
                      ? "Loading the plan…"
                      : "Propose a plan to see every institution paced across the horizon's sessions."}
                  </Empty>
                </div>
              )}
              {excluded.length > 0 && (
                  <div className="ex-excluded">
                    <h3>未进入排期 {excluded.length}</h3>
                    {excluded.map((item) => (
                      <article className="ex-card ex-muted" key={item.preparation_id}>
                        <strong>{item.institution_name || taskName(item.task_id)}</strong>
                        <p>{item.detail || human(item.status)}</p>
                        <small>{human(item.status)}{item.constraint ? ` · ${human(item.constraint)}` : ""}</small>
                      </article>
                    ))}
                  </div>
                )}
              <div className="ex-panel-foot">
                <span>行内串行 · 列间并行 · 一格一位导师</span>
                <span className="ex-foot-actions">
                  <button
                    className="ex-button"
                    disabled={disabled || !campaign}
                    onClick={() => perform(
                      () => core("execution_propose", { campaign_id: campaign }),
                      "Plan proposed. Confirm the queue to make these actions sendable.",
                    )}
                  >
                    <Icon name="plus" size={14} />
                    生成排期
                  </button>
                  <button
                    className="ex-button ex-primary"
                    disabled={disabled || !plan || !plan.proposals.length
                      || plan.proposals.every((p) => p.confirmation_id)}
                    onClick={() => plan && review({ kind: "plan", plan_id: plan.id }, false)}
                  >
                    <Icon name="shield" size={14} />
                    确认入队
                  </button>
                </span>
              </div>
            </>,
            <button
              key="focus"
              type="button"
              className={`ex-icon-button${focused ? " is-active" : ""}`}
              aria-pressed={focused}
              title={focused ? "退出专注（Esc）" : "专注时间线"}
              onClick={() => setFocused(!focused)}
            >
              <Icon name="fit" size={14} />
            </button>,
          )}
          {panel(
            2,
            "send",
            awaiting.length,
            <>
              <div className="ex-panel-sub">
                <span>Confirmed actions, earliest first</span>
                <span className="ex-legend">
                  <span className="ex-chip ex-chip-amber">已到 {scheduledDue.length + immediateDue.length}</span>
                </span>
              </div>
              <div className="ex-scroll">
                {latest && (
                  <article className={`ex-card ex-outcome ${latest.state === "stopped" ? "ex-excluded" : ""}`}>
                    <div className="ex-card-top">
                      <Icon name="send" size={16} />
                      <strong>{human(latest.kind)} run {human(latest.state)}</strong>
                      <span>{date(latest.started_at)}</span>
                    </div>
                    <RunSummary run={latest} />
                    {latest.state === "stopped" && (
                      <p className="ex-hint">
                        Stopped after {latest.executed_count} of {latest.requested_count} ·{" "}
                        {latest.not_reached_count} never reached. Resolve it in the{" "}
                        <a href="#records">execution ledger</a>, then run the remaining
                        actions explicitly.
                      </p>
                    )}
                  </article>
                )}
                {!awaiting.length && !latest && (
                  <Empty icon="send">
                    Confirmed actions become the sending queue. Execution outcomes are
                    observed here, never inferred.
                  </Empty>
                )}
                {awaiting
                  .slice()
                  .sort((a, b) => atOf(confirmationById.get(a.confirmation_id!))
                    - atOf(confirmationById.get(b.confirmation_id!)))
                  .map((row) => {
                    const confirmation = confirmationById.get(row.confirmation_id!);
                    const at = confirmation?.execution.scheduled_at
                      || confirmation?.execution.scheduled_utc || "";
                    return (
                      <div className="ex-queue-row" key={row.preparation_id}>
                        <span className="ex-queue-time">{at ? at.slice(11, 16) : "—"}</span>
                        <span className="ex-queue-body">
                          <strong>{taskName(row.task_id)}</strong>
                          <small>
                            {at ? `${countdown(new Date(at).getTime(), tick)} · ${at.slice(0, 10)}` : "immediate"}
                            {confirmation ? ` · ${human(confirmation.execution.kind)}` : ""}
                          </small>
                        </span>
                        <span className={`ex-chip ex-chip-${QUEUE_TONE[row.state] ?? "gray"}`}>
                          {human(row.state)}
                        </span>
                      </div>
                    );
                  })}
              </div>
              <div className="ex-panel-foot">
                <span>
                  {!available("scheduled") && (
                    <span className="ex-note">定时投放：{basis("scheduled")}</span>
                  )}
                </span>
                <button
                  className="ex-button ex-primary"
                  disabled={disabled || paused || !dueOf("scheduled").length
                    || !available("scheduled")}
                  onClick={() => perform(async () => {
                    await runConfirmations(scheduledDue.map((row) => row.confirmation_id!));
                  })}
                >
                  <Icon name="clock" size={14} />
                  投放到期定时 {scheduledDue.length}
                </button>
              </div>
            </>,
          )}
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
          wide={dialog.type === "rules"}
          title={
            dialog.type === "result"
              ? `Execution run ${human(dialog.run.state)}`
              : dialog.type === "rules"
                ? "排期设置"
                : dialog.type === "adjust"
                  ? "Adjust proposed time"
                  : dialog.type === "slot"
                    ? dialog.slot.supervisor
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
            <div className="ex-banner ex-error" role="alert">{error}</div>
          )}
          {dialog.type === "result" && (
            <>
              <div className="ex-dialog-body">
                <p>
                  {human(dialog.run.kind)} run {human(dialog.run.state)} ·{" "}
                  {dialog.run.executed_count} of {dialog.run.requested_count} reached.
                  Completion alone never claims success: read the observed outcomes.
                </p>
                <RunSummary run={dialog.run} />
                {dialog.run.state === "stopped" && (
                  <div className="ex-banner ex-error">
                    <p>
                      The run stopped after {dialog.run.executed_count} of{" "}
                      {dialog.run.requested_count}; {dialog.run.not_reached_count} action(s)
                      were never reached and stay eligible for a later, explicitly
                      requested run.
                    </p>
                  </div>
                )}
                <ol className="ex-run-items">
                  {dialog.run.items.map((entry) => (
                    <li key={entry.id}>
                      <span className={`ex-chip ex-chip-${OUTCOME_TONE[entry.outcome] ?? "gray"}`}>
                        {human(entry.outcome)}
                      </span>
                      <span>{entry.task_id ? taskName(entry.task_id) : "Action"}</span>
                      {entry.detail && <small>{entry.detail}</small>}
                    </li>
                  ))}
                </ol>
              </div>
              <div className="ex-dialog-actions">
                <button className="ex-button ex-primary" onClick={() => setDialog(null)}>
                  Close
                </button>
              </div>
            </>
          )}
          {dialog.type === "rules" && configuration && (
            <PlanSettings
              configuration={configuration}
              institutions={institutions}
              busy={busy}
              save={(rules) => perform(async () => {
                await core("execution_configure", { campaign_id: campaign, ...rules });
                setDialog(null);
              }, "Rules saved. Propose a new plan to apply them; existing plan times are unchanged.")}
            />
          )}
          {dialog.type === "slot" && (
            <>
              <div className="ex-dialog-body">
                <Message item={reviewById.get(dialog.slot.proposal.preparation_id)
                  ?? dialog.slot.proposal} />
                <dl>
                  <dt>院校</dt>
                  <dd>{dialog.slot.institution}</dd>
                  <dt>档期</dt>
                  <dd>
                    {dialog.slot.date} {DAY_LABEL[dialog.slot.weekday] ?? ""} ·{" "}
                    {dialog.slot.session === null ? "档期" :
                      `${configuration?.windows[dialog.slot.session]?.start ?? ""}–${configuration?.windows[dialog.slot.session]?.end ?? ""}`}
                  </dd>
                  <dt>状态</dt>
                  <dd>{dialog.slot.proposal.confirmation_id ? "已入队" : "已排期"}</dd>
                </dl>
                <p className="ex-hint">
                  Core 会校验窗口、间隔、每日上限，以及同一档期内该校是否已有另一位导师。
                </p>
              </div>
              <div className="ex-dialog-actions">
                <span>改期一个已确认的时间会让那次确认失效</span>
                <button
                  className="ex-button"
                  onClick={() => setDialog({
                    type: "adjust",
                    preparation: dialog.slot.proposal.preparation_id,
                    at: dialog.slot.at.slice(0, 16),
                    timezone: dialog.timezone,
                    plan: dialog.plan,
                  })}
                >
                  改期
                </button>
              </div>
            </>
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
                  Local time in <strong>{dialog.timezone}</strong>. Core checks allowed
                  windows, spacing, daily limits and the institution's session pacing.
                </p>
                <label>
                  Proposed time
                  <input type="datetime-local" name="at" required defaultValue={dialog.at} />
                </label>
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
                  <strong>{taskName(dialog.schedule.task_id)}</strong>, scheduled{" "}
                  {date(dialog.schedule.scheduled_utc)}.
                </p>
                <label>
                  Replacement confirmation
                  <select value={replacement} onChange={(e) => setReplacement(e.target.value)}>
                    <option value="">Choose a confirmed replacement</option>
                    {(data?.confirmations ?? [])
                      .filter((c) => c.task_id === dialog.schedule.task_id
                        && c.preparation_id !== dialog.schedule.preparation_id
                        && c.execution.kind === "scheduled")
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {reviewById.get(c.preparation_id)?.subject || c.preparation_id} ·{" "}
                          {date(c.execution.scheduled_at || c.execution.scheduled_utc)}
                        </option>
                      ))}
                  </select>
                </label>
              </div>
              <div className="ex-dialog-actions">
                <button
                  className="ex-button ex-primary"
                  disabled={busy || !replacement}
                  onClick={() => review({
                    kind: "replacement",
                    schedule_id: dialog.schedule.id,
                    replacement_confirmation_id: replacement,
                  }, false)}
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
                  Confirmation authorizes these details; execution is a separate action.
                </p>
                {Array.isArray(dialog.result.value) ? (
                  dialog.result.value.map((r) => <Message key={r.preparation_id} item={r} />)
                ) : "proposals" in dialog.result.value ? (
                  <>
                    <p>
                      <strong>{dialog.result.value.proposals.length} actions</strong> ·{" "}
                      {dialog.result.value.configuration.timezone} ·{" "}
                      {dialog.result.value.impossible.length
                        + dialog.result.value.unavailable.length} excluded
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
                  onClick={() => perform(async () => {
                    await confirmThen(dialog.request, dialog.result.token, dialog.runAfter);
                  }, dialog.runAfter ? "" : "Confirmation recorded. These actions are now in the sending queue.")}
                >
                  {busy
                    ? progress || "Working…"
                    : dialog.runAfter ? "Authorize and run" : "Confirm exact details"}
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
                  {date(dialog.confirmation.execution.scheduled_at
                    || dialog.confirmation.execution.scheduled_utc)}
                </p>
                {reviewById.get(dialog.confirmation.preparation_id) && (
                  <Message item={reviewById.get(dialog.confirmation.preparation_id)!} />
                )}
                {!available(dialog.confirmation.execution.kind) && (
                  <div className="ex-banner">{basis(dialog.confirmation.execution.kind)}</div>
                )}
              </div>
              <div className="ex-dialog-actions">
                <button
                  className="ex-button ex-primary"
                  disabled={busy || !available(dialog.confirmation.execution.kind) || paused}
                  onClick={() => perform(async () => {
                    await core("execution_run", { confirmation_id: dialog.confirmation.id });
                    setDialog(null);
                  }, "Execution request completed. Inspect the recorded outcome; completion alone does not establish success.")}
                >
                  {busy ? "Executing…" : `Execute ${human(dialog.confirmation.execution.kind)}`}
                </button>
              </div>
            </>
          )}
        </Modal>
      )}
    </AppShell>
  );
}

const atOf = (confirmation?: Confirmation) =>
  confirmation
    ? new Date(confirmation.execution.scheduled_at
      || confirmation.execution.scheduled_utc || 0).getTime()
    : 0;
const blocked = (queue: QueueRow[]) => queue.filter((row) => row.state === "not_ready");
/** The institution of a Task; the workspace report is the source for queue rows. */
function institutionOf(taskId: string, workspace: Workspace | null | undefined) {
  return workspace?.report?.tasks.find((t) => t.task_id === taskId)?.institution_name
    || "Unassigned institution";
}
function rowsOf(rows: QueueRow[], workspace: Workspace | null | undefined) {
  const found = new Map<string, QueueRow[]>();
  for (const row of rows) {
    const key = institutionOf(row.task_id, workspace);
    const group = found.get(key);
    if (group) group.push(row);
    else found.set(key, [row]);
  }
  return [...found.entries()];
}
function institutionCounts(rows: QueueRow[], workspace: Workspace | null | undefined) {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const name = institutionOf(row.task_id, workspace);
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts].map(([name, count]) => ({ name, count }));
}

type DialogState =
  | { type: "rules" }
  | { type: "review"; request: ReviewRequest; result: ReviewResult; runAfter: boolean }
  | { type: "adjust"; preparation: string; at: string; timezone: string; plan: string }
  | { type: "slot"; slot: Slot; plan: string; timezone: string }
  | { type: "replace"; schedule: ExternalSchedule }
  | { type: "run"; confirmation: Confirmation }
  | { type: "result"; run: ExecutionRun };

function RunSummary({ run }: { run: ExecutionRun }) {
  return (
    <div className="ex-run-summary">
      {OUTCOME_LABELS.filter(([key]) => (run.summary?.[key] ?? 0) > 0).map(([key, label]) => (
        <span className={`ex-chip ex-chip-${OUTCOME_TONE[key] ?? "gray"}`} key={key}>
          {label} {run.summary[key]}
        </span>
      ))}
      {run.state === "completed" && (
        <span className="ex-chip ex-chip-gray">{run.requested_count} requested</span>
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
            {value.replacement_confirmation?.execution.scheduled_at
              || value.replacement_confirmation?.execution.scheduled_utc}
          </p>
          <Message item={value.replacement} />
        </>
      )}
    </>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { core, human } from "./core";
import type { Campaign, Detail, Task, Workspace } from "./core";
import { stages, tasksFor, stageMetric } from "./workflow-model";
import Workflow from "./Workflow";
import Icon from "./Icon";
import MailboxPanel from "./MailboxPanel";
import DraftEditor from "./DraftEditor";
import "./App.css";

export default function App() {
  const [data, setData] = useState<Workspace | null>(null);
  const [campaign, setCampaign] = useState("");
  const [selected, setSelected] = useState("mailbox");
  const [search, setSearch] = useState("");
  const [zoom, setZoom] = useState(0.8);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [newCampaign, setNewCampaign] = useState(false);
  const [name, setName] = useState("");
  const [task, setTask] = useState<Task | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [help, setHelp] = useState(false);
  const [view, setView] = useState("workflow");
  const canvas = useRef<HTMLDivElement>(null);
  const modal = useRef<HTMLElement>(null);
  const revision = useRef(0);
  const detailRevision = useRef(0);
  const load = useCallback(async () => {
    const request = ++revision.current;
    setBusy(true);
    setError("");
    try {
      const value = await core<Workspace>(
        "workspace",
        campaign ? { campaign_id: campaign } : {},
      );
      if (request === revision.current) setData(value);
    } catch (e) {
      if (request === revision.current) setError((e as Error).message);
    } finally {
      if (request === revision.current) setBusy(false);
    }
  }, [campaign]);
  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- Synchronize the selected scope with the external Core store.
    void load();
  }, [load]);
  useEffect(() => {
    if (!newCampaign && !help) return;
    const previous = document.activeElement as HTMLElement | null;
    const element = modal.current;
    const focusable = () =>
      Array.from(
        element?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input, [tabindex="0"]',
        ) ?? [],
      );
    (
      element?.querySelector<HTMLInputElement>("input") ?? focusable()[0]
    )?.focus();
    const trap = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const targets = focusable();
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    element?.addEventListener("keydown", trap);
    return () => {
      element?.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, [newCampaign, help]);
  const fit = useCallback(() => {
    if (canvas.current)
      setZoom(
        Math.max(
          0.45,
          Math.min(
            1.1,
            (canvas.current.clientWidth - 40) / 1300,
            (window.innerHeight - 420) / 870,
          ),
        ),
      );
  }, []);
  useEffect(() => {
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [fit]);
  const stage = stages.find((s) => s.id === selected)!;
  const tasks = data
    ? tasksFor(selected, data).filter((t) =>
        `${t.student_name} ${t.supervisor_name} ${t.institution_name}`
          .toLowerCase()
          .includes(search.toLowerCase()),
      )
    : [];
  const openTask = async (value: Task) => {
    const request = ++detailRevision.current;
    setTask(value);
    setDetail(null);
    setError("");
    setNotice("");
    try {
      const result = await core<Detail>("task", { task_id: value.task_id });
      if (request === detailRevision.current) setDetail(result);
    } catch (e) {
      if (request === detailRevision.current) setError((e as Error).message);
    }
  };
  const create = async (event: React.SubmitEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const value = await core<Campaign>("create_campaign", { name });
      setNewCampaign(false);
      setName("");
      setData(null);
      setTask(null);
      setDetail(null);
      detailRevision.current++;
      setCampaign(value.id);
      setNotice(
        "Campaign created. Import source materials through the Core CLI to begin.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const check = async (id: string) => {
    setBusy(true);
    setError("");
    try {
      const result = await core<{ finding: string }>("check_duplicate", {
        preparation_id: id,
      });
      await load();
      if (task) await openTask(task);
      setNotice(
        `Duplicate check: ${human(result.finding)}. Review evidence coverage below.`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const choose = (id: string) => {
    setSelected(id);
    setTask(null);
    setDetail(null);
    detailRevision.current++;
  };
  const count = (id: string) => stageMetric(id, data).count;
  return (
    <div className="app-shell">
      <nav className="rail" aria-label="Main navigation">
        <div className="brand-mark" title="SmartMail">
          <span />
          <span />
        </div>
        <button
          className={view === "workflow" ? "active" : ""}
          onClick={() => setView("workflow")}
          title="Workflow"
          aria-label="Workflow"
        >
          <Icon name="grid" />
        </button>
        <button
          className={view === "tasks" ? "active" : ""}
          onClick={() => {
            setView("tasks");
            choose("intake");
          }}
          title="Outreach tasks"
          aria-label="Outreach tasks"
        >
          <Icon name="source" />
        </button>
        <div className="rail-spacer" />
        <button
          onClick={() => setNewCampaign(true)}
          className="rail-add"
          title="New campaign"
          aria-label="New campaign"
        >
          <Icon name="plus" />
        </button>
        <button
          onClick={() => setHelp(true)}
          title="Workflow guide"
          aria-label="Workflow guide"
        >
          <Icon name="book" />
        </button>
        <div className="avatar">OP</div>
      </nav>
      <div className="workspace">
        <header className="topbar">
          <a className="wordmark" href="/">
            SmartMail<span>CORE</span>
          </a>
          <div className="breadcrumb">
            Workspace <span>/</span> Outreach
          </div>
          <label className="search">
            <Icon name="search" size={17} />
            <input
              aria-label="Search outreach tasks"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Find a student or supervisor…"
            />
            <kbd>⌕</kbd>
          </label>
          <span className={`connection ${error ? "offline" : ""}`}>
            <i />
            {error
              ? "Connection needs attention"
              : data
                ? "Core connected"
                : "Connecting to Core"}
          </span>
          <button
            className="icon-button"
            title="Refresh Core data"
            aria-label="Refresh Core data"
            onClick={() => void load()}
            disabled={busy}
          >
            <Icon name="refresh" size={18} />
          </button>
        </header>
        <div className="page-heading">
          <div>
            <div className="eyebrow">COMMUNICATION OPERATIONS</div>
            <h1>
              Outreach workflow <span>v1.0</span>
            </h1>
            <p>From source materials to meaningful conversations.</p>
          </div>
          <button className="primary" onClick={() => setNewCampaign(true)}>
            <Icon name="plus" size={17} /> New campaign
          </button>
        </div>
        <div className="toolbar">
          <div className="campaign-select">
            <i className="dot" />
            <select
              aria-label="Campaign"
              value={data?.report?.campaign.id || ""}
              disabled={!data?.campaigns.length || busy}
              onChange={(e) => {
                setData(null);
                setTask(null);
                setDetail(null);
                detailRevision.current++;
                setCampaign(e.target.value);
              }}
            >
              {!data?.campaigns.length && <option>No campaign selected</option>}
              {data?.campaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <span className="toolbar-divider" />
          <button
            className={`tab ${view === "workflow" ? "current" : ""}`}
            onClick={() => setView("workflow")}
          >
            <Icon name="branch" size={16} /> Workflow
          </button>
          <button
            className={`tab ${view === "tasks" ? "current" : ""}`}
            onClick={() => {
              setView("tasks");
              choose("intake");
            }}
          >
            <Icon name="source" size={16} /> Tasks{" "}
            <span>{data?.report?.counts.tasks ?? "—"}</span>
          </button>
          <div className="toolbar-space" />
          <span className="flow-state">
            {data?.report?.flow.status ||
              data?.report?.flow.state ||
              "Local workspace"}
          </span>
          <button className="text-button" onClick={() => setHelp(true)}>
            <Icon name="book" size={16} /> Workflow guide
          </button>
        </div>
        {error && (
          <div role="alert" className="banner error">
            {error}
            <button onClick={() => void load()}>Retry connection</button>
          </div>
        )}
        {notice && (
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
        <main className="main-area">
          <section className="canvas-wrap" aria-label="Outreach workflow">
            <div className="canvas-heading">
              <div>
                <span className="live-dot" /> CAMPAIGN OVERVIEW
              </div>
              <span>
                {data?.report
                  ? `${data.report.counts.tasks} outreach tasks`
                  : "Your workflow starts here"}
              </span>
            </div>
            {view === "workflow" ? (
              <div className="canvas-scroll" ref={canvas}>
                <Workflow
                  data={data}
                  selected={selected}
                  onSelect={choose}
                  zoom={zoom}
                />
              </div>
            ) : (
              <div className="task-table">
                <div className="table-head">
                  <h2>Outreach tasks</h2>
                  <span>{tasks.length} results</span>
                </div>
                {tasks.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Supervisor</th>
                        <th>Student</th>
                        <th>Message state</th>
                        <th>Review</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tasks.map((t) => (
                        <tr key={t.task_id}>
                          <td>
                            <button onClick={() => void openTask(t)}>
                              {t.supervisor_name}
                            </button>
                            <small>{t.institution_name}</small>
                          </td>
                          <td>{t.student_name}</td>
                          <td>{human(t.message_status || "intake_only")}</td>
                          <td>
                            {t.exceptions.blocking
                              ? `${t.exceptions.blocking} blockers`
                              : "No task blockers"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="table-empty">
                    <Icon name="source" size={36} />
                    <h3>
                      {search ? "No matching tasks" : "No outreach tasks yet"}
                    </h3>
                    <p>
                      {search
                        ? "Try another student, supervisor, or institution."
                        : "Import a source bundle with the Core CLI to populate this campaign."}
                    </p>
                    <button onClick={() => setHelp(true)}>
                      View setup guide <Icon name="arrow" size={16} />
                    </button>
                  </div>
                )}
              </div>
            )}
            {view === "workflow" && (
              <>
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
                <div className="zoom-controls">
                  <button
                    aria-label="Zoom out"
                    onClick={() => setZoom((z) => Math.max(0.4, z - 0.1))}
                  >
                    −
                  </button>
                  <span>{Math.round(zoom * 100)}%</span>
                  <button
                    aria-label="Zoom in"
                    onClick={() => setZoom((z) => Math.min(1.4, z + 0.1))}
                  >
                    +
                  </button>
                  <button aria-label="Fit workflow" onClick={fit}>
                    <Icon name="fit" size={16} />
                  </button>
                </div>
              </>
            )}
          </section>
          <aside className="inspector">
            <div className="inspector-header">
              <span>{task ? "TASK INSPECTOR" : "WORKFLOW INSPECTOR"}</span>
              <span className="inspector-badge">LIVE</span>
            </div>
            {task ? (
              <>
                <button
                  className="back-button"
                  onClick={() => {
                    setTask(null);
                    detailRevision.current++;
                  }}
                >
                  ← Back to {stage.label.toLowerCase()}
                </button>
                <h2>{task.supervisor_name}</h2>
                <p className="muted">{task.institution_name}</p>
                <dl>
                  <dt>Student</dt>
                  <dd>{task.student_name}</dd>
                  <dt>Message state</dt>
                  <dd>{human(task.message_status || "intake_only")}</dd>
                </dl>
                {!detail ? (
                  <p className="muted">
                    {error
                      ? "Task details unavailable."
                      : "Loading task evidence…"}
                  </p>
                ) : (
                  <>
                    {detail.preparations
                      .filter((p) => p.status === "active")
                      .map((p) => (
                        <section className="message-detail" key={p.id}>
                          <div className="section-label">
                            PREPARATION{" "}
                            <span>{p.ready ? "Ready" : "Blocked"}</span>
                          </div>
                          <dl>
                            <dt>From</dt>
                            <dd>{p.sender}</dd>
                            <dt>To</dt>
                            <dd>{p.recipient}</dd>
                          </dl>
                          <h3>{p.subject || "Subject required"}</h3>
                          <p className="message-body">{p.body}</p>
                          {p.attachment_slots.map((a, i) => (
                            <p key={i} className="attachment">
                              {a.attachment?.name || `${a.label}: unresolved`}
                            </p>
                          ))}
                          {p.readiness_findings.map((f, i) => (
                            <p
                              className={f.blocking ? "finding" : "muted"}
                              key={i}
                            >
                              {f.detail}
                            </p>
                          ))}
                          <DraftEditor
                            preparation={p}
                            sources={detail.rewrite_sources}
                            onSaved={async () => {
                              await load();
                              await openTask(task);
                              setNotice(
                                "草稿已保存并重新校验。内容变更后请重新查重和确认。",
                              );
                            }}
                          />
                          <button
                            className="secondary full"
                            disabled={busy}
                            onClick={() => void check(p.id)}
                          >
                            <Icon name="shield" size={16} /> Check duplicates
                          </button>
                        </section>
                      ))}
                    <div className="section-label">草稿版本记录</div>
                    {detail.preparations.map((p) => (
                      <p className="source-item" key={p.id}>
                        {p.status === "active" ? "当前版本" : "历史版本"} ·{" "}
                        {p.subject || "未设置主题"} · {p.id.slice(0, 8)}
                      </p>
                    ))}
                    <div className="section-label">SOURCE MATERIALS</div>
                    {detail.sources.length ? (
                      detail.sources.map((s) => (
                        <p className="source-item" key={s.id}>
                          <Icon name="source" size={15} />
                          {s.name}
                        </p>
                      ))
                    ) : (
                      <p className="muted">No source materials associated.</p>
                    )}
                    {detail.duplicate_checks.slice(-1).map((c) => (
                      <section className="evidence" key={c.id}>
                        <h3>{human(c.finding)}</h3>
                        <p>{c.detail}</p>
                        {c.evidence_coverage.limitations?.map((l) => (
                          <p key={l}>{l}</p>
                        ))}
                      </section>
                    ))}
                    <div className="section-label">EXECUTION LEDGER</div>
                    {detail.execution_attempts.length ? (
                      detail.execution_attempts.map((a) => (
                        <p className="source-item" key={a.id}>
                          {human(a.state)} · {a.id.slice(0, 8)}
                        </p>
                      ))
                    ) : (
                      <p className="muted">No execution attempts recorded.</p>
                    )}
                  </>
                )}
              </>
            ) : (
              <>
                <div className={`inspector-icon ${stage.color}`}>
                  <Icon name={stage.icon} size={25} />
                </div>
                <h2>{stage.label}</h2>
                <p className="description">{stage.description}</p>
                <div className="stage-stat">
                  <strong>{count(stage.id)}</strong>
                  <span>
                    {stageMetric(stage.id, data).unit === "tasks"
                      ? "outreach tasks at this stage"
                      : stageMetric(stage.id, data).unit}
                  </span>
                </div>
                {(selected === "mailbox" || selected === "database") && data ? (
                  <MailboxPanel
                    key={data.report?.campaign.id || "workspace"}
                    data={data}
                    onRefresh={load}
                  />
                ) : (
                  <>
                    <div className="section-label">
                      {search ? "SEARCH RESULTS" : "OUTREACH TASKS"}
                      <span>{tasks.length}</span>
                    </div>
                    <div className="task-list">
                      {tasks.length ? (
                        tasks.map((t) => (
                          <button
                            key={t.task_id}
                            onClick={() => void openTask(t)}
                          >
                            <span className="task-avatar">
                              {t.supervisor_name.slice(0, 1)}
                            </span>
                            <span>
                              <strong>{t.supervisor_name}</strong>
                              <small>
                                {t.student_name} · {t.institution_name}
                              </small>
                            </span>
                            <Icon name="arrow" size={16} />
                          </button>
                        ))
                      ) : (
                        <div className="empty-stage">
                          <Icon name="source" size={26} />
                          <strong>
                            {!data
                              ? "Waiting for Core"
                              : search
                                ? "No matching tasks"
                                : "Nothing here yet"}
                          </strong>
                          <p>
                            {!data
                              ? "Connect to the local Core to inspect real campaign activity."
                              : data.report
                                ? "Tasks appear here when they match this stage."
                                : "Create a campaign, then import your source materials to get started."}
                          </p>
                          {!data?.campaigns.length && (
                            <button
                              className="text-button"
                              disabled={!data}
                              onClick={() => setNewCampaign(true)}
                            >
                              Create your first campaign{" "}
                              <Icon name="arrow" size={14} />
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </>
                )}
                <div className="inspector-note">
                  <Icon name="shield" size={18} />
                  <p>
                    Core is the source of truth.
                    <br />
                    Stages can overlap across actions. Select a task to inspect
                    its evidence.
                  </p>
                </div>
                <div className="section-label">EXPLORE STAGES</div>
                <div className="stage-list">
                  {stages
                    .filter((s) => s.id !== selected)
                    .map((s) => (
                      <button key={s.id} onClick={() => choose(s.id)}>
                        <span className={`mini-icon ${s.color}`}>
                          <Icon name={s.icon} size={16} />
                        </span>
                        {s.label}
                        <span>{count(s.id)}</span>
                      </button>
                    ))}
                </div>
              </>
            )}
          </aside>
        </main>
        <footer>
          <span>
            <i className="dot" />
            Local workspace · SmartMail Core
          </span>
          <span>
            {data?.report
              ? `Updated ${new Date(data.report.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
              : "No campaign activity loaded"}
            <span className="footer-separator">/</span>Mailbox execution via
            extension
          </span>
        </footer>
      </div>
      {(newCampaign || help) && (
        <div
          className="modal-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setNewCampaign(false);
              setHelp(false);
            }
          }}
        >
          <section
            ref={modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="dialog-title"
            className="modal"
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setNewCampaign(false);
                setHelp(false);
              }
            }}
          >
            <button
              className="modal-close icon-button"
              aria-label="Close dialog"
              onClick={() => {
                setNewCampaign(false);
                setHelp(false);
              }}
            >
              <Icon name="close" />
            </button>
            {newCampaign ? (
              <form onSubmit={create}>
                <div className="eyebrow">START SOMETHING MEANINGFUL</div>
                <h2 id="dialog-title">A new outreach campaign</h2>
                <p>
                  Group outreach tasks, duplicate checks, and follow-up rules in
                  one explicit scope.
                </p>
                <label className="field">
                  Campaign name
                  <input
                    autoFocus
                    required
                    maxLength={200}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Autumn research outreach"
                  />
                </label>
                {error && (
                  <p role="alert" className="finding">
                    {error}
                  </p>
                )}
                <button
                  className="primary full"
                  disabled={busy || !name.trim()}
                >
                  {busy ? "Creating…" : "Create campaign"}
                  <Icon name="arrow" size={16} />
                </button>
              </form>
            ) : (
              <>
                <div className="eyebrow">THE WORKFLOW, EXPLAINED</div>
                <h2 id="dialog-title">Grounded in your Core</h2>
                <p>
                  This canvas maps supported operations. Select a stage to see
                  matching tasks, then inspect message content, readiness
                  findings, and execution evidence.
                </p>
                <h3>Bring in source materials</h3>
                <p>
                  Use the existing CLI from the repository root with the same
                  store as the frontend:
                </p>
                <pre>
                  python -m smartmail student create "Student name" --mailbox
                  student@163.com{"\n"}python -m smartmail import bundle.zip
                  --campaign {data?.report?.campaign.id || "CAMPAIGN_ID"}{" "}
                  --student STUDENT_ID{"\n"}python -m smartmail prepare --import
                  IMPORT_ID
                </pre>
                <p>
                  Refresh this page after importing. Use <code>--home</code>{" "}
                  before the CLI command when your store is in another
                  directory.
                </p>
                <h3>Prepare → confirm → execute</h3>
                <p>
                  Readiness and confirmation are separate. Sending, scheduling,
                  reconciliation, and follow-up preparation use the existing
                  Core CLI and dedicated mailbox extension. This first page
                  supports read-only mailbox intake, persisted observation
                  inspection, duplicate checks, local subject/recipient
                  correction and source-based Rewrite.
                </p>
                <p className="muted">
                  Connections show supported paths, not a timeline or a promise
                  of automatic execution. Unknown outcomes require evidence
                  before retrying.
                </p>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

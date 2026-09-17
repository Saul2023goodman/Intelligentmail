import SearchField from "../../shared/SearchField";
import { useCallback, useEffect, useRef, useState } from "react";
import { core, human } from "../../core";
import type { Detail, Task, Workspace } from "../../core";
import {
  stages,
  tasksFor,
  stageMetric,
  fitViewport,
  clampViewport,
  zoomAt,
  MIN_ZOOM,
  MAX_ZOOM,
  type Viewport,
} from "./workflow-model";
import Workflow from "./Workflow";
import Icon from "../../shared/Icon";
import MailboxPanel from "./MailboxPanel";
import DraftEditor from "./DraftEditor";
import { AppShell, Topbar, NavigationItem } from "../../app/shell";
import type { Route } from "../../app/routes";
import "./Workspace.css";

const ZOOM_STEP = 1.2;
const DRAG_THRESHOLD = 4;
const STUDENT_KEY = "smartmail.selectedStudent";

type DragState = {
  pointerId: number;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
  moved: boolean;
  pointerType: string;
};

type PinchState = {
  startDistance: number;
  worldX: number;
  worldY: number;
  view: Viewport;
  moved: boolean;
};

export default function WorkspacePage({ route }: { route: Route }) {
  const [data, setData] = useState<Workspace | null>(null);
  const [studentId, setStudentId] = useState(
    () => localStorage.getItem(STUDENT_KEY) ?? "",
  );
  const [selected, setSelected] = useState(
    route === "tasks" ? "intake" : "mailbox",
  );
  const [search, setSearch] = useState("");
  const [viewport, setViewport] = useState<Viewport>(() =>
    fitViewport(1024, 640),
  );
  const [panning, setPanning] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [newStudent, setNewStudent] = useState(false);
  const [name, setName] = useState("");
  const [mailboxAddress, setMailboxAddress] = useState("");
  const [task, setTask] = useState<Task | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const view = route;
  const canvas = useRef<HTMLDivElement>(null);
  const modal = useRef<HTMLElement>(null);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const drag = useRef<DragState | null>(null);
  const pinch = useRef<PinchState | null>(null);
  const revision = useRef(0);
  const detailRevision = useRef(0);
  const studentMailbox =
    data?.mailboxes.find((mailbox) => mailbox.student_id === studentId) ??
    null;
  const campaignFor = useCallback(
    (id: string, workspace: Workspace | null) => {
      const mailbox = workspace?.mailboxes.find(
        (item) => item.student_id === id,
      );
      return mailbox
        ? (workspace?.campaigns.find((c) => c.name === mailbox.student_name)
            ?.id ??
          "")
        : "";
    },
    [],
  );
  const load = useCallback(async (campaignId = "") => {
    const request = ++revision.current;
    setBusy(true);
    setError("");
    try {
      const value = await core(
        "workspace",
        campaignId ? { campaign_id: campaignId } : {},
      );
      if (request === revision.current) setData(value);
    } catch (e) {
      if (request === revision.current) setError((e as Error).message);
    } finally {
      if (request === revision.current) setBusy(false);
    }
  }, []);
  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- Synchronize with the external Core store.
    void load();
  }, [load]);
  useEffect(() => {
    if (!data) return;
    if (!studentId) {
      const first = data.mailboxes[0]?.student_id ?? "";
      if (first) {
        // oxlint-disable-next-line react/set-state-in-effect -- Pick the initial Student once the Core's mailbox list arrives.
        setStudentId(first);
        localStorage.setItem(STUDENT_KEY, first);
      }
      return;
    }
    // The selected Student may be absent only while its scope is still loading.
    if (!data.mailboxes.some((mailbox) => mailbox.student_id === studentId))
      return;
    const campaignId = campaignFor(studentId, data);
    if (campaignId && campaignId !== data.report?.campaign.id) {
      void load(campaignId);
    }
  }, [data, studentId, campaignFor, load]);
  const switchStudent = (id: string) => {
    setStudentId(id);
    localStorage.setItem(STUDENT_KEY, id);
    setTask(null);
    setDetail(null);
    detailRevision.current++;
  };
  const reload = () => load(campaignFor(studentId, data));
  useEffect(() => {
    if (!newStudent) return;
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
  }, [newStudent]);
  const hasMailboxes = !!data?.mailboxes.length;
  const fit = useCallback(() => {
    const el = canvas.current;
    if (!el) return;
    setViewport(fitViewport(el.clientWidth, el.clientHeight));
  }, []);
  const zoomBy = useCallback((factor: number) => {
    const el = canvas.current;
    if (!el) return;
    setViewport((current) =>
      zoomAt(
        current,
        el.clientWidth / 2,
        el.clientHeight / 2,
        current.zoom * factor,
        el.clientWidth,
        el.clientHeight,
      ),
    );
  }, []);
  useEffect(() => {
    if (view !== "workflow" || !hasMailboxes) return;
    const el = canvas.current;
    if (!el) return;
    setViewport(fitViewport(el.clientWidth, el.clientHeight));
    const observer = new ResizeObserver(() => {
      setViewport((current) =>
        clampViewport(current, el.clientWidth, el.clientHeight),
      );
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [fit, view, hasMailboxes]);
  useEffect(() => {
    const el = canvas.current;
    if (!el || view !== "workflow" || !hasMailboxes) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = el.getBoundingClientRect();
      const unit =
        event.deltaMode === 1
          ? 16
          : event.deltaMode === 2
            ? rect.height
            : 1;
      const factor = Math.exp(-event.deltaY * unit * 0.0015);
      setViewport((current) =>
        zoomAt(
          current,
          event.clientX - rect.left,
          event.clientY - rect.top,
          current.zoom * factor,
          rect.width,
          rect.height,
        ),
      );
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [view, hasMailboxes]);
  useEffect(() => {
    if (view !== "workflow") return;
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) ||
          target.isContentEditable)
      ) {
        return;
      }
      if (event.key === "+" || event.key === "=") {
        event.preventDefault();
        zoomBy(ZOOM_STEP);
      } else if (event.key === "-" || event.key === "_") {
        event.preventDefault();
        zoomBy(1 / ZOOM_STEP);
      } else if (event.key === "0") {
        event.preventDefault();
        fit();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [view, zoomBy, fit]);
  const swallowNextClick = () => {
    const suppress = (event: Event) => {
      event.preventDefault();
      event.stopPropagation();
    };
    document.addEventListener("click", suppress, { capture: true, once: true });
    window.setTimeout(
      () => document.removeEventListener("click", suppress, { capture: true }),
      300,
    );
  };
  const isInteractiveTarget = (target: EventTarget | null) =>
    target instanceof HTMLElement &&
    !!target.closest("button,a,input,select,textarea");
  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    const el = canvas.current;
    if (!el) return;
    const canPan =
      event.pointerType === "mouse"
        ? event.button === 1 ||
          (event.button === 0 && !isInteractiveTarget(event.target))
        : event.button === 0;
    if (!canPan) return;
    if (event.pointerType === "mouse" && event.button === 1)
      event.preventDefault();
    try {
      el.setPointerCapture(event.pointerId);
    } catch {
      // The pointer may already be captured or released by the browser.
    }
    pointers.current.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY,
    });
    if (pointers.current.size === 1) {
      drag.current = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        originX: viewport.x,
        originY: viewport.y,
        moved: false,
        pointerType: event.pointerType,
      };
      pinch.current = null;
    } else if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      const distance = Math.max(1, Math.hypot(a.x - b.x, a.y - b.y));
      const midX = (a.x + b.x) / 2;
      const midY = (a.y + b.y) / 2;
      const rect = el.getBoundingClientRect();
      drag.current = null;
      pinch.current = {
        startDistance: distance,
        worldX: (midX - rect.left - viewport.x) / viewport.zoom,
        worldY: (midY - rect.top - viewport.y) / viewport.zoom,
        view: viewport,
        moved: false,
      };
      setPanning(true);
    }
  };
  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const el = canvas.current;
    const point = pointers.current.get(event.pointerId);
    if (!el || !point) return;
    point.x = event.clientX;
    point.y = event.clientY;
    const activePinch = pinch.current;
    if (activePinch && pointers.current.size >= 2) {
      const [a, b] = [...pointers.current.values()];
      const distance = Math.max(1, Math.hypot(a.x - b.x, a.y - b.y));
      const rect = el.getBoundingClientRect();
      const midX = (a.x + b.x) / 2 - rect.left;
      const midY = (a.y + b.y) / 2 - rect.top;
      const zoom =
        activePinch.view.zoom * (distance / activePinch.startDistance);
      const nextZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
      if (Math.abs(distance / activePinch.startDistance - 1) > 0.01)
        activePinch.moved = true;
      setViewport(
        clampViewport(
          {
            zoom: nextZoom,
            x: midX - activePinch.worldX * nextZoom,
            y: midY - activePinch.worldY * nextZoom,
          },
          rect.width,
          rect.height,
        ),
      );
      return;
    }
    const activeDrag = drag.current;
    if (!activeDrag || activeDrag.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - activeDrag.startX;
    const deltaY = event.clientY - activeDrag.startY;
    if (!activeDrag.moved && Math.hypot(deltaX, deltaY) > DRAG_THRESHOLD) {
      activeDrag.moved = true;
      setPanning(true);
    }
    if (activeDrag.moved) {
      setViewport((current) =>
        clampViewport(
          {
            ...current,
            x: activeDrag.originX + deltaX,
            y: activeDrag.originY + deltaY,
          },
          el.clientWidth,
          el.clientHeight,
        ),
      );
    }
  };
  const endPointer = (event: React.PointerEvent<HTMLDivElement>) => {
    const el = canvas.current;
    const activeDrag = drag.current;
    const activePinch = pinch.current;
    const moved =
      (activeDrag?.pointerId === event.pointerId && activeDrag.moved) ||
      (pointers.current.size >= 2 && !!activePinch?.moved);
    const endedOnInteractive = isInteractiveTarget(event.nativeEvent.target);
    if (el) {
      try {
        el.releasePointerCapture(event.pointerId);
      } catch {
        // Pointer capture may already be released by the browser.
      }
    }
    if (
      moved &&
      (event.pointerType !== "mouse" || activePinch?.moved) &&
      (endedOnInteractive || activePinch?.moved)
    ) {
      swallowNextClick();
    }
    pointers.current.delete(event.pointerId);
    if (pointers.current.size < 2) pinch.current = null;
    if (activeDrag?.pointerId === event.pointerId) drag.current = null;
    if (pointers.current.size === 0) setPanning(false);
  };
  const handleDoubleClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (isInteractiveTarget(event.target)) return;
    fit();
  };
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
      const result = await core("task", { task_id: value.task_id });
      if (request === detailRevision.current) setDetail(result);
    } catch (e) {
      if (request === detailRevision.current) setError((e as Error).message);
    }
  };
  const createStudent = async (event: React.SubmitEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const value = await core("create_student", {
        name: name.trim(),
        mailbox: mailboxAddress.trim(),
      });
      setNewStudent(false);
      setName("");
      setMailboxAddress("");
      setStudentId(value.id);
      localStorage.setItem(STUDENT_KEY, value.id);
      await load(value.campaign_id);
      setNotice(
        `已添加学生 ${value.name}（${value.mailbox}）。通过 Core CLI 导入来源材料后，任务将出现在工作流中。`,
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
      const result = await core("check_duplicate", { preparation_id: id });
      reload();
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
  const closeDialog = () => {
    setNewStudent(false);
    setError("");
  };
  // Remain mounted while Intake is active, preserving scope and inspector state.
  if (view === "sources" || view === "review" || view === "execution") return null;
  const banners = (floating: boolean) => (
    <>
      {error && (
        <div
          role="alert"
          className={`banner error${floating ? " banner-floating" : ""}`}
        >
          {error}
          <button onClick={reload}>Retry connection</button>
        </div>
      )}
      {notice && !error && (
        <div
          role="status"
          className={`banner${floating ? " banner-floating" : ""}`}
        >
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
  const switcher = (
    <div className="student-switch" role="group" aria-label="Student scope">
      <div className="student-switch-main">
        <span className="student-switch-icon">
          <Icon name="mail" size={15} />
        </span>
        {hasMailboxes ? (
          <select
            aria-label="Switch student"
            value={studentId}
            disabled={busy}
            onChange={(e) => switchStudent(e.target.value)}
          >
            {data?.mailboxes.map((mailbox) => (
              <option key={mailbox.id} value={mailbox.student_id}>
                {mailbox.student_name} · {mailbox.address}
              </option>
            ))}
          </select>
        ) : (
          <span className="student-switch-empty">未设定学生</span>
        )}
        <button
          className="student-switch-add"
          title="新增学生"
          aria-label="新增学生"
          onClick={() => {
            setError("");
            setNewStudent(true);
          }}
        >
          <Icon name="plus" size={15} />
        </button>
      </div>
      <span className="student-switch-meta">
        {studentMailbox
          ? `${studentMailbox.observation_count} 次邮箱读取 · ${data?.report?.counts.tasks ?? 0} outreach tasks`
          : "添加学生以开始工作流"}
      </span>
    </div>
  );
  return (
    <AppShell
      className="workspace-page"
      navigation={
        <>
          <NavigationItem route="workflow" active={view === "workflow"} />
          <NavigationItem
            route="tasks"
            active={view === "tasks"}
            onNavigate={() => choose("intake")}
          />
          <NavigationItem route="sources" />
          <NavigationItem route="review" />
          <NavigationItem route="execution" />
          <div className="rail-spacer" />
          <button
            onClick={() => {
              setError("");
              setNewStudent(true);
            }}
            className="rail-add"
            title="新增学生"
            aria-label="新增学生"
          >
            <Icon name="plus" />
          </button>
        </>
      }
    >
      <div className="workspace">
        <Topbar breadcrumb="Outreach" homeHref="/">
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
            onClick={reload}
            disabled={busy}
          >
            <Icon name="refresh" size={18} />
          </button>
        </Topbar>
        {view === "workflow" ? (
          <section
            className="canvas-wrap canvas-full"
            aria-label="Outreach workflow"
          >
            {switcher}
            {banners(true)}
            {hasMailboxes ? (
              <div
                className={`canvas-scroll${panning ? " panning" : ""}`}
                ref={canvas}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={endPointer}
                onPointerCancel={endPointer}
                onMouseDown={(event) => {
                  if (event.button === 1) event.preventDefault();
                }}
                onDoubleClick={handleDoubleClick}
              >
                <Workflow
                  data={data}
                  selected={selected}
                  onSelect={setSelected}
                  view={viewport}
                />
              </div>
            ) : (
              <div className="canvas-empty">
                <span className="canvas-empty-icon">
                  <Icon name="mail" size={28} />
                </span>
                <h2>设定第一位学生</h2>
                <p>
                  学生即本页的工作流空间（Campaign）。添加学生姓名与其 163
                  邮箱后，即可读取外部邮箱并导入来源材料。
                </p>
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() => {
                    setError("");
                    setNewStudent(true);
                  }}
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
            <div className="zoom-controls">
              <button
                aria-label="Zoom out (−)"
                title="Zoom out (−)"
                disabled={viewport.zoom <= MIN_ZOOM + 0.001}
                onClick={() => zoomBy(1 / ZOOM_STEP)}
              >
                −
              </button>
              <span title="Reset view (0)">
                {Math.round(viewport.zoom * 100)}%
              </span>
              <button
                aria-label="Zoom in (+)"
                title="Zoom in (+)"
                disabled={viewport.zoom >= MAX_ZOOM - 0.001}
                onClick={() => zoomBy(ZOOM_STEP)}
              >
                +
              </button>
              <button
                aria-label="Fit workflow (0)"
                title="Fit workflow (0)"
                onClick={fit}
              >
                <Icon name="fit" size={16} />
              </button>
            </div>
          </section>
        ) : (
          <>
            <div className="scope-strip">
              {switcher}
              <div className="scope-strip-space" />
              <SearchField
                label="Search outreach tasks"
                value={search}
                onChange={setSearch}
                placeholder="Find a student or supervisor…"
              >
                <kbd>⌕</kbd>
              </SearchField>
            </div>
            {banners(false)}
            <main className="main-area">
              <div className="task-table task-table-full">
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
                          <td>
                            {human(t.message_status || "intake_only")}
                          </td>
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
                        : "Import a source bundle with the Core CLI to populate this student's workflow."}
                    </p>
                  </div>
                )}
              </div>
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
                      <dd>
                        {human(task.message_status || "intake_only")}
                      </dd>
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
                                  {a.attachment?.name ||
                                    `${a.label}: unresolved`}
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
                                  reload();
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
                          <p className="muted">
                            No source materials associated.
                          </p>
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
                          <p className="muted">
                            No execution attempts recorded.
                          </p>
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
                    {(selected === "mailbox" || selected === "database") &&
                    data ? (
                      <MailboxPanel
                        key={data.report?.campaign.id || "workspace"}
                        data={data}
                        onRefresh={reload}
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
                                    : "Create a student, then import your source materials to get started."}
                              </p>
                              {!hasMailboxes && (
                                <button
                                  className="text-button"
                                  disabled={!data}
                                  onClick={() => setNewStudent(true)}
                                >
                                  设定第一位学生{" "}
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
                        Stages can overlap across actions. Select a task to
                        inspect its evidence.
                      </p>
                    </div>
                    <div className="section-label">EXPLORE STAGES</div>
                    <div className="stage-list">
                      {stages
                        .filter((s) => s.id !== selected)
                        .map((s) => (
                          <button
                            key={s.id}
                            onClick={() => choose(s.id)}
                          >
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
          </>
        )}
        {newStudent && (
          <div
            className="modal-backdrop"
            onClick={(e) => {
              if (e.target === e.currentTarget) closeDialog();
            }}
          >
            <section
              ref={modal}
              role="dialog"
              aria-modal="true"
              aria-labelledby="dialog-title"
              className="modal"
              onKeyDown={(e) => {
                if (e.key === "Escape") closeDialog();
              }}
            >
              <button
                className="modal-close icon-button"
                aria-label="Close dialog"
                onClick={closeDialog}
              >
                <Icon name="close" />
              </button>
              <form onSubmit={createStudent}>
                <div className="eyebrow">STUDENT WORKSPACE</div>
                <h2 id="dialog-title">设定学生（Campaign）</h2>
                <p>
                  一位学生对应一个工作流空间，绑定其 163
                  发件邮箱。读取、比对查重与跟进都在该学生范围内进行。
                </p>
                <label className="field">
                  学生姓名
                  <input
                    autoFocus
                    required
                    maxLength={200}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="例如：Zhang Wei"
                  />
                </label>
                <label className="field">
                  163 邮箱地址
                  <input
                    required
                    type="email"
                    maxLength={200}
                    value={mailboxAddress}
                    onChange={(e) => setMailboxAddress(e.target.value)}
                    placeholder="student@163.com"
                  />
                </label>
                {error && (
                  <p role="alert" className="finding">
                    {error}
                  </p>
                )}
                <button
                  className="primary full"
                  disabled={busy || !name.trim() || !mailboxAddress.trim()}
                >
                  {busy ? "添加中…" : "添加学生"}
                  <Icon name="arrow" size={16} />
                </button>
              </form>
            </section>
          </div>
        )}
      </div>
    </AppShell>
  );
}

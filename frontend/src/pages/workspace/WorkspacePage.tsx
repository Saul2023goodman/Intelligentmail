import { useCallback, useEffect, useRef, useState } from "react";
import { core } from "../../core";
import type { Workspace } from "../../core";
import { fitScale } from "./workflow-model";
import Workflow from "./Workflow";
import Icon from "../../shared/Icon";
import { AppShell, Topbar, NavigationItem } from "../../app/shell";
import type { Route } from "../../app/routes";
import "./Workspace.css";

const STUDENT_KEY = "smartmail.selectedStudent";

export default function WorkspacePage({ route }: { route: Route }) {
  const [data, setData] = useState<Workspace | null>(null);
  const [studentId, setStudentId] = useState(
    () => localStorage.getItem(STUDENT_KEY) ?? "",
  );
  const [selected, setSelected] = useState("mailbox");
  const [scale, setScale] = useState(1);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [newStudent, setNewStudent] = useState(false);
  const [name, setName] = useState("");
  const [mailboxAddress, setMailboxAddress] = useState("");
  const view = route;
  const frame = useRef<HTMLDivElement>(null);
  const modal = useRef<HTMLElement>(null);
  const activeChip = useRef<HTMLButtonElement>(null);
  const revision = useRef(0);
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
  };
  const reload = () => load(campaignFor(studentId, data));
  const openDialog = () => {
    setError("");
    setNewStudent(true);
  };
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
  useEffect(() => {
    const el = frame.current;
    if (!el || !hasMailboxes) return;
    const update = () => setScale(fitScale(el.clientWidth, el.clientHeight));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMailboxes]);
  useEffect(() => {
    activeChip.current?.scrollIntoView({ inline: "center", block: "nearest" });
  }, [studentId, hasMailboxes]);
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
  const closeDialog = () => {
    setNewStudent(false);
    setError("");
  };
  // Remain mounted while other pages are active, preserving scope state.
  if (view !== "workflow") return null;
  const banners = (
    <>
      {error && (
        <div role="alert" className="banner error">
          {error}
          <button onClick={reload}>Retry connection</button>
        </div>
      )}
      {notice && !error && (
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
      navigation={
        <>
          <NavigationItem route="workflow" active />
          <NavigationItem route="sources" />
          <NavigationItem route="review" />
          <NavigationItem route="execution" />
          <NavigationItem route="mailbox" />
          <NavigationItem route="records" />
          <div className="rail-spacer" />
        </>
      }
    >
      <div className="workspace">
        <Topbar breadcrumb="Workflow" homeHref="/">
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
        <section className="workflow-stage" aria-label="Outreach workflow">
          <div className="student-bar">
            <div className="student-chips" role="group" aria-label="Student switcher">
              {data?.mailboxes.map((mailbox) => {
                const active = mailbox.student_id === studentId;
                return (
                  <button
                    key={mailbox.id}
                    ref={active ? activeChip : undefined}
                    type="button"
                    className={`student-chip${active ? " active" : ""}`}
                    aria-pressed={active}
                    title={`${mailbox.student_name} · ${mailbox.address}`}
                    onClick={() => switchStudent(mailbox.student_id)}
                  >
                    <span className="student-avatar" aria-hidden="true">
                      {mailbox.student_name.slice(0, 1)}
                    </span>
                    <span className="student-name">{mailbox.student_name}</span>
                  </button>
                );
              })}
              <button
                type="button"
                className="student-chip student-chip-add"
                title="新增学生"
                aria-label="新增学生"
                onClick={openDialog}
              >
                <Icon name="plus" size={14} />
                <span className="student-name">新增学生</span>
              </button>
            </div>
            <p className="student-meta">
              {studentMailbox
                ? `${studentMailbox.address} · ${studentMailbox.observation_count} 次邮箱读取 · ${data?.report?.counts.tasks ?? 0} outreach tasks`
                : "添加学生以开始工作流"}
            </p>
          </div>
          {banners}
          <div className="workflow-frame" ref={frame}>
            {hasMailboxes ? (
              <Workflow
                data={data}
                selected={selected}
                onSelect={setSelected}
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
                  邮箱后，即可读取外部邮箱并导入来源材料。
                </p>
                <button className="primary" disabled={busy} onClick={openDialog}>
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
        </section>
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

import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import SearchField from "../../shared/SearchField";
import Icon from "../../shared/Icon";
import { AppShell, Topbar, NavigationItem } from "../../app/shell";
import { core, human, importSources, type IntakeSource, type IntakeTask, type IntakeWorkspace } from "../../core";
import "./SourceMapping.css";

type TaskFilter = "all" | "active" | "incomplete";
type SourceView = IntakeSource & { category: string; importId: string; finding?: string };
const categories = [
  { id: "master", title: "Supervisor records", detail: "Authoritative task identity rows", icon: "source" as const, color: "green" },
  { id: "drafts", title: "Draft messages", detail: "Documents associated to Preparations", icon: "file" as const, color: "blue" },
  { id: "profile", title: "Student profile", detail: "Explicit Student scope", icon: "user" as const, color: "purple" },
  { id: "mailbox", title: "Mailbox identity", detail: "Registered sending mailbox", icon: "mail" as const, color: "blue" },
  { id: "records", title: "Prior outreach records", detail: "Retained evidence outside preparation", icon: "database" as const, color: "amber" },
  { id: "attachments", title: "Attachments", detail: "Preserved candidate source materials", icon: "clip" as const, color: "purple" },
] as const;

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).map((part) => part[0]).slice(0, 2).join("").toUpperCase();
}

export default function IntakePage() {
  const [data, setData] = useState<IntakeWorkspace | null>(null);
  const [campaign, setCampaign] = useState("");
  const [student, setStudent] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<TaskFilter>("all");
  const [selectedSource, setSelectedSource] = useState<SourceView | null>(null);
  const [selectedTask, setSelectedTask] = useState<IntakeTask | null>(null);
  const [inspection, setInspection] = useState<{ title: string; detail: string; evidence: unknown } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const inspector = useRef<HTMLDialogElement>(null);
  const taskDialog = useRef<HTMLDialogElement>(null);
  const dragDepth = useRef(0);

  const load = useCallback(async (campaignId?: string, studentId?: string) => {
    setLoading(true); setError("");
    try {
      const next = await core("intake_workspace", {
        ...(campaignId ? { campaign_id: campaignId } : {}),
        ...(studentId ? { student_id: studentId } : {}),
      });
      setData(next);
      setCampaign(next.campaign?.id ?? "");
      setStudent(next.student?.id ?? "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load intake workspace");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => {
    // Initial synchronization with the long-lived local Core worker.
    // oxlint-disable-next-line react/set-state-in-effect
    void load();
  }, [load]);
  useEffect(() => { if (inspection) inspector.current?.showModal(); }, [inspection]);
  useEffect(() => { if (selectedTask) taskDialog.current?.showModal(); }, [selectedTask]);

  const sources = useMemo<SourceView[]>(() => (data?.imports ?? []).flatMap((imported) =>
    imported.sources.map((source) => ({
      ...source,
      importId: imported.id,
      category: data?.source_categories[source.id] ?? "unresolved",
      finding: imported.findings.find((finding) => finding.source.id === source.id)?.detail,
    }))), [data]);
  const unresolved = sources.filter((source) => source.category === "unresolved"
    && `${source.name} ${source.finding ?? ""}`.toLowerCase().includes(query.toLowerCase()));
  const tasks = (data?.tasks ?? []).filter((item) => {
    const active = Boolean(item.task.supervisor.addresses.length);
    return (filter === "all" || (filter === "active" ? active : !active))
      && `${item.task.supervisor.name} ${item.task.institution.name} ${item.task.supervisor.addresses.join(" ")}`.toLowerCase().includes(query.toLowerCase());
  });
  const currentStudent = data?.students.find((item) => item.id === student) ?? null;
  const activeCount = data?.tasks.filter((item) => item.task.supervisor.addresses.length).length ?? 0;

  async function ingest(files: File[]) {
    if (!files.length || !campaign || !student) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await importSources(campaign, student, files);
      setData(result.workspace);
      setSelectedSource(null);
      const summary = result.import.summary;
      setNotice(`Imported ${summary.rows} supervisor row${summary.rows === 1 ? "" : "s"}; ${result.preparation.preparation_ids.length} local Preparation${result.preparation.preparation_ids.length === 1 ? "" : "s"} available for review.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Core rejected the selected source set");
    } finally { setBusy(false); }
  }
  const hasFiles = (event: DragEvent) => Array.from(event.dataTransfer?.types ?? []).includes("Files");
  const onDragEnter = (event: DragEvent) => { if (hasFiles(event)) { dragDepth.current += 1; setDragging(true); } };
  const onDragOver = (event: DragEvent) => { if (hasFiles(event)) { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; } };
  const onDragLeave = (event: DragEvent) => { if (hasFiles(event)) { dragDepth.current = Math.max(0, dragDepth.current - 1); if (!dragDepth.current) setDragging(false); } };
  const onDrop = (event: DragEvent) => { if (hasFiles(event)) { event.preventDefault(); dragDepth.current = 0; setDragging(false); void ingest(Array.from(event.dataTransfer.files)); } };

  function inspectSource(source: SourceView) {
    setInspection({ title: source.name, detail: `${Math.max(1, Math.round(source.size / 1024))} KB · ${human(source.category)}`, evidence: { source_id: source.id, sha256: source.sha256, import_id: source.importId, finding: source.finding || null } });
  }

  return <AppShell className="sm-app" navigation={<>
    <NavigationItem route="workflow" label="Outreach workflow" /><NavigationItem route="sources" active />
    <NavigationItem route="review" /><NavigationItem route="execution" /><NavigationItem route="mailbox" /><NavigationItem route="records" />
    <div className="sm-rail-line" /><button aria-label="Intake workspace guide" title="Intake workspace guide" onClick={() => setInspection({ title: "Supported source intake", detail: "Import one .xlsx master list or a .zip bundle. Core deterministically associates supported draft documents and retains every source byte.", evidence: { authority: "Core validates patterns, creates Outreach Tasks, and prepares local messages", external_actions: "none" } })}><Icon name="book" /></button>
    <div className="rail-spacer" /><button className="rail-add" aria-label="Add source files" onClick={() => fileInput.current?.click()}><Icon name="plus" /></button>
  </>}>
    <div className="workspace" onDragEnter={onDragEnter} onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}>
      <Topbar className="sm-topbar" breadcrumb="Source mapping" homeHref="#workflow">
        <div className="sm-student-switch" role="group" aria-label="Switch student">{data?.students.map((item) => <button key={item.id} className={item.id === student ? "is-active" : ""} aria-pressed={item.id === student} title={`${item.name} · ${item.mailbox}`} onClick={() => { setStudent(item.id); setSelectedTask(null); void load(campaign, item.id); }}><span className="sm-student-avatar blue">{initials(item.name)}</span><strong>{item.name}</strong></button>)}</div>
        <span className="sm-divider" />
        <label className="sm-campaign"><Icon name="folder" size={15} /><select aria-label="Campaign" value={campaign} disabled={busy} onChange={(event) => { setCampaign(event.target.value); void load(event.target.value, student); }}>{data?.campaigns.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><span className="sm-demo-label">CORE</span></label>
        <SearchField label="Search source findings and tasks" value={query} onChange={setQuery} placeholder="Search source findings or resolved tasks…" iconSize={16} />
        <button className="sm-add-top" disabled={busy || !campaign || !student} onClick={() => fileInput.current?.click()}><Icon name="plus" size={14} />{busy ? "Importing…" : "Add source set"}</button><div className="sm-user">OP</div>
      </Topbar>
      {(notice || error) && <div className="sm-notice" role={error ? "alert" : "status"}><Icon name={error ? "warning" : "check"} size={16} />{error || notice}<button aria-label="Dismiss notification" onClick={() => { setNotice(""); setError(""); }}><Icon name="close" size={15} /></button></div>}
      <main className="sm-board">
        <section className="sm-sources"><div className="sm-column-heading"><Icon name="folder" size={16} /><h2>Unresolved raw sources</h2><span>{String(unresolved.length).padStart(2, "0")}</span></div><div className="sm-source-list">
          {unresolved.map((source) => <button key={source.id} className={`sm-source-card ${selectedSource?.id === source.id ? "is-selected" : ""}`} aria-pressed={selectedSource?.id === source.id} onClick={() => setSelectedSource(selectedSource?.id === source.id ? null : source)} onDoubleClick={() => inspectSource(source)}><span className="sm-file-icon slate"><Icon name="file" size={20} /></span><span className="sm-source-copy"><strong>{source.name}</strong><small>{Math.max(1, Math.round(source.size / 1024))} KB</small><span className="sm-source-meta-line"><em>{source.finding || "Core could not associate this source"}</em></span></span><Icon name="chevron" size={13} /></button>)}
          {!loading && !unresolved.length && <p className="sm-empty">{query ? "No matching unresolved sources." : "No unresolved Source Materials in this scope."}</p>}
          <button className="sm-add-source" disabled={busy || !campaign || !student} onClick={() => fileInput.current?.click()} title="Import a supported .xlsx or .zip source set"><Icon name="plus" size={17} /> Drag &amp; drop a supported source set<span>Browse files</span></button>
          {selectedSource && <div className="sm-selection"><span>Inspecting <strong>{selectedSource.name}</strong></span><button onClick={() => inspectSource(selectedSource)}>Inspect evidence <Icon name="arrow" size={13} /></button><button onClick={() => setSelectedSource(null)}>Clear selection</button></div>}
        </div></section>

        <section className="sm-categories"><div className="sm-column-heading"><Icon name="branch" size={16} /><h2>Stable categories</h2><span>{categories.length} fixed</span></div><div className="sm-category-list">{categories.map((category) => {
          const members = category.id === "profile" || category.id === "mailbox" ? [] : sources.filter((source) => source.category === category.id);
          const count = category.id === "profile" || category.id === "mailbox" ? Number(Boolean(currentStudent)) : members.length;
          return <article className="sm-category-card" data-category={category.id} key={category.id}><button className="sm-category-main" title={category.detail} onClick={() => setInspection({ title: category.title, detail: category.detail, evidence: category.id === "profile" ? currentStudent : category.id === "mailbox" ? { mailbox: currentStudent?.mailbox } : members })}><span className={`sm-rule-icon ${category.color}`}><Icon name={category.icon} size={17} /></span><span className="sm-category-copy"><strong>{category.title}</strong><small>{category.id === "profile" ? currentStudent?.name || "No Student selected" : category.id === "mailbox" ? currentStudent?.mailbox || "No Mailbox registered" : `${members.length} retained source${members.length === 1 ? "" : "s"}`}</small></span><span className="sm-category-count">{count}</span></button><div className="sm-classified-chips">{members.slice(0, 3).map((source) => <button className="sm-file-chip" key={source.id} onClick={() => inspectSource(source)}><Icon name="file" size={11} /><span title={source.name}>{source.name}</span></button>)}{!members.length && category.id !== "profile" && category.id !== "mailbox" && <span className="sm-file-chip is-empty">Nothing retained</span>}{members.length > 3 && <span className="sm-file-chip">+{members.length - 3} more</span>}</div></article>;
        })}</div></section>

        <section className="sm-output"><div className="sm-column-heading"><Icon name="source" size={16} /><h2>Resolved tasks</h2><span>{tasks.length}</span><label className="sm-task-filter"><select aria-label="Filter resolved tasks" value={filter} onChange={(event) => setFilter(event.target.value as TaskFilter)}><option value="all">All</option><option value="active">Active</option><option value="incomplete">Missing email</option></select></label></div><div className="sm-task-list">
          {currentStudent && <div className="sm-task-student"><span className="sm-student-avatar blue">{initials(currentStudent.name)}</span><strong>{currentStudent.name}</strong><small>{data?.campaign?.name}</small><span className="sm-task-student-mail"><Icon name="mail" size={12} />{currentStudent.mailbox}</span></div>}
          {tasks.map((item) => { const active = Boolean(item.task.supervisor.addresses.length); const preparation = item.preparations.find((value) => value.status !== "superseded"); const attachments = preparation?.attachment_slots.filter((slot) => slot.attachment).length ?? 0; return <button key={item.task.id} className={`sm-task-row ${active ? "" : "is-incomplete"}`} onClick={() => setSelectedTask(item)}><span className="sm-task-row-icon"><Icon name={preparation ? "file" : "user"} size={15} /></span><span className="sm-task-row-copy"><strong>{item.task.supervisor.name}</strong><small>{item.task.institution.name} · {item.task.supervisor.addresses.join(", ") || "no email identified"}</small></span><span className={`sm-task-badge ${preparation ? "" : "is-off"}`}><Icon name="file" size={12} />{preparation ? "Prepared" : "No draft"}</span><span className={`sm-task-badge ${attachments ? "" : "is-off"}`}><Icon name="clip" size={12} />{attachments}</span><span className={`sm-task-pill ${active ? "active" : "incomplete"}`}><i className={`sm-dot ${active ? "ready" : ""}`} />{active ? human(item.message_status) : "Missing email"}</span></button>; })}
          {!loading && !tasks.length && <div className="sm-empty"><Icon name="search" size={25} /><p>{data?.tasks.length ? "No matching Outreach Tasks." : "Import a supported source set for this Student and Campaign."}</p><button className="sm-button" onClick={() => { setQuery(""); setFilter("all"); }}>Clear task filters</button></div>}
        </div><div className="sm-output-note"><Icon name="shield" size={14} /><span>Core creates one Outreach Task per Student, Supervisor and Campaign. Preparation and readiness remain separate.</span></div></section>
      </main>
      <footer className="sm-footer"><span><i className="sm-dot ready" />Persisted Core data<span className="footer-separator">|</span>{sources.length} sources · {activeCount} active · {(data?.tasks.length ?? 0) - activeCount} missing email · {currentStudent?.name || "No Student"}</span><span><Icon name="shield" size={12} />Original bytes and evidence are retained</span></footer>
      {dragging && <div className="sm-drop-overlay" aria-hidden="true"><div className="sm-drop-card"><span className="sm-drop-icon"><Icon name="file" size={26} /></span><strong>Drop to import through SmartMail Core</strong><span>Select one .xlsx master list or a .zip bundle containing exactly one master list and its related documents.</span></div></div>}
    </div>
    <input ref={fileInput} type="file" multiple accept=".xlsx,.zip,.docx,.pdf,.csv" hidden onChange={(event) => { void ingest(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
    <dialog ref={inspector} aria-label="Source evidence inspector" className="sm-detail" onClick={(event) => { if (event.target === event.currentTarget) { inspector.current?.close(); setInspection(null); } }}><div className="sm-detail-inner"><div className="sm-detail-top"><span>RETAINED EVIDENCE</span><button aria-label="Close inspector" onClick={() => { inspector.current?.close(); setInspection(null); }}><Icon name="close" size={19} /></button></div><div className="sm-detail-symbol"><Icon name="link" size={27} /></div><h2>{inspection?.title}</h2><p>{inspection?.detail}</p><pre>{JSON.stringify(inspection?.evidence, null, 2)}</pre><div className="sm-detail-note"><Icon name="shield" size={17} />Core remains authoritative for supported associations and readiness.</div><button className="primary full" onClick={() => { inspector.current?.close(); setInspection(null); }}>Done</button></div></dialog>
    <dialog ref={taskDialog} aria-label="Resolved task inspector" className="sm-detail sm-task-detail" onClick={(event) => { if (event.target === event.currentTarget) { taskDialog.current?.close(); setSelectedTask(null); } }}>{selectedTask && (() => { const preparation = selectedTask.preparations.find((item) => item.status !== "superseded"); return <div className="sm-detail-inner"><div className="sm-detail-top"><span>OUTREACH TASK · {preparation?.ready ? "READY" : "IN PREPARATION"}</span><button aria-label="Close task inspector" onClick={() => { taskDialog.current?.close(); setSelectedTask(null); }}><Icon name="close" size={19} /></button></div><div className="sm-detail-symbol"><Icon name={preparation ? "file" : "user"} size={27} /></div><h2>{selectedTask.task.supervisor.name}</h2><p>{currentStudent?.name} → {selectedTask.task.supervisor.name} · {selectedTask.task.institution.name}</p><div className="sm-detail-fields"><div><span>Campaign</span><strong>{data?.campaign?.name}</strong></div><div><span>Recipient address</span><strong>{selectedTask.task.supervisor.addresses.join(", ") || "Missing — no usable address recorded"}</strong></div><div><span>Active Preparation</span><strong>{preparation ? `${preparation.source.name} · ${preparation.subject || "subject required"}` : "No supported draft associated"}</strong></div><div><span>Mailbox identity</span><strong>{selectedTask.task.mailbox.address}</strong></div><div><span>Task exceptions</span><strong>{selectedTask.task.exceptions.map((item) => human(item.code)).join(", ") || "None"}</strong></div><div><span>Readiness findings</span><strong>{preparation?.readiness_findings.map((item) => human(item.code)).join(", ") || "None"}</strong></div></div><div className="sm-detail-note"><Icon name="shield" size={17} />Corrections and attachment confirmation continue in Readiness review.</div><button className="primary full" onClick={() => { taskDialog.current?.close(); setSelectedTask(null); window.location.hash = "#review"; }}>Open readiness review</button></div>; })()}</dialog>
  </AppShell>;
}

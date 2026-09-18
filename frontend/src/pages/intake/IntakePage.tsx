import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import SearchField from "../../shared/SearchField";
import Icon from "../../shared/Icon";
import { AppShell, Topbar } from "../../app/shell";
import { useWorkspaceScope } from "../../app/scope";
import { useCoreQuery } from "../../core/data";
import {
  human,
  importSources,
  recognizeSources,
  type IntakeSource,
  type IntakeWorkspace,
  type RecognitionRelation,
  type RecognitionTypeId,
  type SourceRecognitionAnnotation,
} from "../../core";
import {
  buildImportSelections,
  confidenceTone,
  identitySummary,
  isActionableType,
  recognitionTypeOptions,
  reviewImportability,
  reviewItems,
  typeOption,
  type ReviewItem,
} from "./recognition-model";
import "./SourceMapping.css";

type TaskFilter = "all" | "active" | "incomplete";
type SourceView = IntakeSource & { category: string; importId: string; finding?: string; recognition?: SourceRecognitionAnnotation };
type ReviewRow = ReviewItem;
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
  const { scope } = useWorkspaceScope();
  const campaign = scope?.campaignId ?? "";
  const student = scope?.studentId ?? "";
  const workspaceQuery = useCoreQuery("intake_workspace", { student_id: student }, { enabled: Boolean(student) });
  const data: IntakeWorkspace | null = workspaceQuery.data;
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<TaskFilter>("all");
  const [selectedSource, setSelectedSource] = useState<SourceView | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const taskQuery = useCoreQuery("task", { task_id: selectedTaskId }, { enabled: Boolean(selectedTaskId) });
  const selectedTask = taskQuery.data;
  const [inspection, setInspection] = useState<{ title: string; detail: string; evidence: unknown } | null>(null);
  const [busy, setBusy] = useState(false);
  const [recognizing, setRecognizing] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [review, setReview] = useState<{ rows: ReviewRow[]; relations: RecognitionRelation[] } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const inspector = useRef<HTMLDialogElement>(null);
  const taskDialog = useRef<HTMLDialogElement>(null);
  const reviewDialog = useRef<HTMLDialogElement>(null);
  const dragDepth = useRef(0);
  const loading = workspaceQuery.isLoading;
  const displayError = error || workspaceQuery.error?.message || taskQuery.error?.message || "";

  useEffect(() => { if (inspection) inspector.current?.showModal(); }, [inspection]);
  useEffect(() => { if (selectedTaskId) taskDialog.current?.showModal(); }, [selectedTaskId]);
  useEffect(() => {
    if (review) reviewDialog.current?.showModal();
    else reviewDialog.current?.close();
  }, [review]);

  const sources = useMemo<SourceView[]>(() => (data?.imports ?? []).flatMap((imported) =>
    imported.sources.map((source) => ({
      ...source,
      importId: imported.id,
      category: data?.source_categories[source.id] ?? "unresolved",
      finding: imported.findings.find((finding) => finding.source.id === source.id)?.detail,
      recognition: data?.source_recognition[source.id],
    }))), [data]);
  const unresolved = sources.filter((source) => source.category === "unresolved"
    && `${source.name} ${source.finding ?? ""}`.toLowerCase().includes(query.toLowerCase()));
  const tasks = (data?.tasks ?? []).filter((item) => {
    const active = Boolean(item.recipient_addresses.length);
    return (filter === "all" || (filter === "active" ? active : !active))
      && `${item.supervisor_name} ${item.institution_name} ${item.recipient_addresses.join(" ")}`.toLowerCase().includes(query.toLowerCase());
  });
  const currentStudent = data?.students.find((item) => item.id === student) ?? null;
  const activeCount = data?.tasks.filter((item) => item.recipient_addresses.length).length ?? 0;

  const importability = useMemo(
    () => review ? reviewImportability(review.rows) : { ok: false, issues: [] as string[], advisories: [] as string[] },
    [review],
  );
  const includedCount = review?.rows.filter((row) => row.included).length ?? 0;
  const reviewFiles = useRef<Map<string, File>>(new Map());

  async function ingest(files: File[]) {
    if (!files.length || !campaign || !student) return;
    setRecognizing(true); setError(""); setNotice("");
    try {
      // Stage one: deterministic structural recognition, never an import.
      // Archives return their expanded members; there is no "mixed" row.
      const collection = await recognizeSources(files);
      const fileMap = new Map(files.map((file) => [file.name, file]));
      reviewFiles.current = fileMap;
      const rows: ReviewRow[] = reviewItems(collection.sources).map((row) => {
        const uploadName = row.container || row.name;
        const file = fileMap.get(uploadName);
        if (!file) throw new Error(`Core did not return recognition for ${uploadName}`);
        return { ...row, size: file.size };
      });
      setReview({ rows, relations: collection.relations });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Core could not recognize the selected source set");
    } finally { setRecognizing(false); }
  }

  function setRowType(key: string, type: RecognitionTypeId) {
    setReview((current) => current ? {
      ...current,
      rows: current.rows.map((row) => row.key === key
        ? { ...row, type, included: row.manuallyToggled ? row.included : isActionableType(type) }
        : row),
    } : current);
  }
  function toggleRow(key: string) {
    setReview((current) => current ? {
      ...current,
      rows: current.rows.map((row) => row.key === key
        ? { ...row, included: !row.included, manuallyToggled: true }
        : row),
    } : current);
  }

  async function confirmReviewImport() {
    if (!review || !importability.ok) return;
    const selections = buildImportSelections(review.rows, reviewFiles.current);
    setBusy(true); setError(""); setNotice("");
    try {
      // Stage two: import the operator-approved selection; zips are expanded
      // server-side and revised types persist alongside Core's own recognition.
      const result = await importSources(campaign, student, selections);
      workspaceQuery.setData(result.workspace);
      setReview(null);
      setSelectedSource(null);
      const summary = result.import.summary;
      const created = result.preparation.preparation_ids.length;
      const createdText = created
        ? `; ${created} local Preparation${created === 1 ? "" : "s"} created from letters`
        : summary.rows
          ? "; drafts will associate on the next preparation step"
          : "; reference material retained";
      setNotice(`Imported ${summary.rows} supervisor row${summary.rows === 1 ? "" : "s"}${createdText}.`);
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

  return <AppShell className="sm-app" activeRoute="sources">
    <div className="workspace" onDragEnter={onDragEnter} onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}>
      <Topbar className="sm-topbar" breadcrumb="Source mapping" homeHref="#workflow">
        <SearchField label="Search source findings and tasks" value={query} onChange={setQuery} placeholder="Search source findings or resolved tasks…" iconSize={16} />
      </Topbar>
      {(notice || displayError) && <div className="sm-notice" role={displayError ? "alert" : "status"}><Icon name={displayError ? "warning" : "check"} size={16} />{displayError || notice}<button aria-label="Dismiss notification" onClick={() => { setNotice(""); setError(""); }}><Icon name="close" size={15} /></button></div>}
      <main className="sm-board">
        <section className="sm-sources"><div className="sm-column-heading"><Icon name="folder" size={16} /><h2>Unresolved raw sources</h2><span>{String(unresolved.length).padStart(2, "0")}</span></div><div className="sm-source-list">
          {unresolved.map((source) => <button key={source.id} className={`sm-source-card ${selectedSource?.id === source.id ? "is-selected" : ""}`} aria-pressed={selectedSource?.id === source.id} onClick={() => setSelectedSource(selectedSource?.id === source.id ? null : source)} onDoubleClick={() => inspectSource(source)}><span className="sm-file-icon slate"><Icon name="file" size={20} /></span><span className="sm-source-copy"><strong>{source.name}</strong><small>{Math.max(1, Math.round(source.size / 1024))} KB</small><span className="sm-source-meta-line"><em>{source.recognition?.label ?? (source.finding || "Core could not associate this source")}</em>{source.recognition?.revised && <b className="sm-revised-tag">Revised</b>}</span></span><Icon name="chevron" size={13} /></button>)}
          {!loading && !unresolved.length && <p className="sm-empty">{query ? "No matching unresolved sources." : "No unresolved Source Materials in this scope."}</p>}
          <button className="sm-add-source" disabled={busy || recognizing || !campaign || !student} onClick={() => fileInput.current?.click()} title="Import a supported .xlsx or .zip source set"><Icon name="plus" size={17} />{recognizing ? "Recognizing source set…" : "Drag & drop a supported source set"}<span>{recognizing ? "Please wait" : "Browse files"}</span></button>
          {selectedSource && <div className="sm-selection"><span>Inspecting <strong>{selectedSource.name}</strong></span><button onClick={() => inspectSource(selectedSource)}>Inspect evidence <Icon name="arrow" size={13} /></button><button onClick={() => setSelectedSource(null)}>Clear selection</button></div>}
        </div></section>

        <section className="sm-categories"><div className="sm-column-heading"><Icon name="branch" size={16} /><h2>Stable categories</h2><span>{categories.length} fixed</span></div><div className="sm-category-list">{categories.map((category) => {
          const members = category.id === "profile" || category.id === "mailbox" ? [] : sources.filter((source) => source.category === category.id);
          const count = category.id === "profile" || category.id === "mailbox" ? Number(Boolean(currentStudent)) : members.length;
          return <article className="sm-category-card" data-category={category.id} key={category.id}><button className="sm-category-main" title={category.detail} onClick={() => setInspection({ title: category.title, detail: category.detail, evidence: category.id === "profile" ? currentStudent : category.id === "mailbox" ? { mailbox: currentStudent?.mailbox } : members })}><span className={`sm-rule-icon ${category.color}`}><Icon name={category.icon} size={17} /></span><span className="sm-category-copy"><strong>{category.title}</strong><small>{category.id === "profile" ? currentStudent?.name || "No Student selected" : category.id === "mailbox" ? currentStudent?.mailbox || "No Mailbox registered" : `${members.length} retained source${members.length === 1 ? "" : "s"}`}</small></span><span className="sm-category-count">{count}</span></button><div className="sm-classified-chips">{members.slice(0, 3).map((source) => <button className="sm-file-chip" key={source.id} onClick={() => inspectSource(source)}><Icon name="file" size={11} /><span title={source.name}>{source.name}</span></button>)}{!members.length && category.id !== "profile" && category.id !== "mailbox" && <span className="sm-file-chip is-empty">Nothing retained</span>}{members.length > 3 && <span className="sm-file-chip">+{members.length - 3} more</span>}</div></article>;
        })}</div></section>

        <section className="sm-output"><div className="sm-column-heading"><Icon name="source" size={16} /><h2>Resolved tasks</h2><span>{tasks.length}</span><label className="sm-task-filter"><select aria-label="Filter resolved tasks" value={filter} onChange={(event) => setFilter(event.target.value as TaskFilter)}><option value="all">All</option><option value="active">Active</option><option value="incomplete">Missing email</option></select></label></div><div className="sm-task-list">
          {currentStudent && <div className="sm-task-student"><span className="sm-student-avatar blue">{initials(currentStudent.name)}</span><strong>{currentStudent.name}</strong><small>{data?.campaign?.name}</small><span className="sm-task-student-mail"><Icon name="mail" size={12} />{currentStudent.mailbox}</span></div>}
          {tasks.map((item) => { const active = Boolean(item.recipient_addresses.length); const preparation = item.preparation; const attachments = preparation?.attachment_count ?? 0; return <button key={item.task_id} className={`sm-task-row ${active ? "" : "is-incomplete"}`} onClick={() => setSelectedTaskId(item.task_id)}><span className="sm-task-row-icon"><Icon name={preparation ? "file" : "user"} size={15} /></span><span className="sm-task-row-copy"><strong>{item.supervisor_name}</strong><small>{item.institution_name} · {item.recipient_addresses.join(", ") || "no email identified"}</small></span><span className={`sm-task-badge ${preparation ? "" : "is-off"}`}><Icon name="file" size={12} />{preparation ? "Prepared" : "No draft"}</span><span className={`sm-task-badge ${attachments ? "" : "is-off"}`}><Icon name="clip" size={12} />{attachments}</span><span className={`sm-task-pill ${active ? "active" : "incomplete"}`}><i className={`sm-dot ${active ? "ready" : ""}`} />{active ? human(item.message_status) : "Missing email"}</span></button>; })}
          {!loading && !tasks.length && <div className="sm-empty"><Icon name="search" size={25} /><p>{data?.tasks.length ? "No matching Outreach Tasks." : "Import a supported source set for this Student and Campaign."}</p><button className="sm-button" onClick={() => { setQuery(""); setFilter("all"); }}>Clear task filters</button></div>}
        </div><div className="sm-output-note"><Icon name="shield" size={14} /><span>Core creates one Outreach Task per Student, Supervisor and Campaign. Preparation and readiness remain separate.</span></div></section>
      </main>
      <footer className="sm-footer"><span><i className="sm-dot ready" />Persisted Core data<span className="footer-separator">|</span>{sources.length} sources · {activeCount} active · {(data?.tasks.length ?? 0) - activeCount} missing email · {currentStudent?.name || "No Student"}</span><span><Icon name="shield" size={12} />Original bytes and evidence are retained</span></footer>
      {dragging && <div className="sm-drop-overlay" aria-hidden="true"><div className="sm-drop-card"><span className="sm-drop-icon"><Icon name="file" size={26} /></span><strong>Drop to recognize with SmartMail Core</strong><span>Core classifies .docx, .xlsx and .csv sources from their structure first. You review and revise the types, then import only the approved set.</span></div></div>}
    </div>
    <input ref={fileInput} type="file" multiple accept=".xlsx,.zip,.docx,.pdf,.csv" hidden onChange={(event) => { void ingest(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
    <dialog ref={reviewDialog} aria-label="Review recognized sources" className="sm-recog" onClose={() => setReview(null)} onClick={(event) => { if (event.target === event.currentTarget && !busy) setReview(null); }}>
      {review && <div className="sm-recog-inner" role="document">
        <div className="sm-recog-top">
          <div>
            <span>DETERMINISTIC RECOGNITION</span>
            <h2>{review.rows.length} source{review.rows.length === 1 ? "" : "s"} recognized</h2>
            <p>Core classified every file from its structure and discourse, not its extension. Revise a type or toggle inclusion; uncertain imports stay blocked.</p>
          </div>
          <button aria-label="Cancel recognition review" disabled={busy} onClick={() => setReview(null)}><Icon name="close" size={19} /></button>
        </div>
        {review.relations.length > 0 && <div className="sm-recog-relations">
          {review.relations.map((relation, index) => <div key={index} className="sm-recog-relation">
            <Icon name="branch" size={14} />
            <span><strong>{relation.relation === "exact_duplicate" ? "Exact duplicate" : "Near-duplicate / version"}</strong>
              {": "}{relation.a.split("/").pop()} ↔ {relation.b.split("/").pop()}
              {relation.relation === "near_duplicate" && ` · ${Math.round((relation.containment ?? relation.similarity) * 100)}% shared content`}
              {" — both retained, nothing is merged automatically."}</span>
          </div>)}
        </div>}
        <div className="sm-recog-rows">
          {review.rows.map((row) => {
            const option = typeOption(row.type);
            const revised = row.type !== row.result.type;
            const tone = confidenceTone(row.result.confidence);
            const summary = identitySummary({ ...row.result, type: row.type });
            const evidence = row.result.reasons[0] ?? "No supporting structural evidence; held for operator review.";
            return <article key={row.key} className={`sm-recog-row ${row.included ? "is-included" : "is-excluded"}`}>
              <label className="sm-recog-check" title={row.included ? "Exclude from this import" : "Include in this import"}>
                <input type="checkbox" checked={row.included} disabled={busy} onChange={() => toggleRow(row.key)} />
              </label>
              <span className={`sm-recog-type-icon ${row.included ? "" : "is-off"}`}><Icon name={option.icon} size={17} /></span>
              <div className="sm-recog-copy">
                <strong title={row.name}>{row.name}{revised && <b className="sm-revised-tag">Revised</b>}</strong>
                <small>{row.container && <span className="sm-container-tag" title={`Expanded from ${row.container}`}>{row.container}</span>}{summary ? `${summary} · ` : ""}{Math.max(1, Math.round(row.size / 1024))} KB</small>
                <em title={[...row.result.reasons, ...row.result.cautions].join("\n")}>{evidence}{row.result.cautions.length > 0 ? ` · ${row.result.cautions.length} caution${row.result.cautions.length === 1 ? "" : "s"}` : ""}</em>
              </div>
              <span className={`sm-recog-confidence ${tone}`} title={[...row.result.reasons, ...row.result.cautions].join("\n")}>
                <i className={`sm-dot ${tone === "ready" ? "ready" : ""}`} />{row.result.confidence}
              </span>
              <select aria-label={`Revise recognized type for ${row.name}`} value={row.type} disabled={busy} onChange={(event) => setRowType(row.key, event.target.value as RecognitionTypeId)}>
                <optgroup label="Creates outreach work">
                  {recognitionTypeOptions.filter((item) => item.actionable).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </optgroup>
                <optgroup label="Reference / unresolved">
                  {recognitionTypeOptions.filter((item) => !item.actionable).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </optgroup>
              </select>
            </article>;
          })}
        </div>
        <div className="sm-recog-footer">
          <div className="sm-recog-foot-note">
            {importability.ok
              ? <><Icon name="check" size={15} /><div><span>{includedCount} of {review.rows.length} source{review.rows.length === 1 ? "" : "s"} will import.</span>{importability.advisories.length > 0 && <ul className="sm-recog-advisories">{importability.advisories.map((advisory, index) => <li key={index}>{advisory}</li>)}</ul>}</div></>
              : <><Icon name="warning" size={15} /><div><ul>{importability.issues.map((issue, index) => <li key={index}>{issue}</li>)}</ul>{importability.advisories.length > 0 && <ul className="sm-recog-advisories">{importability.advisories.map((advisory, index) => <li key={index}>{advisory}</li>)}</ul>}</div></>}
          </div>
          <div className="sm-recog-actions">
            <button className="sm-recog-cancel" disabled={busy} onClick={() => setReview(null)}>Cancel</button>
            <button className="primary" disabled={busy || !importability.ok} onClick={() => void confirmReviewImport()}>{busy ? "Importing…" : `Import ${includedCount} source${includedCount === 1 ? "" : "s"}`}</button>
          </div>
        </div>
      </div>}
    </dialog>
    <dialog ref={inspector} aria-label="Source evidence inspector" className="sm-detail" onClick={(event) => { if (event.target === event.currentTarget) { inspector.current?.close(); setInspection(null); } }}><div className="sm-detail-inner"><div className="sm-detail-top"><span>RETAINED EVIDENCE</span><button aria-label="Close inspector" onClick={() => { inspector.current?.close(); setInspection(null); }}><Icon name="close" size={19} /></button></div><div className="sm-detail-symbol"><Icon name="link" size={27} /></div><h2>{inspection?.title}</h2><p>{inspection?.detail}</p><pre>{JSON.stringify(inspection?.evidence, null, 2)}</pre><div className="sm-detail-note"><Icon name="shield" size={17} />Core remains authoritative for supported associations and readiness.</div><button className="primary full" onClick={() => { inspector.current?.close(); setInspection(null); }}>Done</button></div></dialog>
    <dialog ref={taskDialog} aria-label="Resolved task inspector" className="sm-detail sm-task-detail" onClick={(event) => { if (event.target === event.currentTarget) { taskDialog.current?.close(); setSelectedTaskId(""); } }}>{selectedTask ? (() => { const preparation = selectedTask.preparations.find((item) => item.status !== "superseded"); return <div className="sm-detail-inner"><div className="sm-detail-top"><span>OUTREACH TASK · {preparation?.ready ? "READY" : "IN PREPARATION"}</span><button aria-label="Close task inspector" onClick={() => { taskDialog.current?.close(); setSelectedTaskId(""); }}><Icon name="close" size={19} /></button></div><div className="sm-detail-symbol"><Icon name={preparation ? "file" : "user"} size={27} /></div><h2>{selectedTask.task.supervisor.name}</h2><p>{currentStudent?.name} → {selectedTask.task.supervisor.name} · {selectedTask.task.institution.name}</p><div className="sm-detail-fields"><div><span>Campaign</span><strong>{data?.campaign?.name}</strong></div><div><span>Recipient address</span><strong>{selectedTask.task.supervisor.addresses.join(", ") || "Missing — no usable address recorded"}</strong></div><div><span>Active Preparation</span><strong>{preparation ? `${preparation.source.name} · ${preparation.subject || "subject required"}` : "No supported draft associated"}</strong></div><div><span>Mailbox identity</span><strong>{selectedTask.task.mailbox.address}</strong></div><div><span>Task exceptions</span><strong>{selectedTask.task.exceptions.map((item) => human(item.code)).join(", ") || "None"}</strong></div><div><span>Readiness findings</span><strong>{preparation?.readiness_findings.map((item) => human(item.code)).join(", ") || "None"}</strong></div></div><div className="sm-detail-note"><Icon name="shield" size={17} />Corrections and attachment confirmation continue in Readiness review.</div><button className="primary full" onClick={() => { taskDialog.current?.close(); setSelectedTaskId(""); window.location.hash = "#review"; }}>Open readiness review</button></div>; })() : <div className="sm-detail-inner"><h2>{taskQuery.isLoading ? "Loading task details…" : "Task details unavailable"}</h2></div>}</dialog>
  </AppShell>;
}

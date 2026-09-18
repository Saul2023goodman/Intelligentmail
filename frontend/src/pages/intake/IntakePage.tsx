import { Fragment, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import SearchField from "../../shared/SearchField";
import Icon, { type IconName } from "../../shared/Icon";
import { AppShell, Topbar } from "../../app/shell";
import { useWorkspaceScope } from "../../app/scope";
import { useCoreQuery } from "../../core/data";
import { gatewayHealth } from "../../core/gateway";
import {
  core,
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
type MapFilter = "all" | "duplicate" | "conflict" | "unmatched";
type SourceView = IntakeSource & { category: string; importId: string; finding?: string; recognition?: SourceRecognitionAnnotation };
type ReviewRow = ReviewItem;
type ImportSummary = { rows: number; duplicate: number; conflicts: number; new_sources: number; created: number };

// One candidate stream: an uploaded Source Material and a draft observed in the
// Student's own mailbox are both Source Material, so the board never switches
// between two different interfaces — only the channel of a candidate differs.
type Candidate = {
  key: string;
  channel: "upload" | "draft";
  name: string;
  group: string;
  detail: string;
  confidence: string;
  included: boolean;
  duplicate: boolean;
  conflict: boolean;
  unmatched: boolean;
  source?: SourceView;
  observation?: {
    id: string; subject: string; recipient: string; taskId: string; supervisor: string;
    attachmentCount: number; bodyAvailable: boolean; observedTime: string; scheduled: boolean;
  };
};

const groups: { id: string; title: string; icon: IconName; color: string }[] = [
  { id: "unresolved", title: "待判定", icon: "warning", color: "slate" },
  { id: "master", title: "导师名单", icon: "source", color: "green" },
  { id: "drafts", title: "外联草稿", icon: "file", color: "blue" },
  { id: "attachments", title: "附件材料", icon: "clip", color: "purple" },
  { id: "records", title: "既往外联记录", icon: "database", color: "amber" },
  { id: "mailbox", title: "邮箱草稿箱", icon: "mail", color: "teal" },
];
const categoryType: Record<string, RecognitionTypeId> = {
  master: "supervisor_master", drafts: "outreach_draft", attachments: "applicant_cv", records: "tracking_sheet",
};
const typeOfSource = (source: SourceView): RecognitionTypeId =>
  source.recognition?.type ?? categoryType[source.category] ?? "unknown";

export default function IntakePage() {
  const { scope } = useWorkspaceScope();
  const campaign = scope?.campaignId ?? "";
  const student = scope?.studentId ?? "";
  const [expandedTaskId, setExpandedTaskId] = useState("");
  const [query, setQuery] = useState("");
  const [taskFilter, setTaskFilter] = useState<TaskFilter>("all");
  const [mapFilter, setMapFilter] = useState<MapFilter>("all");
  const [focused, setFocused] = useState("");
  const [busy, setBusy] = useState(false);
  const [recognizing, setRecognizing] = useState(false);
  const [observing, setObserving] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [review, setReview] = useState<{ rows: ReviewRow[]; relations: RecognitionRelation[] } | null>(null);
  const [selectedDrafts, setSelectedDrafts] = useState<string[]>([]);
  const [lastImport, setLastImport] = useState<ImportSummary | null>(null);
  const [heldFiles, setHeldFiles] = useState<string[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);

  const ready = Boolean(campaign && student);
  const intakeQuery = useCoreQuery("intake_workspace", { student_id: student }, { enabled: Boolean(student) });
  const draftQuery = useCoreQuery("draft_material", { campaign_id: campaign, student_id: student }, { enabled: ready });
  const mailboxQuery = useCoreQuery("mailbox_workspace", { campaign_id: campaign, student_id: student }, { enabled: ready });
  const workspaceQuery = useCoreQuery("workspace", campaign ? { campaign_id: campaign } : {}, { enabled: Boolean(student) });
  const gatewayQuery = useCoreQuery("gateway_status", {}, { maxAge: 1_000, refetchInterval: 3_000 });
  // Task evidence is fetched only for the row the operator expands.
  const taskQuery = useCoreQuery("task", { task_id: expandedTaskId }, { enabled: Boolean(expandedTaskId) });
  const taskDetail = expandedTaskId ? taskQuery.data : null;

  const data: IntakeWorkspace | null = intakeQuery.data;
  const mailbox = mailboxQuery.data;
  const draftCandidates = useMemo(() => draftQuery.data?.candidates ?? [], [draftQuery.data]);
  const loading = intakeQuery.isLoading || draftQuery.isLoading || mailboxQuery.isLoading;
  const displayError = error || intakeQuery.error?.message || draftQuery.error?.message || mailboxQuery.error?.message || "";

  const studentMailbox = workspaceQuery.data?.mailboxes.find((item) => item.student_id === student) ?? null;
  const gateway = gatewayHealth(gatewayQuery.data ?? workspaceQuery.data?.mailbox_capabilities.gateway, studentMailbox);

  // Uploaded bytes stay in this session only: re-mapping a retained source
  // re-imports the same bytes with a revised type, which Core treats as the
  // same Source Material (idempotent, nothing duplicated).
  const uploadedFiles = useRef<Map<string, File>>(new Map());
  const reviewFiles = useRef<Map<string, File>>(new Map());

  // Scope switches reset the transient pipeline state: a recognition batch and
  // its held bytes describe one Student × Campaign only.
  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- A scope switch invalidates the whole pipeline.
    setReview(null);
    setLastImport(null);
    setFocused("");
    setExpandedTaskId("");
    setSelectedDrafts([]);
    setHeldFiles([]);
  }, [student, campaign]);

  const sources = useMemo<SourceView[]>(() => (data?.imports ?? []).flatMap((imported) =>
    imported.sources.map((source) => ({
      ...source,
      importId: imported.id,
      category: data?.source_categories[source.id] ?? "unresolved",
      finding: imported.findings.find((finding) => finding.source.id === source.id)?.detail,
      recognition: data?.source_recognition[source.id],
    }))), [data]);

  const allFindings = useMemo(() => (data?.imports ?? []).flatMap((imported) => imported.findings.map((finding) => ({
    code: finding.code, detail: finding.detail, blocking: finding.blocking, source: finding.source.name,
  }))), [data]);
  const duplicateFindings = allFindings.filter((finding) => finding.code.includes("duplicate"));
  const blockingFindings = allFindings.filter((finding) => finding.blocking);
  const findingsBySource = useMemo(() => new Map(
    (data?.imports ?? []).flatMap((imported) => imported.findings.map((finding) =>
      [finding.source.id, finding] as const))), [data]);

  const comparisonRows = useMemo(() => mailbox?.rows ?? [], [mailbox]);
  const observedByTask = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of comparisonRows) {
      if (row.local?.task_id && row.observed) {
        counts.set(row.local.task_id, (counts.get(row.local.task_id) ?? 0) + 1);
      }
    }
    return counts;
  }, [comparisonRows]);

  const needle = query.toLowerCase();
  const candidates = useMemo<Candidate[]>(() => {
    const uploaded: Candidate[] = sources.map((source) => {
      const finding = findingsBySource.get(source.id);
      return {
        key: `source:${source.id}`,
        channel: "upload",
        name: source.name,
        group: source.category,
        detail: `${Math.max(1, Math.round(source.size / 1024))} KB · ${source.recognition?.label ?? human(source.category)}`,
        confidence: source.recognition?.confidence ?? "",
        included: true,
        duplicate: Boolean(finding && finding.code.includes("duplicate")),
        conflict: Boolean(finding?.blocking),
        unmatched: source.category === "unresolved",
        source,
      };
    });
    const drafts: Candidate[] = draftCandidates.map((draft) => ({
      key: `draft:${draft.observation_id}`,
      channel: "draft",
      name: draft.subject || "(no subject)",
      group: "mailbox",
      detail: draft.recipient
        ? `${draft.recipient}${draft.attachment_count ? ` · ${draft.attachment_count} 附件` : ""}`
        : "无可用收件人",
      confidence: draft.task_id ? "high" : "low",
      included: false,
      duplicate: false,
      conflict: false,
      unmatched: !draft.task_id,
      observation: {
        id: draft.observation_id, subject: draft.subject, recipient: draft.recipient,
        taskId: draft.task_id, supervisor: draft.supervisor,
        attachmentCount: draft.attachment_count, bodyAvailable: draft.body_available,
        observedTime: draft.observed_time, scheduled: draft.scheduled,
      },
    }));
    return [...uploaded, ...drafts].filter((candidate) =>
      `${candidate.name} ${candidate.detail}`.toLowerCase().includes(needle));
  }, [sources, draftCandidates, findingsBySource, needle]);

  const grouped = useMemo(() => groups
    .map((group) => ({ ...group, items: candidates.filter((candidate) => candidate.group === group.id) }))
    .filter((group) => group.items.length), [candidates]);

  const reviewKeys = useMemo(() => new Set((review?.relations ?? []).flatMap((relation) => [relation.a, relation.b])), [review]);
  const mappingRows = useMemo(() => candidates.filter((candidate) => {
    if (mapFilter === "duplicate") return candidate.duplicate || reviewKeys.has(candidate.name);
    if (mapFilter === "conflict") return candidate.conflict;
    if (mapFilter === "unmatched") return candidate.unmatched;
    return true;
  }), [candidates, mapFilter, reviewKeys]);

  const counts = {
    acquired: candidates.length,
    recognized: candidates.filter((candidate) => candidate.channel === "upload"
      ? Boolean(candidate.source?.recognition) : Boolean(candidate.observation?.recipient)).length,
    duplicates: duplicateFindings.length + (review?.relations.length ?? 0),
    conflicts: blockingFindings.length + draftCandidates.filter((draft) => !draft.task_id).length,
    resolved: data?.tasks.length ?? 0,
  };

  const tasks = (data?.tasks ?? []).filter((item) => {
    const active = Boolean(item.recipient_addresses.length);
    return (taskFilter === "all" || (taskFilter === "active" ? active : !active))
      && `${item.supervisor_name} ${item.institution_name} ${item.recipient_addresses.join(" ")}`.toLowerCase().includes(needle);
  });
  const activeCount = data?.tasks.filter((item) => item.recipient_addresses.length).length ?? 0;

  const importability = useMemo(
    () => review ? reviewImportability(review.rows) : { ok: false, issues: [] as string[], advisories: [] as string[] },
    [review],
  );
  const includedCount = review?.rows.filter((row) => row.included).length ?? 0;
  const importableDrafts = selectedDrafts.filter((id) =>
    draftCandidates.some((draft) => draft.observation_id === id && draft.task_id && draft.body_available));

  async function ingest(files: File[]) {
    if (!files.length || !campaign || !student) return;
    setRecognizing(true); setError(""); setNotice("");
    try {
      const fileMap = new Map(files.map((file) => [file.name, file]));
      reviewFiles.current = fileMap;
      for (const file of files) uploadedFiles.current.set(file.name, file);
      setHeldFiles((current) => [...new Set([...current, ...files.map((file) => file.name)])]);
      const collection = await recognizeSources(files);
      const rows: ReviewRow[] = reviewItems(collection.sources).map((row) => {
        const file = fileMap.get(row.container || row.name);
        if (!file) throw new Error(`Core did not return recognition for ${row.container || row.name}`);
        return { ...row, size: file.size };
      });
      setReview({ rows, relations: collection.relations });
      setFocused("");
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
  async function runImport(selections: Parameters<typeof importSources>[2], summary: (rows: number, created: number) => string) {
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await importSources(campaign, student, selections);
      intakeQuery.setData(result.workspace);
      const imported = result.import.summary;
      setLastImport({
        rows: imported.rows, duplicate: imported.duplicate, conflicts: imported.conflicts,
        new_sources: imported.new_sources, created: result.preparation.preparation_ids.length,
      });
      setNotice(summary(imported.rows, result.preparation.preparation_ids.length));
      return result;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Core rejected the selected source set");
      return null;
    } finally { setBusy(false); }
  }
  async function confirmReviewImport() {
    if (!review || !importability.ok) return;
    const result = await runImport(buildSelections(review), (rows, created) => {
      const createdText = created
        ? `; ${created} 份 Preparation 已建立`
        : rows ? "; 草稿将在下一步关联" : "; 参考材料已保留";
      return `已导入 ${rows} 行${createdText}。`;
    });
    if (result) setReview(null);
  }
  function buildSelections(reviewSet: { rows: ReviewRow[] }) {
    return reviewSet.rows
      .map((row) => {
        const file = reviewFiles.current.get(row.container || row.name);
        return file ? { file, included: row.included, ...(row.type !== row.result.type ? { type: row.type } : {}) } : null;
      })
      .filter((item): item is { file: File; included: boolean; type?: RecognitionTypeId } => Boolean(item));
  }
  async function remapSource(source: SourceView, type: RecognitionTypeId) {
    const file = uploadedFiles.current.get(source.name);
    if (!file) {
      setError(`映射需要原始文件：请重新拖入 ${source.name} 后再调整映射。`);
      return;
    }
    await runImport([{ file, included: true, type }], () => `已重新映射 ${source.name} → ${typeOption(type).label}。`);
  }
  async function importDrafts() {
    if (!importableDrafts.length) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await core("intake_import_drafts", {
        campaign_id: campaign, student_id: student, observation_ids: importableDrafts,
      });
      intakeQuery.setData(result.workspace);
      const skipped = result.skipped.length ? `；${result.skipped.length} 封跳过：${result.skipped[0].reason}` : "";
      setNotice(`已导入 ${result.imported.length} 封草稿为来源材料${skipped}`);
      setSelectedDrafts([]);
      void draftQuery.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Core 无法导入所选草稿");
    } finally { setBusy(false); }
  }
  async function observeMailbox() {
    if (!student || !gateway.canObserve) return;
    setObserving(true); setError(""); setNotice("");
    try {
      const result = await core("refresh_mailbox", { student_id: student });
      await Promise.all([mailboxQuery.refresh(), draftQuery.refresh(), workspaceQuery.refresh()]);
      setNotice(`邮箱证据已更新（${result.observation.status}，${result.observation.messages?.length ?? 0} 封观察）。`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Mailbox observation failed");
    } finally { setObserving(false); }
  }

  const hasFiles = (event: DragEvent) => Array.from(event.dataTransfer?.types ?? []).includes("Files");
  const onDragEnter = (event: DragEvent) => { if (hasFiles(event)) { dragDepth.current += 1; setDragging(true); } };
  const onDragOver = (event: DragEvent) => { if (hasFiles(event)) { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; } };
  const onDragLeave = (event: DragEvent) => { if (hasFiles(event)) { dragDepth.current = Math.max(0, dragDepth.current - 1); if (!dragDepth.current) setDragging(false); } };
  const onDrop = (event: DragEvent) => { if (hasFiles(event)) { event.preventDefault(); dragDepth.current = 0; setDragging(false); void ingest(Array.from(event.dataTransfer.files)); } };

  const stages: { icon: IconName; tone: string; title: string; value: string; sub: string; filter: MapFilter | null }[] = [
    { icon: "folder", tone: "slate", title: "采集", value: String(counts.acquired), sub: `${sources.length} 上传 · ${draftCandidates.length} 草稿箱`, filter: null },
    { icon: "branch", tone: "blue", title: "识别", value: String(counts.recognized), sub: "Core 按结构与来源判定类型", filter: null },
    { icon: "filter", tone: "amber", title: "查重", value: String(counts.duplicates), sub: "与已存来源、批次内重复比对", filter: "duplicate" },
    { icon: "database", tone: "rose", title: "冲突", value: String(counts.conflicts), sub: "既有外联记录与未匹配草稿", filter: "conflict" },
    { icon: "source", tone: "green", title: "落库", value: String(counts.resolved), sub: `${activeCount} 已有邮箱`, filter: null },
  ];

  return <AppShell className="sm-app" activeRoute="sources">
    <div className="workspace" onDragEnter={onDragEnter} onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}>
      <Topbar className="sm-topbar" breadcrumb="Source mapping" homeHref="#workflow">
        <SearchField label="Search candidates and tasks" value={query} onChange={setQuery} placeholder="搜索候选材料或已解析任务…" iconSize={16} />
      </Topbar>
      <div className="sm-stages" role="list" aria-label="Intake pipeline">
        {stages.map((stage, index) => <Fragment key={stage.title}>
          {index > 0 && <span className="sm-stage-link" aria-hidden="true" />}
          <button role="listitem" className={`sm-stage ${stage.filter && mapFilter === stage.filter ? "is-active" : ""}`}
            onClick={() => setMapFilter(stage.filter && mapFilter === stage.filter ? "all" : stage.filter ?? "all")}
            disabled={!stage.filter} title={stage.filter ? "筛选映射行" : stage.sub}>
            <span className={`sm-stage-icon ${stage.tone}`}><Icon name={stage.icon} size={13} /></span>
            <span className="sm-stage-copy"><b>{stage.title}</b><small>{stage.sub}</small></span>
            <em>{stage.value}</em>
          </button>
        </Fragment>)}
      </div>
      {(notice || displayError) && <div className="sm-notice" role={displayError ? "alert" : "status"}><Icon name={displayError ? "warning" : "check"} size={16} />{displayError || notice}<button aria-label="Dismiss notification" onClick={() => { setNotice(""); setError(""); }}><Icon name="close" size={15} /></button></div>}

      <main className="sm-board">
        <section className="sm-sources">
          <div className="sm-column-heading"><Icon name="folder" size={16} /><h2>候选集</h2><span>{candidates.length}</span></div>
          <div className="sm-observe">
            <button className="primary full" disabled={!gateway.canObserve || observing} onClick={() => void observeMailbox()} title={gateway.canObserve ? "只读读取邮箱证据，草稿箱内容会作为候选出现" : "需要连接当前学生的邮箱标签页"}>
              <Icon name="refresh" size={14} />{observing ? "读取中…" : "读取邮箱草稿箱"}
            </button>
            <p className="sm-observe-state"><i className={`sm-dot ${gateway.state === "connected" ? "ready" : ""}`} />{gateway.studentAddress || "未选择学生邮箱"} · {gateway.state === "connected" ? "网关已连接" : gateway.state === "mismatch" ? "网关连着其他邮箱" : gateway.state === "disconnected" ? "网关未连接" : "网关未启用"}</p>
          </div>
          <div className="sm-source-list">
            {grouped.map((group) => <div className="sm-group" key={group.id}>
              <div className="sm-group-label"><Icon name={group.icon} size={11} /><span>{group.title}</span><b>{group.items.length}</b></div>
              {group.items.map((candidate) => <button key={candidate.key}
                className={`sm-source-card ${candidate.key === focused ? "is-selected" : ""} ${candidate.channel === "draft" ? "is-draft" : ""}`}
                aria-pressed={candidate.key === focused}
                onClick={() => setFocused(candidate.key === focused ? "" : candidate.key)}>
                <span className={`sm-file-icon ${group.color}`}><Icon name={candidate.channel === "draft" ? "mail" : group.icon} size={17} /></span>
                <span className="sm-source-copy">
                  <strong title={candidate.name}>{candidate.name}</strong>
                  <span className="sm-source-meta-line">
                    <em className={`sm-channel ${candidate.channel}`}>{candidate.channel === "draft" ? "草稿箱" : "上传"}</em>
                    <i title={candidate.detail}>{candidate.detail}</i>
                  </span>
                </span>
                {candidate.conflict && <span className="sm-flag is-conflict" title="存在阻塞项">!</span>}
                {candidate.unmatched && !candidate.conflict && <span className="sm-flag" title="尚未匹配">?</span>}
              </button>)}
            </div>)}
            {!loading && !grouped.length && <p className="sm-empty">{query ? "没有匹配的候选。" : "拖入来源集，或读取邮箱草稿箱。"}</p>}
            <button className="sm-add-source" disabled={busy || recognizing || !campaign || !student} onClick={() => fileInput.current?.click()} title="Import a supported .xlsx or .zip source set"><Icon name="plus" size={17} />{recognizing ? "识别中…" : "拖入或选择来源集"}<span>{recognizing ? "请稍候" : "浏览文件"}</span></button>
          </div>
        </section>

        <section className="sm-mapping">
          {review ? <>
            <div className="sm-column-heading"><Icon name="branch" size={16} /><h2>识别批次 · {review.rows.length} 个来源</h2>
              <button className="sm-review-close" aria-label="取消本次识别" disabled={busy} onClick={() => setReview(null)}><Icon name="close" size={15} /></button></div>
            <div className="sm-review-rows">
              {review.rows.map((row) => {
                const option = typeOption(row.type);
                const revised = row.type !== row.result.type;
                const tone = confidenceTone(row.result.confidence);
                const summary = identitySummary({ ...row.result, type: row.type });
                const evidence = row.result.reasons[0] ?? "无结构证据，需人工判定。";
                return <article key={row.key} className={`sm-review-row ${row.included ? "is-included" : "is-excluded"}`}>
                  <div className="sm-review-head">
                    <label className="sm-review-check" title={row.included ? "排除" : "纳入"}>
                      <input type="checkbox" checked={row.included} disabled={busy} onChange={() => toggleRow(row.key)} />
                    </label>
                    <span className={`sm-review-icon ${row.included ? "" : "is-off"}`}><Icon name={option.icon} size={15} /></span>
                    <strong title={row.name}>{row.name}{revised && <b className="sm-revised-tag">已修订</b>}</strong>
                    <span className={`sm-review-confidence ${tone}`}><i className={`sm-dot ${tone === "ready" ? "ready" : ""}`} />{row.result.confidence}</span>
                  </div>
                  <small className="sm-review-meta">{row.container && <span className="sm-container-tag">{row.container}</span>}{summary ? `${summary} · ` : ""}{Math.max(1, Math.round(row.size / 1024))} KB</small>
                  <em title={[...row.result.reasons, ...row.result.cautions].join("\n")}>{evidence}</em>
                  <select aria-label={`修订 ${row.name} 的类型`} value={row.type} disabled={busy} onChange={(event) => setRowType(row.key, event.target.value as RecognitionTypeId)}>
                    <optgroup label="产生外联工作">
                      {recognitionTypeOptions.filter((item) => item.actionable).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                    </optgroup>
                    <optgroup label="参考 / 待判定">
                      {recognitionTypeOptions.filter((item) => !item.actionable).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                    </optgroup>
                  </select>
                </article>;
              })}
            </div>
            <div className="sm-review-footer">
              <div className="sm-review-note" role={importability.ok ? "status" : "alert"}>
                {importability.ok
                  ? <><Icon name="check" size={14} /><span>{includedCount} / {review.rows.length} 将导入{importability.advisories.length ? ` · ${importability.advisories[0]}` : ""}</span></>
                  : <><Icon name="warning" size={14} /><span title={importability.issues.join("\n")}>{importability.issues[0]}{importability.issues.length > 1 ? ` (+${importability.issues.length - 1})` : ""}</span></>}
              </div>
              <div className="sm-review-actions">
                <button className="sm-button" disabled={busy} onClick={() => setReview(null)}>取消</button>
                <button className="primary" disabled={busy || !importability.ok} onClick={() => void confirmReviewImport()}>{busy ? "导入中…" : `导入 ${includedCount} 个来源`}</button>
              </div>
            </div>
          </> : <>
            <div className="sm-column-heading"><Icon name="link" size={16} /><h2>映射工作台</h2>
              <div className="sm-map-filters" role="group" aria-label="Filter mapping rows">
                <button className={mapFilter === "all" ? "is-on" : ""} onClick={() => setMapFilter("all")}>全部 {mappingRows.length}</button>
                <button className={mapFilter === "duplicate" ? "is-on" : ""} onClick={() => setMapFilter("duplicate")}>重复 {counts.duplicates}</button>
                <button className={mapFilter === "conflict" ? "is-on" : ""} onClick={() => setMapFilter("conflict")}>冲突 {counts.conflicts}</button>
                <button className={mapFilter === "unmatched" ? "is-on" : ""} onClick={() => setMapFilter("unmatched")}>未匹配 {candidates.filter((candidate) => candidate.unmatched).length}</button>
              </div></div>
            <div className="sm-flow">
              {mappingRows.map((candidate) => {
                if (candidate.channel === "draft" && candidate.observation) {
                  const draft = candidate.observation;
                  const checked = selectedDrafts.includes(draft.id);
                  return <article key={candidate.key} className={`sm-map-row ${draft.taskId ? "" : "is-unmatched"} ${candidate.key === focused ? "is-focused" : ""}`}>
                    <div className="sm-map-side">
                      <span className="sm-compare-tag">草稿箱</span>
                      <strong title={draft.subject}>{draft.subject || "(no subject)"}</strong>
                      <small>{draft.recipient || "无可用收件人"}{draft.attachmentCount ? ` · ${draft.attachmentCount} 附件` : ""}{draft.bodyAvailable ? "" : " · 正文未采集"}</small>
                    </div>
                    <span className="sm-map-arrow" aria-hidden="true"><Icon name="link" size={13} /></span>
                    <div className="sm-map-side">
                      <span className="sm-compare-tag">数据库</span>
                      <strong>{draft.taskId ? draft.supervisor || "已匹配任务" : "无匹配任务"}</strong>
                      <small>{draft.taskId ? "将建立 Preparation" : "先导入导师名单以建立任务"}</small>
                    </div>
                    <label className="sm-map-pick" title={draft.taskId && draft.bodyAvailable ? "纳入本次导入" : "该草稿尚不可导入"}>
                      <input type="checkbox" checked={checked} disabled={!draft.taskId || !draft.bodyAvailable}
                        onChange={() => setSelectedDrafts((current) => checked ? current.filter((id) => id !== draft.id) : [...current, draft.id])} />
                    </label>
                  </article>;
                }
                const source = candidate.source!;
                const finding = findingsBySource.get(source.id);
                return <article key={candidate.key} className={`sm-map-row ${candidate.conflict ? "is-conflict" : ""} ${candidate.key === focused ? "is-focused" : ""}`}
                  onFocus={() => setFocused(candidate.key)}>
                  <div className="sm-map-side">
                    <span className="sm-compare-tag">上传</span>
                    <strong title={source.name}>{source.name}</strong>
                    <small>{Math.max(1, Math.round(source.size / 1024))} KB{candidate.confidence ? ` · ${candidate.confidence}` : ""}</small>
                  </div>
                  <span className="sm-map-arrow" aria-hidden="true"><Icon name="link" size={13} /></span>
                  <div className="sm-map-side">
                    <span className="sm-compare-tag">映射</span>
                    <select aria-label={`重新映射 ${source.name}`} value={typeOfSource(source)}
                      disabled={busy || !heldFiles.includes(source.name)}
                      title={heldFiles.includes(source.name) ? "改动会以原字节重新导入（幂等）" : "原始字节不在本次会话，需重新拖入"}
                      onChange={(event) => void remapSource(source, event.target.value as RecognitionTypeId)}>
                      <optgroup label="产生外联工作">
                        {recognitionTypeOptions.filter((item) => item.actionable).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                      </optgroup>
                      <optgroup label="参考 / 待判定">
                        {recognitionTypeOptions.filter((item) => !item.actionable).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                      </optgroup>
                    </select>
                    <small>{source.recognition?.reasons[0] ?? finding?.detail ?? human(source.category)}</small>
                  </div>
                </article>;
              })}
              {!loading && !mappingRows.length && <p className="sm-empty">{candidates.length ? "该筛选下没有映射行。" : "拖入来源集或读取邮箱草稿箱后，这里会出现映射行。"}</p>}
            </div>
            <div className="sm-review-footer">
              <div className="sm-review-note" role="status">
                <Icon name="shield" size={14} />
                <span>{importableDrafts.length
                  ? `${importableDrafts.length} 封草稿可导入为来源材料`
                  : lastImport
                    ? `上次导入 ${lastImport.rows} 行，${lastImport.duplicate} 重复，${lastImport.conflicts} 冲突`
                    : "草稿箱与上传是同一条管线：识别 → 查重 → 冲突 → 落库"}</span>
              </div>
              <div className="sm-review-actions">
                <button className="primary" disabled={busy || !importableDrafts.length} onClick={() => void importDrafts()}>
                  {busy ? "导入中…" : `导入 ${importableDrafts.length} 封草稿`}</button>
              </div>
            </div>
          </>}
        </section>

        <section className="sm-output">
          <div className="sm-column-heading"><Icon name="source" size={16} /><h2>Outreach tasks</h2><span>{tasks.length}</span>
            <label className="sm-task-filter"><select aria-label="Filter resolved tasks" value={taskFilter} onChange={(event) => setTaskFilter(event.target.value as TaskFilter)}><option value="all">All</option><option value="active">Active</option><option value="incomplete">Missing email</option></select></label></div>
          <div className="sm-task-list">
            {tasks.map((item) => {
              const active = Boolean(item.recipient_addresses.length);
              const preparation = item.preparation;
              const attachments = preparation?.attachment_count ?? 0;
              const observed = observedByTask.get(item.task_id) ?? 0;
              const expanded = item.task_id === expandedTaskId;
              return <div key={item.task_id} className={`sm-task-block ${active ? "" : "is-incomplete"} ${expanded ? "is-open" : ""}`}>
                <button className="sm-task-row" aria-expanded={expanded} onClick={() => setExpandedTaskId(expanded ? "" : item.task_id)}>
                  <span className="sm-task-row-icon"><Icon name={preparation ? "file" : "user"} size={15} /></span>
                  <span className="sm-task-row-copy"><strong>{item.supervisor_name}</strong><small>{item.institution_name} · {item.recipient_addresses.join(", ") || "no email identified"}</small></span>
                  {observed > 0 && <span className="sm-task-badge is-observed"><Icon name="mail" size={12} />{observed}</span>}
                  <span className={`sm-task-badge ${preparation ? "" : "is-off"}`}><Icon name="file" size={12} />{preparation ? "Prepared" : "No draft"}</span>
                  <span className={`sm-task-badge ${attachments ? "" : "is-off"}`}><Icon name="clip" size={12} />{attachments}</span>
                  <span className={`sm-task-pill ${active ? "active" : "incomplete"}`}><i className={`sm-dot ${active ? "ready" : ""}`} />{active ? human(item.message_status) : "Missing email"}</span>
                  <Icon name="chevron" size={13} />
                </button>
                {expanded && <div className="sm-task-detail">
                  <dl className="sm-map-fields">
                    <div><span>Recipient address</span><strong>{item.recipient_addresses.join(", ") || "Missing — no usable address recorded"}</strong></div>
                    <div><span>Active Preparation</span><strong>{preparation ? `${preparation.source_name} · ${preparation.subject || "subject required"}` : "No supported draft associated"}</strong></div>
                    <div><span>Mailbox identity</span><strong>{studentMailbox?.address ?? scope?.mailbox ?? "—"}</strong></div>
                  </dl>
                  <p className="sm-task-exceptions">{taskQuery.isLoading && !taskDetail
                    ? "Loading task evidence…"
                    : taskDetail?.task.exceptions.length
                      ? `Exceptions: ${taskDetail.task.exceptions.map((entry) => human(entry.code)).join(", ")}`
                      : "No exceptions recorded."}</p>
                  <button className="primary full" onClick={() => { window.location.hash = "#review"; }}>打开 Readiness 审查</button>
                </div>}
              </div>;
            })}
            {!loading && !tasks.length && <div className="sm-empty"><Icon name="search" size={25} /><p>{data?.tasks.length ? "没有匹配的外联任务。" : "导入来源集或草稿箱邮件后，这里会出现任务。"}</p><button className="sm-button" onClick={() => { setQuery(""); setTaskFilter("all"); }}>Clear task filters</button></div>}
          </div>
        </section>
      </main>
      {dragging && <div className="sm-drop-overlay" aria-hidden="true"><div className="sm-drop-card"><span className="sm-drop-icon"><Icon name="file" size={26} /><Icon name="mail" size={26} /></span><strong>放入即由 Core 识别</strong><span>上传文件与邮箱草稿走同一条管线：识别 → 查重 → 冲突 → 落库。类型可在中列修订后再导入。</span></div></div>}
    </div>
    <input ref={fileInput} type="file" multiple accept=".xlsx,.zip,.docx,.pdf,.csv" hidden onChange={(event) => { void ingest(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
  </AppShell>;
}

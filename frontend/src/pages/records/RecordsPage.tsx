import { useMemo, useState, type ReactNode } from "react";
import { AppShell, Topbar } from "../../app/shell";
import { PageHeader } from "../../app/page-header";
import { useWorkspaceScope } from "../../app/scope";
import { useCoreQuery } from "../../core/data";
import Icon, { type IconName } from "../../shared/Icon";
import {
  buildLineage,
  buildTaskRows,
  taskHeadline,
  type LineNode,
  type TaskLineage,
  type TaskRowView,
  type Tone,
} from "./records-model";
import {
  duplicateState,
  followUpState,
  formatTime,
  messageState,
} from "./presentation";
import "./Records.css";

const toneClass = (tone: Tone) => `rc-tone-${tone}`;

function flattenNodes(lineage: TaskLineage): LineNode[] {
  const out: LineNode[] = [];
  const walk = (nodes: LineNode[]) => {
    for (const node of nodes) {
      out.push(node);
      if (node.branch) walk(node.branch);
    }
  };
  lineage.groups.forEach((g) => walk(g.nodes));
  walk(lineage.replies);
  walk(lineage.observations);
  walk(lineage.sources);
  return out;
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <details className="rc-json">
      <summary>
        <Icon name="database" size={13} /> {title}
      </summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function Field({ label, value, mono = false }: { label: string; value: unknown; mono?: boolean }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="rc-field">
      <dt>{label}</dt>
      <dd className={mono ? "rc-mono" : ""}>{String(value)}</dd>
    </div>
  );
}

function NodeDetail({ node }: { node: LineNode }) {
  const data = node.data as Record<string, unknown>;
  const fields: ReactNode[] = [];
  const push = (label: string, key: string, mono = false) => {
    if (data[key] !== undefined && data[key] !== null && data[key] !== "")
      fields.push(<Field key={`${key}-${fields.length}`} label={label} value={data[key]} mono={mono} />);
  };
  if (node.kind === "version") {
    push("Preparation ID", "id", true);
    push("Sender", "sender");
    push("Recipient", "recipient");
    push("Status", "status");
    push("Action kind", "action_kind");
    push("Superseded by", "superseded_by", true);
    push("Ready", "ready");
    push("Source", (data.source as { name?: string })?.name ?? "");
  }
  if (node.kind === "confirmation" || node.kind === "cancellation") {
    push("Confirmation ID", "id", true);
    push("Status", "status");
    push("Invalidated reason", "invalidated_reason");
    push("Confirmed at", "confirmed_at");
    push("Content digest", "content_digest", true);
    push("Attachments digest", "attachments_digest", true);
    push("Preparation", "preparation_id", true);
  }
  if (node.kind === "attempt") {
    push("Attempt ID", "id", true);
    push("Sequence", "sequence");
    push("State", "state");
    push("Phase", "phase");
    push("Intent recorded at", "intent_at");
    push("Submission started at", "submission_started_at");
    push("Outcome observed at", "outcome_observed_at");
    push("Updated at", "updated_at");
    const request = data.request as { sender?: string; recipient?: string; subject?: string } | undefined;
    if (request) {
      fields.push(<Field key="req-sender" label="Sender" value={request.sender} />);
      fields.push(<Field key="req-recipient" label="Recipient" value={request.recipient} />);
      fields.push(<Field key="req-subject" label="Subject" value={request.subject} />);
    }
    push("Confirmation", "confirmation_id", true);
    push("Sent record", "sent_record_id", true);
  }
  if (node.kind === "schedule") {
    push("Schedule ID", "id", true);
    push("State", "state");
    push("External ID", "external_id", true);
    push("Mailbox", "mailbox_address");
    push("Scheduled (UTC)", "scheduled_utc");
    push("Replaces schedule", "replaces_schedule_id", true);
    push("Created at", "created_at");
    push("Updated at", "updated_at");
    push("Confirmation", "confirmation_id", true);
  }
  if (node.kind === "sent") {
    push("Sent record ID", "id", true);
    push("Sender", "sender");
    push("Recipient", "recipient");
    push("Reference", "reference", true);
    push("Action kind", "action_kind");
    push("Follows sent record", "follows_sent_record_id", true);
    push("Attempt", "attempt_id", true);
    push("Preparation", "preparation_id", true);
  }
  if (node.kind === "duplicate") {
    push("Check ID", "id", true);
    push("Finding", "finding");
    push("Basis", "basis");
    push("Detail", "detail");
    push("Review required", "review_required");
    push("Checked at", "checked_at");
  }
  if (node.kind === "followup") {
    push("Action ID", "id", true);
    push("Sequence", "sequence");
    push("Status", "status");
    push("Due at", "due_at");
    push("Created at", "created_at");
    push("Detail", "detail");
    push("Follows sent record", "follows_sent_record_id", true);
    push("Preparation", "preparation_id", true);
  }
  if (node.kind === "reply") {
    push("Association ID", "id", true);
    push("Status", "status");
    push("Reply kind", "reply_kind");
    push("Basis", "basis");
    push("Matched rule", "matched_rule");
    push("Resolved by operator", "resolved_by_operator");
    push("Created at", "created_at");
    push("Resolved at", "resolved_at");
    const observation = data.observation as
      | { platform_reference?: string; counterpart?: string; folder?: string; observed_time?: string }
      | undefined;
    if (observation) {
      fields.push(<Field key="obs-ref" label="Platform reference" value={observation.platform_reference} mono />);
      fields.push(<Field key="obs-peer" label="Counterpart" value={observation.counterpart} />);
      fields.push(<Field key="obs-folder" label="Folder" value={observation.folder} />);
      fields.push(<Field key="obs-time" label="Observed time" value={observation.observed_time} />);
    }
  }
  if (node.kind === "observation-run") {
    push("Observation ID", "id", true);
    push("Adapter", "adapter");
    push("Status", "status");
    push("Observed at", "observed_at");
    push("Detail", "detail");
  }
  if (node.kind === "observation-message") {
    const message = (data.message ?? data) as Record<string, unknown>;
    fields.push(<Field key="m-folder" label="Folder" value={message.folder} />);
    fields.push(<Field key="m-direction" label="Direction" value={message.direction} />);
    fields.push(<Field key="m-ref" label="Platform reference" value={message.platform_reference} mono />);
    fields.push(<Field key="m-peer" label="Counterpart" value={message.counterpart} />);
    fields.push(<Field key="m-time" label="Observed time" value={message.observed_time} />);
    fields.push(<Field key="m-status" label="Status" value={message.status} />);
    fields.push(<Field key="m-ambiguity" label="Ambiguity" value={message.ambiguity} />);
  }
  if (node.kind === "reconciliation") {
    push("Reconciliation ID", "id", true);
    push("Observation", "observation_id", true);
    push("Observed at", "observed_at");
    push("Mailbox", "mailbox_address");
  }
  if (node.kind === "sources") {
    push("Source ID", "id", true);
    push("Import", "import_id", true);
    push("Sheet", "sheet");
    push("Row", typeof data.row === "number" ? String(data.row + 1) : "");
    push("Size (bytes)", "size");
    push("SHA-256", "sha256", true);
  }
  return (
    <div className="rc-node-detail">
      <dl>{fields}</dl>
      {node.kind === "sent" && typeof data.body === "string" && (
        <section className="rc-frozen-body">
          <h4><Icon name="database" size={13} /> Frozen message body</h4>
          <pre>{data.body}</pre>
        </section>
      )}
      {node.kind === "version" && Array.isArray(data.corrections) && (data.corrections as unknown[]).length > 0 && (
        <JsonBlock title="Correction history" value={data.corrections} />
      )}
      {node.kind === "version" && Array.isArray(data.transformations) && (data.transformations as unknown[]).length > 0 && (
        <JsonBlock title="Transformations" value={data.transformations} />
      )}
      {node.kind === "version" && Array.isArray(data.readiness_findings) && (
        <JsonBlock title="Readiness findings" value={data.readiness_findings} />
      )}
      {node.kind === "version" && Array.isArray(data.attachment_slots) && (
        <JsonBlock title="Attachment slots" value={data.attachment_slots} />
      )}
      {node.kind === "sent" && Array.isArray(data.attachments) && (
        <JsonBlock title="Frozen attachments" value={data.attachments} />
      )}
      {node.kind === "attempt" && data.evidence !== undefined && data.evidence !== null && (
        <JsonBlock title="Outcome evidence" value={data.evidence} />
      )}
      {node.kind === "schedule" && <JsonBlock title="Platform evidence" value={data.evidence} />}
      {node.kind === "duplicate" && <JsonBlock title="Evidence coverage" value={data.evidence_coverage} />}
      {node.kind === "duplicate" && Array.isArray(data.matches) && (data.matches as unknown[]).length > 0 && (
        <JsonBlock title="Recorded matches" value={data.matches} />
      )}
      {node.kind === "reply" && Array.isArray(data.candidates) && (data.candidates as unknown[]).length > 0 && (
        <JsonBlock title="Candidate tasks" value={data.candidates} />
      )}
      {node.kind === "observation-run" && (
        <JsonBlock title="Coverage and capabilities" value={{ coverage: data.evidence_coverage, capabilities: data.capabilities }} />
      )}
      {node.kind === "observation-message" && (data.message as { evidence?: unknown })?.evidence !== undefined && (
        <JsonBlock title="Observed message evidence" value={(data.message as { evidence?: unknown }).evidence} />
      )}
      {node.kind === "reconciliation" && (data.summary !== undefined || Array.isArray(data.findings)) && (
        <JsonBlock title="Reconciliation detail" value={{ summary: data.summary, findings: data.findings }} />
      )}
      {node.kind === "sources" && data.evidence !== undefined && (
        <JsonBlock title="Association evidence" value={data.evidence} />
      )}
    </div>
  );
}

function TreeNode({ node, selectedKey, onSelect, depth = 0 }: {
  node: LineNode;
  selectedKey: string;
  onSelect: (node: LineNode) => void;
  depth?: number;
}) {
  const selected = selectedKey === node.key;
  return (
    <div className={`rc-tree-entry ${node.faint ? "rc-faint" : ""}`}>
      <button
        className={`rc-node-row ${toneClass(node.tone)} ${selected ? "rc-selected" : ""} ${node.terminal ? "rc-terminal" : ""}`}
        onClick={() => onSelect(node)}
      >
        <span className={`rc-marker ${node.struck ? "rc-struck" : ""}`}>
          <Icon name={node.icon} size={node.terminal ? 17 : 14} />
          {node.version && <span className="rc-version-badge">{node.version}</span>}
        </span>
        <span className="rc-node-text">
          <span className={`rc-node-title ${node.struck ? "rc-line-through" : ""}`}>{node.title}</span>
          {node.subtitle && <span className="rc-node-sub">{node.subtitle}</span>}
          <span className="rc-node-tags">
            {node.tags.map((tag, i) => (
              <span key={i} className={`rc-tag ${tag.tone ? toneClass(tag.tone) : ""}`}>{tag.label}</span>
            ))}
          </span>
        </span>
        <span className="rc-node-time">{formatTime(node.time)}</span>
      </button>
      {node.branch && node.branch.length > 0 && (
        <div className="rc-branch">
          {node.branch.map((child) => (
            <TreeNode key={child.key} node={child} selectedKey={selectedKey} onSelect={onSelect} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function SectionLabel({ icon, title, count }: { icon: IconName; title: string; count: number }) {
  return (
    <div className="rc-section-label">
      <Icon name={icon} size={13} />
      <strong>{title}</strong>
      <span>{count}</span>
    </div>
  );
}

export default function RecordsPage() {
  const { scope } = useWorkspaceScope();
  const campaign = scope?.campaignId ?? "";
  const workspaceQuery = useCoreQuery("records_workspace", { campaign_id: campaign }, { enabled: Boolean(campaign) });
  const data = workspaceQuery.data;
  const loading = workspaceQuery.isLoading;
  const error = workspaceQuery.error?.message || "";
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selectedTask, setSelectedTask] = useState("");
  const detailQuery = useCoreQuery("records_task", { task_id: selectedTask }, { enabled: Boolean(selectedTask) });
  const detail = detailQuery.data;
  const detailLoading = detailQuery.isLoading;
  const [selectedNodeKey, setSelectedNodeKey] = useState("");

  const rows = useMemo(() => (data ? buildTaskRows(data) : []), [data]);
  const filtered = useMemo(
    () =>
      rows.filter((item) => {
        if (statusFilter !== "all" && item.row.message_status !== statusFilter) return false;
        const haystack = `${item.subject} ${item.row.supervisor_name} ${item.row.institution_name} ${item.row.mailbox} ${item.row.student_name}`.toLowerCase();
        return haystack.includes(query.toLowerCase());
      }),
    [rows, query, statusFilter],
  );

  const lineage = useMemo(() => (detail ? buildLineage(detail) : null), [detail]);
  const allNodes = useMemo(() => (lineage ? flattenNodes(lineage) : []), [lineage]);
  const defaultNode =
    allNodes.find((n) => n.kind === "sent") ??
    allNodes.find((n) => n.kind === "version") ??
    allNodes[0] ??
    null;
  const effectiveKey = selectedNodeKey || defaultNode?.key || "";
  const selectedNode = allNodes.find((n) => n.key === effectiveKey) ?? null;

  const selectedTaskRow = data?.tasks.find((t) => t.task_id === selectedTask) ?? null;
  const counts = data?.counts;
  const statusChips: { key: string; label: string; value: number; tone: Tone }[] = counts
    ? [
        { key: "all", label: "All tasks", value: counts.tasks, tone: "blue" },
        ...Object.entries(counts.message_status)
          .filter(([, value]) => value > 0)
          .map(([key, value]) => ({ key, label: messageState(key).label, value, tone: messageState(key).tone })),
      ]
    : [];

  const selectNode = (node: LineNode) => setSelectedNodeKey(node.key);
  const headline = taskHeadline(detail);

  const evidenceCards = lineage && detail
    ? [
        { icon: "database" as IconName, label: "Sent records", value: detail.sent_records.length, node: allNodes.find((n) => n.kind === "sent") },
        { icon: "check" as IconName, label: "Confirmations", value: detail.confirmations.length, node: allNodes.find((n) => n.kind === "confirmation" || n.kind === "cancellation") },
        { icon: "clock" as IconName, label: "Schedules", value: detail.schedules.length, node: allNodes.find((n) => n.kind === "schedule") },
        { icon: "send" as IconName, label: "Attempts", value: detail.execution_attempts.length, node: allNodes.find((n) => n.kind === "attempt") },
        { icon: "mail" as IconName, label: "Observations", value: detail.mailbox.observations.length, node: lineage.observations[0] },
        { icon: "shield" as IconName, label: "Reconciliations", value: detail.mailbox.reconciliations.length, node: lineage.observations.find((n) => n.kind === "reconciliation") },
        { icon: "reply" as IconName, label: "Replies", value: detail.reply_associations.length, node: lineage.replies[0] },
        { icon: "file" as IconName, label: "Sources", value: detail.sources.length, node: lineage.sources[0] },
      ]
    : [];

  return (
    <AppShell
      className="records-page"
      activeRoute="records"
    >
      <div className="workspace">
        <Topbar breadcrumb="Records" homeHref="#workflow">
          <span className="rc-top-note"><Icon name="book" size={15} /> Immutable evidence ledger</span>
        </Topbar>
        <PageHeader
          eyebrow="Historical evidence"
          title="Records"
          subtitle="lineage &amp; traceability"
          meta={<span className="rc-readonly-badge"><Icon name="shield" size={13} /> Read-only · no editing or execution</span>}
        />
        <section className="rc-filters" aria-label="Evidence filters">
          <div className="rc-chips">
            {statusChips.map((chip) => (
              <button
                key={chip.key}
                aria-pressed={statusFilter === chip.key}
                className={`rc-chip ${toneClass(chip.tone)} ${statusFilter === chip.key ? "rc-chip-active" : ""}`}
                onClick={() => setStatusFilter(chip.key)}
              >
                <i />{chip.label}<b>{chip.value}</b>
              </button>
            ))}
          </div>
          <label className="rc-search">
            <Icon name="search" size={15} />
            <input
              aria-label="Search records"
              placeholder="Search subject, supervisor, institution, mailbox…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
        </section>
        {error && (
          <div className="rc-notice rc-error" role="alert">
            <Icon name="warning" size={15} /><span>{error}</span>
            <button onClick={() => void workspaceQuery.refresh()}>Retry</button>
          </div>
        )}
        <main className="rc-main">
          <aside className="rc-list" aria-label="Outreach task records">
            <div className="rc-pane-head">
              <strong>Outreach tasks</strong>
              <span>{loading ? "—" : filtered.length}</span>
            </div>
            <div className="rc-list-scroll">
              {loading ? (
                <div className="rc-empty"><Icon name="book" size={26} /><p>Reading retained records…</p></div>
              ) : filtered.length === 0 ? (
                <div className="rc-empty">
                  <span className="rc-empty-icon"><Icon name="book" size={30} /></span>
                  <h2>{rows.length ? "No records match these filters" : "No retained evidence yet"}</h2>
                  <p>{rows.length ? "Try a different status or search term." : "Preparations, confirmations, attempts and observations appear here as the system of record retains them."}</p>
                </div>
              ) : (
                filtered.map((item) => <TaskListRow key={item.row.task_id} item={item} selected={selectedTask === item.row.task_id} onSelect={() => { setSelectedTask(item.row.task_id); setSelectedNodeKey(""); }} />)
              )}
            </div>
          </aside>
          <section className="rc-lineage" aria-label="Version lineage">
            {!selectedTask ? (
              <div className="rc-empty rc-center-empty">
                <span className="rc-empty-icon"><Icon name="branch" size={34} /></span>
                <h2>Select a task to inspect its evidence chain</h2>
                <p>Version lineage, confirmations, execution attempts, replacements, cancellations, reconciliations and immutable sent records — every node opens the retained evidence.</p>
              </div>
            ) : detailLoading ? (
              <div className="rc-empty rc-center-empty"><Icon name="refresh" size={28} /><p>Loading the full evidence chain…</p></div>
            ) : lineage && detail ? (
              <div className="rc-lineage-scroll">
                <div className="rc-lineage-head">
                  <div className="rc-lineage-title">
                    <span className="rc-title-icon"><Icon name="mail" size={18} /></span>
                    <div>
                      <h2>{headline}</h2>
                      <p>{detail.task.supervisor.name} · {detail.task.institution.name} · {detail.task.mailbox.address}</p>
                    </div>
                  </div>
                  <div className="rc-state-chips">
                    <span className={`rc-chip sm ${toneClass(messageState(detail.message_status).tone)}`}><i />{messageState(detail.message_status).label}</span>
                    {selectedTaskRow && <span className={`rc-chip sm ${toneClass(duplicateState(selectedTaskRow.duplicate_status).tone)}`}><i />{duplicateState(selectedTaskRow.duplicate_status).label}</span>}
                    {selectedTaskRow && <span className={`rc-chip sm ${toneClass(followUpState(selectedTaskRow.follow_up).tone)}`}><i />{followUpState(selectedTaskRow.follow_up).label}</span>}
                  </div>
                </div>
                <div className="rc-track">
                  {lineage.groups.map((group) => (
                    <div className="rc-group" key={group.preparation.id}>
                      <SectionLabel icon="file" title={`${group.label} · ${group.preparation.status === "superseded" ? "superseded version" : "current version"}`} count={group.nodes.length} />
                      {group.nodes.map((node) => (
                        <TreeNode key={node.key} node={node} selectedKey={selectedNode?.key ?? ""} onSelect={selectNode} />
                      ))}
                    </div>
                  ))}
                  {lineage.replies.length > 0 && (
                    <div className="rc-group">
                      <SectionLabel icon="reply" title="External replies" count={lineage.replies.length} />
                      {lineage.replies.map((node) => (
                        <TreeNode key={node.key} node={node} selectedKey={selectedNode?.key ?? ""} onSelect={selectNode} />
                      ))}
                    </div>
                  )}
                  {lineage.observations.length > 0 && (
                    <div className="rc-group">
                      <SectionLabel icon="mail" title="Mailbox observations & reconciliations" count={lineage.observations.length} />
                      {lineage.observations.map((node) => (
                        <TreeNode key={node.key} node={node} selectedKey={selectedNode?.key ?? ""} onSelect={selectNode} />
                      ))}
                    </div>
                  )}
                  {lineage.sources.length > 0 && (
                    <div className="rc-group">
                      <SectionLabel icon="database" title="Source provenance" count={lineage.sources.length} />
                      {lineage.sources.map((node) => (
                        <TreeNode key={node.key} node={node} selectedKey={selectedNode?.key ?? ""} onSelect={selectNode} />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="rc-empty rc-center-empty"><Icon name="warning" size={28} /><p>Evidence chain unavailable.</p></div>
            )}
          </section>
          <aside className="rc-detail" aria-label="Selected evidence detail">
            {selectedNode && lineage ? (
              <div className="rc-detail-scroll">
                <div className={`rc-detail-head ${toneClass(selectedNode.tone)}`}>
                  <span className="rc-detail-icon"><Icon name={selectedNode.icon} size={18} /></span>
                  <div>
                    <h3>{selectedNode.title}</h3>
                    <p>{selectedNode.subtitle || "Retained evidence record"}</p>
                  </div>
                </div>
                <div className="rc-detail-time">
                  <Icon name="clock" size={13} /> {formatTime(selectedNode.time)}
                </div>
                <NodeDetail node={selectedNode} />
                <div className="rc-cards-title"><Icon name="book" size={13} /> Evidence index</div>
                <div className="rc-cards">
                  {evidenceCards.map((card) => (
                    <button
                      key={card.label}
                      className="rc-card"
                      disabled={!card.node}
                      onClick={() => card.node && selectNode(card.node)}
                      title={card.node ? `Inspect ${card.label}` : `No ${card.label.toLowerCase()} retained`}
                    >
                      <span className="rc-card-icon"><Icon name={card.icon} size={15} /></span>
                      <span className="rc-card-text"><strong>{card.label}</strong><small>{card.value} retained</small></span>
                    </button>
                  ))}
                </div>
                <p className="rc-ledger-note">
                  <Icon name="database" size={13} /> Sent Records are immutable: content and attachment bytes stay frozen exactly as confirmed by the mailbox.
                </p>
              </div>
            ) : (
              <div className="rc-empty">
                <span className="rc-empty-icon"><Icon name="shield" size={28} /></span>
                <h2>Evidence inspector</h2>
                <p>Select any node in the lineage to inspect its retained fields, timestamps, digests and raw evidence.</p>
              </div>
            )}
          </aside>
        </main>
        <footer className="rc-footer">
          <span>{filtered.length} of {rows.length} task records</span>
          <span>{data ? `Ledger generated ${formatTime(data.generated_at)}` : "Read-only view"}</span>
          <span>Observations are evidence, not sending authority</span>
        </footer>
      </div>
    </AppShell>
  );
}

function TaskListRow({ item, selected, onSelect }: { item: TaskRowView; selected: boolean; onSelect: () => void }) {
  const meta = messageState(item.row.message_status);
  const counters: { icon: IconName; value: number; title: string; tone?: Tone }[] = [
    { icon: "file", value: item.versions, title: "Versions" },
    { icon: "check", value: item.confirmations, title: "Confirmations" },
    { icon: "send", value: item.attempts, title: "Attempts" },
    { icon: "database", value: item.sent, title: "Sent records", tone: "green" },
    { icon: "clock", value: item.schedules, title: "Schedules", tone: "purple" },
    { icon: "stop", value: item.cancellations, title: "Cancellations", tone: "rose" },
    { icon: "mail", value: item.observations, title: "Observations", tone: "blue" },
    { icon: "reply", value: item.replies, title: "Replies" },
  ];
  return (
    <button className={`rc-task ${selected ? "rc-task-selected" : ""}`} onClick={onSelect}>
      <span className={`rc-task-dot ${toneClass(meta.tone)}`} />
      <span className="rc-task-body">
        <strong className="rc-task-subject">{item.subject}</strong>
        <small>{item.row.supervisor_name} · {item.row.institution_name}</small>
        <span className="rc-task-mail"><Icon name="user" size={11} />{item.row.student_name} · {item.row.mailbox}</span>
        <span className="rc-task-counters">
          {counters.filter((c) => c.value > 0).map((c) => (
            <span key={c.title} className={`rc-counter ${c.tone ? toneClass(c.tone) : ""}`} title={c.title}>
              <Icon name={c.icon} size={11} />{c.value}
            </span>
          ))}
        </span>
      </span>
      <span className={`rc-task-state ${toneClass(meta.tone)}`}>{meta.label}</span>
    </button>
  );
}

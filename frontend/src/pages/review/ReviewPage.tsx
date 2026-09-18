import { useEffect, useMemo, useState } from "react";
import { AppShell, Topbar } from "../../app/shell";
import { PageHeader } from "../../app/page-header";
import { navigate } from "../../app/routes";
import { useWorkspaceScope } from "../../app/scope";
import { useCoreQuery } from "../../core/data";
import { core, human, type ReviewRow } from "../../core";
import Icon from "../../shared/Icon";
import "./Review.css";

type Tone = "blocked" | "attention" | "ready";
type Focus = "recipient" | "subject" | "attachment" | "duplicate" | "source" | "exception";

function relevantExceptions(row: ReviewRow) {
  return row.task.exceptions.filter((exception) =>
    row.preparation.action_kind !== "follow_up" || exception.code !== "prior_outreach_conflict");
}

function toneOf(row: ReviewRow): Tone {
  if (row.preparation.readiness_findings.some((finding) => finding.blocking)) return "blocked";
  if (relevantExceptions(row).some((exception) => exception.blocking)) return "blocked";
  if (row.preparation.attachment_slots.some((slot) => !slot.attachment)) return "attention";
  return "ready";
}

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(-2).map((part) => part[0]).join("").toUpperCase();
}

function Signal({ tone, children }: { tone: Tone; children?: React.ReactNode }) {
  return <span className={`rv-signal ${tone}`}><Icon name={tone === "ready" ? "check" : tone === "blocked" ? "stop" : "warning"} size={13} />{children}</span>;
}

export default function ReviewPage() {
  const { scope } = useWorkspaceScope();
  const campaign = scope?.campaignId ?? "";
  const queryState = useCoreQuery("review_workspace", { campaign_id: campaign }, { enabled: Boolean(campaign) });
  const data = queryState.data;
  const [selectedId, setSelectedId] = useState("");
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [focus, setFocus] = useState<Focus>("source");
  const [panel, setPanel] = useState("message");
  const [mobile, setMobile] = useState("message");
  const [reviewed, setReviewed] = useState<string[]>([]);
  const [subject, setSubject] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loading = queryState.isLoading;
  const displayError = error || queryState.error?.message || "";
  const effectiveSelectedId = data?.rows.some((item) => item.preparation.id === selectedId)
    ? selectedId : data?.rows[0]?.preparation.id || "";
  const row = data?.rows.find((item) => item.preparation.id === effectiveSelectedId) ?? null;
  useEffect(() => {
    // Reset the editable field when the operator selects a different Preparation.
    // oxlint-disable-next-line react/set-state-in-effect
    setSubject(row?.preparation.subject ?? "");
  }, [row?.preparation.id, row?.preparation.subject]);

  const entries = useMemo(() => (data?.rows ?? []).filter((item) => {
    const tone = toneOf(item);
    return (filter === "all" || tone === filter)
      && `${item.task.supervisor.name} ${item.task.institution.name} ${item.preparation.subject}`
        .toLowerCase().includes(query.toLowerCase());
  }), [data, filter, query]);
  const ready = (data?.rows ?? []).filter((item) => toneOf(item) === "ready").length;
  const tone = row ? toneOf(row) : "blocked";
  const blocking = row?.preparation.readiness_findings.filter((finding) => finding.blocking) ?? [];
  const taskExceptions = row ? relevantExceptions(row) : [];
  const taskBlocking = taskExceptions.filter((exception) => exception.blocking);
  const blockerCount = blocking.length + taskBlocking.length;
  const slot = row?.preparation.attachment_slots.find((item) => !item.attachment)
    ?? row?.preparation.attachment_slots[0] ?? null;
  const recordedRecipient = row?.task.supervisor.addresses[0] ?? "";

  async function mutate(action: () => Promise<unknown>, message: string) {
    setBusy(true); setError(""); setNotice("");
    try {
      await action();
      setNotice(message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Core rejected the change");
    } finally { setBusy(false); }
  }

  function choose(item: ReviewRow) {
    setSelectedId(item.preparation.id);
    const first = item.preparation.readiness_findings[0]?.code;
    setFocus(first === "recipient_conflict" || first === "invalid_recipient" ? "recipient"
      : first === "missing_subject" ? "subject"
        : item.preparation.attachment_slots.some((attachment) => !attachment.attachment) ? "attachment" : "source");
    setNotice("");
  }

  return <AppShell className="review-page" activeRoute="review">
    <div className="workspace">
      <Topbar breadcrumb="Review" homeHref="#workflow">
        <span className="rv-demo"><span /> CORE WORKSPACE</span>
      </Topbar>
      <PageHeader
        className="rv-heading"
        eyebrow="Prepare with confidence"
        title="Readiness workbench"
        badge="Review"
        meta={<div className="rv-heading-count"><strong>{ready}<span> / {data?.rows.length ?? 0}</span></strong><span>preparations ready</span></div>}
      />
      <div className="rv-mobile-tabs" aria-label="Workbench panels">{["queue", "message", "checks"].map((tab) => <button key={tab} className={mobile === tab ? "active" : ""} onClick={() => setMobile(tab)}>{tab === "queue" ? "Preparations" : tab === "message" ? "Message" : "Readiness"}</button>)}</div>
      {displayError && <div className="rv-status-banner blocked" role="alert"><Signal tone="blocked" /><div><strong>{displayError}</strong><p>Nothing was treated as successful.</p></div></div>}
      <main className={`rv-layout rv-show-${mobile}`}>
        <aside className="rv-left" aria-label="Preparations and source materials">
          <section className="rv-card rv-queue"><div className="rv-section-title"><h2>Review queue</h2><span className="rv-counter">{String(data?.rows.length ?? 0).padStart(2, "0")}</span></div>
            <div className="rv-search"><Icon name="search" size={16} /><input aria-label="Search preparations" placeholder="Find a supervisor…" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
            <div className="rv-filters">{["all", "blocked", "attention"].map((value) => <button key={value} className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>{value === "all" ? `All ${data?.rows.length ?? 0}` : value === "blocked" ? "Blocked" : "Needs review"}</button>)}</div>
            <div className="rv-queue-list">{entries.map((item) => { const itemTone = toneOf(item); return <button className={`rv-task ${effectiveSelectedId === item.preparation.id ? "selected" : ""}`} key={item.preparation.id} onClick={() => choose(item)}>
              <div className={`rv-initials ${itemTone}`}>{initials(item.task.supervisor.name)}</div><div><strong>{item.task.supervisor.name}</strong><small>{item.task.institution.name}</small><span className={`rv-task-note ${itemTone}`}><Signal tone={itemTone} />{reviewed.includes(item.preparation.id) ? "Review complete" : itemTone === "ready" ? "Checks passed" : itemTone === "blocked" ? "Blocking finding" : "Attachment to review"}</span></div>{effectiveSelectedId === item.preparation.id && <span className="rv-selection-dot" />}
            </button>; })}{!loading && entries.length === 0 && <p className="rv-empty">{data?.rows.length ? "No preparations match your filters." : "Import and prepare supported source materials first."}</p>}</div>
            <div className="rv-queue-foot"><Icon name="user" size={14} />{row ? <>Student: <strong>{row.task.student.name}</strong></> : "No preparation selected"}</div>
          </section>
          <section className="rv-card rv-sources"><div className="rv-section-title"><h2>Source materials</h2><span className="rv-counter">{row?.sources.length ?? 0}</span></div>
            {row?.sources.map((source) => <button key={source.id} className={`rv-source ${focus === "source" ? "selected" : ""}`} onClick={() => { setFocus("source"); setPanel("evidence"); setMobile("message"); }}><span className="rv-file-icon blue"><Icon name="file" size={19} /></span><span><strong>{source.name}</strong><small>{source.sheet ? `${source.sheet} · row ${source.row}` : `${Math.round(source.size / 1024)} KB`}</small></span><Icon name="chevron" size={13} /></button>)}
          </section>
          <div className="rv-legend"><span><i className="blocked" />Blocker</span><span><i className="attention" />Review</span><span><i className="ready" />Verified</span></div>
        </aside>

        <section className="rv-center" aria-label="Preparation preview">
          <div className="rv-preview-toolbar"><div className="rv-view-tabs"><button className={panel === "message" ? "active" : ""} onClick={() => setPanel("message")}><Icon name="mail" size={15} />Message preview</button><button className={panel === "evidence" ? "active" : ""} onClick={() => setPanel("evidence")}>Source evidence</button></div><span>{row ? row.preparation.id.slice(0, 12) : "NO PREPARATION"}</span></div>
          <div className="rv-document-scroll">{row ? <>
            <div className={`rv-status-banner ${tone}`}><Signal tone={tone} /><div><strong>{tone === "blocked" ? "Hold for review — Core reports a blocker" : tone === "attention" ? "Attachment association needs attention" : "Preparation checks passed"}</strong><p>{tone === "ready" ? "No unresolved blockers. Sending still requires separate Confirmation." : blocking[0]?.detail || taskBlocking[0]?.detail || "Review the advisory attachment association."}</p></div></div>
            {panel === "message" ? <article className="rv-paper"><div className="rv-paper-heading"><span className="rv-mail-icon"><Icon name="mail" size={24} /></span><div><span className="rv-eyebrow">{human(row.preparation.action_kind).toUpperCase()}</span><h2>{row.preparation.subject || "Subject required"}</h2></div><span className="rv-local-label">LOCAL PREPARATION</span></div>
              <dl className="rv-envelope"><div><dt>From</dt><dd>{row.task.student.name} <span>&lt;{row.preparation.sender}&gt;</span></dd></div><div><dt>To</dt><dd><button className={`rv-highlight ${blocking.some((item) => item.code.includes("recipient")) ? "blocked" : "ready"} ${focus === "recipient" ? "focused" : ""}`} onClick={() => { setFocus("recipient"); setMobile("checks"); }}>{row.preparation.recipient}<Icon name={blocking.some((item) => item.code.includes("recipient")) ? "warning" : "check"} size={14} /></button></dd></div><div><dt>Subject</dt><dd><button className={`rv-inline ${row.preparation.subject ? "blue" : "attention"}`} onClick={() => { setFocus("subject"); setMobile("checks"); }}>{row.preparation.subject || "Add an authoritative subject"}</button></dd></div></dl>
              <div className="rv-message-body">{row.preparation.body.split(/\n{2,}/).map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div>
              {row.preparation.attachment_slots.map((attachment) => <button className="rv-attachment" key={attachment.id} onClick={() => { setFocus("attachment"); setMobile("checks"); }}><span className="rv-file-icon purple"><Icon name="file" size={19} /></span><span><strong>{attachment.attachment?.name || attachment.candidates?.[0]?.name || attachment.label}</strong><small>{attachment.attachment ? `${attachment.attachment.size} bytes · confirmed snapshot` : "Advisory association — operator confirmation required"}</small></span><Signal tone={attachment.attachment ? "ready" : "attention"} /></button>)}
              <div className="rv-paper-foot"><Icon name="shield" size={13} />This is retained local content; no external mailbox draft was created.</div>
            </article> : <article className="rv-paper rv-evidence"><div className="rv-eyebrow">RETAINED SOURCE EVIDENCE</div><h2>{row.preparation.source.name}</h2><p>Associated with {row.task.supervisor.name} · {row.task.student.name}</p><dl><dt>Institution</dt><dd>{row.task.institution.name}</dd><dt>Recorded recipient</dt><dd>{recordedRecipient || "No usable address recorded"}</dd><dt>Source digest</dt><dd>{row.preparation.source.sha256}</dd><dt>Association</dt><dd><pre>{JSON.stringify(row.preparation.association, null, 2)}</pre></dd></dl><button className="rv-secondary" onClick={() => setPanel("message")}><Icon name="reply" size={15} />Back to message</button></article>}
          </> : <div className="rv-paper rv-evidence"><h2>{loading ? "Loading Core preparations…" : "No prepared communication actions"}</h2><p>Use Source mapping to import a supported bundle and create local Preparations.</p></div>}</div>
          <div className="rv-action-bar"><div><Signal tone={tone} /><span>{notice || (row ? tone === "blocked" ? "Resolve blockers to finish review" : "Ready for operator review" : "Waiting for a Preparation")}</span></div><button className="rv-primary" disabled={!row || tone !== "ready" || reviewed.includes(effectiveSelectedId)} onClick={() => { setReviewed((items) => [...items, effectiveSelectedId]); setNotice("Review marked complete in this operator session. No Confirmation was created."); }}><Icon name="check" size={16} />{reviewed.includes(effectiveSelectedId) ? "Reviewed" : "Mark reviewed"}</button></div>
        </section>

        <aside className="rv-right" aria-label="Readiness checks">
          <section className="rv-card rv-readiness"><div className="rv-section-title"><h2><Icon name="shield" size={17} />Readiness overview</h2><Signal tone={tone}>{tone === "ready" ? "Ready" : tone === "attention" ? "Needs review" : "Blocked"}</Signal></div><div className="rv-score"><strong>{row ? Math.max(0, 6 - blockerCount) : 0}<span>/ 6</span></strong><div><b>checks passed</b><p>{blockerCount ? `${blockerCount} blocker${blockerCount === 1 ? "" : "s"} require resolution` : tone === "attention" ? "Confirm attachment evidence" : "All Core readiness checks complete"}</p></div></div><p className="rv-readiness-note">Readiness is separate from sending Confirmation.</p></section>
          <section className="rv-card rv-finding"><div className="rv-section-title"><h2>{focus === "recipient" ? "Recipient evidence" : focus === "subject" ? "Subject correction" : focus === "attachment" ? "Attachment review" : focus === "duplicate" ? "Duplicate evidence" : focus === "exception" ? "Task exception" : "Source association"}</h2><Icon name="link" size={16} /></div>
            {!row ? <p>Select a Preparation.</p> : focus === "recipient" ? <div className="rv-detail"><div className="rv-compare"><div><span>IN PREPARATION</span><strong>{row.preparation.recipient}</strong><small>{row.preparation.source.name}</small></div><Icon name="arrow" size={17} /><div><span>SUPERVISOR RECORD</span><strong>{recordedRecipient || "Missing"}</strong><small>Retained source association</small></div></div>{recordedRecipient && row.preparation.recipient !== recordedRecipient && <button className="rv-primary" disabled={busy} onClick={() => void mutate(() => core("update_preparation", { preparation_id: row.preparation.id, subject: row.preparation.subject, recipient: recordedRecipient }), "Recipient corrected and readiness recomputed. Any prior Confirmation was invalidated.")}>Use recorded recipient <Icon name="arrow" size={14} /></button>}</div>
              : focus === "subject" ? <form className="rv-detail" onSubmit={(event) => { event.preventDefault(); void mutate(() => core("update_preparation", { preparation_id: row.preparation.id, subject, recipient: row.preparation.recipient }), "Subject updated and readiness recomputed."); }}><label>Authoritative subject<input value={subject} onChange={(event) => setSubject(event.target.value)} /></label><button className="rv-primary" disabled={busy || !subject.trim() || subject === row.preparation.subject}>Save subject</button></form>
                : focus === "attachment" ? <div className="rv-detail">{slot ? <><h3>{slot.attachment?.name || slot.label}</h3><p>{slot.basis}</p>{slot.attachment ? <Signal tone="ready">Confirmed snapshot</Signal> : slot.suggested_source_id ? <button className="rv-primary" disabled={busy} onClick={() => void mutate(() => core("confirm_attachment", { preparation_id: row.preparation.id, slot_id: slot.id }), "Attachment bytes snapshotted and associated with this Preparation.")}>Confirm suggested file</button> : <>{slot.candidates?.map((candidate) => <button className="rv-secondary" key={candidate.id} disabled={busy} onClick={() => void mutate(() => core("set_attachment_source", { preparation_id: row.preparation.id, slot_id: slot.id, source_id: candidate.id }), `Associated ${candidate.name}.`)}>{candidate.name}</button>)}{!slot.candidates?.length && <p>No single preserved Source Material is available for this slot.</p>}</>}</> : <p>No attachment declaration in this Preparation.</p>}</div>
                  : focus === "duplicate" ? <div className="rv-detail">{row.duplicate_check ? <><Signal tone={row.duplicate_check.finding === "no_duplicate_found" ? "ready" : "blocked"}>{human(row.duplicate_check.finding)}</Signal><p>{row.duplicate_check.detail}</p><pre>{JSON.stringify(row.duplicate_check.evidence_coverage, null, 2)}</pre></> : <p>No Duplicate Check has been recorded for this Preparation.</p>}<button className="rv-secondary" disabled={busy} onClick={() => void mutate(() => core("check_duplicate", { preparation_id: row.preparation.id }), "Duplicate evidence refreshed from retained records and mailbox coverage.")}>Run duplicate check</button></div>
                    : focus === "exception" ? <div className="rv-detail">{taskExceptions.length ? taskExceptions.map((exception) => <div key={exception.id}><h3>{human(exception.code)}</h3><p>{exception.detail}</p>{(exception.code === "identity_ambiguity" || exception.code === "prior_outreach_conflict") && <button className="rv-primary" disabled={busy} onClick={() => void mutate(() => core("resolve_review_exception", { task_id: row.task.id, code: exception.code as "identity_ambiguity" | "prior_outreach_conflict" }), `Resolved ${human(exception.code)} after explicit operator review.`)}>Resolve after review</button>}</div>) : <Signal tone="ready">No unresolved Task exceptions for this action</Signal>}</div>
                      : <div className="rv-detail"><Signal tone="ready">Explicit source association</Signal><p>{row.task.supervisor.name} and {row.task.institution.name} are linked through retained import evidence.</p><button className="rv-secondary" onClick={() => { setPanel("evidence"); setMobile("message"); }}>Inspect retained evidence <Icon name="arrow" size={14} /></button></div>}
          </section>
          <section className="rv-card rv-checks"><div className="rv-section-title"><h2>Preparation checklist</h2><span className="rv-counter">6</span></div>{row && [
            { label: "Student & mailbox", detail: `${row.task.student.name} · ${row.preparation.sender}`, field: "source" as Focus, tone: "ready" as Tone },
            { label: "Recipient", detail: blocking.some((item) => item.code.includes("recipient")) ? "Correction required" : "Usable recipient", field: "recipient" as Focus, tone: blocking.some((item) => item.code.includes("recipient")) ? "blocked" as Tone : "ready" as Tone },
            { label: "Subject & body", detail: row.preparation.subject ? "Required content present" : "Authoritative subject missing", field: "subject" as Focus, tone: row.preparation.subject ? "ready" as Tone : "blocked" as Tone },
            { label: "Task exceptions", detail: taskExceptions.length ? `${taskExceptions.length} relevant` : "None unresolved", field: "exception" as Focus, tone: taskExceptions.some((item) => item.blocking) ? "blocked" as Tone : "ready" as Tone },
            { label: "Attachments", detail: slot?.attachment ? "Snapshot confirmed" : slot ? "Association needs review" : "None declared", field: "attachment" as Focus, tone: slot && !slot.attachment ? "attention" as Tone : "ready" as Tone },
            { label: "Duplicate check", detail: row.duplicate_check ? human(row.duplicate_check.finding) : "Not checked", field: "duplicate" as Focus, tone: !row.duplicate_check || row.duplicate_check.review_required ? "attention" as Tone : "ready" as Tone },
          ].map((check) => <button className={`rv-check ${check.tone} ${focus === check.field ? "focused" : ""}`} key={check.label} onClick={() => setFocus(check.field)}><Signal tone={check.tone} /><span><strong>{check.label}</strong><small>{check.detail}</small></span><Icon name="chevron" size={13} /></button>)}</section>
          <div className="rv-guidance"><Icon name="book" size={19} /><div><strong>Core-grounded operator review</strong><p>Every mutation is revalidated and remains separate from external authority.</p></div></div>
        </aside>
      </main>
      <footer className="rv-footer"><span><i />Persisted Core data · no sample records</span><span role="status">{notice || "Review only · no external actions"}</span><button className="rv-secondary" disabled={!ready} onClick={() => navigate("execution")}>Continue to execution</button></footer>
    </div>
  </AppShell>;
}

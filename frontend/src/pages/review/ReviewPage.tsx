import { useState } from "react";
import { AppShell, NavigationItem, Topbar } from "../../app/shell";
import Icon from "../../shared/Icon";
import type { IconName } from "../../shared/Icon";
import "./Review.css";

type Tone = "blocked" | "attention" | "ready";
const preparations: {
  name: string;
  institution: string;
  topic: string;
  status: Tone;
  note: string;
}[] = [
  {
    name: "Dr. Eleanor Morgan",
    institution: "University of Cambridge",
    topic: "Human-centered machine learning",
    status: "blocked",
    note: "Recipient conflict",
  },
  {
    name: "Prof. Daniel Kim",
    institution: "Imperial College London",
    topic: "Trustworthy artificial intelligence",
    status: "attention",
    note: "Attachment to review",
  },
  {
    name: "Dr. Sofia Andersson",
    institution: "University of Edinburgh",
    topic: "Responsible natural language processing",
    status: "ready",
    note: "Checks passed",
  },
  {
    name: "Prof. James Chen",
    institution: "University of Oxford",
    topic: "Interpretable machine learning",
    status: "ready",
    note: "Checks passed",
  },
  {
    name: "Dr. Olivia Patel",
    institution: "University College London",
    topic: "Human–AI collaboration",
    status: "ready",
    note: "Checks passed",
  },
];
const statusLabel = {
  blocked: "Blocked",
  attention: "Needs review",
  ready: "Ready",
};
function Signal({
  tone,
  children,
}: {
  tone: Tone;
  children?: React.ReactNode;
}) {
  return (
    <span className={`rv-signal ${tone}`}>
      <Icon
        name={
          tone === "ready" ? "check" : tone === "blocked" ? "stop" : "warning"
        }
        size={13}
      />
      {children}
    </span>
  );
}
export default function ReviewPage() {
  const [selected, setSelected] = useState(0);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [resolved, setResolved] = useState(false);
  const [attachmentChecked, setAttachmentChecked] = useState(false);
  const [focus, setFocus] = useState("recipient");
  const [panel, setPanel] = useState("message");
  const [mobile, setMobile] = useState("message");
  const [reviewed, setReviewed] = useState<number[]>([]);
  const [notice, setNotice] = useState("");
  const item = preparations[selected];
  const tone: Tone =
    selected === 0 && resolved
      ? "ready"
      : selected === 1 && attachmentChecked
        ? "ready"
        : item.status;
  const address =
    selected === 0
      ? "e.morgan@cam.ac.uk"
      : `${item.name.split(" ").at(-1)?.toLowerCase()}@university.ac.uk`;
  const currentAddress =
    selected === 0 && !resolved ? "eleanor.morgan@cambridge.org" : address;
  const entries = preparations
    .map((p, i) => ({
      ...p,
      id: i,
      status:
        (i === 0 && resolved) || (i === 1 && attachmentChecked)
          ? ("ready" as Tone)
          : p.status,
    }))
    .filter(
      (p) =>
        (filter === "all" || p.status === filter) &&
        `${p.name} ${p.institution}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    );
  function choose(id: number) {
    setSelected(id);
    setFocus(id === 0 ? "recipient" : id === 1 ? "attachment" : "source");
    setNotice("");
  }
  function inspect(field: string) {
    setFocus(field);
    setMobile("checks");
  }
  const sources: {
    icon: IconName;
    title: string;
    detail: string;
    color: string;
  }[] = [
    {
      icon: "file",
      title: "Outreach draft.docx",
      detail: "Message · paragraph 1–4",
      color: "blue",
    },
    {
      icon: "source",
      title: "Supervisor shortlist.xlsx",
      detail: `Supervisor record · row ${selected + 12}`,
      color: "green",
    },
    {
      icon: "file",
      title: "Alex_Lin_CV.pdf",
      detail: "Student CV · 248 KB",
      color: "purple",
    },
  ];
  return (
    <AppShell
      className="review-page"
      navigation={
        <>
          <NavigationItem route="workflow" />
          <NavigationItem route="sources" />
          <NavigationItem route="review" active />
          <div className="rail-spacer" />
        </>
      }
    >
      <div className="workspace">
        <Topbar breadcrumb="Review" homeHref="#workflow">
          <span className="rv-campaign">Autumn 2026 · PhD outreach</span>
          <span className="rv-demo">
            <span /> SAMPLE WORKSPACE
          </span>
        </Topbar>
        <div className="rv-heading">
          <div>
            <div className="rv-eyebrow">PREPARE WITH CONFIDENCE</div>
            <h1>
              Readiness workbench<span>Review</span>
            </h1>
            <p>
              Every detail, backed by evidence. Resolve what matters before
              moving on.
            </p>
          </div>
          <div className="rv-heading-count">
            <strong>
              {
                preparations.filter(
                  (_, i) =>
                    i > 1 ||
                    (i === 0 && resolved) ||
                    (i === 1 && attachmentChecked),
                ).length
              }
              <span> / 5</span>
            </strong>
            <span>preparations ready</span>
          </div>
        </div>
        <div className="rv-mobile-tabs" aria-label="Workbench panels">
          {["queue", "message", "checks"].map((tab) => (
            <button
              key={tab}
              className={mobile === tab ? "active" : ""}
              onClick={() => setMobile(tab)}
            >
              {tab === "queue"
                ? "Preparations"
                : tab === "message"
                  ? "Message"
                  : "Readiness"}
            </button>
          ))}
        </div>
        <main className={`rv-layout rv-show-${mobile}`}>
          <aside
            className="rv-left"
            aria-label="Preparations and source materials"
          >
            <section className="rv-card rv-queue">
              <div className="rv-section-title">
                <h2>Review queue</h2>
                <span className="rv-counter">05</span>
              </div>
              <div className="rv-search">
                <Icon name="search" size={16} />
                <input
                  aria-label="Search preparations"
                  placeholder="Find a supervisor…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <div className="rv-filters">
                {["all", "blocked", "attention"].map((f) => (
                  <button
                    key={f}
                    className={filter === f ? "active" : ""}
                    onClick={() => setFilter(f)}
                  >
                    {f === "all"
                      ? "All 5"
                      : f === "blocked"
                        ? "Blocked"
                        : "Needs review"}
                  </button>
                ))}
              </div>
              <div className="rv-queue-list">
                {entries.map((p) => (
                  <button
                    className={`rv-task ${selected === p.id ? "selected" : ""}`}
                    key={p.id}
                    onClick={() => choose(p.id)}
                  >
                    <div className={`rv-initials ${p.status}`}>
                      {p.name
                        .split(" ")
                        .slice(1)
                        .map((s) => s[0])
                        .join("")}
                    </div>
                    <div>
                      <strong>{p.name}</strong>
                      <small>{p.institution}</small>
                      <span className={`rv-task-note ${p.status}`}>
                        <Signal tone={p.status} />
                        {reviewed.includes(p.id)
                          ? "Review complete"
                          : p.status === "ready"
                            ? "Checks passed"
                            : p.note}
                      </span>
                    </div>
                    {selected === p.id && <span className="rv-selection-dot" />}
                  </button>
                ))}
                {entries.length === 0 && (
                  <p className="rv-empty">
                    No preparations match your filters.
                  </p>
                )}
              </div>
              <div className="rv-queue-foot">
                <Icon name="user" size={14} />
                Student: <strong>Alex Lin</strong>
              </div>
            </section>
            <section className="rv-card rv-sources">
              <div className="rv-section-title">
                <h2>Source materials</h2>
                <span className="rv-counter">3</span>
              </div>
              {sources.map((s, i) => (
                <button
                  key={s.title}
                  className={`rv-source ${focus === (i === 2 ? "attachment" : "source") ? "selected" : ""}`}
                  onClick={() => {
                    setFocus(i === 2 ? "attachment" : "source");
                    setPanel(i === 0 ? "message" : "evidence");
                    setMobile("message");
                  }}
                >
                  <span className={`rv-file-icon ${s.color}`}>
                    <Icon name={s.icon} size={19} />
                  </span>
                  <span>
                    <strong>{s.title}</strong>
                    <small>{s.detail}</small>
                  </span>
                  <Icon name="chevron" size={13} />
                </button>
              ))}
              <p className="rv-source-hint">
                <Icon name="link" size={13} />
                Select a source to inspect its evidence.
              </p>
            </section>
            <div className="rv-legend">
              <span>
                <i className="blocked" />
                Blocker
              </span>
              <span>
                <i className="attention" />
                Review
              </span>
              <span>
                <i className="ready" />
                Verified
              </span>
            </div>
          </aside>
          <section className="rv-center" aria-label="Preparation preview">
            <div className="rv-preview-toolbar">
              <div className="rv-view-tabs">
                <button
                  className={panel === "message" ? "active" : ""}
                  onClick={() => setPanel("message")}
                >
                  <Icon name="mail" size={15} />
                  Message preview
                </button>
                <button
                  className={panel === "evidence" ? "active" : ""}
                  onClick={() => setPanel("evidence")}
                >
                  Source evidence
                </button>
              </div>
              <span>PREP-{String(selected + 1).padStart(3, "0")} · v1</span>
            </div>
            <div className="rv-document-scroll">
              <div className={`rv-status-banner ${tone}`}>
                <Signal tone={tone} />
                <div>
                  <strong>
                    {tone === "blocked"
                      ? "Hold for review — recipient conflict"
                      : tone === "attention"
                        ? "One detail needs your attention"
                        : "Preparation checks passed"}
                  </strong>
                  <p>
                    {tone === "blocked"
                      ? "The draft recipient differs from the associated supervisor record."
                      : tone === "attention"
                        ? "Check the suggested CV against the message before proceeding."
                        : "No unresolved blockers. Sending requires separate confirmation."}
                  </p>
                </div>
              </div>
              {panel === "message" ? (
                <article className="rv-paper">
                  <div className="rv-paper-heading">
                    <span className="rv-mail-icon">
                      <Icon name="mail" size={24} />
                    </span>
                    <div>
                      <span className="rv-eyebrow">INITIAL OUTREACH</span>
                      <h2>PhD inquiry · Autumn 2026</h2>
                    </div>
                    <span className="rv-local-label">LOCAL PREPARATION</span>
                  </div>
                  <dl className="rv-envelope">
                    <div>
                      <dt>From</dt>
                      <dd>
                        Alex Lin <span>&lt;alex.lin@163.com&gt;</span>
                        <Signal tone="ready" />
                      </dd>
                    </div>
                    <div>
                      <dt>To</dt>
                      <dd>
                        <button
                          className={`rv-highlight ${tone === "blocked" ? "blocked" : "ready"} ${focus === "recipient" ? "focused" : ""}`}
                          onClick={() => inspect("recipient")}
                        >
                          {currentAddress}
                          <Icon
                            name={tone === "blocked" ? "warning" : "check"}
                            size={14}
                          />
                        </button>
                      </dd>
                    </div>
                    <div>
                      <dt>Subject</dt>
                      <dd>Prospective PhD student — {item.topic}</dd>
                    </div>
                  </dl>
                  <div className="rv-message-body">
                    <p>Dear {item.name},</p>
                    <p>
                      My name is Alex Lin, and I am writing to express my
                      interest in pursuing a PhD under your supervision at{" "}
                      <button
                        className={`rv-inline blue ${focus === "source" ? "focused" : ""}`}
                        onClick={() => inspect("source")}
                      >
                        {item.institution}
                        <Icon name="link" size={12} />
                      </button>
                      .
                    </p>
                    <p>
                      My research focuses on{" "}
                      <button
                        className="rv-inline blue"
                        onClick={() => inspect("source")}
                      >
                        {item.topic.toLowerCase()}
                        <Icon name="link" size={12} />
                      </button>
                      . I am particularly interested in how we can develop
                      systems that are both technically robust and useful to the
                      people who rely on them.
                    </p>
                    <p>
                      During my master's studies, I explored evaluation methods
                      for machine learning models and developed a strong
                      foundation in experimental research. I would welcome the
                      opportunity to contribute to your group's work.
                    </p>
                    <p>
                      I have attached{" "}
                      <button
                        className={`rv-inline ${selected === 1 && !attachmentChecked ? "attention" : "ready"}`}
                        onClick={() => inspect("attachment")}
                      >
                        my CV for your consideration
                        <Icon name="clip" size={12} />
                      </button>
                      . Are you considering new PhD students for Autumn 2026?
                    </p>
                    <p>Thank you for your time and consideration.</p>
                    <p>
                      Best regards,
                      <br />
                      <strong>Alex Lin</strong>
                      <br />
                      <span className="rv-muted">MSc Computer Science</span>
                    </p>
                  </div>
                  <button
                    className="rv-attachment"
                    onClick={() => inspect("attachment")}
                  >
                    <span className="rv-file-icon purple">
                      <Icon name="file" size={19} />
                    </span>
                    <span>
                      <strong>Alex_Lin_CV.pdf</strong>
                      <small>
                        248 KB ·{" "}
                        {selected === 1 && !attachmentChecked
                          ? "Suggested association"
                          : "Associated source material"}
                      </small>
                    </span>
                    <Signal
                      tone={
                        selected === 1 && !attachmentChecked
                          ? "attention"
                          : "ready"
                      }
                    />
                  </button>
                  <div className="rv-paper-foot">
                    <Icon name="shield" size={13} />
                    Source highlights are review annotations and are not part of
                    the message.
                  </div>
                </article>
              ) : (
                <article className="rv-paper rv-evidence">
                  <div className="rv-eyebrow">SOURCE EVIDENCE · SAMPLE</div>
                  <h2>
                    {focus === "attachment"
                      ? "Alex_Lin_CV.pdf"
                      : "Supervisor shortlist.xlsx"}
                  </h2>
                  <p>Associated with {item.name} · Alex Lin</p>
                  <dl>
                    <dt>Supervisor</dt>
                    <dd>{item.name}</dd>
                    <dt>Institution</dt>
                    <dd>{item.institution}</dd>
                    <dt>Recorded recipient</dt>
                    <dd>{address}</dd>
                    <dt>Research area</dt>
                    <dd>{item.topic}</dd>
                    <dt>Student CV</dt>
                    <dd>Alex Lin · MSc Computer Science · 248 KB</dd>
                  </dl>
                  <div className="rv-evidence-note">
                    This prototype shows illustrative source excerpts. Original
                    file contents are not loaded.
                  </div>
                  <button
                    className="rv-secondary"
                    onClick={() => setPanel("message")}
                  >
                    <Icon name="reply" size={15} />
                    Back to message
                  </button>
                </article>
              )}
            </div>
            <div className="rv-action-bar">
              <div>
                <Signal tone={tone} />
                <span>
                  {reviewed.includes(selected)
                    ? "Review recorded locally"
                    : tone === "blocked"
                      ? "Resolve blocker to finish review"
                      : "Ready for your review"}
                </span>
              </div>
              <button
                className="rv-primary"
                disabled={tone !== "ready" || reviewed.includes(selected)}
                onClick={() => {
                  setReviewed([...reviewed, selected]);
                  setNotice(
                    "Review recorded for this sample preparation. No sending confirmation was created.",
                  );
                }}
              >
                <Icon name="check" size={16} />
                {reviewed.includes(selected) ? "Reviewed" : "Mark reviewed"}
              </button>
            </div>
          </section>
          <aside className="rv-right" aria-label="Readiness checks">
            <section className="rv-card rv-readiness">
              <div className="rv-section-title">
                <h2>
                  <Icon name="shield" size={17} />
                  Readiness overview
                </h2>
                <Signal tone={tone}>{statusLabel[tone]}</Signal>
              </div>
              <div className="rv-score">
                <strong>
                  {tone === "ready" ? "6" : "5"}
                  <span>/ 6</span>
                </strong>
                <div>
                  <b>checks passed</b>
                  <p>
                    {tone === "blocked"
                      ? "1 blocker requires resolution"
                      : tone === "attention"
                        ? "1 item needs review"
                        : "All preparation checks complete"}
                  </p>
                </div>
              </div>
              <div className="rv-segments">
                {Array.from({ length: 6 }, (_, i) => (
                  <span key={i} className={i === 5 ? tone : "ready"} />
                ))}
              </div>
              <p className="rv-readiness-note">
                Readiness is separate from sending confirmation.
              </p>
            </section>
            <section className="rv-card rv-finding">
              <div className="rv-section-title">
                <h2>
                  {focus === "recipient"
                    ? "Recipient evidence"
                    : focus === "attachment"
                      ? "Attachment review"
                      : focus === "duplicate"
                        ? "Duplicate evidence"
                        : "Source association"}
                </h2>
                <Icon name="link" size={16} />
              </div>
              {focus === "recipient" ? (
                <>
                  <div className="rv-compare">
                    <div>
                      <span>IN PREPARATION</span>
                      <strong
                        className={tone === "blocked" ? "rv-red-text" : ""}
                      >
                        {currentAddress}
                      </strong>
                      <small>Outreach draft.docx</small>
                    </div>
                    <Icon name="arrow" size={17} />
                    <div>
                      <span>SUPERVISOR RECORD</span>
                      <strong>{address}</strong>
                      <small>Shortlist · row {selected + 12}</small>
                    </div>
                  </div>
                  {tone === "blocked" ? (
                    <div className="rv-resolution blocked">
                      <strong>
                        <Icon name="warning" size={15} />
                        Resolve the recipient mismatch
                      </strong>
                      <p>
                        Compare the sources and explicitly choose the recorded
                        address for this sample preparation.
                      </p>
                      <button
                        className="rv-primary"
                        onClick={() => {
                          setResolved(true);
                          setNotice(
                            "Sample recipient corrected and checks refreshed. Previous confirmation would be invalidated.",
                          );
                        }}
                      >
                        Use recorded recipient
                        <Icon name="arrow" size={14} />
                      </button>
                    </div>
                  ) : (
                    <div className="rv-resolution ready">
                      <Signal tone="ready" />
                      Recipient matches the associated record.
                    </div>
                  )}
                </>
              ) : focus === "attachment" ? (
                <div className="rv-detail">
                  <span className="rv-file-icon purple">
                    <Icon name="file" />
                  </span>
                  <h3>Alex_Lin_CV.pdf</h3>
                  <p>
                    Student: Alex Lin · 248 KB
                    <br />
                    Suggested by the CV reference in the message.
                  </p>
                  <button
                    className="rv-secondary"
                    onClick={() => {
                      setPanel("evidence");
                      setMobile("message");
                    }}
                  >
                    Inspect source excerpt
                    <Icon name="arrow" size={14} />
                  </button>
                  {selected === 1 && !attachmentChecked && (
                    <button
                      className="rv-primary"
                      onClick={() => {
                        setAttachmentChecked(true);
                        setNotice("CV association checked in this sample.");
                      }}
                    >
                      Confirm sample association
                    </button>
                  )}
                </div>
              ) : focus === "duplicate" ? (
                <div className="rv-detail">
                  <Signal tone="ready">No Duplicate Found</Signal>
                  <p>No matching prior send in the sample evidence coverage.</p>
                  <dl>
                    <dt>Campaign records</dt>
                    <dd>Autumn 2026 · 12 records</dd>
                    <dt>Mailbox observation</dt>
                    <dd>1–17 Sep 2026 · outbound only</dd>
                  </dl>
                  <p>
                    Earlier mailbox history is not covered. This is not proof
                    that no prior send exists.
                  </p>
                </div>
              ) : (
                <div className="rv-detail">
                  <Signal tone="ready">Explicit source association</Signal>
                  <p>
                    {item.name} and {item.institution} match the supervisor
                    record in row {selected + 12}.
                  </p>
                  <button
                    className="rv-secondary"
                    onClick={() => {
                      setPanel("evidence");
                      setMobile("message");
                    }}
                  >
                    Inspect source excerpt
                    <Icon name="arrow" size={14} />
                  </button>
                </div>
              )}
            </section>
            <section className="rv-card rv-checks">
              <div className="rv-section-title">
                <h2>Preparation checklist</h2>
                <span className="rv-counter">6</span>
              </div>
              {[
                {
                  label: "Student & mailbox",
                  detail: "Alex Lin · identity matched",
                  field: "source",
                  tone: "ready" as Tone,
                },
                {
                  label: "Recipient",
                  detail:
                    tone === "blocked"
                      ? "Conflicting source values"
                      : "Matches supervisor record",
                  field: "recipient",
                  tone:
                    tone === "blocked"
                      ? ("blocked" as Tone)
                      : ("ready" as Tone),
                },
                {
                  label: "Subject & body",
                  detail: "Required content present",
                  field: "source",
                  tone: "ready" as Tone,
                },
                {
                  label: "Source associations",
                  detail: "3 materials linked",
                  field: "source",
                  tone: "ready" as Tone,
                },
                {
                  label: "Attachments",
                  detail:
                    selected === 1 && !attachmentChecked
                      ? "CV association needs review"
                      : "CV association checked",
                  field: "attachment",
                  tone:
                    selected === 1 && !attachmentChecked
                      ? ("attention" as Tone)
                      : ("ready" as Tone),
                },
                {
                  label: "Duplicate check",
                  detail: "No match in covered evidence",
                  field: "duplicate",
                  tone: "ready" as Tone,
                },
              ].map((c) => (
                <button
                  className={`rv-check ${c.tone} ${focus === c.field ? "focused" : ""}`}
                  key={c.label}
                  onClick={() => setFocus(c.field)}
                >
                  <Signal tone={c.tone} />
                  <span>
                    <strong>{c.label}</strong>
                    <small>{c.detail}</small>
                  </span>
                  <Icon name="chevron" size={13} />
                </button>
              ))}
            </section>
            <div className="rv-guidance">
              <Icon name="book" size={19} />
              <div>
                <strong>Your review, grounded in evidence</strong>
                <p>
                  Select a highlighted field or a check to trace it back to its
                  source.
                </p>
              </div>
            </div>
          </aside>
        </main>
        <footer className="rv-footer">
          <span>
            <i />
            Local prototype · sample data · changes reset on navigation
          </span>
          <span role="status">
            {notice || "Review only · no external actions"}
          </span>
        </footer>
      </div>
    </AppShell>
  );
}

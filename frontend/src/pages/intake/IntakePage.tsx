import SearchField from "../../shared/SearchField";
import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { IconName } from "../../shared/Icon";
import Icon from "../../shared/Icon";
import { AppShell, Topbar, NavigationItem } from "../../app/shell";
import { navigate } from "../../app/routes";
import "./SourceMapping.css";

type Source = {
  name: string;
  type: string;
  icon: IconName;
  color: string;
  meta: string;
  status: string;
  rule: number;
  fields: [string, string][];
};
const initialSources: Source[] = [
  {
    name: "Supervisor shortlist.xlsx",
    type: "Spreadsheet",
    icon: "source",
    color: "green",
    meta: "12 rows · 6 columns",
    status: "Matched",
    rule: 0,
    fields: [
      ["Sheet / row", "Supervisors · row 2"],
      ["full_name → supervisor", "Dr. Sarah Chen"],
      ["university → institution", "University of Oxford"],
      ["email → recipient", "sarah.chen@example.edu"],
    ],
  },
  {
    name: "Outreach letters.docx",
    type: "Document",
    icon: "file" as const,
    color: "blue",
    meta: "12 letters · 2 students",
    status: "Matched",
    rule: 1,
    fields: [
      ["Section", "Letter 01 · Sarah Chen"],
      ["subject → subject", "PhD inquiry · Human-centered AI"],
      ["body → preparation", "Dear Dr. Chen, I am writing to…"],
      ["Association", "Student + supervisor identifiers"],
    ],
  },
  {
    name: "Research proposal.pdf",
    type: "Document",
    icon: "file" as const,
    color: "rose",
    meta: "8 pages · Lin Wei",
    status: "Matched",
    rule: 2,
    fields: [
      ["Student", "Lin Wei · ST-001"],
      ["Attachment slot", "Research proposal"],
      ["Association", "Explicit student identifier"],
      ["File", "Research proposal.pdf"],
    ],
  },
  {
    name: "Student profiles.xlsx",
    type: "Spreadsheet",
    icon: "user",
    color: "purple",
    meta: "2 students · 8 fields",
    status: "Matched",
    rule: 0,
    fields: [
      ["student_id → student", "ST-001 · Lin Wei"],
      ["mailbox_id → mailbox", "MB-001"],
      ["Research area", "Human-centered AI"],
      ["Source precedence", "Student identity fields"],
    ],
  },
  {
    name: "CVs & transcripts",
    type: "Attachment",
    icon: "clip",
    color: "slate",
    meta: "4 files · 1 missing association",
    status: "Review",
    rule: 2,
    fields: [
      ["Associated files", "Lin_Wei_CV.pdf · Mei_CV.pdf"],
      ["Required slot", "Academic transcript"],
      ["Exception", "Mei Zhang transcript not associated"],
      ["Resolution", "Associate an explicit student ID"],
    ],
  },
  {
    name: "Student mailboxes",
    type: "Mailbox",
    icon: "mail" as const,
    color: "blue",
    meta: "2 identities · 163 Mail",
    status: "Matched",
    rule: 3,
    fields: [
      ["Student", "Lin Wei · ST-001"],
      ["Mailbox", "lin.wei@example.com"],
      ["Association", "Student-owned mailbox ID"],
      ["Usage", "Sender identity only"],
    ],
  },
  {
    name: "Existing mailbox records",
    type: "Mailbox",
    icon: "database",
    color: "purple",
    meta: "18 messages · imported snapshot",
    status: "Review",
    rule: 4,
    fields: [
      ["Evidence coverage", "Sent + Inbox · 01–15 Sep 2026"],
      ["Observed messages", "18 · read-only sample snapshot"],
      ["Duplicate suspicion", "Lin Wei → Dr. James Wilson"],
      ["Limitations", "Earlier history not inspected"],
    ],
  },
  {
    name: "Previous outreach.csv",
    type: "Imported record",
    icon: "database",
    color: "amber",
    meta: "6 records · campaign scoped",
    status: "Matched",
    rule: 4,
    fields: [
      ["Campaign", "Autumn 2026 · PhD outreach"],
      ["Record key", "Student + supervisor + campaign"],
      ["Use", "Reconciliation evidence"],
      ["Authority", "Does not overwrite preparation"],
    ],
  },
];
const rules = [
  {
    title: "Match identities",
    caption: "Student + supervisor + campaign",
    icon: "link" as const,
    color: "green",
    detail:
      "Join explicit identifiers from the shortlist and student profiles. A supervisor can have multiple known email addresses; an email address alone is not the identity.",
    mapping: [
      ["student_id", "Student"],
      ["supervisor_id", "Supervisor"],
      ["campaign_id", "Outreach task scope"],
    ],
  },
  {
    title: "Normalize fields",
    caption: "Columns → structured preparation",
    icon: "file" as const,
    color: "blue",
    detail:
      "Map supported columns and document sections into recipient, institution, subject and body. Retain the original value and applied rule as a transformation record.",
    mapping: [
      ["full_name", "supervisor_name"],
      ["university", "institution_name"],
      ["Trim email whitespace", "recipient"],
    ],
  },
  {
    title: "Associate attachments",
    caption: "Explicit student & document slots",
    icon: "branch" as const,
    color: "purple",
    detail:
      "Associate CVs, proposals and transcripts using explicit student identifiers. A missing association remains a blocker; filenames alone do not establish a match.",
    mapping: [
      ["student_id + CV", "CV slot"],
      ["student_id + proposal", "Proposal slot"],
      ["Missing transcript", "Operator review"],
    ],
  },
  {
    title: "Bind mailbox identity",
    caption: "Student-owned sending mailbox",
    icon: "mail" as const,
    color: "amber",
    detail:
      "Bind the mailbox registered to the student to the sender field. Mailbox association prepares an action but does not grant permission to send.",
    mapping: [
      ["student.mailbox_id", "Mailbox identity"],
      ["mailbox.address", "Preparation sender"],
      ["Confirmation", "Required separately"],
    ],
  },
  {
    title: "Check prior outreach",
    caption: "Campaign-scoped evidence check",
    icon: "copy" as const,
    color: "rose",
    detail:
      "Compare imported records and mailbox observations for the same student, supervisor and campaign. Possible previous sends are held for review within the available evidence coverage.",
    mapping: [
      ["Sent + Inbox snapshot", "Mailbox observation"],
      ["Imported CSV", "Reconciliation evidence"],
      ["Potential prior send", "Duplicate suspicion"],
    ],
  },
  {
    title: "Validate preparation",
    caption: "Required fields & source coverage",
    icon: "shield" as const,
    color: "slate",
    detail:
      "Check required fields, source associations, attachment slots and unresolved exceptions. Ready preparation still requires a separate sending plan and operator confirmation.",
    mapping: [
      ["Required fields", "Complete"],
      ["Unresolved exception", "Block preparation"],
      ["All checks satisfied", "Ready preparation"],
    ],
  },
];
const groups = [
  {
    student: "Lin Wei",
    initials: "LW",
    area: "Human-centered AI",
    color: "blue",
    tasks: [
      {
        name: "Dr. Sarah Chen",
        school: "Oxford",
        status: "Ready",
        sources: [0, 1, 2, 3, 5],
      },
      {
        name: "Prof. Michael Brown",
        school: "Cambridge",
        status: "Ready",
        sources: [0, 1, 2, 3, 5],
      },
      {
        name: "Dr. James Wilson",
        school: "Imperial",
        status: "Duplicate",
        sources: [0, 1, 3, 5, 6, 7],
      },
    ],
  },
  {
    student: "Mei Zhang",
    initials: "MZ",
    area: "Computational biology",
    color: "green",
    tasks: [
      {
        name: "Prof. Emma Taylor",
        school: "UCL",
        status: "Review",
        sources: [0, 1, 3, 4, 5],
      },
      {
        name: "Dr. Oliver Martin",
        school: "Edinburgh",
        status: "Ready",
        sources: [0, 1, 3, 4, 5],
      },
      {
        name: "Prof. Sophie Lee",
        school: "Manchester",
        status: "Ready",
        sources: [0, 1, 3, 4, 5],
      },
    ],
  },
  {
    student: "Lin Wei",
    initials: "LW",
    area: "Machine learning",
    color: "amber",
    tasks: [
      {
        name: "Dr. Daniel Kim",
        school: "ETH Zürich",
        status: "Ready",
        sources: [0, 1, 2, 3, 5],
      },
      {
        name: "Prof. Anna Müller",
        school: "EPFL",
        status: "Ready",
        sources: [0, 1, 2, 3, 5],
      },
      {
        name: "Dr. Lucas Garcia",
        school: "TU Delft",
        status: "Ready",
        sources: [0, 1, 2, 3, 5],
      },
    ],
  },
  {
    student: "Mei Zhang",
    initials: "MZ",
    area: "Biomedical informatics",
    color: "purple",
    tasks: [
      {
        name: "Prof. Emily Davis",
        school: "Stanford",
        status: "Ready",
        sources: [0, 1, 3, 4, 5],
      },
      {
        name: "Dr. Noah Anderson",
        school: "MIT",
        status: "Ready",
        sources: [0, 1, 3, 4, 5],
      },
      {
        name: "Prof. Mia Robinson",
        school: "Harvard",
        status: "Review",
        sources: [0, 1, 3, 4, 5],
      },
    ],
  },
];
type Inspection = {
  kind: string;
  title: string;
  description: string;
  fields: string[][];
};
const colors: Record<string, string> = {
  green: "#17b887",
  blue: "#4b86ff",
  purple: "#9864ef",
  rose: "#fa647d",
  amber: "#f5aa2c",
  slate: "#91a0b9",
};

export default function IntakePage() {
  const onBack = () => navigate("workflow");
  useEffect(() => {
    const previousTitle = document.title;
    document.title = "SmartMail — Source mapping";
    return () => {
      document.title = previousTitle;
    };
  }, []);
  const [sources, setSources] = useState(initialSources);
  const [selected, setSelected] = useState<number | null>(null);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [filter, setFilter] = useState("All tasks");
  const [type, setType] = useState("All sources");
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<number[]>([]);
  const [notice, setNotice] = useState("");
  const [validated, setValidated] = useState(false);
  const [zoom, setZoom] = useState(100);
  const fileInput = useRef<HTMLInputElement>(null);
  const drawer = useRef<HTMLDialogElement>(null);
  const inspect = (value: Inspection) => {
    setInspection(value);
    drawer.current?.showModal();
  };
  const visibleSources = sources
    .map((s, index) => ({ ...s, index }))
    .filter(
      (s) =>
        (type === "All sources" || s.type === type) &&
        s.name.toLowerCase().includes(query.toLowerCase()),
    );
  const visibleGroups = groups
    .map((g, index) => ({
      ...g,
      index,
      tasks: g.tasks.filter(
        (t) =>
          (filter === "All tasks" ||
            (filter === "Needs review"
              ? t.status !== "Ready"
              : filter === "Duplicate suspicion"
                ? t.status === "Duplicate"
                : t.status === "Ready")) &&
          (selected === null || t.sources.includes(selected)) &&
          `${g.student} ${t.name} ${t.school}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      ),
    }))
    .filter((g) => g.tasks.length);
  const taskCount = visibleGroups.reduce((sum, g) => sum + g.tasks.length, 0);
  const activeRule = selected === null ? null : sources[selected].rule;
  return (
    <AppShell
      className="sm-app"
      navigation={
        <>
          <NavigationItem route="workflow" label="Outreach workflow" />
          <NavigationItem route="sources" active />
          <div className="sm-rail-line" />
          <button
            aria-label="Source association guide"
            title="Source association guide"
            onClick={() =>
              inspect({
                kind: "WORKSPACE GUIDE",
                title: "Every task has a source",
                description:
                  "Select a source to trace its associations. Inspect a rule to see how fields are normalized, or open a task to review its source evidence.",
                fields: [
                  [
                    "1 · Source materials",
                    "Original documents and imported records",
                  ],
                  [
                    "2 · Mapping rules",
                    "Explicit associations and supported transformations",
                  ],
                  [
                    "3 · Outreach tasks",
                    "One student + one supervisor + one campaign",
                  ],
                  [
                    "Sample workspace",
                    "Changes are local to this page and reset on reload.",
                  ],
                ],
              })
            }
          >
            <Icon name="book" />
          </button>
          <div className="rail-spacer" />
          <button
            className="rail-add"
            aria-label="Add source files"
            onClick={() => fileInput.current?.click()}
          >
            <Icon name="plus" />
          </button>
        </>
      }
    >
      <div className="workspace">
        <Topbar
          className="sm-topbar"
          breadcrumb="Source mapping"
          homeHref="#workflow"
          onHome={onBack}
        >
          <SearchField
            label="Search sources and tasks"
            value={query}
            onChange={setQuery}
            placeholder="Search sources or outreach tasks…"
            iconSize={16}
          />
          <span className="sm-sample">
            <i /> Sample workspace
          </span>
          <div className="sm-user">OP</div>
        </Topbar>
        <section className="sm-heading">
          <div>
            <div className="eyebrow">PREPARATION / SOURCE ASSOCIATIONS</div>
            <h1>
              From sources to structure<span className="sm-version">02</span>
            </h1>
            <p>
              Connect the context. Keep the evidence. Prepare every outreach
              task.
            </p>
          </div>
          <div className="sm-heading-actions">
            <button
              className="sm-button"
              onClick={() => fileInput.current?.click()}
            >
              <Icon name="plus" size={16} /> Add sources
            </button>
            <button
              className="primary"
              onClick={() => {
                setValidated(true);
                setFilter("All tasks");
                setNotice(
                  "Sample validation complete: 9 ready preparations, 2 attachment blockers and 1 duplicate suspicion. No live records were changed.",
                );
              }}
            >
              <Icon name="check" size={16} />{" "}
              {validated ? "Validate again" : "Validate mapping"}
            </button>
          </div>
        </section>
        <div className="sm-toolbar">
          <div className="sm-campaign">
            <Icon name="folder" size={16} />
            <span>Autumn 2026 · PhD outreach</span>
            <span className="sm-demo-label">DEMO</span>
          </div>
          <span className="sm-divider" />
          <button onClick={onBack} className="sm-nav-tab">
            <Icon name="grid" size={15} /> Workflow
          </button>
          <span className="sm-nav-tab current">
            <Icon name="branch" size={15} /> Source mapping
          </span>
          <div className="sm-toolbar-spacer" />
          <span className="sm-toolbar-note">
            <Icon name="shield" size={14} /> Source evidence preserved
          </span>
        </div>
        <div className="sm-summary">
          <div className="sm-source-filters">
            <label>
              <Icon name="filter" size={14} />
              <select
                aria-label="Source type"
                value={type}
                onChange={(e) => setType(e.target.value)}
              >
                {[
                  "All sources",
                  "Spreadsheet",
                  "Document",
                  "Attachment",
                  "Mailbox",
                  "Imported record",
                ].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <span>{sources.length} source materials</span>
          </div>
          <div className="sm-stats">
            <span>
              <i className="sm-dot ready" />
              <b>9</b> ready
            </span>
            <button
              onClick={() =>
                setFilter(
                  filter === "Needs review" ? "All tasks" : "Needs review",
                )
              }
            >
              <i className="sm-dot review" />
              <b>2</b> need review
            </button>
            <button onClick={() => setFilter("Duplicate suspicion")}>
              <i className="sm-dot duplicate" />
              <b>1</b> duplicate suspicion
            </button>
          </div>
          <div className="sm-coverage">
            <div>
              <span>Preparation readiness</span>
              <b>75%</b>
            </div>
            <div className="sm-progress">
              <i />
            </div>
          </div>
        </div>
        {notice && (
          <div className="sm-notice" role="status">
            <Icon name="check" size={16} />
            {notice}
            <button
              aria-label="Dismiss notification"
              onClick={() => setNotice("")}
            >
              <Icon name="close" size={15} />
            </button>
          </div>
        )}
        <main className="sm-board">
          <section className="sm-sources">
            <div className="sm-column-heading">
              <Icon name="folder" size={16} />
              <h2>Source materials</h2>
              <span>{visibleSources.length.toString().padStart(2, "0")}</span>
            </div>
            <div className="sm-source-list">
              {visibleSources.map((s) => (
                <button
                  key={s.index}
                  className={`sm-source-card ${selected === s.index ? "is-selected" : ""}`}
                  style={{ "--source-color": colors[s.color] } as CSSProperties}
                  aria-pressed={selected === s.index}
                  onClick={() =>
                    setSelected(selected === s.index ? null : s.index)
                  }
                  onDoubleClick={() =>
                    inspect({
                      kind: "SOURCE MATERIAL",
                      title: s.name,
                      description: `${s.type} · ${s.meta}`,
                      fields: s.fields,
                    })
                  }
                >
                  <span className={`sm-file-icon ${s.color}`}>
                    <Icon name={s.icon} size={25} />
                  </span>
                  <span className="sm-source-copy">
                    <strong>{s.name}</strong>
                    <small>{s.meta}</small>
                    <span>
                      <i
                        className={`sm-dot ${s.status === "Matched" ? "ready" : "review"}`}
                      />
                      {s.status === "Matched"
                        ? "Associated"
                        : s.status === "Review"
                          ? "Needs review"
                          : "Not mapped"}
                    </span>
                  </span>
                  <Icon name="chevron" size={13} />
                  <i className="sm-source-port" />
                </button>
              ))}
              {!visibleSources.length && (
                <p className="sm-empty">No matching source materials.</p>
              )}
              <button
                className="sm-add-source"
                onClick={() => fileInput.current?.click()}
              >
                <Icon name="plus" size={17} /> Add source materials
                <span>Browse files</span>
              </button>
              {selected !== null && (
                <div className="sm-selection">
                  <span>Tracing: {sources[selected].name}</span>
                  <button
                    onClick={() =>
                      inspect({
                        kind: "SOURCE MATERIAL",
                        title: sources[selected].name,
                        description: `${sources[selected].type} · Original source evidence`,
                        fields: sources[selected].fields,
                      })
                    }
                  >
                    Inspect source <Icon name="arrow" size={13} />
                  </button>
                  <button onClick={() => setSelected(null)}>
                    Clear selection
                  </button>
                </div>
              )}
            </div>
          </section>
          <section className="sm-mapping">
            <div className="sm-column-heading">
              <Icon name="branch" size={16} />
              <h2>Match & normalize</h2>
              <span>6 rules</span>
            </div>
            <div className="sm-map-viewport">
              <div
                className="sm-map"
                style={{ transform: `scale(${zoom / 100})` }}
              >
                <div className="sm-map-labels">
                  <span>ASSOCIATE</span>
                  <span>TRANSFORM</span>
                  <span>VALIDATE</span>
                </div>
                <div className="sm-map-guide one" />
                <div className="sm-map-guide two" />
                <svg
                  className="sm-wires"
                  viewBox="0 0 640 650"
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  {visibleSources
                    .filter((s) => s.rule >= 0)
                    .map((s, i) => {
                      const y = 48 + i * 77;
                      const target = 85 + s.rule * 94;
                      return (
                        <path
                          key={`in-${i}`}
                          className={
                            selected !== null && selected !== s.index
                              ? "dimmed"
                              : ""
                          }
                          stroke={colors[s.color]}
                          d={`M 0 ${y} C 115 ${y}, 75 ${target}, 200 ${target}`}
                        />
                      );
                    })}
                  {rules.map((r, i) => (
                    <g
                      key={r.title}
                      className={
                        activeRule !== null && activeRule !== i ? "dimmed" : ""
                      }
                    >
                      <path
                        stroke={colors[r.color]}
                        strokeDasharray={i > 3 ? "4 5" : undefined}
                        d={`M 410 ${85 + i * 94} C 490 ${85 + i * 94}, 455 319, 505 319`}
                      />
                      <circle
                        cx="505"
                        cy="319"
                        r="4"
                        fill="white"
                        stroke={colors[r.color]}
                      />
                    </g>
                  ))}
                  {visibleGroups.map((g, i) => (
                    <path
                      key={`out-${i}`}
                      stroke={colors[g.color]}
                      d={`M 505 319 C 564 319, 568 ${76 + i * 164}, 640 ${76 + i * 164}`}
                    />
                  ))}
                  <circle
                    cx="505"
                    cy="319"
                    r="16"
                    fill="#fff"
                    stroke="#d9e3f1"
                  />
                  <path
                    d="M498 313h11m-4-4 4 4-4 4m6 8h-11m4-4-4 4 4 4"
                    stroke="#8094b0"
                  />
                </svg>
                {rules.map((r, i) => (
                  <button
                    key={r.title}
                    className={`sm-rule ${activeRule === i ? "is-selected" : ""} ${activeRule !== null && activeRule !== i ? "is-muted" : ""}`}
                    style={
                      {
                        top: 52 + i * 94,
                        "--source-color": colors[r.color],
                      } as CSSProperties
                    }
                    onClick={() =>
                      inspect({
                        kind: `MAPPING RULE 0${i + 1}`,
                        title: r.title,
                        description: r.detail,
                        fields: r.mapping,
                      })
                    }
                  >
                    <i className="sm-rule-port in" />
                    <span className={`sm-rule-icon ${r.color}`}>
                      <Icon name={r.icon} size={25} />
                    </span>
                    <span>
                      <strong>{r.title}</strong>
                      <small>{r.caption}</small>
                      <em>
                        <i
                          className={`sm-dot ${i === 4 ? "duplicate" : i === 2 ? "review" : "ready"}`}
                        />
                        {i === 4
                          ? "1 potential match"
                          : i === 2
                            ? "2 tasks need review"
                            : "Rule configured"}
                      </em>
                    </span>
                    <i className="sm-rule-port out" />
                  </button>
                ))}
                <div className="sm-map-tag top">
                  <i className="sm-dot ready" /> Explicit associations
                </div>
                <div className="sm-map-tag bottom">
                  <Icon name="shield" size={12} /> Traceable transformations
                </div>
              </div>
              <div className="sm-map-bottom">
                <span>
                  <i /> Associated <i className="dashed" /> Review path
                </span>
                <div>
                  <button
                    aria-label="Zoom mapping out"
                    disabled={zoom <= 70}
                    onClick={() => setZoom((z) => z - 10)}
                  >
                    −
                  </button>
                  <button
                    aria-label="Reset mapping zoom"
                    onClick={() => setZoom(100)}
                  >
                    {zoom}%
                  </button>
                  <button
                    aria-label="Zoom mapping in"
                    disabled={zoom >= 120}
                    onClick={() => setZoom((z) => z + 10)}
                  >
                    +
                  </button>
                </div>
              </div>
            </div>
          </section>
          <section className="sm-output">
            <div className="sm-column-heading">
              <Icon name="source" size={16} />
              <h2>Outreach tasks</h2>
              <span>{taskCount}</span>
              <label className="sm-task-filter">
                <select
                  aria-label="Filter outreach tasks"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option>All tasks</option>
                  <option>Ready</option>
                  <option>Needs review</option>
                  <option>Duplicate suspicion</option>
                </select>
              </label>
            </div>
            <div className="sm-task-groups">
              {visibleGroups.map((g) => (
                <div
                  className="sm-task-group"
                  key={g.index}
                  style={{ "--source-color": colors[g.color] } as CSSProperties}
                >
                  <button
                    className="sm-group-heading"
                    aria-expanded={!collapsed.includes(g.index)}
                    onClick={() =>
                      setCollapsed((c) =>
                        c.includes(g.index)
                          ? c.filter((v) => v !== g.index)
                          : [...c, g.index],
                      )
                    }
                  >
                    <span className={`sm-student-icon ${g.color}`}>
                      {g.initials}
                    </span>
                    <span>
                      <strong>{g.student}</strong>
                      <small>{g.area}</small>
                    </span>
                    <span className="sm-group-count">
                      {g.tasks.length} {g.tasks.length === 1 ? "task" : "tasks"}
                    </span>
                    <Icon name="chevron" size={14} />
                  </button>
                  {!collapsed.includes(g.index) && (
                    <div className="sm-group-rows">
                      {g.tasks.map((t) => (
                        <button
                          className="sm-task-row"
                          key={t.name}
                          onClick={() =>
                            inspect({
                              kind: "OUTREACH TASK · SAMPLE",
                              title: t.name,
                              description: `${g.student} → ${t.name} · ${t.school}`,
                              fields: [
                                ["Campaign", "Autumn 2026 · PhD outreach"],
                                [
                                  "Preparation",
                                  t.status === "Ready"
                                    ? "Ready · operator confirmation required before sending"
                                    : t.status === "Duplicate"
                                      ? "Blocked · possible prior outreach"
                                      : "Blocked · missing transcript association",
                                ],
                                [
                                  "Mailbox identity",
                                  g.student === "Lin Wei"
                                    ? "lin.wei@example.com"
                                    : "mei.zhang@example.com",
                                ],
                                [
                                  "Source associations",
                                  t.sources
                                    .map((i) => sources[i].name)
                                    .join(" · "),
                                ],
                                [
                                  "Transformation record",
                                  "Shortlist full_name → supervisor; university → institution; trimmed email → recipient",
                                ],
                                ...(t.status === "Duplicate"
                                  ? [
                                      [
                                        "Evidence coverage",
                                        "18 mailbox messages + 6 imported records · 01–15 Sep 2026; earlier history not inspected",
                                      ],
                                    ]
                                  : []),
                              ],
                            })
                          }
                        >
                          <span className="sm-tree-dot" />
                          <Icon name="file" size={17} />
                          <span className="sm-task-name">
                            <strong>{t.name}</strong>
                            <small>{t.school}</small>
                          </span>
                          <span
                            className={`sm-task-status ${t.status.toLowerCase()}`}
                            title={
                              t.status === "Duplicate"
                                ? "Duplicate suspicion"
                                : t.status
                            }
                          >
                            <i className={`sm-dot ${t.status.toLowerCase()}`} />
                            {t.status === "Duplicate" ? "Check" : t.status}
                          </span>
                          <span
                            className="sm-task-evidence"
                            title={`${t.sources.length} source associations`}
                          >
                            <Icon name="link" size={13} />
                            {t.sources.length}
                          </span>
                          <Icon name="arrow" size={13} />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {!visibleGroups.length && (
                <div className="sm-empty">
                  <Icon name="search" size={25} />
                  <p>No matching outreach tasks.</p>
                  <button
                    className="sm-button"
                    onClick={() => {
                      setSelected(null);
                      setQuery("");
                      setFilter("All tasks");
                    }}
                  >
                    Clear task filters
                  </button>
                </div>
              )}
            </div>
            <div className="sm-output-note">
              <Icon name="shield" size={15} />
              <span>
                Ready means prepared.
                <br />
                Sending requires operator confirmation.
              </span>
            </div>
          </section>
        </main>
        <footer className="sm-footer">
          <span>
            <i className="sm-dot ready" /> Sample data · local preview only
            <span className="footer-separator">|</span>
            {sources.length} sources → 6 rules → 12 outreach tasks
          </span>
          <span>
            <Icon name="link" size={12} /> Every association retains its source
          </span>
        </footer>
      </div>
      <input
        ref={fileInput}
        type="file"
        multiple
        accept=".xlsx,.csv,.docx,.pdf,.txt,.eml,.msg"
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (!files.length) return;
          setSources((s) => [
            ...s,
            ...files.map((f): Source => ({
              name: f.name,
              type: /\.(xlsx|csv)$/i.test(f.name) ? "Spreadsheet" : "Document",
              icon: "file" as const,
              color: "slate",
              meta: `${Math.max(1, Math.round(f.size / 1024))} KB · local file`,
              status: "Pending",
              rule: -1,
              fields: [
                ["File", f.name],
                ["State", "Queued in this sample session only"],
                ["Mapping", "Not parsed or associated"],
                ["Next step", "Import through Core for supported extraction"],
              ] as [string, string][],
            })),
          ]);
          setNotice(
            `${files.length} local file${files.length > 1 ? "s" : ""} added to this preview. File contents have not been parsed; no tasks were created.`,
          );
          e.target.value = "";
        }}
      />
      <dialog
        ref={drawer}
        aria-label="Source mapping inspector"
        className="sm-detail"
        onClick={(e) => {
          if (e.target === e.currentTarget) drawer.current?.close();
        }}
      >
        <div className="sm-detail-inner">
          <div className="sm-detail-top">
            <span>{inspection?.kind}</span>
            <button
              aria-label="Close inspector"
              onClick={() => drawer.current?.close()}
            >
              <Icon name="close" size={19} />
            </button>
          </div>
          <div className="sm-detail-symbol">
            <Icon name="link" size={27} />
          </div>
          <h2>{inspection?.title}</h2>
          <p>{inspection?.description}</p>
          <div className="sm-detail-fields">
            {inspection?.fields.map(([label, value]) => (
              <div key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
          <div className="sm-detail-note">
            <Icon name="shield" size={17} /> Original sources are retained. This
            sample workspace does not modify live preparations or send messages.
          </div>
          <button
            className="primary full"
            onClick={() => drawer.current?.close()}
          >
            Done
          </button>
        </div>
      </dialog>
    </AppShell>
  );
}

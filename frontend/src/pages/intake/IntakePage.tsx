import SearchField from "../../shared/SearchField";
import { useEffect, useRef, useState, type DragEvent } from "react";
import type { CSSProperties } from "react";
import Icon from "../../shared/Icon";
import { AppShell, Topbar, NavigationItem } from "../../app/shell";
import { navigate } from "../../app/routes";
import {
  students,
  categories,
  categoryById,
  colors,
  cloneWorkspace,
  attachmentPool,
  effectiveAttachments,
} from "./normalization-model";
import type {
  Category,
  CategoryId,
  RawSource,
  Student,
  StudentWorkspace,
  Supervisor,
} from "./normalization-model";
import "./SourceMapping.css";

type Inspection = {
  kind: string;
  title: string;
  description: string;
  fields: [string, string][];
};

type TaskFilter = "all" | "active" | "incomplete";

const filterLabels: Record<TaskFilter, string> = {
  all: "All",
  active: "Active",
  incomplete: "Missing email",
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
  const [studentId, setStudentId] = useState(students[0].id);
  const [spaces, setSpaces] = useState<
    Record<string, StudentWorkspace>
  >(() =>
    Object.fromEntries(
      students.map((student) => [student.id, cloneWorkspace(student.workspace)]),
    ),
  );
  const student: Student =
    students.find((value) => value.id === studentId) ?? students[0];
  const space = spaces[studentId];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [taskEditorId, setTaskEditorId] = useState<string | null>(null);
  const [filter, setFilter] = useState<TaskFilter>("all");
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const drawer = useRef<HTMLDialogElement>(null);
  const taskDrawer = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (taskEditorId) taskDrawer.current?.showModal();
  }, [taskEditorId]);
  const closeTask = () => {
    taskDrawer.current?.close();
    setTaskEditorId(null);
  };

  const inspect = (value: Inspection) => {
    setInspection(value);
    drawer.current?.showModal();
  };
  const inspectSource = (source: RawSource) =>
    inspect({
      kind: "RAW SOURCE MATERIAL",
      title: source.name,
      description: `${source.type} · ${source.meta}`,
      fields: source.fields,
    });
  const inspectCategory = (category: Category) => {
    const classified = space.classified[category.id];
    const active = space.supervisors.filter((value) => value.email);
    const incomplete = space.supervisors.filter((value) => !value.email);
    const dynamic: [string, string][] =
      category.id === "master"
        ? [
            [
              "Resolved tasks",
              `${active.length} active · ${incomplete.length} missing email`,
            ],
          ]
        : category.id === "drafts"
          ? [
              [
                "Matched letters",
                active
                  .flatMap((value) => (value.draft ? [value.draft.section] : []))
                  .join(" · ") || "None yet",
              ],
            ]
          : category.id === "attachments"
            ? [
                [
                  "Attachment pool",
                  attachmentPool(space).join(" · ") || "No files classified",
                ],
                [
                  "Default target",
                  `${active.length} identified task${active.length === 1 ? "" : "s"}`,
                ],
                [
                  "Per-task overrides",
                  overrideCount() === 0
                    ? "None — defaults apply"
                    : `${overrideCount()} task${overrideCount() === 1 ? "" : "s"} customized`,
                ],
              ]
            : category.id === "profile"
              ? [["Student", `${student.studentId} · ${student.name}`]]
              : category.id === "mailbox"
                ? [["Bound mailbox", student.mailbox]]
                : [
                    [
                      "Evidence sources",
                      classified.map((value) => value.name).join(" · ") ||
                        "None yet",
                    ],
                  ];
    inspect({
      kind: "STABLE CATEGORY",
      title: category.title,
      description: category.detail,
      fields: [
        ...category.mapping,
        ...dynamic,
        [
          `Classified for ${student.name}`,
          classified.length
            ? classified.map((value) => value.name).join(" · ")
            : "Nothing classified yet",
        ],
      ],
    });
  };
  const sourceAssociations = (supervisor: Supervisor) =>
    [
      space.classified.master[0]?.name,
      supervisor.draft?.document,
      ...space.classified.attachments.map((value) => value.name),
      space.classified.mailbox[0]?.name,
    ]
      .filter((value): value is string => Boolean(value))
      .join(" · ");

  const selectedSource =
    space.unresolved.find((value) => value.id === selectedId) ?? null;

  const activeSupervisors = space.supervisors.filter((value) => value.email);
  const incompleteSupervisors = space.supervisors.filter(
    (value) => !value.email,
  );
  const poolFiles = attachmentPool(space);
  const overrideCount = () =>
    Object.values(space.overrides).filter((files) => files.length).length;
  const visibleSources = space.unresolved.filter((value) =>
    `${value.name} ${value.type} ${value.meta}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const visibleTasks = [...activeSupervisors, ...incompleteSupervisors].filter(
    (value) =>
      (filter === "all"
        ? true
        : filter === "active"
          ? Boolean(value.email)
          : !value.email) &&
      `${value.name} ${value.institution} ${value.email ?? ""} ${value.draft?.section ?? ""}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const editedSupervisor =
    space.supervisors.find((value) => value.id === taskEditorId) ?? null;

  const patchSpace = (
    produce: (draft: StudentWorkspace) => StudentWorkspace,
    message: string,
  ) => {
    setSpaces((previous) => ({
      ...previous,
      [studentId]: produce(previous[studentId]),
    }));
    setNotice(message);
  };

  const stageFiles = (files: File[]) => {
    if (!files.length) return;
    const staged: RawSource[] = files.map((file, index) => ({
      id: `staged-${Date.now()}-${index}`,
      name: file.name,
      type: /\.(xlsx|csv)$/i.test(file.name) ? "Spreadsheet" : "Document",
      icon: "file" as const,
      color: "slate",
      meta: `${Math.max(1, Math.round(file.size / 1024))} KB · local file`,
      files: /\.(pdf|zip)$/i.test(file.name) ? [file.name] : undefined,
      fields: [
        ["File", file.name],
        ["State", "Unresolved in this sample session only"],
        ["Next step", "Classify into a stable category"],
        ["Import", "Import through Core for supported extraction"],
      ],
    }));
    patchSpace(
      (draft) => ({ ...draft, unresolved: [...staged, ...draft.unresolved] }),
      `${files.length} local file${files.length > 1 ? "s" : ""} staged as unresolved raw sources. File contents are not parsed in this sample.`,
    );
    setSelectedId(null);
  };

  const dragHasFiles = (event: DragEvent) =>
    Array.from(event.dataTransfer?.types ?? []).includes("Files");
  const onDragEnter = (event: DragEvent) => {
    if (!dragHasFiles(event)) return;
    dragDepth.current += 1;
    setDragging(true);
  };
  const onDragOver = (event: DragEvent) => {
    if (!dragHasFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  };
  const onDragLeave = (event: DragEvent) => {
    if (!dragHasFiles(event)) return;
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  };
  const onDrop = (event: DragEvent) => {
    if (!dragHasFiles(event)) return;
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    stageFiles(Array.from(event.dataTransfer.files));
  };
  const classify = (categoryId: CategoryId) => {
    const source = selectedSource;
    if (!source) return;
    const category = categoryById(categoryId);
    patchSpace(
      (draft) => ({
        ...draft,
        unresolved: draft.unresolved.filter((value) => value.id !== source.id),
        classified: {
          ...draft.classified,
          [categoryId]: [source, ...draft.classified[categoryId]],
        },
      }),
      `Classified “${source.name}” into ${category.title} for ${student.name}.`,
    );
    setSelectedId(null);
  };
  const sendBack = (categoryId: CategoryId, sourceId: string) => {
    const source = space.classified[categoryId].find(
      (value) => value.id === sourceId,
    );
    if (!source) return;
    const category = categoryById(categoryId);
    patchSpace(
      (draft) => ({
        ...draft,
        unresolved: [...draft.unresolved, source],
        classified: {
          ...draft.classified,
          [categoryId]: draft.classified[categoryId].filter(
            (value) => value.id !== sourceId,
          ),
        },
      }),
      `Returned “${source.name}” from ${category.title} to unresolved raw sources.`,
    );
    if (selectedId === sourceId) setSelectedId(null);
  };
  const toggleFile = (supervisorId: string, file: string) => {
    setSpaces((previous) => {
      const current = previous[studentId];
      const excluded = new Set(current.overrides[supervisorId] ?? []);
      if (excluded.has(file)) excluded.delete(file);
      else excluded.add(file);
      const overrides = { ...current.overrides };
      if (excluded.size) overrides[supervisorId] = [...excluded];
      else delete overrides[supervisorId];
      return { ...previous, [studentId]: { ...current, overrides } };
    });
  };
  const resetOverrides = (supervisorId: string) => {
    const supervisor = space.supervisors.find((value) => value.id === supervisorId);
    setSpaces((previous) => {
      const current = previous[studentId];
      const overrides = { ...current.overrides };
      delete overrides[supervisorId];
      return { ...previous, [studentId]: { ...current, overrides } };
    });
    setNotice(
      `Reset attachments for ${supervisor?.name ?? "task"} to the default: every identified file.`,
    );
  };
  const switchStudent = (id: string) => {
    if (id === studentId) return;
    setStudentId(id);
    setSelectedId(null);
    setTaskEditorId(null);
    setFilter("all");
    setNotice("");
  };
  const categorySummary = (category: Category): string => {
    switch (category.id) {
      case "master":
        return `${activeSupervisors.length} with email · ${incompleteSupervisors.length} missing email`;
      case "drafts": {
        const matched = activeSupervisors.filter((value) => value.draft).length;
        return `${matched} matched letter${matched === 1 ? "" : "s"}`;
      }
      case "profile":
        return `${student.studentId} · ${student.area}`;
      case "mailbox":
        return student.mailbox;
      case "records":
        return space.classified.records.length
          ? `${space.classified.records.length} evidence source${space.classified.records.length === 1 ? "" : "s"}`
          : "No evidence classified yet";
      case "attachments": {
        const overrides = overrideCount();
        return `${poolFiles.length} file${poolFiles.length === 1 ? "" : "s"} · default to ${activeSupervisors.length} task${activeSupervisors.length === 1 ? "" : "s"}${
          overrides ? ` · ${overrides} override${overrides === 1 ? "" : "s"}` : ""
        }`;
      }
    }
  };

  return (
    <AppShell
      className="sm-app"
      navigation={
        <>
          <NavigationItem route="workflow" label="Outreach workflow" />
          <NavigationItem route="sources" active />
          <NavigationItem route="review" />
          <NavigationItem route="execution" />
          <NavigationItem route="mailbox" />
          <div className="sm-rail-line" />
          <button
            aria-label="Normalization workspace guide"
            title="Normalization workspace guide"
            onClick={() =>
              inspect({
                kind: "WORKSPACE GUIDE",
                title: "Normalize one student at a time",
                description:
                  "Work unresolved raw materials through stable categories and review the resolved tasks for the selected student. Switch students in the top bar.",
                fields: [
                  [
                    "1 · Unresolved raw sources",
                    "Imported files not yet placed in a stable category",
                  ],
                  [
                    "2 · Stable categories",
                    "Classify sources here; attachments default to every identified task",
                  ],
                  [
                    "3 · Resolved tasks",
                    "Supervisors with an email are active; missing emails stay grey on the board",
                  ],
                  [
                    "Per-task overrides",
                    "Open a task to remove an attachment for that task only",
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
      <div
        className="workspace"
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <Topbar
          className="sm-topbar"
          breadcrumb="Source mapping"
          homeHref="#workflow"
          onHome={onBack}
        >
          <div
            className="sm-student-switch"
            role="group"
            aria-label="Switch student"
          >
            {students.map((value) => (
              <button
                key={value.id}
                className={value.id === studentId ? "is-active" : ""}
                aria-pressed={value.id === studentId}
                title={`${value.studentId} · ${value.area} · ${value.mailbox}`}
                onClick={() => switchStudent(value.id)}
              >
                <span className={`sm-student-avatar ${value.color}`}>
                  {value.initials}
                </span>
                <strong>{value.name}</strong>
              </button>
            ))}
          </div>
          <span className="sm-divider" />
          <div className="sm-campaign">
            <Icon name="folder" size={15} />
            <span>Autumn 2026 · PhD outreach</span>
            <span className="sm-demo-label">DEMO</span>
          </div>
          <SearchField
            label="Search raw sources and tasks"
            value={query}
            onChange={setQuery}
            placeholder="Search raw sources or resolved tasks…"
            iconSize={16}
          />
          <button
            className="sm-add-top"
            onClick={() => fileInput.current?.click()}
          >
            <Icon name="plus" size={14} /> Add raw sources
          </button>
          <span className="sm-sample">
            <i /> Sample
          </span>
          <div className="sm-user">OP</div>
        </Topbar>
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
              <h2>Unresolved raw sources</h2>
              <span>
                {visibleSources.length.toString().padStart(2, "0")}
              </span>
            </div>
            <div className="sm-source-list">
              {visibleSources.map((value) => (
                <button
                  key={value.id}
                  className={`sm-source-card ${selectedId === value.id ? "is-selected" : ""}`}
                  style={{ "--source-color": colors[value.color] } as CSSProperties}
                  aria-pressed={selectedId === value.id}
                  onClick={() =>
                    setSelectedId(
                      selectedId === value.id ? null : value.id,
                    )
                  }
                  onDoubleClick={() => inspectSource(value)}
                >
                  <span className={`sm-file-icon ${value.color}`}>
                    <Icon name={value.icon} size={20} />
                  </span>
                  <span className="sm-source-copy">
                    <strong>{value.name}</strong>
                    <small>{value.meta}</small>
                    <span className="sm-source-meta-line">
                      {value.suggested ? (
                        <em className="sm-suggested">
                          Suggested: {categoryById(value.suggested).title}
                        </em>
                      ) : (
                        <em>Not yet classified</em>
                      )}
                    </span>
                  </span>
                  <Icon name="chevron" size={13} />
                </button>
              ))}
              {!visibleSources.length && (
                <p className="sm-empty">
                  {query
                    ? "No matching raw sources."
                    : `Every raw source for ${student.name} is classified.`}
                </p>
              )}
              <button
                className="sm-add-source"
                onClick={() => fileInput.current?.click()}
                title="Drag & drop files anywhere on the board, or click to browse"
              >
                <Icon name="plus" size={17} /> Drag &amp; drop raw source materials
                <span>Browse files</span>
              </button>
              {selectedSource && (
                <div className="sm-selection">
                  <span>
                    Classifying <strong>{selectedSource.name}</strong> — pick a
                    category in the center column.
                  </span>
                  <button onClick={() => inspectSource(selectedSource)}>
                    Inspect source <Icon name="arrow" size={13} />
                  </button>
                  <button onClick={() => setSelectedId(null)}>
                    Clear selection
                  </button>
                </div>
              )}
            </div>
          </section>
          <section className="sm-categories">
            <div className="sm-column-heading">
              <Icon name="branch" size={16} />
              <h2>Stable categories</h2>
              <span>{categories.length} fixed</span>
            </div>
            <div className="sm-category-list">
              {categories.map((category) => {
                const classified = space.classified[category.id];
                return (
                  <article
                    key={category.id}
                    className={`sm-category-card ${selectedSource ? "has-target" : ""}`}
                    data-category={category.id}
                    style={
                      { "--source-color": colors[category.color] } as CSSProperties
                    }
                  >
                    <button
                      className="sm-category-main"
                      onClick={() => inspectCategory(category)}
                      title={category.caption}
                    >
                      <span className={`sm-rule-icon ${category.color}`}>
                        <Icon name={category.icon} size={17} />
                      </span>
                      <span className="sm-category-copy">
                        <strong>{category.title}</strong>
                        <small>{categorySummary(category)}</small>
                      </span>
                      <span className="sm-category-count">
                        {classified.length}
                      </span>
                    </button>
                    <div className="sm-classified-chips">
                      {classified.length ? (
                        classified.map((source) => (
                          <span className="sm-file-chip" key={source.id}>
                            <Icon name={source.icon} size={11} />
                            <span title={source.name}>{source.name}</span>
                            <button
                              aria-label={`Return ${source.name} to unresolved raw sources`}
                              title="Return to unresolved raw sources"
                              onClick={() => sendBack(category.id, source.id)}
                            >
                              <Icon name="close" size={10} />
                            </button>
                          </span>
                        ))
                      ) : (
                        <span className="sm-file-chip is-empty">
                          Nothing classified
                        </span>
                      )}
                    </div>
                    <button
                      className="sm-classify-btn"
                      disabled={!selectedSource}
                      aria-label={
                        selectedSource
                          ? `Classify ${selectedSource.name} into ${category.title}`
                          : `Classify selected raw source into ${category.title}`
                      }
                      title={
                        selectedSource
                          ? `Classify “${selectedSource.name}” into ${category.title}`
                          : "Select a raw source first"
                      }
                      onClick={() => classify(category.id)}
                    >
                      <Icon name="plus" size={15} />
                    </button>
                  </article>
                );
              })}
            </div>
          </section>
          <section className="sm-output">
            <div className="sm-column-heading">
              <Icon name="source" size={16} />
              <h2>Resolved tasks</h2>
              <span>{visibleTasks.length}</span>
              <label className="sm-task-filter">
                <select
                  aria-label="Filter resolved tasks"
                  value={filter}
                  onChange={(event) =>
                    setFilter(event.target.value as TaskFilter)
                  }
                >
                  {(Object.keys(filterLabels) as TaskFilter[]).map((value) => (
                    <option key={value} value={value}>
                      {filterLabels[value]}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="sm-task-list">
              <div className="sm-task-student">
                <span className={`sm-student-avatar ${student.color}`}>
                  {student.initials}
                </span>
                <strong>{student.name}</strong>
                <small>
                  {student.studentId} · {student.area}
                </small>
                <span className="sm-task-student-mail">
                  <Icon name="mail" size={12} />
                  {student.mailbox}
                </span>
              </div>
              {visibleTasks.map((supervisor) => {
                const isActive = Boolean(supervisor.email);
                const attached = effectiveAttachments(space, supervisor.id);
                return (
                  <button
                    key={supervisor.id}
                    className={`sm-task-row ${isActive ? "" : "is-incomplete"}`}
                    onClick={() => setTaskEditorId(supervisor.id)}
                  >
                    <span className="sm-task-row-icon">
                      <Icon name={supervisor.draft ? "file" : "user"} size={15} />
                    </span>
                    <span className="sm-task-row-copy">
                      <strong>{supervisor.name}</strong>
                      <small>
                        {isActive
                          ? `${supervisor.institution} · ${supervisor.email}`
                          : `${supervisor.institution} · no email identified`}
                      </small>
                    </span>
                    <span
                      className={`sm-task-badge ${supervisor.draft ? "" : "is-off"}`}
                      title={
                        supervisor.draft
                          ? `Matched draft · ${supervisor.draft.section}`
                          : "No draft letter matched"
                      }
                    >
                      <Icon name="file" size={12} />
                      {supervisor.draft ? "Draft" : "No draft"}
                    </span>
                    <span
                      className={`sm-task-badge ${isActive && attached.length ? "" : "is-off"}`}
                      title={
                        isActive
                          ? `Attachments: ${attached.join(" · ") || "none for this task"}`
                          : "Attachments held until an email is identified"
                      }
                    >
                      <Icon name="clip" size={12} />
                      {isActive ? attached.length : "–"}
                    </span>
                    <span
                      className={`sm-task-pill ${isActive ? "active" : "incomplete"}`}
                    >
                      <i className={`sm-dot ${isActive ? "ready" : ""}`} />
                      {isActive ? "Active" : "Missing email"}
                    </span>
                  </button>
                );
              })}
              {!visibleTasks.length && (
                <div className="sm-empty">
                  <Icon name="search" size={25} />
                  <p>No matching resolved tasks.</p>
                  <button
                    className="sm-button"
                    onClick={() => {
                      setQuery("");
                      setFilter("all");
                    }}
                  >
                    Clear task filters
                  </button>
                </div>
              )}
            </div>
            <div className="sm-output-note">
              <Icon name="shield" size={14} />
              <span>
                Grey tasks are master-list supervisors without an email. Open
                any task for draft, recipient and attachment overrides.
              </span>
            </div>
          </section>
        </main>
        <footer className="sm-footer">
          <span>
            <i className="sm-dot ready" /> Sample data · local preview only
            <span className="footer-separator">|</span>
            {space.unresolved.length} unresolved · {activeSupervisors.length}{" "}
            active · {incompleteSupervisors.length} missing email ·{" "}
            {student.name}
          </span>
          <span>
            <Icon name="link" size={12} /> Attachments default to all
            identified tasks
          </span>
        </footer>
        {dragging && (
          <div className="sm-drop-overlay" aria-hidden="true">
            <div className="sm-drop-card">
              <span className="sm-drop-icon">
                <Icon name="file" size={26} />
              </span>
              <strong>Drop files to stage raw sources</strong>
              <span>
                Files are added to {student.name}’s unresolved list, ready to
                classify into stable categories. .xlsx, .csv, .docx, .pdf,
                .txt, .eml, .msg and .zip are accepted.
              </span>
            </div>
          </div>
        )}
      </div>
      <input
        ref={fileInput}
        type="file"
        multiple
        accept=".xlsx,.csv,.docx,.pdf,.txt,.eml,.msg,.zip"
        hidden
        onChange={(event) => {
          stageFiles(Array.from(event.target.files ?? []));
          event.target.value = "";
        }}
      />
      <dialog
        ref={drawer}
        aria-label="Source mapping inspector"
        className="sm-detail"
        onClick={(event) => {
          if (event.target === event.currentTarget) drawer.current?.close();
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
            <Icon name="shield" size={17} /> Normalization is local to this
            sample workspace. Original sources are retained and no live
            preparation or message is modified.
          </div>
          <button
            className="primary full"
            onClick={() => drawer.current?.close()}
          >
            Done
          </button>
        </div>
      </dialog>
      <dialog
        ref={taskDrawer}
        aria-label="Resolved task inspector"
        className="sm-detail sm-task-detail"
        onClick={(event) => {
          if (event.target === event.currentTarget) closeTask();
        }}
      >
        {editedSupervisor &&
          (() => {
            const isActive = Boolean(editedSupervisor.email);
            const excluded = space.overrides[editedSupervisor.id] ?? [];
            const attached = effectiveAttachments(space, editedSupervisor.id);
            return (
              <div className="sm-detail-inner">
                <div className="sm-detail-top">
                  <span>
                    {isActive
                      ? "OUTREACH TASK · ACTIVE"
                      : "OUTREACH TASK · INCOMPLETE"}
                  </span>
                  <button
                    aria-label="Close task inspector"
                    onClick={closeTask}
                  >
                    <Icon name="close" size={19} />
                  </button>
                </div>
                <div
                  className={`sm-detail-symbol ${isActive ? "" : "is-incomplete"}`}
                >
                  <Icon name={editedSupervisor.draft ? "file" : "user"} size={27} />
                </div>
                <h2>{editedSupervisor.name}</h2>
                <p>
                  {student.name} → {editedSupervisor.name} ·{" "}
                  {editedSupervisor.institution}
                </p>
                <div className="sm-detail-fields">
                  <div>
                    <span>Campaign</span>
                    <strong>Autumn 2026 · PhD outreach</strong>
                  </div>
                  <div>
                    <span>Recipient address</span>
                    <strong>
                      {editedSupervisor.email ??
                        "Missing — no usable address in the supervisor master list"}
                    </strong>
                  </div>
                  <div>
                    <span>Matched draft</span>
                    <strong>
                      {editedSupervisor.draft
                        ? `${editedSupervisor.draft.section} · ${editedSupervisor.draft.document}`
                        : "No letter matched"}
                    </strong>
                  </div>
                  {editedSupervisor.draft && (
                    <div>
                      <span>Draft subject</span>
                      <strong>{editedSupervisor.draft.subject}</strong>
                    </div>
                  )}
                  <div>
                    <span>Mailbox identity</span>
                    <strong>{student.mailbox}</strong>
                  </div>
                  <div>
                    <span>Source associations</span>
                    <strong>{sourceAssociations(editedSupervisor)}</strong>
                  </div>
                  {!isActive && (
                    <div>
                      <span>Blocker</span>
                      <strong>
                        invalid_recipient · task stays incomplete until an email
                        is identified
                      </strong>
                    </div>
                  )}
                </div>
                {isActive && (
                  <div className="sm-detail-attachments">
                    <div className="sm-detail-attach-head">
                      <span>
                        <Icon name="clip" size={14} /> Attachments
                      </span>
                      <em>
                        {excluded.length
                          ? `${attached.length} of ${poolFiles.length} · per-task override`
                          : `Default · all ${poolFiles.length} identified files`}
                      </em>
                    </div>
                    {poolFiles.map((file) => (
                      <label key={file}>
                        <input
                          type="checkbox"
                          checked={!excluded.includes(file)}
                          onChange={() => toggleFile(editedSupervisor.id, file)}
                        />
                        <Icon name="clip" size={13} />
                        {file}
                      </label>
                    ))}
                    {excluded.length > 0 && (
                      <button
                        className="sm-reset-btn"
                        onClick={() => resetOverrides(editedSupervisor.id)}
                      >
                        <Icon name="refresh" size={12} />
                        Reset to default (all files)
                      </button>
                    )}
                  </div>
                )}
                <div className="sm-detail-note">
                  <Icon name="shield" size={17} /> Unchecking a file removes it
                  for this task only. Every other task keeps the default
                  attachment set.
                </div>
                <button className="primary full" onClick={closeTask}>
                  Done
                </button>
              </div>
            );
          })()}
      </dialog>
    </AppShell>
  );
}

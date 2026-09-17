import type { IconName } from "../../shared/Icon";

export type ColorKey =
  | "green"
  | "blue"
  | "purple"
  | "rose"
  | "amber"
  | "slate";

export const colors: Record<ColorKey, string> = {
  green: "#17b887",
  blue: "#4b86ff",
  purple: "#9864ef",
  rose: "#fa647d",
  amber: "#f5aa2c",
  slate: "#91a0b9",
};

export type CategoryId =
  | "master"
  | "drafts"
  | "profile"
  | "mailbox"
  | "records"
  | "attachments";

export type RawSource = {
  id: string;
  name: string;
  type: string;
  icon: IconName;
  color: ColorKey;
  meta: string;
  suggested?: CategoryId;
  files?: string[];
  fields: [string, string][];
};

export type Category = {
  id: CategoryId;
  title: string;
  caption: string;
  icon: IconName;
  color: ColorKey;
  detail: string;
  mapping: [string, string][];
};

export const categories: Category[] = [
  {
    id: "master",
    title: "Supervisor master list",
    caption: "Supervisor rows and recipient addresses",
    icon: "source",
    color: "green",
    detail:
      "Rows from the supervisor workbook resolve to outreach tasks for the current student. A row with a usable email becomes an active task; a row without an address stays visible as an incomplete task.",
    mapping: [
      ["Supervisor + institution", "Outreach task identity"],
      ["Email column", "Recipient address"],
      ["Missing address", "Incomplete task held on the board"],
    ],
  },
  {
    id: "drafts",
    title: "Draft letters",
    caption: "Message documents matched to supervisors",
    icon: "file",
    color: "blue",
    detail:
      "Normalize each letter's email declaration, subject and body, then match it to one supervisor. The matched draft is shown directly on the resolved task.",
    mapping: [
      ["Document section", "Matched draft"],
      ["Email: declaration", "Recipient evidence"],
      ["Subject / body", "Preparation content"],
    ],
  },
  {
    id: "attachments",
    title: "Attachments",
    caption: "Default to every identified task",
    icon: "clip",
    color: "rose",
    detail:
      "Files classified here default onto every task with an identified email for the current student. Removing a file on one task creates a per-task override only; every other task keeps the default.",
    mapping: [
      ["Classified file", "Available to all identified tasks"],
      ["Default", "Attached to all resolved tasks"],
      ["Per-task removal", "Override for that task only"],
    ],
  },
  {
    id: "profile",
    title: "Student profile",
    caption: "Student identity and context",
    icon: "user",
    color: "purple",
    detail:
      "Identity fields establish which student this workspace normalizes. Student identity fields take precedence over filename or mailbox guesses.",
    mapping: [
      ["student_id", "Student identity"],
      ["Research area", "Student context"],
      ["Identity fields", "Source precedence"],
    ],
  },
  {
    id: "mailbox",
    title: "Sending mailbox",
    caption: "Student-owned sender identity",
    icon: "mail",
    color: "amber",
    detail:
      "Bind the mailbox registered to the student as the preparation sender. Binding prepares an action but never grants permission to send.",
    mapping: [
      ["student.mailbox_id", "Mailbox identity"],
      ["mailbox.address", "Preparation sender"],
      ["Confirmation", "Required separately"],
    ],
  },
  {
    id: "records",
    title: "Prior outreach records",
    caption: "Campaign-scoped reconciliation evidence",
    icon: "database",
    color: "slate",
    detail:
      "Imported records and mailbox observations are evidence for reconciliation and duplicate detection. They never overwrite preparation content.",
    mapping: [
      ["Imported CSV", "Reconciliation evidence"],
      ["Mailbox observation", "Duplicate detection"],
      ["Authority", "Does not overwrite preparation"],
    ],
  },
];

export const categoryById = (id: CategoryId): Category =>
  categories.find((category) => category.id === id)!;

export type DraftMatch = {
  document: string;
  section: string;
  subject: string;
};

export type Supervisor = {
  id: string;
  name: string;
  institution: string;
  email: string | null;
  draft: DraftMatch | null;
};

export type StudentWorkspace = {
  unresolved: RawSource[];
  classified: Record<CategoryId, RawSource[]>;
  baseAttachments: string[];
  overrides: Record<string, string[]>;
  supervisors: Supervisor[];
};

export type Student = {
  id: string;
  name: string;
  initials: string;
  area: string;
  color: ColorKey;
  studentId: string;
  mailbox: string;
  workspace: StudentWorkspace;
};

const letterFields = (
  section: string,
  email: string,
  subject: string,
): [string, string][] => [
  ["Section", section],
  ["Email: declaration", email],
  ["subject → subject", subject],
  ["body → preparation", "Dear … I am writing to express my interest…"],
];

const linWorkspace: StudentWorkspace = {
  baseAttachments: ["Lin_Wei_CV.pdf", "Research proposal.pdf"],
  overrides: {},
  supervisors: [
    {
      id: "lw-chen",
      name: "Dr. Sarah Chen",
      institution: "University of Oxford",
      email: "sarah.chen@example.edu",
      draft: {
        document: "Outreach letters.docx",
        section: "Letter 01 · Sarah Chen",
        subject: "PhD inquiry · Human-centered AI",
      },
    },
    {
      id: "lw-brown",
      name: "Prof. Michael Brown",
      institution: "University of Cambridge",
      email: "michael.brown@example.edu",
      draft: {
        document: "Outreach letters.docx",
        section: "Letter 02 · Michael Brown",
        subject: "PhD inquiry · Human-centered AI",
      },
    },
    {
      id: "lw-kim",
      name: "Dr. Daniel Kim",
      institution: "ETH Zürich",
      email: "daniel.kim@example.ch",
      draft: {
        document: "Outreach letters.docx",
        section: "Letter 03 · Daniel Kim",
        subject: "PhD inquiry · Human-centered AI",
      },
    },
    {
      id: "lw-muller",
      name: "Prof. Anna Müller",
      institution: "EPFL",
      email: "anna.muller@example.ch",
      draft: {
        document: "Outreach letters.docx",
        section: "Letter 04 · Anna Müller",
        subject: "PhD inquiry · Human-centered AI",
      },
    },
    {
      id: "lw-garcia",
      name: "Dr. Lucas Garcia",
      institution: "TU Delft",
      email: "lucas.garcia@example.nl",
      draft: null,
    },
    {
      id: "lw-wilson",
      name: "Dr. James Wilson",
      institution: "Imperial College London",
      email: null,
      draft: null,
    },
  ],
  classified: {
    master: [
      {
        id: "lw-master",
        name: "Supervisor shortlist.xlsx",
        type: "Spreadsheet",
        icon: "source",
        color: "green",
        meta: "6 rows for this student",
        fields: [
          ["Sheet / rows", "Supervisors · rows 2–7"],
          ["full_name → supervisor", "Chen · Brown · Kim · Müller · Garcia · Wilson"],
          ["university → institution", "Oxford · Cambridge · ETH · EPFL · TU Delft · Imperial"],
          ["email → recipient", "5 identified · 1 missing"],
        ],
      },
    ],
    drafts: [
      {
        id: "lw-letters",
        name: "Outreach letters.docx",
        type: "Document",
        icon: "file",
        color: "blue",
        meta: "2 letters matched",
        fields: letterFields(
          "Letter 01 · Sarah Chen",
          "sarah.chen@example.edu",
          "PhD inquiry · Human-centered AI",
        ),
      },
    ],
    profile: [
      {
        id: "lw-profile",
        name: "Student profiles.xlsx",
        type: "Spreadsheet",
        icon: "user",
        color: "purple",
        meta: "ST-001 · 8 fields",
        fields: [
          ["student_id → student", "ST-001 · Lin Wei"],
          ["Research area", "Human-centered AI"],
          ["mailbox_id → mailbox", "MB-001"],
          ["Source precedence", "Student identity fields"],
        ],
      },
    ],
    mailbox: [
      {
        id: "lw-mailbox",
        name: "Student mailboxes · 163 Mail",
        type: "Mailbox",
        icon: "mail",
        color: "amber",
        meta: "lin.wei@example.com",
        fields: [
          ["Student", "Lin Wei · ST-001"],
          ["Mailbox", "lin.wei@example.com"],
          ["Association", "Student-owned mailbox ID"],
          ["Usage", "Sender identity only"],
        ],
      },
    ],
    records: [],
    attachments: [
      {
        id: "lw-pack",
        name: "Lin Wei attachment pack",
        type: "Attachment",
        icon: "clip",
        color: "slate",
        meta: "2 files · all identified tasks",
        files: ["Lin_Wei_CV.pdf", "Research proposal.pdf"],
        fields: [
          ["Files", "Lin_Wei_CV.pdf · Research proposal.pdf"],
          ["Default", "Every task with an identified email"],
          ["Association", "Explicit student identifier ST-001"],
          ["Overrides", "Configured per task"],
        ],
      },
    ],
  },
  unresolved: [
    {
      id: "lw-transcript",
      name: "Lin Wei academic transcript.pdf",
      type: "Document",
      icon: "file",
      color: "rose",
      meta: "1 page · attachment file",
      suggested: "attachments",
      files: ["Lin Wei academic transcript.pdf"],
      fields: [
        ["Student", "Lin Wei · ST-001"],
        ["Attachment slot", "Academic transcript"],
        ["Suggested category", "Attachments"],
        ["File", "Lin Wei academic transcript.pdf"],
      ],
    },
    {
      id: "lw-observation",
      name: "Mailbox observation · lin.wei",
      type: "Mailbox",
      icon: "database",
      color: "blue",
      meta: "18 messages · 01–15 Sep 2026",
      suggested: "records",
      fields: [
        ["Evidence coverage", "Sent + Inbox · 01–15 Sep 2026"],
        ["Observed messages", "18 · read-only snapshot"],
        ["Duplicate suspicion", "Lin Wei → Dr. James Wilson"],
        ["Suggested category", "Prior outreach records"],
      ],
    },
    {
      id: "lw-csv",
      name: "Previous outreach.csv",
      type: "Imported record",
      icon: "database",
      color: "amber",
      meta: "6 records · campaign scoped",
      suggested: "records",
      fields: [
        ["Campaign", "Autumn 2026 · PhD outreach"],
        ["Record key", "Student + supervisor + campaign"],
        ["Use", "Reconciliation evidence"],
        ["Authority", "Does not overwrite preparation"],
      ],
    },
    {
      id: "lw-notes",
      name: "Funding notes.txt",
      type: "Document",
      icon: "file",
      color: "slate",
      meta: "Plain text · not parsed",
      fields: [
        ["State", "Unclassified raw material"],
        ["Mapping", "No supported pattern applied"],
        ["Content", "Operator notes about funding deadlines"],
        ["Next step", "Classify into a stable category"],
      ],
    },
    {
      id: "lw-language",
      name: "Language certificate.pdf",
      type: "Document",
      icon: "file",
      color: "purple",
      meta: "1 page · evidence file",
      suggested: "attachments",
      files: ["Language certificate.pdf"],
      fields: [
        ["Student", "Lin Wei · ST-001"],
        ["Attachment slot", "Language certificate"],
        ["Suggested category", "Attachments"],
        ["File", "Language certificate.pdf"],
      ],
    },
    {
      id: "lw-contacts",
      name: "Conference contacts.xlsx",
      type: "Spreadsheet",
      icon: "source",
      color: "green",
      meta: "9 rows · unrelated sheet",
      fields: [
        ["State", "Unclassified raw material"],
        ["Content", "Contacts from a recruitment fair"],
        ["Mapping", "No supported master headers"],
        ["Next step", "Operator reviews or discards"],
      ],
    },
    {
      id: "lw-email",
      name: "Wilson reply.eml",
      type: "Mailbox",
      icon: "mail",
      color: "amber",
      meta: "1 message · saved email",
      suggested: "records",
      fields: [
        ["Message", "Reply from Dr. James Wilson"],
        ["Use", "Potential reconciliation evidence"],
        ["Association", "Not linked to a task yet"],
        ["Suggested category", "Prior outreach records"],
      ],
    },
  ],
};

const meiWorkspace: StudentWorkspace = {
  baseAttachments: ["Mei_CV.pdf"],
  overrides: {},
  supervisors: [
    {
      id: "mz-taylor",
      name: "Prof. Emma Taylor",
      institution: "University College London",
      email: "emma.taylor@example.ac.uk",
      draft: {
        document: "Outreach letters.docx",
        section: "Letter 07 · Emma Taylor",
        subject: "PhD inquiry · Computational biology",
      },
    },
    {
      id: "mz-martin",
      name: "Dr. Oliver Martin",
      institution: "University of Edinburgh",
      email: "oliver.martin@example.ac.uk",
      draft: {
        document: "Outreach letters.docx",
        section: "Letter 08 · Oliver Martin",
        subject: "PhD inquiry · Computational biology",
      },
    },
    {
      id: "mz-davis",
      name: "Prof. Emily Davis",
      institution: "Stanford University",
      email: "emily.davis@example.edu",
      draft: {
        document: "Outreach letters.docx",
        section: "Letter 09 · Emily Davis",
        subject: "PhD inquiry · Computational biology",
      },
    },
    {
      id: "mz-anderson",
      name: "Dr. Noah Anderson",
      institution: "MIT",
      email: "noah.anderson@example.edu",
      draft: {
        document: "Outreach letters.docx",
        section: "Letter 10 · Noah Anderson",
        subject: "PhD inquiry · Computational biology",
      },
    },
    {
      id: "mz-robinson",
      name: "Prof. Mia Robinson",
      institution: "Harvard University",
      email: "mia.robinson@example.edu",
      draft: null,
    },
    {
      id: "mz-lee",
      name: "Prof. Sophie Lee",
      institution: "University of Manchester",
      email: null,
      draft: null,
    },
  ],
  classified: {
    master: [
      {
        id: "mz-master",
        name: "Supervisor shortlist.xlsx",
        type: "Spreadsheet",
        icon: "source",
        color: "green",
        meta: "6 rows for this student",
        fields: [
          ["Sheet / rows", "Supervisors · rows 9–14"],
          ["full_name → supervisor", "Taylor · Martin · Davis · Anderson · Robinson · Lee"],
          ["university → institution", "UCL · Edinburgh · Stanford · MIT · Harvard · Manchester"],
          ["email → recipient", "5 identified · 1 missing"],
        ],
      },
    ],
    drafts: [
      {
        id: "mz-letters",
        name: "Outreach letters.docx",
        type: "Document",
        icon: "file",
        color: "blue",
        meta: "2 letters matched",
        fields: letterFields(
          "Letter 07 · Emma Taylor",
          "emma.taylor@example.ac.uk",
          "PhD inquiry · Computational biology",
        ),
      },
    ],
    profile: [
      {
        id: "mz-profile",
        name: "Student profiles.xlsx",
        type: "Spreadsheet",
        icon: "user",
        color: "purple",
        meta: "ST-002 · 8 fields",
        fields: [
          ["student_id → student", "ST-002 · Mei Zhang"],
          ["Research area", "Computational biology"],
          ["mailbox_id → mailbox", "MB-002"],
          ["Source precedence", "Student identity fields"],
        ],
      },
    ],
    mailbox: [
      {
        id: "mz-mailbox",
        name: "Student mailboxes · 163 Mail",
        type: "Mailbox",
        icon: "mail",
        color: "amber",
        meta: "mei.zhang@example.com",
        fields: [
          ["Student", "Mei Zhang · ST-002"],
          ["Mailbox", "mei.zhang@example.com"],
          ["Association", "Student-owned mailbox ID"],
          ["Usage", "Sender identity only"],
        ],
      },
    ],
    records: [],
    attachments: [
      {
        id: "mz-pack",
        name: "Mei Zhang attachment pack",
        type: "Attachment",
        icon: "clip",
        color: "slate",
        meta: "1 file · all identified tasks",
        files: ["Mei_CV.pdf"],
        fields: [
          ["Files", "Mei_CV.pdf"],
          ["Default", "Every task with an identified email"],
          ["Association", "Explicit student identifier ST-002"],
          ["Overrides", "Configured per task"],
        ],
      },
    ],
  },
  unresolved: [
    {
      id: "mz-transcript",
      name: "Mei Zhang transcript.pdf",
      type: "Document",
      icon: "file",
      color: "rose",
      meta: "Attachment · no student ID in file",
      suggested: "attachments",
      files: ["Mei Zhang transcript.pdf"],
      fields: [
        ["Attachment slot", "Academic transcript"],
        ["Association", "Not established"],
        ["Resolution", "Operator confirms student ST-002"],
        ["Suggested category", "Attachments"],
      ],
    },
    {
      id: "mz-supplement",
      name: "Outreach letters supplement.docx",
      type: "Document",
      icon: "file",
      color: "blue",
      meta: "1 letter · unmatched",
      suggested: "drafts",
      fields: [
        ["Section", "Unindexed letter"],
        ["Matched supervisor", "None yet"],
        ["Resolution", "Match within Draft letters"],
        ["Suggested category", "Draft letters"],
      ],
    },
    {
      id: "mz-observation",
      name: "Mailbox observation · mei.zhang",
      type: "Mailbox",
      icon: "database",
      color: "blue",
      meta: "12 messages · 01–15 Sep 2026",
      suggested: "records",
      fields: [
        ["Evidence coverage", "Sent + Inbox · 01–15 Sep 2026"],
        ["Observed messages", "12 · read-only snapshot"],
        ["Earlier history", "Not inspected"],
        ["Suggested category", "Prior outreach records"],
      ],
    },
    {
      id: "mz-notes",
      name: "Scholarship context.docx",
      type: "Document",
      icon: "file",
      color: "slate",
      meta: "1 page · not parsed",
      fields: [
        ["State", "Unclassified raw material"],
        ["Mapping", "No supported pattern applied"],
        ["Content", "Funding body background notes"],
        ["Next step", "Classify into a stable category"],
      ],
    },
    {
      id: "mz-publication",
      name: "Writing sample.pdf",
      type: "Document",
      icon: "file",
      color: "purple",
      meta: "6 pages · evidence file",
      suggested: "attachments",
      files: ["Writing sample.pdf"],
      fields: [
        ["Student", "Mei Zhang · ST-002"],
        ["Attachment slot", "Writing sample"],
        ["Suggested category", "Attachments"],
        ["File", "Writing sample.pdf"],
      ],
    },
    {
      id: "mz-csv2",
      name: "Earlier campaign export.csv",
      type: "Imported record",
      icon: "database",
      color: "amber",
      meta: "11 records · campaign scoped",
      suggested: "records",
      fields: [
        ["Campaign", "Spring 2026 · PhD outreach"],
        ["Record key", "Student + supervisor + campaign"],
        ["Use", "Reconciliation evidence"],
        ["Suggested category", "Prior outreach records"],
      ],
    },
    {
      id: "mz-forward",
      name: "Taylor forward.eml",
      type: "Mailbox",
      icon: "mail",
      color: "blue",
      meta: "1 message · saved email",
      suggested: "records",
      fields: [
        ["Message", "Forwarded reply from Prof. Emma Taylor"],
        ["Use", "Potential reconciliation evidence"],
        ["Association", "Not linked to a task yet"],
        ["Suggested category", "Prior outreach records"],
      ],
    },
  ],
};

export const students: Student[] = [
  {
    id: "lin-wei",
    name: "Lin Wei",
    initials: "LW",
    area: "Human-centered AI",
    color: "blue",
    studentId: "ST-001",
    mailbox: "lin.wei@example.com",
    workspace: linWorkspace,
  },
  {
    id: "mei-zhang",
    name: "Mei Zhang",
    initials: "MZ",
    area: "Computational biology",
    color: "green",
    studentId: "ST-002",
    mailbox: "mei.zhang@example.com",
    workspace: meiWorkspace,
  },
];

export const cloneWorkspace = (workspace: StudentWorkspace): StudentWorkspace => ({
  unresolved: workspace.unresolved.map((source) => ({ ...source })),
  classified: Object.fromEntries(
    categories.map((category) => [
      category.id,
      workspace.classified[category.id].map((source) => ({ ...source })),
    ]),
  ) as Record<CategoryId, RawSource[]>,
  baseAttachments: [...workspace.baseAttachments],
  overrides: Object.fromEntries(
    Object.entries(workspace.overrides).map(([id, files]) => [id, [...files]]),
  ),
  supervisors: workspace.supervisors.map((supervisor) => ({
    ...supervisor,
    draft: supervisor.draft ? { ...supervisor.draft } : null,
  })),
});

export const attachmentPool = (space: StudentWorkspace): string[] => [
  ...new Set([
    ...space.baseAttachments,
    ...space.classified.attachments.flatMap((source) => source.files ?? []),
  ]),
];

export const effectiveAttachments = (
  space: StudentWorkspace,
  supervisorId: string,
): string[] =>
  attachmentPool(space).filter(
    (file) => !space.overrides[supervisorId]?.includes(file),
  );

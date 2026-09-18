// Pure review model for deterministic source recognition.
// Mirrors smartmail/recognition.py TYPE_PROFILES; no React or Core access here
// so the auto-recognition + manual-revision rules are unit-testable.

import type { IconName } from "../../shared/Icon";
import type { ImportSelection } from "../../core";
import type {
  RecognitionConfidence,
  RecognitionResult,
  RecognitionTypeId,
} from "../../core/recognition-types";

export type RecognitionTypeOption = {
  id: RecognitionTypeId;
  label: string;
  actionable: boolean;
  icon: IconName;
};

// Display order doubles as the manual-revision option list.
export const recognitionTypeOptions: RecognitionTypeOption[] = [
  { id: "supervisor_master", label: "Supervisor master list", actionable: true, icon: "source" },
  { id: "outreach_draft", label: "Single supervisor outreach draft", actionable: true, icon: "file" },
  { id: "multi_draft_bundle", label: "Multi-draft bundle", actionable: true, icon: "file" },
  { id: "bulk_import", label: "Structured outreach batch import", actionable: true, icon: "file" },
  { id: "applicant_cv", label: "Applicant / student CV", actionable: true, icon: "clip" },
  { id: "tracking_sheet", label: "Outreach tracking / template sheet", actionable: false, icon: "database" },
  { id: "program_reference", label: "Program research / reference workbook", actionable: false, icon: "book" },
  { id: "planning_document", label: "Application planning document", actionable: false, icon: "book" },
  { id: "maintenance_log", label: "Mail maintenance / log document", actionable: false, icon: "book" },
  { id: "scholar_cv", label: "Scholar / faculty CV", actionable: false, icon: "clip" },
  { id: "unrelated", label: "Unrelated source", actionable: false, icon: "search" },
  { id: "bundle", label: "Mixed source bundle", actionable: false, icon: "folder" },
  { id: "ambiguous", label: "Ambiguous source", actionable: false, icon: "warning" },
  { id: "unknown", label: "Unrecognized source", actionable: false, icon: "warning" },
];

const optionById = new Map(recognitionTypeOptions.map((option) => [option.id, option]));

export const typeOption = (id: RecognitionTypeId): RecognitionTypeOption =>
  optionById.get(id) ?? recognitionTypeOptions[recognitionTypeOptions.length - 1];

export const isActionableType = (id: RecognitionTypeId): boolean => typeOption(id).actionable;

export type ConfidenceTone = "ready" | "waiting" | "muted";

export const confidenceTone = (confidence: RecognitionConfidence): ConfidenceTone =>
  confidence === "high" ? "ready" : confidence === "medium" ? "waiting" : "muted";

export function identitySummary(result: RecognitionResult): string {
  const identities = result.identities ?? {};
  switch (result.type) {
    case "outreach_draft": {
      const addressee = identities.addressee as { name?: string; email?: string } | undefined;
      const target = addressee?.email || addressee?.name || "addressee unresolved";
      return identities.student ? `${String(identities.student)} → ${target}` : target;
    }
    case "multi_draft_bundle": {
      const addressed = result.segments.filter((segment) => segment.emails.length).length;
      const student = identities.student ? ` · ${String(identities.student)}` : "";
      return `${result.segments.length} letter${result.segments.length === 1 ? "" : "s"} · ${addressed} addressed${student}`;
    }
    case "applicant_cv":
    case "scholar_cv": {
      const role = identities.cv_role ? `${String(identities.cv_role)} CV` : "CV";
      return identities.person ? `${identities.person} · ${role}` : role;
    }
    case "supervisor_master": {
      const rows = identities.row_count ?? 0;
      const emails = identities.email_count ?? 0;
      return `${rows} supervisor row${rows === 1 ? "" : "s"} · ${emails} address${emails === 1 ? "" : "es"}`;
    }
    case "bulk_import": {
      const rows = identities.row_count ?? 0;
      const recipients = identities.recipient_count ?? 0;
      return `${rows} message row${rows === 1 ? "" : "s"} · ${recipients} recipient${recipients === 1 ? "" : "s"}`;
    }
    default:
      return "";
  }
}

// A review row is always a concrete file: either a loose upload or one member
// expanded from a zip. The archive itself never appears as a row ("no mixed").
export type ReviewItem = {
  key: string;
  name: string;
  container: string;
  size: number;
  result: RecognitionResult;
  type: RecognitionTypeId;
  included: boolean;
  manuallyToggled: boolean;
};

export function reviewItems(sources: RecognitionResult[]): ReviewItem[] {
  return sources.map((result) => {
    const container = result.container ?? "";
    return {
      key: container ? `${container}::${result.name}` : result.name,
      name: result.name,
      container,
      size: 0,
      result,
      type: result.type,
      included: result.actionable,
      manuallyToggled: false,
    };
  });
}

export type Importability = {
  ok: boolean;
  issues: string[];
  advisories: string[];
};

// The supervisor master workbook is recommended, not required: with no master
// the draft letters establish their own Outreach Tasks. Blockers are reserved
// for conditions Core cannot turn into safe work.
export function reviewImportability(entries: ReviewItem[]): Importability {
  const included = entries.filter((entry) => entry.included);
  const issues: string[] = [];
  const advisories: string[] = [];
  if (!included.length) {
    return { ok: false, issues: ["Select at least one source to import."], advisories };
  }

  const masters = included.filter((entry) => entry.type === "supervisor_master");
  if (masters.length > 1) {
    issues.push("Choose one supervisor master workbook per import; exclude or revise the others.");
  }
  for (const entry of included) {
    if (entry.type === "bulk_import") {
      issues.push(
        `"${entry.name}" is a structured outreach batch (CSV). Batch rows go through the 163 extension import, not this workflow; exclude it.`,
      );
    }
    if (entry.type === "unknown" || entry.type === "ambiguous") {
      issues.push(`"${entry.name}" is unresolved (${entry.type}); revise its type or exclude it.`);
    }
  }

  const drafts = included.filter((entry) =>
    entry.type === "outreach_draft" || entry.type === "multi_draft_bundle");
  const workItems = included.filter((entry) => isActionableType(entry.type));
  if (!masters.length) {
    if (drafts.length) {
      advisories.push(
        "No supervisor master list included: each addressed letter creates its own Outreach Task; letters without a recipient stay blocked pending an address.",
      );
    } else if (!workItems.length) {
      advisories.push("No outreach work in this set; sources will be retained as reference material only.");
    }
  }

  return { ok: issues.length === 0, issues, advisories };
}

// Group the reviewed rows back into one selection per uploaded file.
// Archive members travel as a `members` allowlist on their zip upload.
export function buildImportSelections(
  entries: ReviewItem[],
  files: Map<string, File>,
): ImportSelection[] {
  const selections = new Map<string, ImportSelection>();
  const resolveFile = (name: string): File => {
    const file = files.get(name);
    if (!file) throw new Error(`Reviewed file is no longer attached: ${name}`);
    return file;
  };
  for (const entry of entries) {
    const uploadName = entry.container || entry.name;
    const existing = selections.get(uploadName);
    if (entry.container) {
      const selection = existing ?? { file: resolveFile(uploadName), included: false, members: [] };
      if (entry.included) {
        selection.included = true;
        selection.members = [
          ...(selection.members ?? []),
          { name: entry.name, ...(entry.type !== entry.result.type ? { type: entry.type } : {}) },
        ];
      }
      selections.set(uploadName, selection);
    } else {
      selections.set(uploadName, {
        file: resolveFile(uploadName),
        included: entry.included,
        ...(entry.type !== entry.result.type ? { type: entry.type } : {}),
      });
    }
  }
  // Keep the original upload order for a predictable payload.
  return [...selections.values()];
}

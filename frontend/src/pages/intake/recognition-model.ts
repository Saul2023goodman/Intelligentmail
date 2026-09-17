// Pure review model for deterministic source recognition.
// Mirrors smartmail/recognition.py TYPE_PROFILES; no React or Core access here
// so the auto-recognition + manual-revision rules are unit-testable.

import type { IconName } from "../../shared/Icon";
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

export type ReviewEntry = {
  name: string;
  format: string;
  type: RecognitionTypeId;
  included: boolean;
  members?: RecognitionResult[];
};

export type Importability = { ok: boolean; issues: string[] };

// The Core import path accepts one .xlsx supervisor master (optionally with
// related documents bundled around it) or one .zip that contains exactly that.
// Everything else is reported up front instead of failing opaquely in Core.
export function reviewImportability(entries: ReviewEntry[]): Importability {
  const included = entries.filter((entry) => entry.included);
  const issues: string[] = [];
  if (!included.length) {
    return { ok: false, issues: ["Select at least one source to import."] };
  }

  const zips = included.filter((entry) => entry.format === "zip");
  if (zips.length > 1) {
    issues.push("Choose one archive per import; merge the others first.");
  }
  if (zips.length === 1 && included.length > 1) {
    issues.push(`Import the archive on its own; extract "${zips[0].name}" to pick members individually.`);
  }

  for (const entry of included.filter((item) => item.format === "csv")) {
    issues.push(
      `"${entry.name}" is a ${typeOption(entry.type).label}. Batch CSV rows are not created by this import path; exclude it and use the extension batch workflow.`,
    );
  }

  const looseXlsx = included.filter((entry) => entry.format === "xlsx");
  for (const entry of looseXlsx) {
    if (entry.type !== "supervisor_master") {
      issues.push(
        `"${entry.name}" is recognized as ${typeOption(entry.type).label}, not a supervisor master list. Revise its type or exclude it.`,
      );
    }
  }
  if (!zips.length) {
    if (looseXlsx.length > 1) {
      issues.push("Choose one supervisor master workbook per import.");
    } else if (looseXlsx.length === 0) {
      const only = included.length === 1;
      issues.push(only
        ? `A document cannot be imported alone. Add the supervisor master workbook (.xlsx) to the same source set.`
        : "Add the supervisor master workbook (.xlsx) to this source set.");
    }
  } else {
    for (const entry of zips) {
      const memberXlsx = (entry.members ?? []).filter((member) => member.format === "xlsx");
      if (memberXlsx.length !== 1) {
        issues.push(`Archive "${entry.name}" must contain exactly one .xlsx master workbook (found ${memberXlsx.length}).`);
      } else if (memberXlsx[0].type !== "supervisor_master") {
        issues.push(`The workbook inside "${entry.name}" is recognized as ${memberXlsx[0].label}, not a supervisor master list.`);
      }
    }
  }

  return { ok: issues.length === 0, issues };
}

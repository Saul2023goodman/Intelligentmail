import type { DuplicateCheck, FullPreparation } from "./records-types";
import type { Campaign, StudentWorkspace, Task } from "./types";
import type { Confirmation } from "./execution-types";
import type { SourceRecognitionAnnotation } from "./recognition-types";

export type IntakeSource = {
  id: string;
  name: string;
  sha256: string;
  size: number;
};
export type IntakeImport = {
  id: string;
  campaign_id: string;
  student_id: string;
  sources: IntakeSource[];
  findings: {
    id: string;
    source: { id: string; name: string };
    code: string;
    detail: string;
    blocking: boolean;
  }[];
};
export type IntakeTask = {
  task: {
    id: string;
    campaign_id: string;
    student_id: string;
    supervisor: { id: string; name: string; addresses: string[] };
    institution: { id: string; name: string };
    mailbox: { id: string; address: string };
    exceptions: { id: string; code: string; detail: string; blocking: number }[];
    source_associations: unknown[];
  };
  message_status: string;
  preparations: FullPreparation[];
  sources: IntakeSource[];
};
export type IntakeWorkspace = {
  campaigns: Campaign[];
  students: StudentWorkspace[];
  campaign: Campaign | null;
  student: { id: string; name: string } | null;
  imports: IntakeImport[];
  source_categories: Record<string, string>;
  source_recognition: Record<string, SourceRecognitionAnnotation>;
  tasks: IntakeTask[];
};
export type IntakeImportResult = {
  import: {
    id: string;
    task_ids: string[];
    duplicate: boolean;
    summary: {
      rows: number;
      new: number;
      reused: number;
      duplicate: number;
      conflicts: number;
      new_sources: number;
    };
  };
  preparation: { preparation_ids: string[]; unassociated_source_ids: string[] };
  workspace: IntakeWorkspace;
};

export type ReviewRow = {
  task: IntakeTask["task"] & {
    student: { id: string; name: string };
    campaign: Campaign;
  };
  report: Task;
  preparation: FullPreparation;
  sources: (IntakeSource & { sheet: string; row: number; evidence: unknown })[];
  duplicate_check: DuplicateCheck | null;
  confirmation: Confirmation | null;
};
export type ReviewWorkspace = { campaign: Campaign; rows: ReviewRow[] };

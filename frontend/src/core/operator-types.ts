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
export type IntakeTaskDetail = {
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
export type IntakeTaskSummary = {
  task_id: string;
  supervisor_name: string;
  institution_name: string;
  recipient_addresses: string[];
  message_status: string;
  preparation: null | {
    id: string;
    subject: string;
    source_name: string;
    attachment_count: number;
  };
};
export type IntakeWorkspace = {
  campaigns: Campaign[];
  students: StudentWorkspace[];
  campaign: Campaign | null;
  student: { id: string; name: string } | null;
  imports: IntakeImport[];
  source_categories: Record<string, string>;
  source_recognition: Record<string, SourceRecognitionAnnotation>;
  tasks: IntakeTaskSummary[];
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
  task: IntakeTaskDetail["task"] & {
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

export type FollowUpRule = {
  campaign_id: string;
  delay_days: number;
  maximum_count: number;
  subject_template: string;
  body_template: string;
  has_templates: boolean;
  enabled: boolean;
  timezone: string;
  send_time: string;
  revision: number;
  policy_digest: string;
  confirmed_at: string;
  updated_at: string;
};
export type FollowUpStatus = {
  task_id: string;
  state: string;
  eligible: boolean;
  due_at: string;
  next_sequence: number;
  supervisor_name: string;
  institution_name: string;
  recipient_addresses: string[];
  counts: {
    ordinary_replies: number;
    automatic_replies: number;
    ambiguous: number;
    follow_up_sent: number;
    follow_up_actions: number;
    open_follow_up: number;
  };
  rule: null | { delay_days: number; maximum_count: number; has_templates: boolean };
};
export type FollowUpAutomationAction = {
  id: string;
  task_id: string;
  campaign_id: string;
  sequence: number;
  follows_sent_record_id: string;
  status: string;
  due_at: string;
  preparation_id: string | null;
  preparation: null | {
    id: string;
    status: string;
    ready: boolean;
    subject: string;
    recipient: string;
    action_kind: string;
  };
  confirmation: Confirmation | null;
  attempt: null | {
    id: string;
    state: string;
    updated_at: string;
    phase: string;
  };
  detail: string;
  created_at: string;
  rule_revision: number;
  policy_digest: string;
};
export type FollowUpWorkspace = {
  campaign: Campaign;
  rule: FollowUpRule | null;
  statuses: FollowUpStatus[];
  actions: FollowUpAutomationAction[];
  summary: {
    tasks: number;
    due: number;
    waiting: number;
    reply_stopped: number;
    review_required: number;
    open_actions: number;
    sent_actions: number;
    states: Record<string, number>;
  };
  flow: { state: string; reason: string; detail?: string };
  availability: { available: boolean; verified: boolean; basis: string };
};
export type FollowUpProcessResult = {
  campaign_id: string;
  enabled: boolean;
  created_action_ids: string[];
  ready_preparation_ids: string[];
  state: string;
  detail: string;
  workspace: FollowUpWorkspace;
};

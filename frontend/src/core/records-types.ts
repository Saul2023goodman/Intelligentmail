import type { MailboxSummary } from "./types";
import type { ObservationMessage } from "./mailbox-types";

export type Evidence = Record<string, unknown>;

export type RecordsConfirmation = {
  id: string;
  preparation_id: string;
  task_id: string;
  status: "active" | "consumed" | "invalidated" | string;
  execution: { kind: string; scheduled_utc?: string; [key: string]: unknown };
  content_digest: string;
  attachments_digest: string;
  invalidated_reason: string;
  confirmed_at: string;
};

export type RequestAttachment = {
  id: string;
  label: string;
  name: string;
  sha256: string;
  size: number;
};

export type ExecutionAttempt = {
  id: string;
  confirmation_id: string;
  preparation_id: string;
  task_id: string;
  sequence: number;
  state: string;
  phase: string;
  intent_at: string | null;
  submission_started_at: string | null;
  outcome_observed_at: string | null;
  updated_at: string | null;
  request: {
    sender?: string;
    recipient?: string;
    subject?: string;
    scheduled_utc?: string;
    attachments?: RequestAttachment[];
    [key: string]: unknown;
  };
  evidence: Evidence | null;
  sent_record_id: string | null;
};

export type SentAttachment = RequestAttachment;

export type SentRecord = {
  id: string;
  preparation_id: string;
  task_id: string;
  attempt_id: string;
  sender: string;
  recipient: string;
  subject: string;
  body: string;
  attachments: SentAttachment[];
  evidence: Evidence;
  reference: string;
  action_kind: string;
  follows_sent_record_id: string | null;
};

export type RecordsSchedule = {
  id: string;
  confirmation_id: string;
  attempt_id: string;
  preparation_id: string;
  task_id: string;
  mailbox_address: string;
  external_id: string;
  scheduled_utc: string;
  state: string;
  replaces_schedule_id: string | null;
  evidence: Evidence;
  created_at: string;
  updated_at: string;
};

export type PlanProposal = {
  preparation_id: string;
  task_id: string;
  status: string;
  reason: string;
  constraint: string;
  detail: string;
  scheduled_at: string;
  scheduled_utc: string;
  confirmation_id: string | null;
  recipient: string;
  subject: string;
};

export type RecordsPlan = {
  id: string;
  campaign_id: string;
  status: string;
  created_at: string;
  configuration: {
    timezone: string;
    windows: unknown[];
    spacing_minutes: number;
    daily_limit: number;
    horizon_days: number;
  };
  proposals: PlanProposal[];
  unavailable: PlanProposal[];
  impossible: PlanProposal[];
};

export type DuplicateCheck = {
  id: string;
  task_id: string;
  preparation_id: string | null;
  checked_at: string;
  finding: string;
  review_required: boolean;
  basis: string;
  detail: string;
  evidence_coverage: Evidence;
  matches: unknown[];
};

export type ReplyAssociation = {
  id: string;
  task_id: string | null;
  student_id: string;
  status: string;
  reply_kind: string;
  basis: string;
  matched_rule: string;
  resolved_by_operator: boolean;
  created_at: string;
  resolved_at: string;
  candidate_task_ids: string[];
  candidates: {
    id: string;
    campaign_id: string;
    supervisor_name: string;
    institution_name: string;
  }[];
  observation: {
    id: string;
    folder: string;
    platform_reference: string;
    counterpart: string;
    subject: string;
    observed_time: string;
    status: string;
  } | null;
};

export type FollowUpAction = {
  id: string;
  task_id: string;
  campaign_id: string;
  sequence: number;
  follows_sent_record_id: string | null;
  status: string;
  due_at: string | null;
  preparation_id: string | null;
  preparation: {
    id: string;
    status: string;
    ready: boolean;
    subject: string;
    recipient: string;
    action_kind: string;
  } | null;
  detail: string;
  created_at: string;
};

export type RecordsReportRow = {
  task_id: string;
  student_id: string;
  student_name: string;
  supervisor_id: string;
  supervisor_name: string;
  institution_id: string;
  institution_name: string;
  mailbox: string;
  message_status: string;
  duplicate_status: string;
  duplicate_coverage: Evidence | null;
  exceptions: { total: number; blocking: number };
  follow_up: string;
  preparation_ids: string[];
};

export type RecordsWorkspace = {
  campaign: { id: string; name: string };
  generated_at: string;
  flow: { campaign_id?: string; state?: string; reason?: string; detail?: string };
  rule: unknown | null;
  counts: {
    tasks: number;
    message_status: Record<string, number>;
    duplicate_status: Record<string, number>;
    exceptions: Record<string, number>;
    follow_up: Record<string, number>;
  };
  tasks: RecordsReportRow[];
  confirmations: RecordsConfirmation[];
  attempts: ExecutionAttempt[];
  sent_records: SentRecord[];
  schedules: RecordsSchedule[];
  plans: RecordsPlan[];
  duplicate_checks: DuplicateCheck[];
  reply_associations: ReplyAssociation[];
  follow_up_actions: FollowUpAction[];
  mailboxes: MailboxSummary[];
};

export type ReadinessFinding = { code: string; detail: string; blocking: number };
export type Transformation = { code: string; detail: string };
export type Correction = { field: string; value: string; prior: string };
export type AttachmentSlot = {
  id: string;
  label: string;
  attachment: SentAttachment | null;
  [key: string]: unknown;
};

export type FullPreparation = {
  id: string;
  task_id: string;
  action_kind: string;
  linked_sent_record_id: string | null;
  sender: string;
  recipient: string;
  subject: string;
  body: string;
  status: "active" | "superseded" | string;
  superseded_by: string | null;
  ready: boolean;
  source: { id: string; name: string; sha256: string };
  association: Evidence;
  transformations: Transformation[];
  readiness_findings: ReadinessFinding[];
  corrections: Correction[];
  attachment_slots: AttachmentSlot[];
  [key: string]: unknown;
};

export type MailboxObservation = {
  id: string;
  student_id: string;
  mailbox_address: string;
  adapter: string;
  observed_at: string;
  status: string;
  detail: string;
  evidence_coverage: Evidence;
  capabilities: Evidence;
  messages: ObservationMessage[];
  reconciliation_id: string | null;
};

export type Reconciliation = {
  id: string;
  student_id: string;
  mailbox_address: string;
  observation_id: string;
  observed_at: string;
  summary: Evidence;
  findings: {
    id: string;
    message_observation_id: string | null;
    finding: string;
    local_kind: string;
    local_id: string;
    basis: string;
    detail: string;
  }[];
};

export type RecordsTaskDetail = {
  task: {
    id: string;
    campaign_id: string;
    student_id: string;
    supervisor_id: string;
    student: { id: string; name: string };
    campaign: { id: string; name: string };
    mailbox: { id: string; address: string };
    supervisor: { id: string; name: string; addresses: string[] };
    institution: { id: string; name: string };
    source_associations: unknown[];
    exceptions: unknown[];
    [key: string]: unknown;
  };
  message_status: string;
  preparations: FullPreparation[];
  sources: {
    id: string;
    name: string;
    sha256: string;
    size: number;
    import_id: string;
    sheet: string;
    row: number;
    evidence: Evidence;
  }[];
  execution_attempts: ExecutionAttempt[];
  sent_records: SentRecord[];
  duplicate_checks: DuplicateCheck[];
  reply_associations: ReplyAssociation[];
  follow_up: { rule: unknown; status: unknown; actions: FollowUpAction[] };
  confirmations: RecordsConfirmation[];
  schedules: RecordsSchedule[];
  mailbox: {
    observations: MailboxObservation[];
    reconciliations: Reconciliation[];
  };
};

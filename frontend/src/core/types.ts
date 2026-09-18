export type Campaign = { id: string; name: string };
export type StudentWorkspace = {
  id: string;
  name: string;
  mailbox: string;
  campaign_id: string;
};
export type DeletedStudentWorkspace = {
  id: string;
  name: string;
  mailbox: string;
  campaign_ids: string[];
  deleted: true;
};
export type Task = {
  task_id: string;
  student_name: string;
  supervisor_name: string;
  institution_name: string;
  mailbox: string;
  message_status: string;
  duplicate_status: string;
  follow_up: string;
  exceptions: { total: number; blocking: number };
  preparation_ids: string[];
};
export type Preparation = {
  id: string;
  task_id: string;
  blocking_count: number;
  subject: string;
};
export type MailboxGateway = {
  adapter: string;
  connected: boolean;
  mailbox_address: string;
  protocol: number;
};
export type Workspace = {
  mailboxes: MailboxSummary[];
  mailbox_capabilities: {
    adapter: string;
    capabilities: {
      [operation: string]: { available: boolean; verified: boolean; basis: string };
      read_history: { available: boolean; verified: boolean; basis: string };
    };
    gateway: MailboxGateway;
  };
  campaigns: Campaign[];
  preparations: Preparation[];
  confirmations: { task_id: string; preparation_id: string }[];
  report: null | {
    campaign: Campaign;
    generated_at: string;
    flow: { status?: string; state?: string; reason?: string };
    tasks: Task[];
    counts: { tasks: number; message_status: Record<string, number> };
  };
};
export type Detail = {
  rewrite_sources: { id: string; name: string }[];
  preparations: {
    id: string;
    status: string;
    sender: string;
    recipient: string;
    subject: string;
    body: string;
    ready: boolean;
    source: { id: string; name: string };
    readiness_findings: { code: string; detail: string; blocking: number }[];
    attachment_slots: { label: string; attachment: null | { name: string } }[];
  }[];
  sources: { id: string; name: string }[];
  execution_attempts: { id: string; state: string }[];
  duplicate_checks: {
    id: string;
    finding: string;
    detail: string;
    evidence_coverage: { limitations?: string[] };
  }[];
};
export type MailboxSummary = {
  id: string;
  student_id: string;
  student_name: string;
  address: string;
  /** The Student's own Campaign; one Student owns exactly one Campaign. */
  campaign_id: string;
  observation_count: number;
  message_count: number;
  latest: null | {
    id: string;
    status: string;
    observed_at: string;
    detail: string;
    evidence_coverage: { complete: boolean };
  };
};
export type MailboxHistory = {
  observations: {
    id: string;
    student_id: string;
    mailbox_address: string;
    adapter: string;
    status: string;
    observed_at: string;
    detail: string;
    evidence_coverage: { complete: boolean };
    capabilities: Record<string, unknown>;
    messages: {
      id: string;
      subject: string;
      counterpart: string;
      folder: string;
      status: string;
    }[];
  }[];
  reconciliations: {
    id: string;
    student_id: string;
    mailbox_address: string;
    observation_id: string;
    observed_at: string;
    summary: Record<string, unknown>;
    findings: {
      id: string;
      message_observation_id: string | null;
      finding: string;
      local_kind: string;
      local_id: string;
      basis: string;
      detail: string;
    }[];
  }[];
};

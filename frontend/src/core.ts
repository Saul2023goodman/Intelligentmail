export type Campaign = { id: string; name: string };
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
export type Workspace = {
  mailboxes: MailboxSummary[];
  mailbox_capabilities: {
    adapter: string;
    capabilities: {
      read_history: { available: boolean; verified: boolean; basis: string };
    };
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
    status: string;
    observed_at: string;
    detail: string;
    evidence_coverage: { complete: boolean };
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
    observation_id: string;
    findings: { id: string; finding: string; detail: string }[];
  }[];
};
export async function core<T>(
  command: string,
  args: Record<string, string> = {},
): Promise<T> {
  const response = await fetch("/api/core", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command, ...args }),
  });
  const value = await response.json().catch(() => {
    throw new Error("Core is offline. Start the frontend with npm run dev.");
  });
  if (value.error) throw new Error(value.error);
  if (!response.ok) throw new Error("Unable to reach SmartMail Core");
  return value.result;
}
export const human = (text: string) => text.replaceAll("_", " ");

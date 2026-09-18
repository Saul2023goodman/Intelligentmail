export type ObservationMessage = {
  id: string; subject: string; counterpart: string; folder: string; status: string;
  direction: string; platform_reference: string; observed_time: string;
  ambiguity: string; evidence: Record<string, unknown>;
};
export type Finding = {
  id: string; finding: string; basis: string; detail: string;
  local_kind: string; local_id: string; message_observation_id: string | null;
};
export type ComparisonRow = {
  id: string;
  local: null | {
    id: string; kind: string; state: string; subject: string; recipient: string;
    time: string; task_id: string; supervisor: string; institution: string;
    evidence: Record<string, unknown>;
  };
  observed: ObservationMessage | null;
  findings: Finding[];
};
export type ObservationSummary = {
  id: string; observed_at: string; status: string; detail: string;
  evidence_coverage: { complete: boolean; folders?: unknown[]; limitations?: string[]; limitation?: string; [key: string]: unknown };
};
// An observed draft is Source Material: Core captured its body during the
// observation, so it can be imported the way an upload is. Attachment bytes
// are never assumed — only descriptors the reader produced are reported.
export type DraftMaterialCandidate = {
  observation_id: string; subject: string; recipient: string; recipients: string[];
  observed_time: string; status: string; scheduled: boolean;
  body_chars: number; body_available: boolean;
  attachment_count: number; attachments_available: number;
  task_id: string; supervisor: string; campaign_id: string;
};
export type MailboxWorkspace = {
  rows: ComparisonRow[];
  observation: (ObservationSummary & { messages: ObservationMessage[] }) | null;
  reconciliation: null | { id: string; observed_at: string; findings: Finding[] };
  history: ObservationSummary[];
  flow: { state?: string; reason?: string };
};

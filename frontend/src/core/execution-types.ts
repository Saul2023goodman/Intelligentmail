export type PlanConfiguration = {
  timezone: string;
  windows: { days: string[]; start: string; end: string }[];
  spacing_minutes: number;
  daily_limit: number;
  horizon_days: number;
  /** Advisors of one institution allowed per session; one is the safe default. */
  institution_limit: number;
};
export type ExecutionDetails = {
  kind: string;
  scheduled_at?: string;
  scheduled_utc?: string;
  timezone?: string;
  schedule_id?: string;
};
export type Confirmation = {
  id: string;
  preparation_id: string;
  task_id: string;
  status: string;
  execution: ExecutionDetails;
  confirmed_at: string;
};
export type PreparationReview = {
  preparation_id: string;
  task_id: string;
  status: string;
  sender: string;
  recipient: string;
  subject: string;
  body: string;
  message: string;
  ready: boolean;
  already_sent: boolean;
  attachments: { id: string; name: string; size: number; sha256: string }[];
  readiness_findings: { code: string; detail: string; blocking: number }[];
  execution: ExecutionDetails;
  confirmation_id: string | null;
};
export type Proposal = Omit<
  PreparationReview,
  "body" | "already_sent" | "execution"
> & {
  scheduled_at: string;
  scheduled_utc: string;
  timezone: string;
  reason: string;
  detail: string;
  constraint: string;
  /** The institution the Outreach Task belongs to; planning paces per institution. */
  institution_name: string;
  supervisor_name: string;
};
export type SendingPlan = {
  id: string;
  status: string;
  created_at: string;
  configuration: PlanConfiguration;
  proposals: Proposal[];
  unavailable: Proposal[];
  impossible: Proposal[];
};
export type ExternalSchedule = {
  id: string;
  task_id: string;
  preparation_id: string;
  confirmation_id: string;
  mailbox_address: string;
  external_id: string;
  scheduled_utc: string;
  state: string;
  evidence: Record<string, unknown>;
};
export type Attempt = {
  id: string;
  task_id: string;
  preparation_id: string;
  confirmation_id: string;
  state: string;
  updated_at: string;
  phase: string;
  evidence: Record<string, unknown>;
  request: { subject: string; recipient: string };
};
/** One Confirmation's place in a run, including the record that it was never reached. */
export type ExecutionRunItem = {
  id: string;
  run_id: string;
  confirmation_id: string;
  preparation_id: string | null;
  task_id: string | null;
  sequence: number;
  attempt_id: string | null;
  outcome: string;
  detail: string;
};
/** One operator-initiated ordered execution of a set of active Confirmations. */
export type ExecutionRun = {
  id: string;
  campaign_id: string;
  kind: string;
  state: "running" | "completed" | "stopped";
  requested_count: number;
  executed_count: number;
  reached_count: number;
  not_reached_count: number;
  started_at: string;
  finished_at: string;
  detail: string;
  items: ExecutionRunItem[];
  summary: Record<string, number>;
  /** Present for one-item runs: the single-action result shape kept for compatibility. */
  attempts?: Attempt[];
  paused?: boolean;
};
/** One active Preparation with its authorization state; readiness is never authorization. */
export type QueueRow = {
  preparation_id: string;
  task_id: string;
  supervisor_name: string;
  recipient: string;
  subject: string;
  state:
    | "ready_to_authorize"
    | "awaiting_execution"
    | "externally_scheduled"
    | "already_sent"
    | "not_ready";
  blocking_codes: string[];
  confirmation_id: string | null;
  confirmation_kind: string | null;
  sent_record_id: string | null;
  external_schedule_id: string | null;
};
/** Availability is reported per kind, so a disabled kind blocks only its own region. */
export type Availability = {
  kind: string;
  available: boolean;
  capability: string;
  basis: string;
};
export type ExecutionWorkspace = {
  configuration: PlanConfiguration;
  plans: SendingPlan[];
  reviews: PreparationReview[];
  confirmations: Confirmation[];
  schedules: ExternalSchedule[];
  attempts: Attempt[];
  queue: QueueRow[];
  runs: ExecutionRun[];
  availability: Record<string, Availability>;
};
export type ReviewRequest =
  | { kind: "plan"; plan_id: string }
  | { kind: "immediate"; preparation_ids: string[] }
  | { kind: "cancellation"; schedule_id: string }
  | {
      kind: "replacement";
      schedule_id: string;
      replacement_confirmation_id: string;
    };
export type OperationReview = {
  schedule: ExternalSchedule;
  note: string;
  replacement?: PreparationReview;
  replacement_confirmation?: Confirmation;
};
export type ReviewResult = {
  token: string;
  value: SendingPlan | PreparationReview[] | OperationReview;
};

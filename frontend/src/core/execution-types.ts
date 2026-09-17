export type PlanConfiguration = {
  timezone: string;
  windows: { days: string[]; start: string; end: string }[];
  spacing_minutes: number;
  daily_limit: number;
  horizon_days: number;
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
export type ExecutionWorkspace = {
  configuration: PlanConfiguration;
  plans: SendingPlan[];
  reviews: PreparationReview[];
  confirmations: Confirmation[];
  schedules: ExternalSchedule[];
  attempts: Attempt[];
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

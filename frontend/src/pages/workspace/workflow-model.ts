import type { Task, Workspace } from "../../core";

export const GRAPH_WIDTH = 1300;
export const GRAPH_HEIGHT = 870;
const MIN_SCALE = 0.2;
const MAX_SCALE = 1;

export function fitScale(width: number, height: number, padding = 40): number {
  const scale = Math.min(
    Math.max(0, width - padding * 2) / GRAPH_WIDTH,
    Math.max(0, height - padding * 2) / GRAPH_HEIGHT,
  );
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
}

export const stages = [
  {
    id: "mailbox",
    label: "Mailbox gateway",
    caption: "Mailbox gateway · connection status",
    icon: "mail",
    color: "blue",
    x: 55,
    y: 60,
    description:
      "External execution infrastructure: connects one signed-in mailbox tab via the dedicated 163 mail extension and the native bridge; observation and confirmed sending both go through this bus. Click to view connection health, read mailbox evidence, or manage the connection; observation is read-only and never authorizes sending.",
  },
  {
    id: "database",
    label: "SmartMail database",
    caption: "Persistent records & evidence",
    icon: "database",
    color: "purple",
    x: 295,
    y: 60,
    description:
      "Stores mailbox observation batches, source materials, tasks, preparation versions, and execution evidence. External observations and local Preparations are stored separately; later Reconciliation and duplicate checks use these records.",
  },
  {
    id: "comparison",
    label: "Reconciliation & duplicate check",
    caption: "Task matching · historical send check",
    icon: "filter",
    color: "amber",
    x: 55,
    y: 213,
    description:
      "During observation intake, Core reconciles and links identifiable evidence; tasks with an existing Preparation can run a duplicate check against send records in this Campaign and the student mailbox's observation history. Duplicate suspicions go to manual handling, and insufficient coverage is shown explicitly.",
  },
  {
    id: "intake",
    label: "Source materials",
    caption: "Outreach tasks",
    icon: "source",
    color: "blue",
    x: 535,
    y: 60,
    description:
      "Preserved source materials are explicitly associated with a student, supervisor, and campaign.",
  },
  {
    id: "preparation",
    label: "Update / adjust draft",
    caption: "Local Preparation · history retained",
    icon: "mail",
    color: "blue",
    x: 295,
    y: 213,
    description:
      "After selecting a task you can adjust the subject and recipients, or Rewrite the body by revising the source document. Changes trigger revalidation, a new duplicate check, and renewed Confirmation; external draft observations never automatically overwrite local content.",
  },
  {
    id: "ready",
    label: "Ready preparation",
    caption: "Readiness validated",
    icon: "check",
    color: "green",
    x: 535,
    y: 213,
    description:
      "Preparations with no blocking readiness findings. Readiness does not grant sending authorization.",
  },
  {
    id: "confirmation",
    label: "Confirmation",
    caption: "Recorded authorizations",
    icon: "shield",
    color: "green",
    x: 775,
    y: 213,
    description:
      "Operator authorization binds exact content and execution details. The Core rechecks expiry and blockers before execution.",
  },
  {
    id: "blocked",
    label: "Operator review",
    caption: "Resolve blockers",
    icon: "filter",
    color: "rose",
    x: 535,
    y: 505,
    description:
      "Inspect blocking readiness findings, task exceptions, or duplicate suspicions. Corrections and revalidation remain Core operations.",
  },
  {
    id: "unknown",
    label: "Unknown outcome",
    caption: "Reconcile before retry",
    icon: "clock",
    color: "amber",
    x: 775,
    y: 505,
    description:
      "Available evidence cannot establish the outcome. Inspect the execution ledger and reconcile before explicit continuation.",
  },
  {
    id: "scheduled",
    label: "Externally scheduled",
    caption: "Mailbox evidence",
    icon: "clock",
    color: "blue",
    x: 1040,
    y: 213,
    description:
      "The mailbox has confirmed a schedule. Elapsed time alone never establishes a sent message.",
  },
  {
    id: "sent",
    label: "Sent record",
    caption: "Frozen send evidence",
    icon: "send",
    color: "green",
    x: 1040,
    y: 360,
    description:
      "A sent outcome is established by mailbox evidence and retained as immutable history.",
  },
  {
    id: "failed",
    label: "Observed failure",
    caption: "Execution paused",
    icon: "stop",
    color: "rose",
    x: 1040,
    y: 505,
    description:
      "A failed external attempt pauses the execution flow for operator handling. Acknowledgment is not proof of sending.",
  },
  {
    id: "reply",
    label: "Associated reply",
    caption: "Ordinary reply received",
    icon: "reply",
    color: "purple",
    x: 535,
    y: 688,
    description:
      "A reliably associated ordinary reply prevents no-reply follow-up eligibility. Automatic replies are recorded separately.",
  },
  {
    id: "followup",
    label: "Follow-up due",
    caption: "Separate action required",
    icon: "branch",
    color: "purple",
    x: 775,
    y: 688,
    description:
      "The Core evaluates campaign timing and count limits. Every follow-up is a separate action needing its own preparation and confirmation.",
  },
] as const;
export type Stage = (typeof stages)[number];
export function tasksFor(stage: string, data: Workspace): Task[] {
  const tasks = data.report?.tasks ?? [];
  const prepared = (task: Task) =>
    data.preparations.filter((p) => p.task_id === task.task_id);
  return tasks.filter((task) => {
    switch (stage) {
      case "intake":
        return true;
      case "comparison":
      case "preparation":
        return prepared(task).length > 0;
      case "ready":
        return prepared(task).some((p) => p.blocking_count === 0);
      case "confirmation":
        return data.confirmations.some((c) => c.task_id === task.task_id);
      case "blocked":
        return (
          task.exceptions.blocking > 0 ||
          prepared(task).some((p) => p.blocking_count > 0) ||
          [
            "duplicate_suspicion",
            "ambiguous_match",
            "repeat_execution",
          ].includes(task.duplicate_status)
        );
      case "unknown":
        return task.message_status === "unknown_outcome";
      case "failed":
        return task.message_status === "observed_failure";
      case "scheduled":
        return task.message_status === "externally_scheduled";
      case "sent":
        return task.message_status === "sent";
      case "reply":
        return task.follow_up === "ordinary_reply_received";
      case "followup":
        return task.follow_up === "due";
      default:
        return false;
    }
  });
}

export function stageMetric(
  stage: string,
  data: Workspace | null,
): { count: number | string; unit: string } {
  if (stage === "mailbox")
    return { count: data?.mailboxes.length ?? "—", unit: "student mailboxes" };
  if (stage === "database")
    return {
      count: data
        ? data.mailboxes.reduce(
            (total, mailbox) => total + mailbox.observation_count,
            0,
          )
        : "—",
      unit: "observation batches",
    };
  return { count: data ? tasksFor(stage, data).length : "—", unit: "tasks" };
}

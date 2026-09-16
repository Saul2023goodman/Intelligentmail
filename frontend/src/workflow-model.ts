import type { Task, Workspace } from "./core";

export const stages = [
  {
    id: "intake",
    label: "Source materials",
    caption: "Outreach tasks",
    icon: "source",
    color: "blue",
    x: 55,
    y: 257,
    description:
      "Preserved source materials are explicitly associated with a student, supervisor, and campaign.",
  },
  {
    id: "preparation",
    label: "Preparation",
    caption: "Local message content",
    icon: "mail",
    color: "blue",
    x: 295,
    y: 257,
    description:
      "The Core associates documents and prepares message content. Select a task to inspect its source, message, and attachments.",
  },
  {
    id: "ready",
    label: "Ready preparation",
    caption: "Readiness validated",
    icon: "check",
    color: "green",
    x: 550,
    y: 132,
    description:
      "Preparations with no blocking readiness findings. Readiness does not grant sending authorization.",
  },
  {
    id: "confirmation",
    label: "Confirmation",
    caption: "Recorded authorizations",
    icon: "shield",
    color: "green",
    x: 790,
    y: 132,
    description:
      "Operator authorization binds exact content and execution details. The Core rechecks expiry and blockers before execution.",
  },
  {
    id: "blocked",
    label: "Operator review",
    caption: "Resolve blockers",
    icon: "filter",
    color: "rose",
    x: 550,
    y: 382,
    description:
      "Inspect blocking readiness findings, task exceptions, or duplicate suspicions. Corrections and revalidation remain Core operations.",
  },
  {
    id: "unknown",
    label: "Unknown outcome",
    caption: "Reconcile before retry",
    icon: "clock",
    color: "amber",
    x: 790,
    y: 382,
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
    y: 132,
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
    y: 257,
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
    y: 382,
    description:
      "A failed external attempt pauses the execution flow for operator handling. Acknowledgment is not proof of sending.",
  },
  {
    id: "reply",
    label: "Associated reply",
    caption: "Ordinary reply received",
    icon: "reply",
    color: "purple",
    x: 550,
    y: 602,
    description:
      "A reliably associated ordinary reply prevents no-reply follow-up eligibility. Automatic replies are recorded separately.",
  },
  {
    id: "followup",
    label: "Follow-up due",
    caption: "Separate action required",
    icon: "branch",
    color: "purple",
    x: 790,
    y: 602,
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

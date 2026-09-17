import type { RecordsConfirmation } from "../../core";
import type { Tone } from "./records-model";

type ToneLabel = { label: string; tone: Tone };

export const messageStates: Record<string, ToneLabel> = {
  sent: { label: "Sent", tone: "green" },
  locally_planned: { label: "Locally planned", tone: "blue" },
  externally_scheduled: { label: "Externally scheduled", tone: "purple" },
  observed_failure: { label: "Observed failure", tone: "rose" },
  unknown_outcome: { label: "Unknown outcome", tone: "amber" },
  intake_only: { label: "Intake only", tone: "gray" },
};

export function messageState(state: string): ToneLabel {
  return messageStates[state] ?? { label: state ? state.replaceAll("_", " ") : "No preparation", tone: "gray" };
}

export const duplicateStates: Record<string, ToneLabel> = {
  no_duplicate_found: { label: "No duplicate", tone: "green" },
  duplicate_suspicion: { label: "Duplicate suspicion", tone: "rose" },
  ambiguous_match: { label: "Ambiguous match", tone: "amber" },
  repeat_execution: { label: "Repeat execution", tone: "rose" },
  linked_follow_up: { label: "Linked follow-up", tone: "purple" },
  unchecked: { label: "Unchecked", tone: "gray" },
};

export function duplicateState(state: string): ToneLabel {
  return duplicateStates[state] ?? { label: state.replaceAll("_", " "), tone: "gray" };
}

export function duplicateTone(finding: string): Tone {
  return duplicateState(finding).tone;
}

export const attemptStates: Record<string, ToneLabel> = {
  sent: { label: "Sent", tone: "green" },
  failed: { label: "Failed", tone: "rose" },
  unknown: { label: "Unknown outcome", tone: "amber" },
  in_progress: { label: "In progress", tone: "blue" },
  not_attempted: { label: "Not attempted", tone: "gray" },
  externally_scheduled: { label: "Externally scheduled", tone: "purple" },
  cancelled: { label: "Cancelled", tone: "rose" },
  removed: { label: "Removal observed", tone: "rose" },
  cancel_unknown: { label: "Cancel unknown", tone: "amber" },
  done: { label: "Done", tone: "green" },
};

export function attemptState(state: string): ToneLabel {
  return attemptStates[state] ?? { label: state.replaceAll("_", " "), tone: "gray" };
}

export const scheduleStates: Record<string, ToneLabel> = {
  placement_unknown: { label: "Placement unknown", tone: "gray" },
  externally_scheduled: { label: "Externally scheduled", tone: "purple" },
  sent: { label: "Observed sent", tone: "green" },
  cancelled: { label: "Cancelled", tone: "rose" },
  cancel_unknown: { label: "Cancellation unknown", tone: "amber" },
  replaced: { label: "Replaced", tone: "amber" },
};

export function scheduleState(state: string): ToneLabel {
  return scheduleStates[state] ?? { label: state.replaceAll("_", " "), tone: "gray" };
}

export const followUpStates: Record<string, ToneLabel> = {
  due: { label: "Due", tone: "amber" },
  waiting: { label: "Waiting", tone: "blue" },
  ordinary_reply_received: { label: "Ordinary reply", tone: "green" },
  reply_review_required: { label: "Reply review", tone: "rose" },
  maximum_reached: { label: "Maximum reached", tone: "gray" },
  no_initial_send: { label: "No initial send", tone: "gray" },
  follow_up_open: { label: "Follow-up open", tone: "blue" },
  rule_not_configured: { label: "Rule not configured", tone: "gray" },
};

export function followUpState(state: string): ToneLabel {
  return followUpStates[state] ?? { label: state ? state.replaceAll("_", " ") : "—", tone: "gray" };
}

export function confirmationTone(confirmation: RecordsConfirmation): Tone {
  if (confirmation.status === "consumed") return "green";
  if (confirmation.status === "active") return "blue";
  switch (confirmation.invalidated_reason) {
    case "expired":
      return "amber";
    case "renewed":
    case "content_changed":
    case "adjusted":
      return "purple";
    case "rewrite":
      return "gray";
    default:
      return "rose";
  }
}

export function formatTime(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

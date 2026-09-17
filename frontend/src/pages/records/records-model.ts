import type {
  DuplicateCheck,
  ExecutionAttempt,
  FullPreparation,
  MailboxObservation,
  Reconciliation,
  RecordsConfirmation,
  RecordsReportRow,
  RecordsSchedule,
  RecordsTaskDetail,
  RecordsWorkspace,
  SentRecord,
} from "../../core";
import type { IconName } from "../../shared/Icon";
import {
  attemptState,
  confirmationTone,
  duplicateTone,
  scheduleState,
} from "./presentation";

export type Tone = "blue" | "green" | "amber" | "rose" | "gray" | "purple";

export type NodeKind =
  | "version"
  | "confirmation"
  | "attempt"
  | "schedule"
  | "sent"
  | "cancellation"
  | "duplicate"
  | "followup"
  | "reply"
  | "observation-run"
  | "observation-message"
  | "reconciliation"
  | "sources";

export type LineNode = {
  key: string;
  kind: NodeKind;
  icon: IconName;
  tone: Tone;
  title: string;
  subtitle?: string;
  time?: string | null;
  version?: string;
  tags: { label: string; tone?: Tone }[];
  branch?: LineNode[];
  struck?: boolean;
  faint?: boolean;
  terminal?: boolean;
  data: unknown;
};

export type VersionGroup = {
  label: string;
  state: Tone;
  preparation: FullPreparation;
  nodes: LineNode[];
};

export type TaskLineage = {
  groups: VersionGroup[];
  replies: LineNode[];
  observations: LineNode[];
  sources: LineNode[];
};

const keyOf = (kind: string, id: string) => `${kind}:${id}`;

function groupBy<T>(items: T[], key: (item: T) => string): Map<string, T[]> {
  const map = new Map<string, T[]>();
  for (const item of items) {
    const value = key(item);
    const bucket = map.get(value);
    if (bucket) bucket.push(item);
    else map.set(value, [item]);
  }
  return map;
}

export function shortId(id: string | null | undefined): string {
  return id ? id.slice(0, 8) : "—";
}

function confirmationNode(
  confirmation: RecordsConfirmation,
  attempts: ExecutionAttempt[],
  schedulesByAttempt: Map<string, RecordsSchedule>,
  sentByAttempt: Map<string, SentRecord>,
): LineNode {
  const executionKind = String(confirmation.execution?.kind ?? "immediate");
  const isCancellation = executionKind === "cancellation";
  const isReplacement = executionKind === "replacement";
  const isRecall = executionKind === "recall";
  const kind: NodeKind = isCancellation
    ? "cancellation"
    : "confirmation";
  const icon: IconName = isCancellation
    ? "stop"
    : isReplacement
      ? "file"
      : isRecall
        ? "reply"
        : "check";
  const tags: LineNode["tags"] = [
    { label: executionKind.replaceAll("_", " "), tone: "purple" },
    { label: confirmation.status.replaceAll("_", " ") },
  ];
  if (confirmation.invalidated_reason)
    tags.push({
      label: `invalidated · ${confirmation.invalidated_reason.replaceAll("_", " ")}`,
      tone: "rose",
    });
  const scheduled = confirmation.execution?.scheduled_utc;
  if (typeof scheduled === "string")
    tags.push({ label: "scheduled authorization", tone: "purple" });
  const node: LineNode = {
    key: keyOf("confirmation", confirmation.id),
    kind,
    icon,
    tone: confirmationTone(confirmation),
    title: isCancellation
      ? "Cancellation authorization"
      : isReplacement
        ? "Replacement authorization"
        : isRecall
          ? "Recall authorization"
          : "Confirmation",
    subtitle: `digest ${shortId(confirmation.content_digest)}`,
    time: confirmation.confirmed_at,
    tags,
    data: confirmation,
    branch: [],
  };
  for (const attempt of attempts) {
    const schedule = schedulesByAttempt.get(attempt.id);
    const sent = sentByAttempt.get(attempt.id) ?? (attempt.sent_record_id ? sentByAttempt.get(attempt.sent_record_id) : undefined);
    const attemptTags: LineNode["tags"] = [
      { label: `attempt #${attempt.sequence}` },
      { label: attempt.state.replaceAll("_", " "), tone: attemptState(attempt.state).tone },
    ];
    if (attempt.phase && attempt.phase !== attempt.state)
      attemptTags.push({ label: `phase · ${attempt.phase.replaceAll("_", " ")}` });
    const attemptNode: LineNode = {
      key: keyOf("attempt", attempt.id),
      kind: "attempt",
      icon: "send",
      tone: attemptState(attempt.state).tone,
      title: `Execution attempt · ${attemptState(attempt.state).label}`,
      subtitle: attempt.request?.recipient
        ? `to ${attempt.request.recipient}`
        : "recipient not retained in ledger row",
      time: attempt.outcome_observed_at ?? attempt.submission_started_at ?? attempt.intent_at,
      tags: attemptTags,
      data: attempt,
      branch: [],
    };
    if (attempt.intent_at)
      attemptNode.branch!.push({
        key: `${attemptNode.key}:intent`,
        kind: "attempt",
        icon: "clock",
        tone: "gray",
        title: "Intent recorded",
        time: attempt.intent_at,
        tags: [{ label: "phase" }],
        faint: true,
        data: { phase: "intent_recorded", at: attempt.intent_at },
      });
    if (attempt.submission_started_at)
      attemptNode.branch!.push({
        key: `${attemptNode.key}:submission`,
        kind: "attempt",
        icon: "clock",
        tone: "blue",
        title: "Submission started",
        time: attempt.submission_started_at,
        tags: [{ label: "phase" }],
        faint: true,
        data: { phase: "submission_started", at: attempt.submission_started_at },
      });
    if (schedule) {
      const meta = scheduleState(schedule.state);
      const scheduleNode: LineNode = {
        key: keyOf("schedule", schedule.id),
        kind: "schedule",
        icon: "clock",
        tone: meta.tone,
        title: `External schedule · ${meta.label}`,
        subtitle: schedule.external_id || "external identifier unavailable",
        time: schedule.scheduled_utc || schedule.updated_at,
        tags: [{ label: schedule.state.replaceAll("_", " "), tone: meta.tone }],
        struck: schedule.state === "replaced" || schedule.state === "cancelled",
        data: schedule,
        branch: [],
      };
      if (schedule.replaces_schedule_id)
        scheduleNode.branch!.push({
          key: `${scheduleNode.key}:replaces`,
          kind: "schedule",
          icon: "clock",
          tone: "amber",
          title: `Replaces earlier schedule ${shortId(schedule.replaces_schedule_id)}`,
          tags: [{ label: "replacement chain", tone: "amber" }],
          faint: true,
          data: { replaces_schedule_id: schedule.replaces_schedule_id },
        });
      attemptNode.branch!.push(scheduleNode);
    }
    if (sent) {
      attemptNode.branch!.push({
        key: keyOf("sent", sent.id),
        kind: "sent",
        icon: "database",
        tone: "green",
        title: sent.subject || "Immutable sent record",
        subtitle: `${sent.action_kind.replaceAll("_", " ")} · ref ${sent.reference || "—"}`,
        time: attempt.outcome_observed_at,
        terminal: true,
        tags: [
          { label: "immutable sent record", tone: "green" },
          { label: `${sent.attachments.length} attachment${sent.attachments.length === 1 ? "" : "s"}` },
          ...(sent.follows_sent_record_id
            ? [{ label: `follows ${shortId(sent.follows_sent_record_id)}`, tone: "purple" as Tone }]
            : []),
        ],
        data: sent,
      });
    }
    node.branch!.push(attemptNode);
  }
  return node;
}

export function buildLineage(detail: RecordsTaskDetail): TaskLineage {
  const confirmationsByPrep = groupBy(detail.confirmations, (c) => c.preparation_id);
  const attemptsByConfirmation = groupBy(detail.execution_attempts, (a) => a.confirmation_id);
  const attemptsByPrep = groupBy(detail.execution_attempts, (a) => a.preparation_id);
  const schedulesByAttempt = new Map(detail.schedules.map((s) => [s.attempt_id, s]));
  const sentByAttempt = new Map(detail.sent_records.map((s) => [s.attempt_id, s]));
  const checksByPrep = groupBy(
    detail.duplicate_checks.filter((c) => c.preparation_id),
    (c) => c.preparation_id as string,
  );
  const actionsByPrep = groupBy(
    detail.follow_up.actions.filter((a) => a.preparation_id),
    (a) => a.preparation_id as string,
  );

  const groups: VersionGroup[] = detail.preparations.map((preparation, index) => {
    const label = `v${index + 1}`;
    const nodes: LineNode[] = [];
    const versionTags: LineNode["tags"] = [
      { label: preparation.action_kind.replaceAll("_", " "), tone: "purple" },
      {
        label: preparation.ready ? "ready" : "not ready",
        tone: preparation.ready ? "green" : "amber",
      },
    ];
    if (preparation.corrections.length)
      versionTags.push({
        label: `${preparation.corrections.length} correction${preparation.corrections.length === 1 ? "" : "s"}`,
        tone: "amber",
      });
    if (preparation.transformations.length)
      versionTags.push({ label: `${preparation.transformations.length} transforms` });
    nodes.push({
      key: keyOf("version", preparation.id),
      kind: "version",
      icon: "file",
      tone: preparation.status === "superseded" ? "gray" : "blue",
      title: preparation.subject || "Untitled preparation",
      subtitle: preparation.recipient,
      version: label,
      tags: versionTags,
      data: preparation,
    });
    for (const confirmation of confirmationsByPrep.get(preparation.id) ?? []) {
      nodes.push(
        confirmationNode(
          confirmation,
          attemptsByConfirmation.get(confirmation.id) ?? [],
          schedulesByAttempt,
          sentByAttempt,
        ),
      );
    }
    for (const check of checksByPrep.get(preparation.id) ?? []) {
      nodes.push(duplicateNode(check));
    }
    for (const action of actionsByPrep.get(preparation.id) ?? []) {
      nodes.push({
        key: keyOf("followup", action.id),
        kind: "followup",
        icon: "reply",
        tone: action.status === "due" ? "amber" : action.status.includes("reply") ? "green" : "blue",
        title: `Follow-up #${action.sequence} · ${action.status.replaceAll("_", " ")}`,
        subtitle: action.preparation?.subject || action.detail || "linked follow-up action",
        time: action.due_at ?? action.created_at,
        tags: [
          { label: action.status.replaceAll("_", " ") },
          ...(action.follows_sent_record_id
            ? [{ label: `after sent ${shortId(action.follows_sent_record_id)}`, tone: "purple" as Tone }]
            : []),
        ],
        data: action,
      });
    }
    // Attempts that predate this projection's confirmation link stay visible.
    const linkedAttempts = new Set(
      (confirmationsByPrep.get(preparation.id) ?? []).flatMap((c) =>
        (attemptsByConfirmation.get(c.id) ?? []).map((a) => a.id),
      ),
    );
    for (const attempt of attemptsByPrep.get(preparation.id) ?? []) {
      if (linkedAttempts.has(attempt.id)) continue;
      nodes.push(
        confirmationNode(
          {
            id: `unlinked-${attempt.confirmation_id}`,
            preparation_id: preparation.id,
            task_id: attempt.task_id,
            status: "invalidated",
            execution: { kind: "immediate" },
            content_digest: "",
            attachments_digest: "",
            invalidated_reason: "",
            confirmed_at: attempt.intent_at ?? "",
          },
          [attempt],
          schedulesByAttempt,
          sentByAttempt,
        ),
      );
    }
    return {
      label,
      preparation,
      state: preparation.status === "superseded" ? "gray" : "blue",
      nodes,
    };
  });

  // Checks recorded against the Task rather than a specific version.
  for (const check of detail.duplicate_checks.filter((c) => !c.preparation_id)) {
    const group = groups[groups.length - 1];
    group?.nodes.push(duplicateNode(check));
  }

  const replies: LineNode[] = detail.reply_associations.map((reply) => {
    const tone: Tone =
      reply.status === "associated"
        ? reply.reply_kind === "automatic"
          ? "purple"
          : "green"
        : reply.status === "ambiguous"
          ? "amber"
          : "gray";
    return {
      key: keyOf("reply", reply.id),
      kind: "reply",
      icon: "reply",
      tone,
      title:
        reply.observation?.subject ||
        `${reply.status.replaceAll("_", " ")} reply association`,
      subtitle: reply.observation
        ? `${reply.observation.counterpart} · ${reply.observation.platform_reference}`
        : "observed message unavailable",
      time: reply.resolved_at || reply.created_at,
      tags: [
        { label: reply.status.replaceAll("_", " "), tone },
        { label: reply.reply_kind ? reply.reply_kind.replaceAll("_", " ") : "unclassified" },
        { label: reply.basis.replaceAll("_", " ") },
        ...(reply.status === "ambiguous"
          ? [{ label: `${reply.candidate_task_ids.length} candidates`, tone: "amber" as Tone }]
          : []),
      ],
      data: reply,
    };
  });

  const observations: LineNode[] = [];
  for (const run of detail.mailbox.observations) {
    observations.push(observationRunNode(run, detail.mailbox.reconciliations));
  }
  for (const reconciliation of detail.mailbox.reconciliations) {
    observations.push(reconciliationNode(reconciliation));
  }

  const sources: LineNode[] = detail.sources.length
    ? [
        {
          key: "sources:root",
          kind: "sources",
          icon: "database",
          tone: "gray",
          title: `Source material · ${detail.sources.length} retained source${detail.sources.length === 1 ? "" : "s"}`,
          subtitle: "Imported material and row associations never change",
          tags: [{ label: "provenance" }],
          data: detail.sources,
          branch: detail.sources.map((source) => ({
            key: keyOf("source", source.id),
            kind: "sources" as NodeKind,
            icon: "file" as IconName,
            tone: "gray" as Tone,
            title: source.name,
            subtitle: `${source.sheet} · row ${source.row + 1} · sha256 ${shortId(source.sha256)}`,
            tags: [{ label: `${source.size} bytes` }],
            data: source,
          })),
        },
      ]
    : [];

  return { groups, replies, observations, sources };
}

function duplicateNode(check: DuplicateCheck): LineNode {
  const tone = duplicateTone(check.finding);
  return {
    key: keyOf("duplicate", check.id),
    kind: "duplicate",
    icon: "shield",
    tone,
    title: `Duplicate check · ${check.finding.replaceAll("_", " ")}`,
    subtitle: check.detail || check.basis.replaceAll("_", " "),
    time: check.checked_at,
    tags: [
      { label: check.finding.replaceAll("_", " "), tone },
      ...(check.review_required ? [{ label: "review required", tone: "amber" as Tone }] : []),
      { label: `${check.matches.length} match${check.matches.length === 1 ? "" : "es"}` },
    ],
    data: check,
  };
}

function observationRunNode(run: MailboxObservation, reconciliations: Reconciliation[]): LineNode {
  const reconciliation = reconciliations.find((r) => r.observation_id === run.id);
  const linkedFindings = reconciliation?.findings ?? [];
  return {
    key: keyOf("observation-run", run.id),
    kind: "observation-run",
    icon: "mail",
    tone: run.status === "complete" ? "blue" : run.status === "wrong_mailbox" ? "rose" : "amber",
    title: `Mailbox observation · ${run.status.replaceAll("_", " ")}`,
    subtitle: run.detail || run.mailbox_address,
    time: run.observed_at,
    tags: [
      { label: `${run.messages.length} observed message${run.messages.length === 1 ? "" : "s"}` },
      {
        label: run.evidence_coverage?.complete ? "coverage complete" : "partial coverage",
        tone: run.evidence_coverage?.complete ? "green" : "amber",
      },
    ],
    data: run,
    branch: run.messages.map((message, index) => {
      const finding = linkedFindings.find((f) => f.message_observation_id === message.id);
      const tone: Tone =
        message.direction === "inbound"
          ? "green"
          : message.status === "sent"
            ? "green"
            : message.status === "scheduled"
              ? "purple"
              : message.status === "failed"
                ? "rose"
                : message.status === "ambiguous"
                  ? "amber"
                  : "gray";
      return {
        key: `${keyOf("observation-run", run.id)}:msg:${message.id || index}`,
        kind: "observation-message" as NodeKind,
        icon: (message.direction === "inbound" ? "reply" : "send") as IconName,
        tone,
        title: message.subject || "Observed message without subject",
        subtitle: `${message.folder} · ${message.counterpart} · ${message.observed_time || "time unavailable"}`,
        tags: [
          { label: message.direction },
          { label: message.status.replaceAll("_", " "), tone },
          ...(finding
            ? [{ label: finding.finding.replaceAll("_", " "), tone: "blue" as Tone }]
            : []),
        ],
        data: { message, finding: finding ?? null },
      };
    }),
  };
}

function reconciliationNode(reconciliation: Reconciliation): LineNode {
  return {
    key: keyOf("reconciliation", reconciliation.id),
    kind: "reconciliation",
    icon: "shield",
    tone: reconciliation.findings.length ? "amber" : "green",
    title: `Reconciliation · ${reconciliation.findings.length} finding${reconciliation.findings.length === 1 ? "" : "s"}`,
    subtitle: reconciliation.mailbox_address,
    time: reconciliation.observed_at,
    tags: [{ label: "read-only comparison" }],
    data: reconciliation,
    branch: reconciliation.findings.map((finding) => ({
      key: keyOf("reconciliation-finding", finding.id),
      kind: "reconciliation" as NodeKind,
      icon: "branch" as IconName,
      tone: "amber" as Tone,
      title: finding.finding.replaceAll("_", " "),
      subtitle: finding.detail || finding.basis.replaceAll("_", " "),
      tags: [
        { label: finding.local_kind.replaceAll("_", " ") },
        { label: shortId(finding.local_id) },
      ],
      data: finding,
    })),
  };
}

export type TaskRowView = {
  row: RecordsReportRow;
  subject: string;
  versions: number;
  confirmations: number;
  attempts: number;
  sent: number;
  schedules: number;
  cancellations: number;
  observations: number;
  replies: number;
};

export function buildTaskRows(workspace: RecordsWorkspace): TaskRowView[] {
  return workspace.tasks.map((row) => {
    const taskAttempts = workspace.attempts.filter((a) => a.task_id === row.task_id);
    const taskConfirmations = workspace.confirmations.filter((c) => c.task_id === row.task_id);
    const taskSent = workspace.sent_records.filter((s) => s.task_id === row.task_id);
    const taskSchedules = workspace.schedules.filter((s) => s.task_id === row.task_id);
    const taskReplies = workspace.reply_associations.filter((r) => r.task_id === row.task_id);
    const prepIds = new Set<string>([
      ...row.preparation_ids,
      ...taskConfirmations.map((c) => c.preparation_id),
      ...taskAttempts.map((a) => a.preparation_id),
      ...taskSent.map((s) => s.preparation_id),
      ...workspace.follow_up_actions
        .filter((a) => a.task_id === row.task_id && a.preparation_id)
        .map((a) => a.preparation_id as string),
    ]);
    const mailbox = workspace.mailboxes.find((m) => m.student_id === row.student_id);
    const subject =
      taskSent[taskSent.length - 1]?.subject ||
      taskAttempts[taskAttempts.length - 1]?.request?.subject ||
      workspace.follow_up_actions.find(
        (a) => a.task_id === row.task_id && a.preparation?.subject,
      )?.preparation?.subject ||
      workspace.plans
        .flatMap((p) => p.proposals)
        .find((proposal) => proposal.task_id === row.task_id)?.subject ||
      "Preparation without retained subject";
    return {
      row,
      subject,
      versions: prepIds.size,
      confirmations: taskConfirmations.length,
      attempts: taskAttempts.length,
      sent: taskSent.length,
      schedules: taskSchedules.length,
      cancellations: taskConfirmations.filter(
        (c) => c.execution?.kind === "cancellation",
      ).length,
      observations: mailbox?.observation_count ?? 0,
      replies: taskReplies.length,
    };
  });
}

export function taskHeadline(detail: RecordsTaskDetail | null): string {
  if (!detail) return "";
  return (
    detail.sent_records[detail.sent_records.length - 1]?.subject ||
    detail.execution_attempts[detail.execution_attempts.length - 1]?.request?.subject ||
    detail.preparations[detail.preparations.length - 1]?.subject ||
    "Outreach task"
  );
}

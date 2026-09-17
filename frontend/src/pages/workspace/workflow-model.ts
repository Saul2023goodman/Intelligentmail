import type { Task, Workspace } from "../../core";

export const GRAPH_WIDTH = 1300;
export const GRAPH_HEIGHT = 870;
export const MIN_ZOOM = 0.2;
export const MAX_ZOOM = 2.5;

export type Viewport = { zoom: number; x: number; y: number };

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

export function fitViewport(width: number, height: number): Viewport {
  const zoom = clamp(
    Math.min(width / GRAPH_WIDTH, height / GRAPH_HEIGHT),
    MIN_ZOOM,
    MAX_ZOOM,
  );
  return {
    zoom,
    x: (width - GRAPH_WIDTH * zoom) / 2,
    y: (height - GRAPH_HEIGHT * zoom) / 2,
  };
}

export function clampViewport(
  view: Viewport,
  width: number,
  height: number,
  padding = 48,
): Viewport {
  const scaledWidth = GRAPH_WIDTH * view.zoom;
  const scaledHeight = GRAPH_HEIGHT * view.zoom;
  const axis = (position: number, contentSize: number, viewportSize: number) => {
    const max = padding;
    const min =
      contentSize >= viewportSize - padding * 2
        ? viewportSize - contentSize - padding
        : padding - contentSize;
    return Math.min(max, Math.max(min, position));
  };
  return {
    zoom: view.zoom,
    x: axis(view.x, scaledWidth, width),
    y: axis(view.y, scaledHeight, height),
  };
}

export function zoomAt(
  view: Viewport,
  anchorX: number,
  anchorY: number,
  nextZoom: number,
  width: number,
  height: number,
): Viewport {
  const zoom = clamp(nextZoom, MIN_ZOOM, MAX_ZOOM);
  const worldX = (anchorX - view.x) / view.zoom;
  const worldY = (anchorY - view.y) / view.zoom;
  return clampViewport(
    {
      zoom,
      x: anchorX - worldX * zoom,
      y: anchorY - worldY * zoom,
    },
    width,
    height,
  );
}

export const stages = [
  {
    id: "mailbox",
    label: "读取外部邮箱",
    caption: "扩展只读观察",
    icon: "mail",
    color: "blue",
    x: 55,
    y: 60,
    description:
      "通过已连接的 163 邮箱扩展读取邮件元数据及证据覆盖范围。每次读取会交给 Core 保存并对账，不会自动创建任务或授权发送。",
  },
  {
    id: "database",
    label: "SmartMail 数据库",
    caption: "持久化记录与证据",
    icon: "database",
    color: "purple",
    x: 295,
    y: 60,
    description:
      "保存邮箱观察批次、来源材料、任务、草稿版本和执行证据。外部观察与本地 Preparation 分开存储；后续比对和查重使用这些记录。",
  },
  {
    id: "comparison",
    label: "比对与查重",
    caption: "任务匹配 · 历史发送检查",
    icon: "filter",
    color: "amber",
    x: 55,
    y: 213,
    description:
      "读取入库时 Core 对账并关联可识别的证据；选中已有 Preparation 的任务可执行查重，检查本 Campaign 内的发送记录及该学生邮箱的观察历史。重复疑似进入人工处理，覆盖不足会明确展示。",
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
    label: "更新 / 调整草稿",
    caption: "本地 Preparation · 保留历史",
    icon: "mail",
    color: "blue",
    x: 295,
    y: 213,
    description:
      "选择任务后可调整主题、收件人，或通过修订来源文档 Rewrite 正文。修改后重新校验、重新查重和确认；外部草稿观察不会自动覆盖本地内容。",
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
    return { count: data?.mailboxes.length ?? "—", unit: "学生邮箱" };
  if (stage === "database")
    return {
      count: data
        ? data.mailboxes.reduce(
            (total, mailbox) => total + mailbox.observation_count,
            0,
          )
        : "—",
      unit: "读取批次",
    };
  return { count: data ? tasksFor(stage, data).length : "—", unit: "tasks" };
}

import type { Campaign, MailboxHistory, Workspace } from "./types";
import type {
  ExecutionWorkspace,
  PlanConfiguration,
  SendingPlan,
  ReviewRequest,
  ReviewResult,
} from "./execution-types";
import type { RecordsTaskDetail, RecordsWorkspace } from "./records-types";
import type {
  IntakeImportResult,
  IntakeTaskDetail,
  IntakeWorkspace,
  ReviewWorkspace,
} from "./operator-types";
import type {
  RecognitionCollection,
  RecognitionTypeId,
} from "./recognition-types";
import { publishCoreMutation } from "./events.ts";
export type * from "./types";
export type * from "./execution-types";
export type * from "./mailbox-types";
export type * from "./records-types";
export type * from "./operator-types";
export type * from "./recognition-types";

/** The allowlist mirrors smartmail/ui.py. Core owns all domain decisions. */
export type Commands = {
  intake_workspace: {
    args: { campaign_id?: string; student_id?: string };
    result: IntakeWorkspace;
  };
  intake_recognize: {
    args: { files: { name: string; content: string }[] };
    result: RecognitionCollection;
  };
  intake_import: {
    args: {
      campaign_id: string;
      student_id: string;
      files: {
        name: string;
        content: string;
        type?: RecognitionTypeId;
        included?: boolean;
        members?: { name: string; type?: RecognitionTypeId }[];
      }[];
    };
    result: IntakeImportResult;
  };
  review_workspace: {
    args: { campaign_id: string };
    result: ReviewWorkspace;
  };
  confirm_attachment: {
    args: { preparation_id: string; slot_id: string };
    result: import("./records-types").FullPreparation;
  };
  set_attachment_source: {
    args: { preparation_id: string; slot_id: string; source_id: string };
    result: import("./records-types").FullPreparation;
  };
  resolve_review_exception: {
    args: { task_id: string; code: "identity_ambiguity" | "prior_outreach_conflict" };
    result: unknown;
  };
  mailbox_workspace: {
    args: { campaign_id: string; student_id: string };
    result: import("./mailbox-types").MailboxWorkspace;
  };
  execution_workspace: {
    args: { campaign_id: string };
    result: ExecutionWorkspace;
  };
  execution_configure: {
    args: PlanConfiguration & { campaign_id: string };
    result: PlanConfiguration;
  };
  execution_propose: { args: { campaign_id: string }; result: SendingPlan };
  execution_adjust: {
    args: { plan_id: string; preparation_id: string; scheduled_at: string };
    result: SendingPlan;
  };
  execution_review: { args: ReviewRequest; result: ReviewResult };
  execution_confirm: {
    args: ReviewRequest & { token: string };
    result: unknown;
  };
  execution_run: {
    args: { confirmation_id: string };
    result: { paused?: boolean; flow?: { state: string } };
  };
  workspace: { args: { campaign_id?: string }; result: Workspace };
  task: { args: { task_id: string }; result: IntakeTaskDetail & { rewrite_sources: { id: string; name: string }[] } };
  create_campaign: { args: { name: string }; result: Campaign };
  create_student: {
    args: { name: string; mailbox: string };
    result: import("./types").StudentWorkspace;
  };
  check_duplicate: {
    args: { preparation_id: string };
    result: { finding: string };
  };
  mailbox_history: { args: { student_id: string }; result: MailboxHistory };
  records_workspace: {
    args: { campaign_id: string };
    result: RecordsWorkspace;
  };
  records_task: { args: { task_id: string }; result: RecordsTaskDetail };
  refresh_mailbox: {
    args: { student_id: string };
    result: {
      observation: { status: string; messages: unknown[]; detail: string };
    };
  };
  update_preparation: {
    args: { preparation_id: string; subject: string; recipient: string };
    result: unknown;
  };
  rewrite: {
    args: { preparation_id: string; source_id: string };
    result: unknown;
  };
};

export type CommandName = keyof Commands;
export type CommandArgs<K extends CommandName> = Commands[K]["args"];
export type CommandResult<K extends CommandName> = Commands[K]["result"];

type Request = {
  [K in keyof Commands]: [command: K, args: Commands[K]["args"]];
}[keyof Commands];

// A discriminated tuple prevents mixing a command with another command's arguments.
export async function core<T extends Request>(
  ...request: T
): Promise<Commands[T[0]]["result"]> {
  const [command, args] = request;
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
  if (MUTATING_COMMANDS.has(command)) {
    publishCoreMutation({ command, args: args as Record<string, unknown> });
  }
  return value.result;
}

const MUTATING_COMMANDS = new Set<CommandName>([
  "intake_import",
  "confirm_attachment",
  "set_attachment_source",
  "resolve_review_exception",
  "execution_configure",
  "execution_propose",
  "execution_adjust",
  "execution_confirm",
  "execution_run",
  "create_campaign",
  "create_student",
  "check_duplicate",
  "refresh_mailbox",
  "update_preparation",
  "rewrite",
]);

export const human = (text: string) => text.replaceAll("_", " ");

async function fileContent(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunk = 0x8000;
  for (let start = 0; start < bytes.length; start += chunk) {
    binary += String.fromCharCode(...bytes.subarray(start, start + chunk));
  }
  return btoa(binary);
}

export async function recognizeSources(files: File[]) {
  return core("intake_recognize", {
    files: await Promise.all(
      files.map(async (file) => ({ name: file.name, content: await fileContent(file) })),
    ),
  });
}

export type ImportSelection = {
  file: File;
  type?: RecognitionTypeId;
  included?: boolean;
  members?: { name: string; type?: RecognitionTypeId }[];
};

export async function importSources(
  campaignId: string,
  studentId: string,
  selections: ImportSelection[],
) {
  return core("intake_import", {
    campaign_id: campaignId,
    student_id: studentId,
    files: await Promise.all(
      selections.map(async ({ file, type, included, members }) => ({
        name: file.name,
        content: await fileContent(file),
        ...(type ? { type } : {}),
        ...(included !== undefined ? { included } : {}),
        ...(members ? { members } : {}),
      })),
    ),
  });
}

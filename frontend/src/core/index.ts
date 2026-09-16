import type { Campaign, Detail, MailboxHistory, Workspace } from "./types";
export type * from "./types";

/** The allowlist mirrors smartmail/ui.py. Core owns all domain decisions. */
type Commands = {
  workspace: { args: { campaign_id?: string }; result: Workspace };
  task: { args: { task_id: string }; result: Detail };
  create_campaign: { args: { name: string }; result: Campaign };
  check_duplicate: {
    args: { preparation_id: string };
    result: { finding: string };
  };
  mailbox_history: { args: { student_id: string }; result: MailboxHistory };
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
  return value.result;
}

export const human = (text: string) => text.replaceAll("_", " ");

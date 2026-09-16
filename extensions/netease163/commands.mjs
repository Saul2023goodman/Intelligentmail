/* Protocol orchestration is independent of Chrome for deterministic acceptance tests. */
export const PROTOCOL = 1;
export const HOST = "com.smartmail.netease163";

export const OPERATIONS = ["observe", "submit", "schedule", "cancel_schedule", "recall"];
const MUTATING = new Set(["submit", "schedule", "cancel_schedule", "recall"]);

export function assertCommand(command) {
  if (!command || typeof command.id !== "string" || !OPERATIONS.includes(command.operation)
      || !Number.isFinite(command.deadline) || command.deadline <= Date.now()
      || !command.payload || typeof command.payload !== "object") throw new Error("Invalid or expired native command");
}

export async function fetchAttachments(command, rpc) {
  const descriptors = command.payload.attachments;
  if (!Array.isArray(descriptors) || descriptors.some(file => !Number.isSafeInteger(file.size) || file.size < 0)
      || descriptors.reduce((total, file) => total + file.size, 0) > 20 * 1024 * 1024)
    throw new Error("Unsupported confirmed attachment sizes");
  const files = [];
  for (let position = 0; position < descriptors.length; position++) {
    const parts = [];
    let offset = 0;
    while (true) {
      assertCommand(command);
      const chunk = await rpc("attachment", { command_id: command.id, position, offset });
      if (typeof chunk.data !== "string" || !Number.isSafeInteger(chunk.next) || chunk.next < offset
          || chunk.next > descriptors[position].size || (!chunk.done && chunk.next === offset))
        throw new Error("Invalid confirmed attachment chunk");
      parts.push(chunk.data);
      offset = chunk.next;
      if (chunk.done) break;
    }
    if (offset !== descriptors[position].size) throw new Error("Truncated confirmed attachment");
    // All non-final chunks are multiples of three bytes, so concatenation preserves base64.
    files.push(parts.join(""));
  }
  return files;
}

const failureEnvelope = (command, permitted, detail) => {
  if (command?.operation === "observe") return {
    status: "failed", mailbox_address: "", detail,
    coverage: { complete: false, folders: [] }, messages: [], observed_at: new Date().toISOString()
  };
  return { outcome: permitted ? "unknown" : "failed", detail, reference: "" };
};

export async function executeCommand(command, { invoke, rpc, connected }) {
  let permitted = false;
  try {
    assertCommand(command);
    if (!connected()) throw new Error("Mailbox connection was closed");
    if (command.operation === "observe")
      return await invoke("observe", command.payload.mailbox_address, command.deadline);

    const payload = command.payload;
    let files = [];
    if (command.operation === "submit") {
      if (payload.kind !== "immediate") throw new Error("Only confirmed immediate submissions are supported");
      files = await fetchAttachments(command, rpc);
      const prepared = await invoke("prepare", command, files);
      if (!prepared?.prepared) throw new Error("Compose preparation was not verified");
      assertCommand(command);
      if (!connected()) throw new Error("Connection closed before submission");
      const permit = await rpc("authorize", { command_id: command.id });
      if (!permit.permitted || permit.deadline !== command.deadline) throw new Error("Submission permit is unavailable");
      permitted = true;
      assertCommand(command);
      if (!connected()) throw new Error("Connection closed before submission");
      return await invoke("send", command);
    }

    if (!MUTATING.has(command.operation)) throw new Error("Unsupported command operation");
    if (command.operation === "schedule") {
      if (payload.kind !== "scheduled") throw new Error("Only confirmed native schedules are supported");
      if (!Number.isFinite(Number(payload.scheduled_epoch_ms)))
        throw new Error("A confirmed exact schedule time is required");
      files = await fetchAttachments(command, rpc);
    } else if (command.operation === "cancel_schedule") {
      if (payload.kind !== "cancel_schedule") throw new Error("Only confirmed cancellation is supported");
      if (!payload.external_id) throw new Error("Cancellation requires the observed external schedule identity");
    } else if (command.operation === "recall") {
      if (payload.kind !== "recall") throw new Error("Only a confirmed Recall is supported");
      if (!payload.external_id) throw new Error("Recall requires the observed Sent message identity");
    }
    assertCommand(command);
    if (!connected()) throw new Error("Connection closed before the confirmed external operation");
    const permit = await rpc("authorize", { command_id: command.id });
    if (!permit.permitted || permit.deadline !== command.deadline) throw new Error("Operation permit is unavailable");
    permitted = true;
    assertCommand(command);
    if (!connected()) throw new Error("Connection closed before the confirmed external operation");
    if (command.operation === "schedule") return await invoke("placeSchedule", command, files);
    if (command.operation === "cancel_schedule") return await invoke("cancelSchedule", command);
    return await invoke("recallMessage", command);
  } catch (error) {
    return failureEnvelope(command, permitted, String(error.message || error));
  }
}

/* Protocol orchestration is independent of Chrome for deterministic acceptance tests. */
export const PROTOCOL = 1;
export const HOST = "com.smartmail.netease163";

export function assertCommand(command) {
  if (!command || typeof command.id !== "string" || !["observe", "submit"].includes(command.operation)
      || !Number.isFinite(command.deadline) || command.deadline <= Date.now()
      || !command.payload || typeof command.payload !== "object") throw new Error("Invalid or expired native command");
}

export async function executeCommand(command, { invoke, rpc, connected }) {
  let permitted = false;
  try {
    assertCommand(command);
    if (!connected()) throw new Error("Mailbox connection was closed");
    if (command.operation === "observe") return await invoke("observe", command.payload.mailbox_address, command.deadline);
    if (command.payload.kind !== "immediate") throw new Error("Only confirmed immediate submissions are supported");
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
  } catch (error) {
    const detail = String(error.message || error);
    if (command?.operation === "observe") return {
      status: "failed", mailbox_address: "", detail,
      coverage: { complete: false, folders: [] }, messages: [], observed_at: new Date().toISOString()
    };
    return { outcome: permitted ? "unknown" : "failed", detail, reference: "" };
  }
}

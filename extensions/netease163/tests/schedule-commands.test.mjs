import test from "node:test";
import assert from "node:assert/strict";
import { executeCommand } from "../commands.mjs";

const deadline = () => Date.now() + 60000;

function scheduleCommand(overrides = {}) {
  return {
    id: "sched-1", operation: "schedule", deadline: deadline(),
    payload: {
      kind: "scheduled", sender: "student@163.com", recipient: "supervisor@example.edu",
      subject: "Scheduled", body: "Confirmed content",
      scheduled_epoch_ms: Date.now() + 3 * 3600_000,
      attachments: [], ...overrides
    }
  };
}

function peer(overrides = {}) {
  const events = [];
  return {
    events, connected: () => true,
    invoke: async (method, ...args) => {
      events.push(method);
      if (method === "placeSchedule")
        return { outcome: "scheduled", reference: "761:ext-1", external_id: "761:ext-1",
          mailbox_address: "student@163.com",
          evidence: { folder: "drafts", schedule_delivery: true } };
      if (method === "cancelSchedule")
        return { outcome: "removed", reference: "ext-1", external_id: "ext-1",
          mailbox_address: "student@163.com" };
      if (method === "recallMessage")
        return { outcome: "recalled", reference: "ext-1", mailbox_address: "student@163.com" };
      return {};
    },
    rpc: async method => { events.push(method); return { permitted: true, deadline: overrides.deadline }; },
    ...overrides
  };
}

test("schedule placement pulls attachments, obtains one permit, then places", async () => {
  const command = scheduleCommand({ attachments: [{ size: 3, name: "a.txt", sha256: "x" }] });
  const extension = peer();
  const chunks = { calls: 0 };
  extension.rpc = async method => {
    extension.events.push(method);
    if (method === "attachment") { chunks.calls++; return { data: "YWJj", next: 3, done: true }; }
    return { permitted: true, deadline: command.deadline };
  };
  const result = await executeCommand(command, extension);
  assert.equal(result.outcome, "scheduled");
  assert.deepEqual(extension.events, ["attachment", "authorize", "placeSchedule"]);
  assert.equal(chunks.calls, 1);
});

test("a schedule without an exact future time is rejected before authority", async () => {
  const command = scheduleCommand({ scheduled_epoch_ms: "not-a-number" });
  const extension = peer();
  const result = await executeCommand(command, extension);
  assert.equal(result.outcome, "failed");
  assert.ok(!extension.events.includes("authorize"));
});

test("schedule never proceeds without a permit", async () => {
  const command = scheduleCommand();
  const extension = peer({
    rpc: async method => { extension.events.push(method); return { permitted: false }; }
  });
  const result = await executeCommand(command, extension);
  assert.equal(result.outcome, "failed");
  assert.ok(!extension.events.includes("placeSchedule"));
});

test("a failed placement after the permit becomes Unknown, never a duplicate click", async () => {
  const command = scheduleCommand();
  let placements = 0;
  const extension = peer({
    deadline: command.deadline,
    invoke: async method => {
      if (method === "placeSchedule") { placements++; throw new Error("page navigated away"); }
      return {};
    }
  });
  const result = await executeCommand(command, extension);
  assert.equal(result.outcome, "unknown");
  assert.equal(placements, 1);
});

test("cancellation requires the observed external identity and a permit", async () => {
  const command = { id: "cancel-1", operation: "cancel_schedule", deadline: deadline(),
    payload: { kind: "cancel_schedule", sender: "student@163.com", external_id: "761:ext-1",
      recipient: "supervisor@example.edu", subject: "Scheduled" } };
  const extension = peer({ deadline: command.deadline });
  const result = await executeCommand(command, extension);
  assert.equal(result.outcome, "removed");
  assert.deepEqual(extension.events, ["authorize", "cancelSchedule"]);
});

test("cancellation without an external id is rejected before authority", async () => {
  const command = { id: "cancel-2", operation: "cancel_schedule", deadline: deadline(),
    payload: { kind: "cancel_schedule", sender: "student@163.com", external_id: "" } };
  const extension = peer();
  const result = await executeCommand(command, extension);
  assert.equal(result.outcome, "failed");
  assert.ok(!extension.events.includes("authorize"));
});

test("recall is a separately permitted operation with its own page call", async () => {
  const command = { id: "recall-1", operation: "recall", deadline: deadline(),
    payload: { kind: "recall", sender: "student@163.com", external_id: "761:ext-1",
      recipient: "supervisor@example.edu", subject: "Sent earlier" } };
  const extension = peer({ deadline: command.deadline });
  const result = await executeCommand(command, extension);
  assert.equal(result.outcome, "recalled");
  assert.deepEqual(extension.events, ["authorize", "recallMessage"]);
});

test("connection loss after the schedule permit is Unknown rather than failed", async () => {
  const command = scheduleCommand();
  let connected = true;
  const extension = peer({
    connected: () => connected,
    rpc: async method => {
      extension.events.push(method);
      connected = false;
      return { permitted: true, deadline: command.deadline };
    },
    deadline: command.deadline
  });
  const result = await executeCommand(command, extension);
  assert.equal(result.outcome, "unknown");
});

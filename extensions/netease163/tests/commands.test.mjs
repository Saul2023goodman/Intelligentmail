import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import { executeCommand } from "../commands.mjs";

const command = () => ({ id: "one", operation: "submit", deadline: Date.now() + 60000,
  payload: { kind: "immediate", sender: "student@163.com", recipient: "supervisor@example.edu", subject: "Hello", body: "Confirmed", attachments: [] } });

function peer(overrides = {}) {
  const events = [];
  return { events, connected: () => true,
    invoke: async method => { events.push(method); return method === "prepare" ? { prepared: true } : { outcome: "sent" }; },
    rpc: async (method) => { events.push(method); return overrides.permit || { permitted: true, deadline: overrides.deadline }; },
    ...overrides
  };
}

test("one preparation and one permit precede the only submission", async () => {
  const next = command();
  const extension = peer({ deadline: next.deadline });
  assert.equal((await executeCommand(next, extension)).outcome, "sent");
  assert.deepEqual(extension.events, ["prepare", "authorize", "send"]);
});

test("a preparation failure never asks for authority or clicks send", async () => {
  let requests = 0;
  const result = await executeCommand(command(), peer({
    invoke: async () => { throw new Error("Unexpected extra recipient"); }, rpc: async () => { requests++; }
  }));
  assert.equal(result.outcome, "failed");
  assert.equal(requests, 0);
});

test("connection loss after prepare cannot send", async () => {
  let connected = true;
  const result = await executeCommand(command(), peer({
    connected: () => connected, invoke: async () => { connected = false; return { prepared: true }; },
    rpc: async () => { assert.fail("Disconnected command must not obtain a permit"); }
  }));
  assert.equal(result.outcome, "failed");
});

test("expiry while awaiting authority cannot send late", async () => {
  const next = command();
  const calls = [];
  const result = await executeCommand(next, peer({
    invoke: async method => { calls.push(method); return { prepared: true }; },
    rpc: async () => { next.deadline = Date.now() - 1; return { permitted: true, deadline: next.deadline }; }
  }));
  assert.deepEqual(calls, ["prepare"]);
  assert.equal(result.outcome, "unknown");
});

test("an uncertain send result is never retried", async () => {
  const next = command();
  let sends = 0;
  const result = await executeCommand(next, peer({ deadline: next.deadline,
    invoke: async method => { if (method === "prepare") return { prepared: true }; sends++; throw new Error("Document navigated"); }
  }));
  assert.equal(result.outcome, "unknown");
  assert.equal(sends, 1);
});

test("read-only observation cannot request a submission permit", async () => {
  const next = { ...command(), operation: "observe", payload: { mailbox_address: "student@163.com" } };
  const result = await executeCommand(next, peer({
    invoke: async (method, mailbox) => { assert.equal(method, "observe"); assert.equal(mailbox, "student@163.com"); return { status: "partial" }; },
    rpc: async () => assert.fail("Read-only observation must not request authority")
  }));
  assert.equal(result.status, "partial");
});

test("incomplete attachment transport refuses compose", async () => {
  const next = command();
  next.payload.attachments = [{ size: 4 }];
  const result = await executeCommand(next, peer({
    rpc: async () => ({ data: "YWJj", next: 3, done: true }),
    invoke: async () => assert.fail("Truncated bytes must not reach compose")
  }));
  assert.equal(result.outcome, "failed");
});

const source = await readFile(new URL("../common.js", import.meta.url), "utf8");
const context = vm.createContext({ setTimeout, clearTimeout, URL, Date, Intl });
vm.runInContext(source, context);
const api = context.SmartMail163;
const started = Date.now();
const request = command().payload;
const row = { id: "new", from: "student@163.com", to: request.recipient, subject: request.subject,
  sentDate: new Date(started).toISOString(), sndStatus: 3 };

test("Sent evidence requires a new canonical ID and positive send status", () => {
  assert.equal(api.newSentMatch([row], [], request, started)?.id, "new");
  assert.equal(api.newSentMatch([row], ["new"], request, started), null);
  assert.equal(api.newSentMatch([{ ...row, sndStatus: 0 }], [], request, started), null);
});

test("invalid dates, old dates and ambiguous matches do not establish Sent", () => {
  for (const sentDate of ["unknown", "2001-01-01T00:00:00Z"])
    assert.equal(api.newSentMatch([{ ...row, sentDate }], [], request, started), null);
  assert.equal(api.newSentMatch([row, { ...row, id: "another" }], [], request, started), null);
});

test("exact recipients and subject exclude near matches and extra recipients", () => {
  for (const different of [{ to: "other@example.edu" }, { to: request.recipient + ", other@example.edu" },
    { from: "other@163.com" }, { subject: request.subject + " changed" }])
    assert.equal(api.newSentMatch([{ ...row, ...different }], [], request, started), null);
});

test("schedule XML uses the fixed wmsvr object grammar and Beijing wall-clock date", () => {
  const at = new context.Date("2026-09-20T07:30:00.000Z"); // 15:30 Beijing
  const xml = api.toXml({
    action: "schedule", returnInfo: false, notifyEML: true,
    attrs: { account: "student@163.com", to: ["student@163.com"], cc: [],
      priority: 3, scheduleDate: at, attachments: [{ id: 7 }] }
  });
  assert.ok(xml.startsWith("<object>"));
  assert.ok(xml.includes('<string name="action">schedule</string>'));
  assert.ok(xml.includes('<boolean name="returnInfo">false</boolean>'));
  assert.ok(xml.includes('<boolean name="notifyEML">true</boolean>'));
  assert.ok(xml.includes('<array name="to"><string>student@163.com</string></array>'));
  assert.ok(xml.includes('<array name="cc"/>'));
  assert.ok(xml.includes('<int name="priority">3</int>'));
  assert.ok(xml.includes('<date name="scheduleDate">2026-09-20 15:30:00</date>'));
  assert.ok(xml.includes('<object><int name="id">7</int></object>'));
  assert.equal(api.beijingStamp(at), "2026-09-20 15:30:00");
});

test("XML escaping keeps confirmed content safe in element text", () => {
  assert.ok(api.toXml({ subject: '<a href="x">&\n</a>' })
    .includes("&lt;a href=&quot;x&quot;&gt;&amp;"));
});

test("the manifest grants only the dedicated mailbox origin and packaged scripts", async () => {
  const manifest = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url), "utf8"));
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.host_permissions, ["https://mail.163.com/*"]);
  assert.equal(manifest.permissions.includes("debugger"), false);
  assert.equal(manifest.permissions.includes("cookies"), false);
  assert.equal(manifest.externally_connectable, undefined);
});

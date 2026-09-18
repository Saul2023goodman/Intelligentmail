import test from "node:test";
import assert from "node:assert/strict";
import {
  BUSY_POLL_DELAY_MS,
  IDLE_POLL_DELAY_MS,
  mailboxIdentity,
  nextPollDelay,
} from "../connection.mjs";

test("the scripting result supplies the normalized Native Messaging mailbox", () => {
  assert.equal(
    mailboxIdentity([{ documentId: "document", result: " Student@163.COM " }]),
    "student@163.com",
  );
});

test("missing or ambiguous scripting results never invent an identity", () => {
  for (const value of [undefined, null, [], [{}], [{ result: 7 }],
    [{ result: "a@163.com" }, { result: "b@163.com" }]])
    assert.equal(mailboxIdentity(value), "");
});

test("idle pickup is responsive while a busy operation keeps a calm heartbeat", () => {
  assert.equal(nextPollDelay(false), IDLE_POLL_DELAY_MS);
  assert.equal(nextPollDelay(true), BUSY_POLL_DELAY_MS);
  assert.ok(IDLE_POLL_DELAY_MS < BUSY_POLL_DELAY_MS);
});

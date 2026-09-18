import test from "node:test";
import assert from "node:assert/strict";
import {
  BUSY_POLL_DELAY_MS,
  IDLE_POLL_DELAY_MS,
  mailboxIdentity,
  nextPollDelay,
  isMailboxTab,
  reconnectDelay,
  selectMailboxTab,
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

test("only a fully loaded authenticated mailbox document is connectable", () => {
  assert.equal(isMailboxTab({ id: 1, status: "complete", url: "https://mail.163.com/js6/main.jsp?sid=x" }), true);
  assert.equal(isMailboxTab({ id: 1, status: "loading", url: "https://mail.163.com/js6/main.jsp" }), false);
  assert.equal(isMailboxTab({ id: 1, status: "complete", url: "https://mail.163.com/" }), false);
  assert.equal(isMailboxTab({ id: 1, status: "complete", url: "https://example.com/js6/main.jsp" }), false);
});

test("automatic discovery avoids guessing between background mailbox tabs", () => {
  const first = { id: 1, status: "complete", url: "https://mail.163.com/js6/main.jsp?sid=one", active: false };
  const second = { id: 2, status: "complete", url: "https://mail.163.com/js6/main.jsp?sid=two", active: false };
  assert.equal(selectMailboxTab([first]), first);
  assert.equal(selectMailboxTab([first, { ...second, active: true }]).id, 2);
  assert.equal(selectMailboxTab([first, second]), null);
  assert.equal(selectMailboxTab([first, second], 1), first);
});

test("reconnect backoff is bounded", () => {
  assert.equal(reconnectDelay(0), 500);
  assert.equal(reconnectDelay(3), 4000);
  assert.equal(reconnectDelay(99), 15000);
});

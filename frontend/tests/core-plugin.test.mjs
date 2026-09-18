import assert from "node:assert/strict";
import { test } from "node:test";
import { coreWorkerArguments } from "../core-plugin.ts";

test("ordinary development keeps external mailbox mutations disabled", () => {
  const args = coreWorkerArguments({});
  assert.equal(args.includes("--enable-extension-send"), false);
  assert.equal(args.includes("--enable-extension-schedule"), false);
  assert.equal(args.includes("--enable-extension-recall"), false);
});

test("acceptance mode enables send and schedule independently of Recall", () => {
  const args = coreWorkerArguments({
    SMARTMAIL_ENABLE_EXTENSION_SEND: "1",
    SMARTMAIL_ENABLE_EXTENSION_SCHEDULE: "true",
    SMARTMAIL_ENABLE_EXTENSION_RECALL: "no",
  });
  assert.equal(args.includes("--enable-extension-send"), true);
  assert.equal(args.includes("--enable-extension-schedule"), true);
  assert.equal(args.includes("--enable-extension-recall"), false);
});

import assert from "node:assert/strict";
import { test } from "node:test";
import { gatewayHealth } from "../src/core/gateway.ts";

const student = (address = "student@163.com") => ({
  id: "mb1",
  student_id: "s1",
  student_name: "Student",
  address,
  campaign_id: "c1",
  observation_count: 0,
  message_count: 0,
  latest: null,
});

const gateway = (overrides = {}) => ({
  adapter: "163-extension",
  connected: false,
  mailbox_address: "",
  protocol: 1,
  ...overrides,
});

test("a disabled adapter reports an unavailable gateway with no observation", () => {
  const health = gatewayHealth(
    { adapter: "disabled", connected: false, mailbox_address: "", protocol: 0 },
    student(),
  );
  assert.equal(health.state, "unavailable");
  assert.equal(health.enabled, false);
  assert.equal(health.canObserve, false);
});

test("an enabled adapter without a bridge connection asks for a connection", () => {
  const health = gatewayHealth(gateway(), student());
  assert.equal(health.state, "disconnected");
  assert.equal(health.enabled, true);
  assert.equal(health.canObserve, false);
});

test("a bridge connected to another mailbox is a scope mismatch", () => {
  const health = gatewayHealth(
    gateway({ connected: true, mailbox_address: "other@163.com" }),
    student(),
  );
  assert.equal(health.state, "mismatch");
  assert.equal(health.connectedAddress, "other@163.com");
  assert.equal(health.canObserve, false);
});

test("a bridge connected to the selected Student's mailbox is healthy", () => {
  const health = gatewayHealth(
    gateway({ connected: true, mailbox_address: "STUDENT@163.com" }),
    student(),
  );
  assert.equal(health.state, "connected");
  assert.equal(health.canObserve, true);
});

test("health follows the selected Student when the scope switches", () => {
  const connected = gateway({ connected: true, mailbox_address: "a@163.com" });
  assert.equal(gatewayHealth(connected, student("a@163.com")).state, "connected");
  assert.equal(gatewayHealth(connected, student("b@163.com")).state, "mismatch");
});

test("a connected gateway without a selected Student cannot observe yet", () => {
  const health = gatewayHealth(
    gateway({ connected: true, mailbox_address: "student@163.com" }),
    null,
  );
  assert.equal(health.state, "connected");
  assert.equal(health.canObserve, false);
});

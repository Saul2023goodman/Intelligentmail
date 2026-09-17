import assert from "node:assert/strict";
import { test } from "node:test";
import { resolveRoute, navigate } from "../src/app/routes.ts";
import { core, importSources } from "../src/core/index.ts";

test("existing links and unknown hashes resolve predictably", () => {
  assert.equal(resolveRoute("#source-mapping"), "sources");
  assert.equal(resolveRoute("#workflow"), "workflow");
  assert.equal(resolveRoute("#tasks"), "workflow");
  assert.equal(resolveRoute("#review"), "review");
  assert.equal(resolveRoute("#execution"), "execution");
  assert.equal(resolveRoute(""), "workflow");
  assert.equal(resolveRoute("#unknown"), "workflow");
});

test("navigation writes a history-compatible hash", (t) => {
  t.mock.method(globalThis, "fetch", async () => {
    throw new Error("Routing must not call Core");
  });
  const previous = globalThis.window;
  globalThis.window = { location: { hash: "" } };
  try {
    navigate("sources");
    assert.equal(window.location.hash, "#source-mapping");
    navigate("review");
    assert.equal(window.location.hash, "#review");
  } finally {
    globalThis.window = previous;
  }
});

test("Core preserves the bridge protocol and result", async (t) => {
  const result = { campaigns: [], report: null };
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/core");
    assert.equal(options.method, "POST");
    assert.equal(options.headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(options.body), {
      command: "workspace",
      campaign_id: "campaign-1",
    });
    return Response.json({ result });
  });
  assert.deepEqual(
    await core("workspace", { campaign_id: "campaign-1" }),
    result,
  );
});

test("Core surfaces domain blockers without converting them to success", async (t) => {
  t.mock.method(globalThis, "fetch", async () =>
    Response.json({ error: "Preparation is superseded" }),
  );
  await assert.rejects(
    core("rewrite", { preparation_id: "p", source_id: "s" }),
    /Preparation is superseded/,
  );
});

test("Core explains an unavailable static-host bridge", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response("<html></html>"));
  await assert.rejects(core("workspace", {}), /Core is offline/);
});

test("Core rejects HTTP failures and network failures", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () =>
    Response.json({}, { status: 503 }),
  );
  await assert.rejects(core("workspace", {}), /Unable to reach SmartMail Core/);
  fetch.mock.mockImplementation(async () => {
    throw new Error("Network unavailable");
  });
  await assert.rejects(core("workspace", {}), /Network unavailable/);
});

test("browser intake transports selected bytes through the allowlisted command", async (t) => {
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    const request = JSON.parse(options.body);
    assert.equal(request.command, "intake_import");
    assert.equal(request.campaign_id, "campaign-1");
    assert.equal(request.student_id, "student-1");
    assert.deepEqual(request.files, [{ name: "master.xlsx", content: "AQID" }]);
    return Response.json({ result: { import: {}, preparation: {}, workspace: {} } });
  });
  await importSources(
    "campaign-1",
    "student-1",
    [new File([new Uint8Array([1, 2, 3])], "master.xlsx")],
  );
});

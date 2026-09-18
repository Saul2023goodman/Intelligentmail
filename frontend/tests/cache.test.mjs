import assert from "node:assert/strict";
import { test } from "node:test";
import { CoreQueryCache, queryKey } from "../src/core/cache.ts";

test("Core query keys are stable and identical reads are deduplicated", async () => {
  let calls = 0;
  const cache = new CoreQueryCache(async () => ({ version: ++calls }));

  assert.equal(
    queryKey("workspace", { student_id: "s", campaign_id: "c" }),
    queryKey("workspace", { campaign_id: "c", student_id: "s" }),
  );
  const [first, second] = await Promise.all([
    cache.fetch("workspace", { campaign_id: "c" }),
    cache.fetch("workspace", { campaign_id: "c" }),
  ]);
  assert.deepEqual(first, { version: 1 });
  assert.deepEqual(second, first);
  assert.equal(calls, 1);
  assert.deepEqual(await cache.fetch("workspace", { campaign_id: "c" }), first);
  assert.equal(calls, 1);
});

test("active invalidation preserves cached data while refreshing", async () => {
  let release;
  let calls = 0;
  const cache = new CoreQueryCache(async () => {
    calls += 1;
    if (calls === 1) return { tasks: ["old"] };
    return new Promise((resolve) => { release = resolve; });
  });
  const args = { campaign_id: "c" };
  await cache.fetch("records_workspace", args);
  const unsubscribe = cache.subscribe("records_workspace", args, () => undefined);

  cache.invalidate((command) => command === "records_workspace");
  const synchronizing = cache.snapshot("records_workspace", args);
  assert.deepEqual(synchronizing.data, { tasks: ["old"] });
  assert.equal(synchronizing.isFetching, true);
  release({ tasks: ["new"] });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(cache.snapshot("records_workspace", args).data, { tasks: ["new"] });
  unsubscribe();
});

test("inactive invalidation defers network work until the query is used again", async () => {
  let calls = 0;
  const cache = new CoreQueryCache(async () => ++calls);
  const args = { task_id: "task-1" };
  await cache.fetch("task", args);
  cache.invalidate((command) => command === "task");
  assert.equal(calls, 1);
  assert.equal(cache.snapshot("task", args).isStale, true);
  assert.equal(await cache.fetch("task", args), 2);
});

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  confidenceTone,
  identitySummary,
  reviewImportability,
  typeOption,
} from "../src/pages/intake/recognition-model.ts";

const result = (overrides) => ({
  name: "x",
  format: "docx",
  type: "outreach_draft",
  label: "Single supervisor outreach draft",
  confidence: "high",
  actionable: true,
  reasons: [],
  cautions: [],
  evidence: {},
  identities: {},
  segments: [],
  alternatives: [],
  sha256: "",
  ...overrides,
});

const entry = (overrides) => ({ name: "x", format: "docx", type: "outreach_draft", included: true, ...overrides });

test("confidence maps to board tones", () => {
  assert.equal(confidenceTone("high"), "ready");
  assert.equal(confidenceTone("medium"), "waiting");
  assert.equal(confidenceTone("low"), "muted");
});

test("a lone document cannot import without a master workbook", () => {
  const verdict = reviewImportability([entry({ name: "Ping Tan.docx" })]);
  assert.equal(verdict.ok, false);
  assert.match(verdict.issues[0], /master workbook/);
});

test("one recognized master plus documents is importable", () => {
  const verdict = reviewImportability([
    entry({ name: "master.xlsx", format: "xlsx", type: "supervisor_master" }),
    entry({ name: "Ping Tan.docx" }),
    entry({ name: "plan.docx", type: "planning_document", included: false }),
  ]);
  assert.deepEqual(verdict.issues, []);
  assert.equal(verdict.ok, true);
});

test("multiple loose workbooks are blocked", () => {
  const verdict = reviewImportability([
    entry({ name: "a.xlsx", format: "xlsx", type: "supervisor_master" }),
    entry({ name: "b.xlsx", format: "xlsx", type: "supervisor_master" }),
  ]);
  assert.equal(verdict.ok, false);
  assert.match(verdict.issues.join(" "), /one supervisor master/);
});

test("a workbook revised away from master is blocked with the recognized label", () => {
  const verdict = reviewImportability([
    entry({ name: "track.xlsx", format: "xlsx", type: "tracking_sheet" }),
    entry({ name: "Ping Tan.docx" }),
  ]);
  assert.equal(verdict.ok, false);
  assert.match(verdict.issues.join(" "), /tracking/i);
});

test("batch CSV rows are not silently sent through the master import path", () => {
  const verdict = reviewImportability([
    entry({ name: "batch.csv", format: "csv", type: "bulk_import" }),
    entry({ name: "master.xlsx", format: "xlsx", type: "supervisor_master" }),
  ]);
  assert.equal(verdict.ok, false);
  assert.match(verdict.issues[0], /Batch CSV/);
});

test("an empty selection stays blocked", () => {
  assert.equal(reviewImportability([]).ok, false);
  assert.equal(reviewImportability([entry({ included: false })]).ok, false);
});

test("a zip is validated through its recognized members", () => {
  const good = reviewImportability([entry({
    name: "bundle.zip",
    format: "zip",
    type: "bundle",
    members: [
      result({ name: "m.xlsx", format: "xlsx", type: "supervisor_master" }),
      result({ name: "d.docx", type: "outreach_draft" }),
    ],
  })]);
  assert.equal(good.ok, true);

  const wrong = reviewImportability([entry({
    name: "bundle.zip",
    format: "zip",
    type: "bundle",
    members: [result({ name: "p.xlsx", format: "xlsx", type: "program_reference", label: "Program research / reference workbook" })],
  })]);
  assert.equal(wrong.ok, false);
  assert.match(wrong.issues.join(" "), /not a supervisor master/);

  const mixed = reviewImportability([
    entry({ name: "bundle.zip", format: "zip", type: "bundle" }),
    entry({ name: "master.xlsx", format: "xlsx", type: "supervisor_master" }),
  ]);
  assert.equal(mixed.ok, false);
  assert.match(mixed.issues.join(" "), /on its own/);
});

test("identity summaries stay compact", () => {
  assert.equal(
    identitySummary(result({ identities: { student: "Shen Hui", addressee: { name: "Tan" } } })),
    "Shen Hui → Tan",
  );
  assert.equal(
    identitySummary(result({
      type: "multi_draft_bundle",
      segments: [{ emails: ["a@example.edu"] }, { emails: [] }],
      identities: { student: "Junhao Jiao" },
    })),
    "2 letters · 1 addressed · Junhao Jiao",
  );
  assert.equal(
    identitySummary(result({
      type: "supervisor_master",
      identities: { row_count: 68, email_count: 63 },
    })),
    "68 supervisor rows · 63 addresses",
  );
  assert.equal(
    identitySummary(result({
      type: "scholar_cv",
      label: typeOption("scholar_cv").label,
      identities: { person: "Pat Example", cv_role: "scholar" },
    })),
    "Pat Example · scholar CV",
  );
});

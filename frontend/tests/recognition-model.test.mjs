import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildImportSelections,
  confidenceTone,
  identitySummary,
  reviewImportability,
  reviewItems,
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
  sha256: "abc",
  ...overrides,
});

const item = ({ included, ...overrides } = {}) => {
  const entry = reviewItems([result(overrides)])[0];
  return included === undefined ? entry : { ...entry, included };
};
const verdict = (entries) => reviewImportability(entries);

test("confidence maps to board tones", () => {
  assert.equal(confidenceTone("high"), "ready");
  assert.equal(confidenceTone("medium"), "waiting");
  assert.equal(confidenceTone("low"), "muted");
});

test("zip archives flatten to member rows tagged with their container", () => {
  const rows = reviewItems([
    result({ name: "Ping Tan.docx", container: "pack.zip" }),
    result({
      name: "导师名单.xlsx", format: "xlsx", type: "supervisor_master",
      label: "Supervisor master list", container: "pack.zip",
    }),
    result({ name: "loose.docx" }),
  ]);
  assert.deepEqual(rows.map((row) => [row.name, row.container, row.key]), [
    ["Ping Tan.docx", "pack.zip", "pack.zip::Ping Tan.docx"],
    ["导师名单.xlsx", "pack.zip", "pack.zip::导师名单.xlsx"],
    ["loose.docx", "", "loose.docx"],
  ]);
  assert.equal(rows[1].included, true);
});

test("a lone document imports without a master and emits an advisory, not a block", () => {
  const v = verdict([item({ name: "Ping Tan.docx" })]);
  assert.equal(v.ok, true);
  assert.equal(v.issues.length, 0);
  assert.match(v.advisories[0], /master list/i);
});

test("one recognized master plus documents imports cleanly", () => {
  const v = verdict([
    item({
      name: "master.xlsx", format: "xlsx", type: "supervisor_master",
      label: "Supervisor master list",
    }),
    item({ name: "Ping Tan.docx" }),
    item({ name: "plan.docx", type: "planning_document", actionable: false, included: false }),
  ]);
  assert.deepEqual(v.issues, []);
  assert.equal(v.ok, true);
  assert.equal(v.advisories.length, 0);
});

test("multiple loose master workbooks are blocked", () => {
  const v = verdict([
    item({ name: "a.xlsx", format: "xlsx", type: "supervisor_master", label: "Supervisor master list" }),
    item({ name: "b.xlsx", format: "xlsx", type: "supervisor_master", label: "Supervisor master list" }),
  ]);
  assert.equal(v.ok, false);
  assert.match(v.issues.join(" "), /one supervisor master/);
});

test("a non-master workbook can ride along as reference", () => {
  const v = verdict([
    item({ name: "Ping Tan.docx" }),
    item({
      name: "track.xlsx", format: "xlsx", type: "tracking_sheet",
      label: "Outreach tracking / template sheet", actionable: false, included: true,
    }),
  ]);
  assert.equal(v.ok, true);
  assert.equal(v.issues.length, 0);
});

test("batch CSV rows stay out of this import workflow", () => {
  const v = verdict([
    item({ name: "batch.csv", format: "csv", type: "bulk_import", label: "Structured outreach batch import" }),
    item({
      name: "master.xlsx", format: "xlsx", type: "supervisor_master",
      label: "Supervisor master list",
    }),
  ]);
  assert.equal(v.ok, false);
  assert.match(v.issues[0], /extension import/);
});

test("unresolved types must be revised before import", () => {
  const v = verdict([
    item({
      name: "weird.docx", type: "unknown", label: "Unrecognized source",
      confidence: "low", actionable: false, included: true,
    }),
  ]);
  assert.equal(v.ok, false);
  assert.match(v.issues[0], /unresolved/);
});

test("an empty selection stays blocked", () => {
  assert.equal(verdict([]).ok, false);
  assert.equal(verdict([item({ included: false })]).ok, false);
});

test("reference-only sets are allowed and clearly advisory", () => {
  const v = verdict([
    item({
      name: "plan.docx", type: "planning_document",
      label: "Application planning document", actionable: false, included: true,
    }),
  ]);
  assert.equal(v.ok, true);
  assert.match(v.advisories[0], /reference material/i);
});

test("import payload groups zip members onto their archive", () => {
  const entries = reviewItems([
    result({ name: "Ping Tan.docx", container: "pack.zip" }),
    result({
      name: "plan.docx", type: "planning_document", actionable: false,
      container: "pack.zip", included: false,
    }),
    result({ name: "loose.docx" }),
  ]).map((entry) => ({ ...entry, size: 10 }));
  const files = new Map([
    ["pack.zip", new File([new Uint8Array([1])], "pack.zip")],
    ["loose.docx", new File([new Uint8Array([2])], "loose.docx")],
  ]);
  const selections = buildImportSelections(entries, files);
  assert.equal(selections.length, 2);
  const archive = selections.find((selection) => selection.file.name === "pack.zip");
  assert.equal(archive.included, true);
  assert.deepEqual(archive.members, [{ name: "Ping Tan.docx" }]);
  const loose = selections.find((selection) => selection.file.name === "loose.docx");
  assert.equal(loose.included, true);
  assert.equal(loose.members, undefined);
});

test("revised member types travel in the archive payload", () => {
  const entries = reviewItems([
    result({ name: "CV.docx", type: "applicant_cv", container: "pack.zip" }),
  ]).map((entry) => ({
    ...entry, size: 10, type: "scholar_cv", included: true, manuallyToggled: true,
  }));
  const files = new Map([["pack.zip", new File([new Uint8Array([1])], "pack.zip")]]);
  const [selection] = buildImportSelections(entries, files);
  assert.deepEqual(selection.members, [{ name: "CV.docx", type: "scholar_cv" }]);
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
      type: "supervisor_master", format: "xlsx",
      identities: { row_count: 68, email_count: 63 },
    })),
    "68 supervisor rows · 63 addresses",
  );
  assert.equal(
    identitySummary(result({
      type: "scholar_cv", label: typeOption("scholar_cv").label,
      identities: { person: "Pat Example", cv_role: "scholar" },
    })),
    "Pat Example · scholar CV",
  );
});

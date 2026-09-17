"""Rewrite with inspectable history: fresh identities and hidden Superseded Preparations."""

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl import Workbook

from smartmail import SmartMail, SmartMailError

ROOT = Path(__file__).resolve().parent.parent

DRAFT_NAME = "Example University_Dr Alex Green.docx"
DEFAULT_ROWS = [["Example University", "Dr Alex Green", "alex@example.edu", ""]]


def master(path, rows, headers=None):
    """Anonymized master list using the inspected workbook's layout."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers or ["大学", "导师", "邮箱📮", "URL"])
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()
    return path


def draft_paragraphs(recipient, salutation, body, note=None):
    """The observed outreach draft layout: Email line, salutation, body, sign-off, internal note."""
    lines = [f"Email: {recipient}", "", "", "", salutation, ""]
    for paragraph in body:
        lines.extend([paragraph, ""])
    lines += ["Yours sincerely,", "Sipei Yao"]
    if note is not None:
        lines += ["", "", "", note]
    return lines


def document(path, paragraphs):
    """Minimal .docx carrying only word/document.xml, as the extractor reads."""
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>' for text in paragraphs
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{namespace}"><w:body>{body}</w:body></w:document>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return path


def bundle(path, members):
    """A .zip import bundle with exactly one master workbook plus other Source Materials."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, item in members:
            archive.write(item, name)
    return path


class RewriteTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "state"
        self.core = SmartMail(self.home)
        self.addCleanup(self.core.__exit__)
        self.campaign = self.core.create_campaign("2027 outreach")
        self.student = self.core.create_student("Test Student", "student@163.com")

    def import_bundle(self, documents, master_rows=None, extra=()):
        rows = master_rows if master_rows is not None else DEFAULT_ROWS
        master_path = master(self.directory / "master.xlsx", rows)
        members = [("master.xlsx", master_path)]
        for index, (name, paragraphs) in enumerate(documents):
            members.append((name, document(self.directory / f"draft-{index}.docx", paragraphs)))
        for name, item in extra:
            members.append((name, item))
        source = bundle(self.directory / "bundle.zip", members)
        return self.core.import_master(self.campaign["id"], self.student["id"], source)

    def draft(self, body):
        return (DRAFT_NAME, draft_paragraphs("alex@example.edu", "Dear Dr Green,", body))

    def first_preparation(self, body=("First version.",)):
        imported = self.import_bundle([self.draft(list(body))])
        preparation_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        return imported, preparation_id

    def revised_source(self, body, extra=()):
        imported = self.import_bundle([self.draft(list(body))], extra=extra)
        return next(s for s in self.core.get_import(imported["id"])["sources"]
                    if s["name"] == DRAFT_NAME)

    def blocking_codes(self, preparation):
        return {f["code"] for f in preparation["readiness_findings"] if f["blocking"]}


class RewriteIdentityTests(RewriteTestCase):
    def test_rewrite_creates_a_fresh_preparation_and_hides_the_replaced_version(self):
        imported, first_id = self.first_preparation()
        self.assertTrue(self.core.set_subject(first_id, "PhD supervision enquiry")["ready"])
        revised = self.revised_source(["Second version."])

        replaced = self.core.rewrite(first_id, source_id=revised["id"])

        self.assertNotEqual(replaced["id"], first_id)
        self.assertEqual(replaced["task_id"], imported["task_ids"][0])
        self.assertIn("Second version.", replaced["body"])
        self.assertIsNone(replaced["superseded_by"])
        self.assertEqual(replaced["status"], "active")
        self.assertIn("missing_subject", self.blocking_codes(replaced))

        self.assertEqual([p["id"] for p in self.core.list_preparations(self.campaign["id"])],
                         [replaced["id"]])

        prior = self.core.get_preparation(first_id)
        self.assertEqual(prior["superseded_by"], replaced["id"])
        self.assertEqual(prior["status"], "superseded")
        self.assertIn("First version.", prior["body"])
        self.assertEqual(prior["subject"], "PhD supervision enquiry")


class HistoryInspectionTests(RewriteTestCase):
    def rewrite_chain(self, bodies=("First version.", "Second version.", "Third version.")):
        imported, first_id = self.first_preparation([bodies[0]])
        ids = [first_id]
        for body in bodies[1:]:
            ids.append(self.core.rewrite(ids[-1], source_id=self.revised_source([body])["id"])["id"])
        return imported, ids

    def test_history_exposes_prior_content_sources_and_transformations(self):
        imported, ids = self.rewrite_chain()

        history = self.core.get_preparation_history(ids[-1])
        self.assertEqual(history["task_id"], imported["task_ids"][0])
        self.assertEqual(history["active_id"], ids[-1])
        self.assertEqual([v["id"] for v in history["versions"]], list(reversed(ids)))
        self.assertEqual([v["status"] for v in history["versions"]],
                         ["active", "superseded", "superseded"])

        oldest = history["versions"][-1]
        self.assertIn("First version.", oldest["body"])
        self.assertEqual(oldest["source"]["name"], DRAFT_NAME)
        self.assertEqual(len(oldest["source"]["sha256"]), 64)
        self.assertEqual(oldest["association"]["supervisor"], "Dr Alex Green")
        self.assertIn("body_restructured", {t["code"] for t in oldest["transformations"]})

    def test_history_is_reachable_from_any_version(self):
        _, ids = self.rewrite_chain(bodies=("First version.", "Second version."))
        self.assertEqual(self.core.get_preparation_history(ids[0]),
                         self.core.get_preparation_history(ids[1]))

    def test_history_for_an_unknown_preparation_is_reported(self):
        with self.assertRaises(SmartMailError):
            self.core.get_preparation_history("unknown")


class ReplacementRequiresRewriteTests(RewriteTestCase):
    def test_a_revised_import_document_is_surfaced_instead_of_replacing_active_work(self):
        imported, first_id = self.first_preparation(["First version."])
        revised = self.import_bundle([self.draft(["Second version."])])

        result = self.core.prepare_from_documents(revised["id"])

        self.assertEqual(result["preparation_ids"], [])
        self.assertEqual(len(result["unassociated_source_ids"]), 1)
        findings = self.core.list_unassociated_documents(revised["id"])
        self.assertEqual([f["code"] for f in findings], ["replacement_requires_rewrite"])
        self.assertTrue(findings[0]["blocking"])
        self.assertIn(first_id, findings[0]["detail"])

        active = self.core.list_preparations(self.campaign["id"])
        self.assertEqual([p["id"] for p in active], [first_id])
        self.assertIn("First version.", self.core.get_preparation(first_id)["body"])

    def test_the_explicit_rewrite_completes_the_replacement_and_clears_the_finding(self):
        imported, first_id = self.first_preparation(["First version."])
        revised = self.import_bundle([self.draft(["Second version."])])
        self.core.prepare_from_documents(revised["id"])
        revised_source = next(s for s in self.core.get_import(revised["id"])["sources"]
                              if s["name"] == DRAFT_NAME)

        replaced = self.core.rewrite(first_id, source_id=revised_source["id"])

        self.assertEqual([p["id"] for p in self.core.list_preparations(self.campaign["id"])],
                         [replaced["id"]])
        self.assertEqual(self.core.list_unassociated_documents(revised["id"]), [])

    def test_a_document_for_a_task_without_active_work_still_prepares(self):
        rows = [["Example University", "Dr Alex Green", "alex@example.edu", ""],
                ["Example University", "Dr Blair Blue", "blair@example.edu", ""]]
        imported = self.import_bundle([self.draft(["First version."])], master_rows=rows)
        first_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]

        revised = self.import_bundle([
            self.draft(["Second version."]),
            ("Example University_Dr Blair Blue.docx",
             draft_paragraphs("blair@example.edu", "Dear Dr Blue,", ["New Blair version."])),
        ], master_rows=rows)
        result = self.core.prepare_from_documents(revised["id"])

        self.assertEqual(len(result["preparation_ids"]), 1)
        created = self.core.get_preparation(result["preparation_ids"][0])
        self.assertIn("New Blair version.", created["body"])
        self.assertEqual([f["code"] for f in self.core.list_unassociated_documents(revised["id"])],
                         ["replacement_requires_rewrite"])
        self.assertEqual(sorted(p["id"] for p in self.core.list_preparations(self.campaign["id"])),
                         sorted([first_id, created["id"]]))


class RewriteValidationTests(RewriteTestCase):
    def test_rewrite_rejects_an_unknown_preparation_or_source(self):
        imported, first_id = self.first_preparation()
        revised = self.revised_source(["Second version."])

        with self.assertRaises(SmartMailError):
            self.core.rewrite("unknown", source_id=revised["id"])
        with self.assertRaises(SmartMailError):
            self.core.rewrite(first_id, source_id="unknown")
        self.assertEqual(self.core.get_preparation(first_id)["status"], "active")

    def test_rewrite_requires_a_draft_describing_the_same_outreach_task(self):
        imported, first_id = self.first_preparation()
        other = self.import_bundle([("Example University_Dr Blair Blue.docx",
                                     draft_paragraphs("blair@example.edu", "Dear Dr Blue,", ["Other."]))])
        other_sources = self.core.get_import(other["id"])["sources"]
        master_source = next(s for s in self.core.get_import(imported["id"])["sources"]
                             if s["name"].endswith(".xlsx"))

        for source in [next(s for s in other_sources if s["name"].endswith("Blair Blue.docx")),
                       master_source]:
            with self.assertRaises(SmartMailError):
                self.core.rewrite(first_id, source_id=source["id"])
        self.assertEqual(self.core.get_preparation(first_id)["status"], "active")

    def test_a_superseded_preparation_cannot_be_rewritten_again(self):
        imported, first_id = self.first_preparation()
        second = self.core.rewrite(first_id, source_id=self.revised_source(["Second version."])["id"])

        with self.assertRaises(SmartMailError):
            self.core.rewrite(first_id, source_id=self.revised_source(["Third version."])["id"])
        self.assertEqual(self.core.get_preparation(second["id"])["status"], "active")

    def test_repeated_rewrite_from_the_same_source_still_produces_a_fresh_identity(self):
        imported, first_id = self.first_preparation()
        source = next(s for s in self.core.get_import(imported["id"])["sources"]
                      if s["name"] == DRAFT_NAME)

        second = self.core.rewrite(first_id, source_id=source["id"])
        third = self.core.rewrite(second["id"], source_id=source["id"])

        self.assertEqual(len({first_id, second["id"], third["id"]}), 3)
        versions = [v["id"] for v in self.core.get_preparation_history(third["id"])["versions"]]
        self.assertEqual(versions, [third["id"], second["id"], first_id])
        self.assertEqual([p["id"] for p in self.core.list_preparations(self.campaign["id"])],
                         [third["id"]])


DECLARATION = "I have attached my CV and would welcome the opportunity to discuss my background."


class RewriteSnapshotTests(RewriteTestCase):
    def cv(self):
        return ("Test Student - CV.docx", document(
            self.directory / "cv.docx", ["Test Student", "E-mail: student@163.com"]))

    def test_rewrite_keeps_the_superseded_attachment_and_gives_the_fresh_one_its_own_slot(self):
        imported = self.import_bundle([self.draft([DECLARATION])], extra=[self.cv()])
        first_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        slot = self.core.get_preparation(first_id)["attachment_slots"][0]
        attachment = self.core.confirm_attachment(first_id, slot["id"])["attachment_slots"][0]["attachment"]
        snapshot = self.core.read_attachment(attachment["id"])

        replaced = self.core.rewrite(
            first_id, source_id=self.revised_source([DECLARATION], extra=[self.cv()])["id"])

        versions = {v["id"]: v for v in self.core.get_preparation_history(replaced["id"])["versions"]}
        prior_attachment = versions[first_id]["attachment_slots"][0]["attachment"]
        self.assertEqual(prior_attachment["sha256"], attachment["sha256"])
        self.assertEqual(self.core.read_attachment(prior_attachment["id"]), snapshot)

        fresh_slot = versions[replaced["id"]]["attachment_slots"][0]
        self.assertEqual(fresh_slot["label"], "Student CV")
        self.assertIsNone(fresh_slot["attachment"])
        self.assertIsNotNone(fresh_slot["suggested_source_id"])

    def test_editing_the_imported_file_after_rewrite_leaves_history_unchanged(self):
        original = self.directory / "Updated CV.pdf"
        original.write_bytes(b"preserved attachment bytes")
        imported = self.import_bundle([self.draft([DECLARATION])])
        first_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        slot = self.core.get_preparation(first_id)["attachment_slots"][0]
        self.core.set_attachment(first_id, slot["id"], path=original)

        replaced = self.core.rewrite(first_id, source_id=self.revised_source([DECLARATION])["id"])
        original.write_bytes(b"edited after import")

        prior = next(v for v in self.core.get_preparation_history(replaced["id"])["versions"]
                     if v["id"] == first_id)
        self.assertEqual(
            self.core.read_attachment(prior["attachment_slots"][0]["attachment"]["id"]),
            b"preserved attachment bytes")


class RewritePersistenceTests(RewriteTestCase):
    def test_active_work_and_history_survive_restart(self):
        imported, first_id = self.first_preparation()
        self.core.set_subject(first_id, "PhD supervision enquiry")
        second = self.core.rewrite(first_id, source_id=self.revised_source(["Second version."])["id"])

        with SmartMail(self.home) as restarted:
            self.assertEqual([p["id"] for p in restarted.list_preparations(self.campaign["id"])],
                             [second["id"]])
            history = restarted.get_preparation_history(second["id"])
            self.assertEqual(history["active_id"], second["id"])
            self.assertEqual([v["id"] for v in history["versions"]], [second["id"], first_id])
            self.assertEqual(history["versions"][-1]["subject"], "PhD supervision enquiry")
            self.assertIn("First version.", history["versions"][-1]["body"])
            self.assertEqual(restarted.get_preparation(first_id)["status"], "superseded")

    def test_superseded_attachment_snapshot_survives_restart(self):
        imported = self.import_bundle([self.draft([DECLARATION])], extra=[(
            "Test Student - CV.docx", document(self.directory / "cv.docx", ["Curriculum vitae"]))])
        first_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        slot = self.core.get_preparation(first_id)["attachment_slots"][0]
        attachment = self.core.confirm_attachment(first_id, slot["id"])["attachment_slots"][0]["attachment"]
        snapshot = self.core.read_attachment(attachment["id"])
        second = self.core.rewrite(
            first_id,
            source_id=self.revised_source(
                [DECLARATION, "Thank you for your consideration."])["id"])

        with SmartMail(self.home) as restarted:
            prior = next(v for v in restarted.get_preparation_history(second["id"])["versions"]
                         if v["id"] == first_id)
            self.assertEqual(restarted.get_preparation(first_id)["status"], "superseded")
            self.assertEqual(
                restarted.read_attachment(prior["attachment_slots"][0]["attachment"]["id"]), snapshot)


class TerminalRewriteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "state-rewrite"

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "smartmail", "--home", str(self.home), *arguments],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def write_bundle(self, body, name):
        master_path = master(self.directory / "master.xlsx", DEFAULT_ROWS)
        docx = document(self.directory / f"{name}.docx",
                        draft_paragraphs("alex@example.edu", "Dear Dr Green,", [body]))
        return bundle(self.directory / f"{name}-bundle.zip",
                      [("master.xlsx", master_path), (DRAFT_NAME, docx)])

    def build_store(self):
        with SmartMail(self.home) as core:
            campaign = core.create_campaign("2027 outreach")
            student = core.create_student("Test Student", "student@163.com")
        first = json.loads(self.run_cli(
            "import", str(self.write_bundle("First version.", "first")),
            "--campaign", campaign["id"], "--student", student["id"]).stdout)
        preparation_id = json.loads(
            self.run_cli("prepare", "--import", first["id"]).stdout)["preparation_ids"][0]
        self.run_cli("preparation", "set-subject", preparation_id, "PhD supervision enquiry")
        return campaign, first, preparation_id

    def test_terminal_rewrites_and_reports_history(self):
        campaign, first, first_id = self.build_store()
        revised = json.loads(self.run_cli(
            "import", str(self.write_bundle("Second version.", "second")),
            "--campaign", campaign["id"], "--student", json.loads(
                self.run_cli("student", "list").stdout)[0]["id"]).stdout)

        again = json.loads(self.run_cli("prepare", "--import", revised["id"]).stdout)
        self.assertEqual(again["preparation_ids"], [])
        findings = json.loads(self.run_cli("imports", "findings", revised["id"]).stdout)
        self.assertEqual([f["code"] for f in findings], ["replacement_requires_rewrite"])
        revised_source = next(
            s for s in json.loads(self.run_cli("imports", "show", revised["id"]).stdout)["sources"]
            if s["name"] == DRAFT_NAME)

        rewritten = self.run_cli("preparation", "rewrite", first_id, "--source", revised_source["id"])
        self.assertEqual(rewritten.returncode, 0, rewritten.stderr)
        replaced = json.loads(rewritten.stdout)
        self.assertNotEqual(replaced["id"], first_id)
        self.assertIn("Second version.", replaced["body"])

        listed = json.loads(self.run_cli("preparation", "list", "--campaign", campaign["id"]).stdout)
        self.assertEqual([p["id"] for p in listed], [replaced["id"]])

        history = json.loads(self.run_cli("preparation", "history", replaced["id"]).stdout)
        self.assertEqual(history["active_id"], replaced["id"])
        self.assertEqual([v["id"] for v in history["versions"]], [replaced["id"], first_id])
        self.assertEqual(history["versions"][-1]["subject"], "PhD supervision enquiry")

    def test_terminal_reports_an_unknown_source_on_rewrite(self):
        campaign, first, first_id = self.build_store()
        failed = self.run_cli("preparation", "rewrite", first_id, "--source", "unknown")
        self.assertEqual(failed.returncode, 2)
        self.assertIn("error", json.loads(failed.stderr))
        self.assertEqual(
            [p["id"] for p in json.loads(
                self.run_cli("preparation", "list", "--campaign", campaign["id"]).stdout)],
            [first_id])


if __name__ == "__main__":
    unittest.main()

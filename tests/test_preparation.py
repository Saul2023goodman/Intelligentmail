import inspect
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


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "state"
        self.core = SmartMail(self.home)
        self.addCleanup(self.core.__exit__)
        self.campaign = self.core.create_campaign("2027 outreach")
        self.student = self.core.create_student("Test Student", "student@163.com")

    def import_bundle(self, master_rows, documents, headers=None):
        master_path = master(self.directory / "master.xlsx", master_rows, headers=headers)
        members = [("master.xlsx", master_path)]
        for name, paragraphs in documents:
            docx = document(self.directory / f"{len(members)}.docx", paragraphs)
            members.append((name, docx))
        source = bundle(self.directory / "bundle.zip", members)
        return self.core.import_master(self.campaign["id"], self.student["id"], source)

    def test_draft_document_associates_to_task_and_produces_preparation(self):
        body = [
            "I hope this email finds you well.",
            "I am writing to ask about PhD supervision.",
        ]
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", body,
            ))],
        )
        result = self.core.prepare_from_documents(imported["id"])
        self.assertEqual(len(result["preparation_ids"]), 1)

        preparation = self.core.get_preparation(result["preparation_ids"][0])
        self.assertEqual(preparation["task_id"], imported["task_ids"][0])
        self.assertEqual(preparation["sender"], "student@163.com")
        self.assertEqual(preparation["recipient"], "alex@example.edu")
        self.assertEqual(preparation["subject"], "")
        self.assertEqual(
            preparation["body"],
            "Dear Dr Green,\n\nI hope this email finds you well.\n\n"
            "I am writing to ask about PhD supervision.\n\nYours sincerely,\nSipei Yao",
        )
        self.assertEqual(preparation["source"]["name"], "Example University_Dr Alex Green.docx")
        self.assertEqual(self.core.list_preparations(self.campaign["id"])[0]["id"], preparation["id"])

    def test_internal_research_note_is_separated_and_recorded(self):
        note = "Research source: Example University profile — https://example.edu/alex"
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", ["Hello."], note=note,
            ))],
        )
        preparation = self.core.get_preparation(
            self.core.prepare_from_documents(imported["id"])["preparation_ids"][0])
        self.assertEqual(
            preparation["body"], "Dear Dr Green,\n\nHello.\n\nYours sincerely,\nSipei Yao")
        self.assertEqual(preparation["internal_note"], note)
        self.assertEqual(preparation["association"]["source"], "Example University_Dr Alex Green.docx")
        self.assertEqual(
            {t["code"] for t in preparation["transformations"]},
            {"recipient_extracted", "body_restructured", "internal_note_separated"},
        )

    def test_missing_subject_blocks_readiness_without_invented_content(self):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", ["Hello."],
            ))],
        )
        preparation = self.core.get_preparation(
            self.core.prepare_from_documents(imported["id"])["preparation_ids"][0])
        self.assertEqual(preparation["subject"], "")
        self.assertIn("missing_subject", self.blocking_codes(preparation))
        self.assertFalse(preparation["ready"])

    def test_draft_recipient_conflicting_with_recorded_address_blocks_readiness(self):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "recorded@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "draft@example.edu", "Dear Dr Green,", ["Hello."],
            ))],
        )
        preparation = self.core.get_preparation(
            self.core.prepare_from_documents(imported["id"])["preparation_ids"][0])
        self.assertEqual(preparation["recipient"], "draft@example.edu")
        self.assertIn("recipient_conflict", self.blocking_codes(preparation))
        self.assertFalse(preparation["ready"])

    def test_draft_recipient_fills_a_missing_master_address_without_conflict(self):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "https://example.edu/people/alex", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", ["Hello."],
            ))],
        )
        preparation = self.core.get_preparation(
            self.core.prepare_from_documents(imported["id"])["preparation_ids"][0])
        self.assertEqual(preparation["recipient"], "alex@example.edu")
        self.assertNotIn("recipient_conflict", {f["code"] for f in preparation["readiness_findings"]})
        self.assertIn("recipient_filled_missing_address",
                      {t["code"] for t in preparation["transformations"]})

    def test_local_part_case_difference_is_not_a_recipient_conflict(self):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "Alex.Green@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex.green@example.edu", "Dear Dr Green,", ["Hello."],
            ))],
        )
        preparation = self.core.get_preparation(
            self.core.prepare_from_documents(imported["id"])["preparation_ids"][0])
        self.assertEqual(preparation["recipient"], "alex.green@example.edu")
        self.assertNotIn("recipient_conflict", {f["code"] for f in preparation["readiness_findings"]})

    def test_unusable_draft_recipient_blocks_readiness(self):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "not-an-address", "Dear Dr Green,", ["Hello."],
            ))],
        )
        preparation = self.core.get_preparation(
            self.core.prepare_from_documents(imported["id"])["preparation_ids"][0])
        self.assertIn("invalid_recipient", self.blocking_codes(preparation))
        self.assertFalse(preparation["ready"])

    def test_identity_conflict_on_the_task_blocks_readiness(self):
        imported = self.import_bundle(
            [["University", "Alex Green", "a@example.edu", ""]],
            [("University_Alex Green.docx", draft_paragraphs(
                "a@example.edu", "Dear Alex Green,", ["Hello."],
            ))],
        )
        other = self.core.create_student("Other Student", "other@163.com")
        master(self.directory / "other.xlsx", [["University", "Alex Green", "b@example.edu", ""]])
        self.core.import_master(self.campaign["id"], other["id"], self.directory / "other.xlsx")

        preparation = self.core.get_preparation(
            self.core.prepare_from_documents(imported["id"])["preparation_ids"][0])
        self.assertIn("identity_conflict", self.blocking_codes(preparation))
        self.assertFalse(preparation["ready"])

    def blocking_codes(self, preparation):
        return {f["code"] for f in preparation["readiness_findings"] if f["blocking"]}

    def test_draft_matching_no_task_surfaces_a_document_exception(self):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Other University_Dr Nobody.docx", draft_paragraphs(
                "nobody@example.edu", "Dear Dr Nobody,", ["Hello."],
            ))],
        )
        result = self.core.prepare_from_documents(imported["id"])
        self.assertEqual(result["preparation_ids"], [])
        self.assertEqual(len(result["unassociated_source_ids"]), 1)
        findings = self.core.list_unassociated_documents(imported["id"])
        self.assertEqual(findings[0]["code"], "unassociated_document")
        self.assertTrue(findings[0]["blocking"])
        self.assertEqual(findings[0]["source"]["name"], "Other University_Dr Nobody.docx")
        self.assertEqual(len(self.core.list_tasks(self.campaign["id"])), 1)
        self.assertEqual(self.core.list_preparations(self.campaign["id"]), [])

    def test_non_draft_document_is_preserved_but_not_prepared(self):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", ["Hello."],
            )),
             ("Sipei Yao - CV.docx", ["Sipei Yao", "E-mail: student@163.com | Tel: 123"])],
        )
        result = self.core.prepare_from_documents(imported["id"])
        self.assertEqual(len(result["preparation_ids"]), 1)
        self.assertEqual(self.core.list_unassociated_documents(imported["id"]), [])

    def test_malformed_document_surfaces_an_exception(self):
        master_path = master(
            self.directory / "master.xlsx",
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]])
        broken = self.directory / "broken.docx"
        broken.write_bytes(b"not a zip archive")
        source = bundle(self.directory / "bundle.zip", [
            ("master.xlsx", master_path), ("Broken University_X.docx", broken)])
        imported = self.core.import_master(self.campaign["id"], self.student["id"], source)
        result = self.core.prepare_from_documents(imported["id"])
        self.assertEqual(result["preparation_ids"], [])
        findings = self.core.list_unassociated_documents(imported["id"])
        self.assertEqual([f["code"] for f in findings], ["unsupported_document"])
        self.assertTrue(findings[0]["blocking"])

    def test_repeat_preparation_does_not_duplicate_document_findings(self):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Other University_Dr Nobody.docx", draft_paragraphs(
                "nobody@example.edu", "Dear Dr Nobody,", ["Hello."],
            ))],
        )
        self.core.prepare_from_documents(imported["id"])
        self.core.prepare_from_documents(imported["id"])
        self.assertEqual(len(self.core.list_unassociated_documents(imported["id"])), 1)

    def test_preparation_survives_restart(self):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", ["Hello."],
            ))],
        )
        preparation_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        with SmartMail(self.home) as restarted:
            self.assertEqual(restarted.get_preparation(preparation_id)["recipient"], "alex@example.edu")

    def test_repeat_preparation_reuses_identity_without_duplication(self):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", ["Hello."],
            ))],
        )
        first = self.core.prepare_from_documents(imported["id"])
        second = self.core.prepare_from_documents(imported["id"])
        self.assertEqual(first["preparation_ids"], second["preparation_ids"])
        self.assertEqual(len(self.core.list_preparations(self.campaign["id"])), 1)

    def test_preview_exposes_the_full_local_message(self):
        note = "Research source: Example University profile — https://example.edu/alex"
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", ["Hello."], note=note,
            ))],
        )
        preparation_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        preview = self.core.preview_preparation(preparation_id)
        self.assertEqual(preview["sender"], "student@163.com")
        self.assertEqual(preview["recipient"], "alex@example.edu")
        self.assertEqual(preview["subject"], "")
        self.assertIn("Dear Dr Green,", preview["text"])
        self.assertIn("Yours sincerely,", preview["text"])
        self.assertNotIn("Research source", preview["text"])
        self.assertEqual(preview["internal_note"], note)
        summary = self.core.list_preparations(self.campaign["id"])[0]
        self.assertEqual(summary["blocking_count"], 1)

    def test_preparation_is_local_and_modifies_no_source_bytes(self):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", ["Hello."],
            ))],
        )
        document_source = next(
            source for source in self.core.get_import(imported["id"])["sources"]
            if source["name"].endswith(".docx"))
        original = self.core.read_source(document_source["id"])
        self.core.prepare_from_documents(imported["id"])
        self.assertEqual(self.core.read_source(document_source["id"]), original)
        self.assertEqual(list(inspect.signature(SmartMail.__init__).parameters), ["self", "home"])


class TerminalPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "state"

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "smartmail", "--home", str(self.home), *arguments],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def build_store(self):
        with SmartMail(self.home) as core:
            campaign = core.create_campaign("2027 outreach")
            student = core.create_student("Test Student", "student@163.com")
            master_path = master(
                self.directory / "master.xlsx",
                [["Example University", "Dr Alex Green", "alex@example.edu", ""]])
            docx = document(self.directory / "draft.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", ["Hello."], note="Research source: X — https://x"))
            source = bundle(self.directory / "bundle.zip", [
                ("master.xlsx", master_path), ("Example University_Dr Alex Green.docx", docx)])
            imported = core.import_master(campaign["id"], student["id"], source)
        return campaign, imported

    def test_terminal_prepares_lists_shows_previews_and_reports_findings(self):
        campaign, imported = self.build_store()
        prepared = self.run_cli("prepare", "--import", imported["id"])
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        preparation_id = json.loads(prepared.stdout)["preparation_ids"][0]

        listed = self.run_cli("preparation", "list", "--campaign", campaign["id"])
        self.assertEqual(json.loads(listed.stdout)[0]["id"], preparation_id)

        shown = self.run_cli("preparation", "show", preparation_id)
        self.assertIn("missing_subject",
                      [finding["code"] for finding in json.loads(shown.stdout)["readiness_findings"]])

        previewed = self.run_cli("preparation", "preview", preparation_id)
        self.assertEqual(previewed.returncode, 0, previewed.stderr)
        self.assertIn("Dear Dr Green,", previewed.stdout)
        self.assertNotIn("Research source", previewed.stdout)

        findings = self.run_cli("imports", "findings", imported["id"])
        self.assertEqual(json.loads(findings.stdout), [])

    def test_terminal_reports_an_unknown_import(self):
        failed = self.run_cli("prepare", "--import", "unknown")
        self.assertEqual(failed.returncode, 2)
        self.assertIn("error", json.loads(failed.stderr))


if __name__ == "__main__":
    unittest.main()

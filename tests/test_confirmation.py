"""Confirmation: reviewing and binding an exact Preparation before any execution."""

import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl import Workbook

from smartmail import SmartMail, SmartMailError

DRAFT_NAME = "Example University_Dr Alex Green.docx"
DEFAULT_ROWS = [["Example University", "Dr Alex Green", "alex@example.edu", ""]]
DECLARATION = "I have attached my CV and would welcome the opportunity to discuss my background."
SUBJECT = "PhD supervision enquiry"


def master(path, rows, headers=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers or ["大学", "导师", "邮箱📮", "URL"])
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()
    return path


def draft_paragraphs(recipient, salutation, body, note=None):
    lines = [f"Email: {recipient}", "", "", "", salutation, ""]
    for paragraph in body:
        lines.extend([paragraph, ""])
    lines += ["Yours sincerely,", "Sipei Yao"]
    if note is not None:
        lines += ["", "", "", note]
    return lines


def document(path, paragraphs):
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
    with zipfile.ZipFile(path, "w") as archive:
        for name, item in members:
            archive.write(item, name)
    return path


class ConfirmationTestCase(unittest.TestCase):
    rows = DEFAULT_ROWS

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
        rows = master_rows if master_rows is not None else self.rows
        master_path = master(self.directory / "master.xlsx", rows)
        members = [("master.xlsx", master_path)]
        for index, (name, paragraphs) in enumerate(documents):
            members.append((name, document(self.directory / f"draft-{index}.docx", paragraphs)))
        for name, item in extra:
            members.append((name, item))
        source = bundle(self.directory / "bundle.zip", members)
        return self.core.import_master(self.campaign["id"], self.student["id"], source)

    def cv(self):
        content = ["Test Student", "E-mail: student@163.com"]
        path = document(self.directory / "cv.docx", content)
        return ("Test Student - CV.docx", path), path.read_bytes()

    def first_preparation(self, body=(DECLARATION,), attach=True, subject=SUBJECT):
        (cv_name, cv_path), cv_bytes = self.cv()
        imported = self.import_bundle(
            [(DRAFT_NAME, draft_paragraphs("alex@example.edu", "Dear Dr Green,", list(body)))],
            extra=[(cv_name, cv_path)])
        preparation_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        if subject is not None:
            self.core.set_subject(preparation_id, subject)
        if attach:
            slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
            self.core.confirm_attachment(preparation_id, slot["id"])
        return self.core.get_preparation(preparation_id), cv_bytes

    def blocking_codes(self, preparation):
        return {f["code"] for f in preparation["readiness_findings"] if f["blocking"]}


class ReviewTests(ConfirmationTestCase):
    def test_review_exposes_the_exact_message_and_attachment_contents(self):
        preparation, cv_bytes = self.first_preparation()

        review = self.core.review_confirmation(preparation["id"])

        self.assertEqual(review["sender"], "student@163.com")
        self.assertEqual(review["recipient"], "alex@example.edu")
        self.assertEqual(review["subject"], SUBJECT)
        self.assertEqual(review["execution"], {"kind": "immediate"})
        self.assertTrue(review["ready"])
        self.assertFalse(review["already_sent"])
        self.assertIsNone(review["confirmation_id"])

        self.assertEqual([a["name"] for a in review["attachments"]], ["Test Student - CV.docx"])
        attachment = review["attachments"][0]
        self.assertEqual(len(attachment["sha256"]), 64)
        self.assertEqual(attachment["size"], len(cv_bytes))
        self.assertEqual(self.core.read_attachment(attachment["id"]), cv_bytes)

        self.assertIn("Dear Dr Green,", review["message"])
        self.assertIn(SUBJECT, review["message"])
        self.assertIn("To: alex@example.edu", review["message"])

    def test_review_reports_blocking_findings_for_an_unready_preparation(self):
        preparation, _ = self.first_preparation(subject=None)

        review = self.core.review_confirmation(preparation["id"])

        self.assertFalse(review["ready"])
        self.assertIn("missing_subject", {f["code"] for f in review["readiness_findings"]})

    def test_review_of_an_unknown_preparation_is_reported(self):
        with self.assertRaises(SmartMailError):
            self.core.review_confirmation("unknown")


class ConfirmTests(ConfirmationTestCase):
    def two_ready_preparations(self):
        rows = [["Example University", "Dr Alex Green", "alex@example.edu", ""],
                ["Example University", "Dr Blair Blue", "blair@example.edu", ""]]
        (cv_name, cv_path), _ = self.cv()
        imported = self.import_bundle([
            (DRAFT_NAME, draft_paragraphs("alex@example.edu", "Dear Dr Green,", [DECLARATION])),
            ("Example University_Dr Blair Blue.docx",
             draft_paragraphs("blair@example.edu", "Dear Dr Blue,", [DECLARATION])),
        ], master_rows=rows, extra=[(cv_name, cv_path)])
        ids = self.core.prepare_from_documents(imported["id"])["preparation_ids"]
        for preparation_id in ids:
            self.core.set_subject(preparation_id, SUBJECT)
        return ids

    def revised_source(self, body=(DECLARATION,)):
        imported = self.import_bundle(
            [(DRAFT_NAME, draft_paragraphs("alex@example.edu", "Dear Dr Green,", list(body)))])
        return next(s for s in self.core.get_import(imported["id"])["sources"]
                    if s["name"] == DRAFT_NAME)

    def test_confirm_binds_the_exact_preparation_and_its_attachments(self):
        preparation, _ = self.first_preparation()

        confirmation = self.core.confirm(preparation["id"])

        self.assertEqual(confirmation["preparation_id"], preparation["id"])
        self.assertEqual(confirmation["task_id"], preparation["task_id"])
        self.assertEqual(confirmation["status"], "active")
        self.assertEqual(confirmation["execution"], {"kind": "immediate"})
        self.assertEqual(len(confirmation["content_digest"]), 64)
        self.assertEqual(len(confirmation["attachments_digest"]), 64)
        self.assertEqual(self.core.get_confirmation(confirmation["id"]), confirmation)
        self.assertEqual([c["id"] for c in self.core.list_confirmations(self.campaign["id"])],
                         [confirmation["id"]])
        self.assertEqual(self.core.review_confirmation(preparation["id"])["confirmation_id"],
                         confirmation["id"])

    def test_confirm_refuses_an_unready_preparation(self):
        preparation, _ = self.first_preparation(subject=None)

        with self.assertRaisesRegex(SmartMailError, "missing_subject"):
            self.core.confirm(preparation["id"])

        self.assertEqual(self.core.list_confirmations(self.campaign["id"]), [])

    def test_confirm_is_idempotent_and_renews_after_a_content_change(self):
        preparation, _ = self.first_preparation()

        first = self.core.confirm(preparation["id"])
        self.assertEqual(self.core.confirm(preparation["id"])["id"], first["id"])

        self.core.set_subject(preparation["id"], "A revised subject")
        renewed = self.core.confirm(preparation["id"])

        self.assertNotEqual(renewed["id"], first["id"])
        self.assertEqual(self.core.get_confirmation(first["id"])["status"], "invalidated")
        self.assertEqual(self.core.get_confirmation(first["id"])["invalidated_reason"], "renewed")
        self.assertEqual([c["id"] for c in self.core.list_confirmations(self.campaign["id"])],
                         [renewed["id"]])

    def test_batch_confirm_returns_one_confirmation_per_preparation(self):
        ids = self.two_ready_preparations()

        confirmations = self.core.confirm_preparations(ids)

        self.assertEqual([c["preparation_id"] for c in confirmations], ids)
        self.assertEqual(len({c["id"] for c in confirmations}), 2)
        self.assertEqual({c["id"] for c in self.core.list_confirmations(self.campaign["id"])},
                         {c["id"] for c in confirmations})

    def test_confirm_refuses_a_superseded_preparation(self):
        preparation, _ = self.first_preparation()
        superseded_id = preparation["id"]
        self.core.rewrite(superseded_id, source_id=self.revised_source(["Second version."])["id"])

        with self.assertRaises(SmartMailError):
            self.core.confirm(superseded_id)

    def test_confirm_and_read_back_a_confirmation_by_unknown_id_is_reported(self):
        with self.assertRaises(SmartMailError):
            self.core.get_confirmation("unknown")
        with self.assertRaises(SmartMailError):
            self.core.confirm("unknown")


if __name__ == "__main__":
    unittest.main()

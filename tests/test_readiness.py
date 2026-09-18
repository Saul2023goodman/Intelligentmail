"""Resolving readiness Exceptions, field corrections and advisory attachments."""

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


class ReadinessTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "state"
        self.core = SmartMail(self.home)
        self.addCleanup(self.core.__exit__)
        self.campaign = self.core.create_campaign("2027 outreach")
        self.student = self.core.create_student("Test Student", "student@163.com")

    def import_bundle(self, master_rows, documents, headers=None, extra=()):
        master_path = master(self.directory / "master.xlsx", master_rows, headers=headers)
        members = [("master.xlsx", master_path)]
        for name, paragraphs in documents:
            docx = document(self.directory / f"{len(members)}.docx", paragraphs)
            members.append((name, docx))
        for name, item in extra:
            members.append((name, item))
        source = bundle(self.directory / "bundle.zip", members)
        return self.core.import_master(self.campaign["id"], self.student["id"], source)

    def blocking_codes(self, preparation):
        return {f["code"] for f in preparation["readiness_findings"] if f["blocking"]}


class ExceptionInspectionTests(ReadinessTestCase):
    def test_blocking_exceptions_are_listed_with_source_evidence_and_findings(self):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "https://example.edu/people/alex", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", ["Hello."],
            ))],
        )
        preparation_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]

        exceptions = self.core.list_exceptions(self.campaign["id"])
        self.assertEqual(len(exceptions), 1)
        exception = exceptions[0]
        self.assertEqual(exception["code"], "invalid_recipient")
        self.assertTrue(exception["blocking"])
        self.assertEqual(exception["task_id"], imported["task_ids"][0])
        self.assertEqual(exception["supervisor_name"], "Dr Alex Green")
        self.assertEqual(exception["source"]["name"], "master.xlsx")
        self.assertEqual(len(exception["source"]["sha256"]), 64)

        self.assertEqual(self.core.get_exception(exception["id"]), exception)

        preparation = self.core.get_preparation(preparation_id)
        self.assertEqual(exception["readiness_findings"], preparation["readiness_findings"])
        self.assertEqual([f["code"] for f in exception["readiness_findings"]], ["missing_subject"])

    def test_unknown_exception_is_reported_as_an_operator_error(self):
        with self.assertRaises(SmartMailError):
            self.core.get_exception("unknown")


class SubjectCorrectionTests(ReadinessTestCase):
    def prepare(self):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", ["Hello."],
            ))],
        )
        return self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]

    def test_supplying_a_subject_clears_the_blocking_finding(self):
        preparation_id = self.prepare()
        self.assertFalse(self.core.get_preparation(preparation_id)["ready"])

        corrected = self.core.set_subject(preparation_id, "  PhD supervision enquiry  ")
        self.assertEqual(corrected["subject"], "PhD supervision enquiry")
        self.assertTrue(corrected["ready"])
        self.assertEqual(corrected["readiness_findings"], [])
        self.assertEqual(corrected["corrections"],
                         [{"field": "subject", "value": "PhD supervision enquiry", "prior": ""}])
        self.assertEqual(corrected["body"], self.core.get_preparation(preparation_id)["body"])

        with SmartMail(self.home) as restarted:
            self.assertEqual(restarted.get_preparation(preparation_id)["subject"],
                             "PhD supervision enquiry")

    def test_a_blank_subject_is_rejected_without_changing_the_preparation(self):
        preparation_id = self.prepare()
        for value in ["", "   "]:
            with self.assertRaises(SmartMailError):
                self.core.set_subject(preparation_id, value)
        self.assertEqual(self.core.get_preparation(preparation_id)["subject"], "")
        self.assertIn("missing_subject", self.blocking_codes(self.core.get_preparation(preparation_id)))


class RecipientCorrectionTests(ReadinessTestCase):
    def prepare(self, recorded, declared):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", recorded, ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                declared, "Dear Dr Green,", ["Hello."],
            ))],
        )
        return self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]

    def test_correcting_the_recipient_to_a_recorded_address_clears_the_conflict(self):
        preparation_id = self.prepare("recorded@example.edu", "draft@example.edu")
        self.assertIn("recipient_conflict", self.blocking_codes(self.core.get_preparation(preparation_id)))

        corrected = self.core.set_recipient(preparation_id, "Recorded@Example.edu")
        self.assertEqual(corrected["recipient"], "Recorded@example.edu")
        self.assertEqual(self.blocking_codes(corrected), {"missing_subject"})
        self.assertEqual(corrected["corrections"],
                         [{"field": "recipient", "value": "Recorded@example.edu",
                           "prior": "draft@example.edu"}])

    def test_correcting_an_unusable_recipient_records_the_operator_value(self):
        preparation_id = self.prepare("recorded@example.edu", "not-an-address")
        self.assertIn("invalid_recipient", self.blocking_codes(self.core.get_preparation(preparation_id)))

        corrected = self.core.set_recipient(preparation_id, "recorded@example.edu")
        self.assertEqual(corrected["recipient"], "recorded@example.edu")
        self.assertNotIn("invalid_recipient", self.blocking_codes(corrected))

    def test_a_correction_that_still_conflicts_stays_blocking_without_guessing(self):
        preparation_id = self.prepare("recorded@example.edu", "draft@example.edu")
        corrected = self.core.set_recipient(preparation_id, "unrecorded@example.edu")
        self.assertEqual(corrected["recipient"], "unrecorded@example.edu")
        self.assertIn("recipient_conflict", self.blocking_codes(corrected))
        self.assertFalse(corrected["ready"])

    def test_an_unusable_correction_is_rejected_without_changing_the_preparation(self):
        preparation_id = self.prepare("recorded@example.edu", "draft@example.edu")
        for value in ["not-an-address", "", "  "]:
            with self.assertRaises(SmartMailError):
                self.core.set_recipient(preparation_id, value)
        self.assertEqual(self.core.get_preparation(preparation_id)["recipient"], "draft@example.edu")


DECLARATION = "I have attached my CV and would welcome the opportunity to discuss my background."


class AttachmentSuggestionTests(ReadinessTestCase):
    def cv(self, name):
        return name, document(self.directory / f"cv-{len(name)}.docx",
                              ["Test Student", "E-mail: student@163.com"])

    def prepare(self, body, extra=(), documents=None):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            documents or [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", body,
            ))],
            extra=extra,
        )
        return self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]

    def test_a_declared_attachment_creates_an_advisory_slot_with_the_best_candidate(self):
        preparation_id = self.prepare([DECLARATION], extra=[self.cv("Test Student - CV.docx")])
        preparation = self.core.get_preparation(preparation_id)

        self.assertEqual(len(preparation["attachment_slots"]), 1)
        slot = preparation["attachment_slots"][0]
        self.assertEqual(slot["label"], "Student CV")
        self.assertIn("I have attached my CV", slot["basis"])
        self.assertIsNone(slot["attachment"])
        self.assertEqual([c["name"] for c in slot["candidates"]], ["Test Student - CV.docx"])
        self.assertEqual(slot["suggested_source_id"], slot["candidates"][0]["id"])
        self.assertEqual(len(slot["candidates"][0]["sha256"]), 64)
        self.assertEqual(self.blocking_codes(preparation), {"missing_subject"})

    def test_no_declaration_creates_no_slot(self):
        preparation_id = self.prepare(["I hope this email finds you well."],
                                      extra=[self.cv("Test Student - CV.docx")])
        preparation = self.core.get_preparation(preparation_id)
        self.assertEqual(preparation["attachment_slots"], [])
        self.assertEqual(self.blocking_codes(preparation), {"missing_subject"})

    def test_several_matching_files_are_surfaced_without_a_single_suggestion(self):
        preparation_id = self.prepare([DECLARATION], extra=[
            self.cv("Test Student - CV.docx"), self.cv("Test Student - Academic CV.docx")])
        slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
        self.assertEqual([c["name"] for c in slot["candidates"]],
                         ["Test Student - CV.docx", "Test Student - Academic CV.docx"])
        self.assertIsNone(slot["suggested_source_id"])

    def test_missing_candidate_leaves_the_slot_empty_and_readiness_unchanged(self):
        preparation_id = self.prepare([DECLARATION])
        preparation = self.core.get_preparation(preparation_id)
        self.assertEqual([c for c in preparation["attachment_slots"][0]["candidates"]], [])
        self.assertIsNone(preparation["attachment_slots"][0]["suggested_source_id"])
        self.assertEqual(self.blocking_codes(preparation), {"missing_subject"})

    def test_repeating_preparation_refreshes_suggestions_without_duplicating_slots(self):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", [DECLARATION]))],
            extra=[self.cv("Test Student - CV.docx")],
        )
        first = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        self.core.prepare_from_documents(imported["id"])
        self.core.suggest_attachment_slots(first)
        slots = self.core.get_preparation(first)["attachment_slots"]
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0]["suggested_source_id"], slots[0]["candidates"][0]["id"])


class AttachmentConfirmationTests(ReadinessTestCase):
    def prepare(self, extra=()):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", [DECLARATION]))],
            extra=extra,
        )
        return self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]

    def cv(self):
        return ("Test Student - CV.docx", document(
            self.directory / "cv.docx", ["Test Student", "E-mail: student@163.com"]))

    def test_confirming_the_suggested_candidate_preserves_the_source_bytes(self):
        preparation_id = self.prepare(extra=[self.cv()])
        slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
        self.assertIsNone(slot["attachment"])

        confirmed = self.core.confirm_attachment(preparation_id, slot["id"])
        confirmed_slot = confirmed["attachment_slots"][0]
        attachment = confirmed_slot["attachment"]
        source = slot["candidates"][0]
        self.assertEqual(attachment["name"], "Test Student - CV.docx")
        self.assertEqual(attachment["sha256"], source["sha256"])
        self.assertEqual(self.core.read_attachment(attachment["id"]),
                         self.core.read_source(source["id"]))
        self.assertEqual(confirmed["corrections"],
                         [{"field": "attachment:Student CV", "value": "Test Student - CV.docx",
                           "prior": ""}])
        self.assertEqual(self.blocking_codes(confirmed), {"missing_subject"})

        with SmartMail(self.home) as restarted:
            self.assertEqual(restarted.get_preparation(preparation_id)["attachment_slots"][0]
                             ["attachment"]["sha256"], source["sha256"])

    def test_replacing_with_a_preserved_source_keeps_the_new_bytes_verbatim(self):
        other = ("Archive CV.docx", document(
            self.directory / "other.docx", ["Test Student", "An older document"]))
        preparation_id = self.prepare(extra=[self.cv(), other])
        slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
        first = next(c for c in slot["candidates"] if c["name"] == "Test Student - CV.docx")
        alternative = next(c for c in slot["candidates"] if c["name"] == "Archive CV.docx")
        self.core.set_attachment(preparation_id, slot["id"], source_id=first["id"])

        replaced = self.core.set_attachment(preparation_id, slot["id"], source_id=alternative["id"])
        attachment = replaced["attachment_slots"][0]["attachment"]
        self.assertEqual(attachment["name"], "Archive CV.docx")
        self.assertEqual(self.core.read_attachment(attachment["id"]),
                         self.core.read_source(alternative["id"]))
        self.assertEqual(replaced["corrections"][-1],
                         {"field": "attachment:Student CV", "value": "Archive CV.docx",
                          "prior": "Test Student - CV.docx"})

    def test_importing_a_file_preserves_its_exact_bytes(self):
        preparation_id = self.prepare()
        slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
        original = self.directory / "Updated CV.pdf"
        original.write_bytes(b"%PDF-1.4 preserved attachment bytes\x00\xff")

        imported = self.core.set_attachment(preparation_id, slot["id"], path=original)
        attachment = imported["attachment_slots"][0]["attachment"]
        self.assertEqual(attachment["name"], "Updated CV.pdf")
        self.assertEqual(self.core.read_attachment(attachment["id"]),
                         b"%PDF-1.4 preserved attachment bytes\x00\xff")
        original.write_bytes(b"edited after import")

        with SmartMail(self.home) as restarted:
            self.assertEqual(restarted.read_attachment(attachment["id"]),
                             b"%PDF-1.4 preserved attachment bytes\x00\xff")

    def test_confirming_without_a_single_suggestion_is_rejected(self):
        preparation_id = self.prepare(extra=[self.cv(),
                                             ("Test Student - Academic CV.docx", document(
                                                 self.directory / "cv2.docx",
                                                 ["Test Student", "A second document"]))])
        slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
        self.assertIsNone(slot["suggested_source_id"])
        with self.assertRaises(SmartMailError):
            self.core.confirm_attachment(preparation_id, slot["id"])

    def test_an_attachment_argument_must_name_exactly_one_file(self):
        preparation_id = self.prepare(extra=[self.cv()])
        slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
        for arguments in [{}, {"source_id": slot["candidates"][0]["id"],
                               "path": self.directory / "cv.docx"}]:
            with self.assertRaises(SmartMailError):
                self.core.set_attachment(preparation_id, slot["id"], **arguments)


class AttachmentSlotManagementTests(ReadinessTestCase):
    def prepare(self, extra=()):
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", [DECLARATION]))],
            extra=extra,
        )
        return self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]

    def test_an_operator_can_add_a_slot_with_an_imported_file(self):
        preparation_id = self.prepare()
        transcript = self.directory / "Transcript.pdf"
        transcript.write_bytes(b"transcript bytes")

        added = self.core.add_attachment_slot(preparation_id, "  Transcript  ", path=transcript)
        self.assertEqual([s["label"] for s in added["attachment_slots"]], ["Student CV", "Transcript"])
        slot = added["attachment_slots"][1]
        self.assertEqual(slot["declared"], "Transcript")
        self.assertIn("Added by the operator", slot["basis"])
        self.assertEqual(slot["attachment"]["name"], "Transcript.pdf")
        self.assertEqual(self.core.read_attachment(slot["attachment"]["id"]), b"transcript bytes")

    def test_an_operator_can_add_an_empty_slot_and_remove_any_slot(self):
        preparation_id = self.prepare()
        added = self.core.add_attachment_slot(preparation_id, "Portfolio")
        self.assertEqual(added["attachment_slots"][1]["attachment"], None)

        empty_slot = added["attachment_slots"][1]
        removed = self.core.remove_attachment_slot(preparation_id, empty_slot["id"])
        self.assertEqual([s["label"] for s in removed["attachment_slots"]], ["Student CV"])

    def test_removing_a_slot_discards_its_confirmed_attachment(self):
        preparation_id = self.prepare(extra=[("Test Student - CV.docx", document(
            self.directory / "cv.docx", ["Test Student", "E-mail: student@163.com"]))])
        slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
        confirmed = self.core.confirm_attachment(preparation_id, slot["id"])
        attachment_id = confirmed["attachment_slots"][0]["attachment"]["id"]

        removed = self.core.remove_attachment_slot(preparation_id, slot["id"])
        self.assertEqual(removed["attachment_slots"], [])
        with self.assertRaises(SmartMailError):
            self.core.read_attachment(attachment_id)

    def test_slot_arguments_are_validated(self):
        preparation_id = self.prepare()
        with self.assertRaises(SmartMailError):
            self.core.add_attachment_slot(preparation_id, "   ")
        with self.assertRaises(SmartMailError):
            self.core.add_attachment_slot(preparation_id, "Student CV")
        with self.assertRaises(SmartMailError):
            self.core.add_attachment_slot(preparation_id, "Missing", path=self.directory / "none.pdf")
        self.assertEqual(len(self.core.get_preparation(preparation_id)["attachment_slots"]), 1)
        with self.assertRaises(SmartMailError):
            self.core.remove_attachment_slot(preparation_id, "unknown")


class IdentityConfirmationTests(ReadinessTestCase):
    def ambiguous_import(self):
        return self.import_bundle(
            [["University", "Alex Green", "shared@example.edu", ""],
             ["University", "Blair Blue", "shared@example.edu", ""]],
            [("University_Alex Green.docx", draft_paragraphs(
                "shared@example.edu", "Dear Dr Green,", ["Hello."]))],
        )

    def test_confirming_task_identity_clears_the_derived_readiness_conflict(self):
        imported = self.ambiguous_import()
        preparation_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        self.assertIn("identity_conflict", self.blocking_codes(self.core.get_preparation(preparation_id)))

        tasks = {t["supervisor_name"]: t for t in self.core.list_tasks(self.campaign["id"])}
        ambiguity = [e for e in self.core.list_exceptions(self.campaign["id"])
                     if e["code"] == "identity_ambiguity" and e["task_id"] == tasks["Alex Green"]["id"]]
        self.assertEqual(len(ambiguity), 1)
        self.assertTrue(ambiguity[0]["blocking"])
        self.assertIn("Unresolved Supervisor identity", ambiguity[0]["detail"])
        self.assertIn("identity_conflict",
                      {f["code"] for f in ambiguity[0]["readiness_findings"]})

        confirmed = self.core.confirm_task_identity(tasks["Alex Green"]["id"])
        self.assertEqual(confirmed["exceptions"], [])
        self.assertEqual(self.blocking_codes(self.core.get_preparation(preparation_id)),
                         {"missing_subject"})

        remaining = [e["task_id"] for e in self.core.list_exceptions(self.campaign["id"])
                     if e["code"] == "identity_ambiguity"]
        self.assertEqual(remaining, [tasks["Blair Blue"]["id"]])
        with SmartMail(self.home) as restarted:
            self.assertEqual(self.blocking_codes(restarted.get_preparation(preparation_id)),
                             {"missing_subject"})

    def test_a_task_without_an_identity_conflict_cannot_be_confirmed(self):
        imported = self.import_bundle(
            [["University", "Alex Green", "alex@example.edu", ""]],
            [("University_Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", ["Hello."]))],
        )
        with self.assertRaises(SmartMailError):
            self.core.confirm_task_identity(imported["task_ids"][0])
        with self.assertRaises(SmartMailError):
            self.core.confirm_task_identity("unknown")


class LocalOnlyTests(ReadinessTestCase):
    def test_corrections_are_local_and_write_nothing_outside_the_store(self):
        transcript = self.directory / "Transcript.pdf"
        transcript.write_bytes(b"transcript bytes")
        imported = self.import_bundle(
            [["Example University", "Dr Alex Green", "alex@example.edu", ""]],
            [("Example University_Dr Alex Green.docx", draft_paragraphs(
                "alex@example.edu", "Dear Dr Green,", [DECLARATION]))],
            extra=[("Test Student - CV.docx", document(self.directory / "cv.docx", ["Curriculum vitae"]))],
        )
        preparation_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        untouched = {path: path.stat().st_mtime_ns for path in self.directory.rglob("*")
                     if path.is_file() and "state" not in path.parts}

        slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
        self.core.set_subject(preparation_id, "PhD supervision enquiry")
        self.core.set_recipient(preparation_id, "alex@example.edu")
        self.core.confirm_attachment(preparation_id, slot["id"])
        self.core.add_attachment_slot(preparation_id, "Transcript", path=transcript)

        self.assertEqual(untouched, {path: path.stat().st_mtime_ns for path in self.directory.rglob("*")
                                     if path.is_file() and "state" not in path.parts})
        self.assertFalse(self.core.mailbox.enabled)
        # The facade must expose no sending capability. "draft" used to stand in
        # for it, but an observed draft is imported as local Source Material and
        # never sent, so the words that actually denote sending are asserted.
        self.assertEqual(
            [name for name in dir(SmartMail)
             if any(word in name.lower() for word in ("send", "browser", "smtp", "deliver"))], [])


class TerminalReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "state-correct"

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
                [["Example University", "Dr Alex Green", "Alex.Green@example.edu", ""]])
            docx = document(self.directory / "draft.docx", draft_paragraphs(
                "alex.green@example.edu", "Dear Dr Green,", [DECLARATION]))
            cv = document(self.directory / "cv.docx", ["Test Student", "E-mail: student@163.com"])
            source = bundle(self.directory / "bundle.zip", [
                ("master.xlsx", master_path),
                ("Example University_Dr Alex Green.docx", docx),
                ("Test Student - CV.docx", cv)])
            imported = core.import_master(campaign["id"], student["id"], source)
            cv_source = next(s for s in core.get_import(imported["id"])["sources"]
                             if s["name"].endswith("CV.docx"))
        return campaign, imported, cv_source

    def test_terminal_corrects_fields_and_manages_attachments(self):
        campaign, imported, cv_source = self.build_store()
        prepared = self.run_cli("prepare", "--import", imported["id"])
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        preparation_id = json.loads(prepared.stdout)["preparation_ids"][0]

        shown = json.loads(self.run_cli("preparation", "show", preparation_id).stdout)
        slot = shown["attachment_slots"][0]
        self.assertEqual(slot["label"], "Student CV")
        self.assertEqual(slot["suggested_source_id"], cv_source["id"])
        self.assertIn("missing_subject", [f["code"] for f in shown["readiness_findings"]])

        confirmed = json.loads(self.run_cli(
            "preparation", "confirm", preparation_id, "--slot", slot["id"]).stdout)
        self.assertEqual(confirmed["attachment_slots"][0]["attachment"]["name"],
                         "Test Student - CV.docx")
        self.assertEqual(confirmed["attachment_slots"][0]["attachment"]["sha256"],
                         cv_source["sha256"])

        corrected = json.loads(self.run_cli(
            "preparation", "set-subject", preparation_id, "PhD supervision enquiry").stdout)
        self.assertEqual(corrected["subject"], "PhD supervision enquiry")
        corrected = json.loads(self.run_cli(
            "preparation", "set-recipient", preparation_id, "Alex.Green@example.edu").stdout)
        self.assertEqual(corrected["recipient"], "Alex.Green@example.edu")
        self.assertEqual(corrected["readiness_findings"], [])
        self.assertEqual([c["field"] for c in corrected["corrections"]],
                         ["attachment:Student CV", "subject", "recipient"])

        reflected = json.loads(self.run_cli("preparation", "suggest", preparation_id).stdout)
        self.assertEqual(len(reflected), 1)
        transcript = self.directory / "Transcript.pdf"
        transcript.write_bytes(b"transcript bytes")
        added = json.loads(self.run_cli(
            "preparation", "add-attachment", preparation_id,
            "--label", "Transcript", "--file", str(transcript)).stdout)
        self.assertEqual([s["label"] for s in added["attachment_slots"]], ["Student CV", "Transcript"])
        removed = json.loads(self.run_cli(
            "preparation", "remove-attachment", preparation_id,
            "--slot", added["attachment_slots"][1]["id"]).stdout)
        self.assertEqual([s["label"] for s in removed["attachment_slots"]], ["Student CV"])

        previewed = self.run_cli("preparation", "preview", preparation_id)
        self.assertEqual(previewed.returncode, 0, previewed.stderr)
        self.assertIn("Attachments: Test Student - CV.docx", previewed.stdout)
        self.assertIn("Subject: PhD supervision enquiry", previewed.stdout)

        again = json.loads(self.run_cli("preparation", "show", preparation_id).stdout)
        self.assertEqual(again["attachment_slots"][0]["attachment"]["sha256"], cv_source["sha256"])

    def test_terminal_lists_exceptions_and_confirms_identity(self):
        with SmartMail(self.home) as core:
            campaign = core.create_campaign("2027 outreach")
            student = core.create_student("Test Student", "student@163.com")
            master_path = master(self.directory / "master.xlsx", [
                ["University", "Alex Green", "shared@example.edu", ""],
                ["University", "Blair Blue", "shared@example.edu", ""]])
            docx = document(self.directory / "draft.docx", draft_paragraphs(
                "shared@example.edu", "Dear Dr Green,", ["Hello."]))
            source = bundle(self.directory / "bundle.zip", [
                ("master.xlsx", master_path), ("University_Alex Green.docx", docx)])
            imported = core.import_master(campaign["id"], student["id"], source)
            preparation_id = core.prepare_from_documents(imported["id"])["preparation_ids"][0]
            tasks = {t["supervisor_name"]: t for t in core.list_tasks(campaign["id"])}

        listed = self.run_cli("exceptions", "list", "--campaign", campaign["id"])
        self.assertEqual(listed.returncode, 0, listed.stderr)
        exceptions = json.loads(listed.stdout)
        ambiguity = [e for e in exceptions if e["task_id"] == tasks["Alex Green"]["id"]]
        self.assertEqual([e["code"] for e in ambiguity], ["identity_ambiguity"])
        self.assertEqual(ambiguity[0]["source"]["name"], "master.xlsx")
        self.assertIn("identity_conflict", [f["code"] for f in ambiguity[0]["readiness_findings"]])

        shown = self.run_cli("exceptions", "show", ambiguity[0]["id"])
        self.assertEqual(json.loads(shown.stdout), ambiguity[0])

        confirmed = self.run_cli("task", "confirm-identity", tasks["Alex Green"]["id"])
        self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
        self.assertEqual(json.loads(confirmed.stdout)["exceptions"], [])

        preparation = json.loads(self.run_cli("preparation", "show", preparation_id).stdout)
        self.assertNotIn("identity_conflict",
                         [f["code"] for f in preparation["readiness_findings"]])
        remaining = json.loads(self.run_cli(
            "exceptions", "list", "--campaign", campaign["id"]).stdout)
        self.assertEqual([e["task_id"] for e in remaining], [tasks["Blair Blue"]["id"]])

    def test_terminal_reports_an_unknown_exception(self):
        failed = self.run_cli("exceptions", "show", "unknown")
        self.assertEqual(failed.returncode, 2)
        self.assertIn("error", json.loads(failed.stderr))


if __name__ == "__main__":
    unittest.main()

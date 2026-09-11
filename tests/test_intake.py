import tempfile
import unittest
import zipfile
from pathlib import Path

from openpyxl import Workbook

from smartmail import SmartMail, SmartMailError


def master(path, rows, headers=None, merges=()):
    """Anonymized fixture using the inspected master list's layout."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers or ["大学", "导师", "邮箱📮", "URL"])
    for row in rows:
        sheet.append(row)
    for cells in merges:
        sheet.merge_cells(cells)
    workbook.save(path)
    workbook.close()
    return path


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "state"
        self.core = SmartMail(self.home)
        self.addCleanup(self.core.__exit__)
        self.campaign = self.core.create_campaign("2027 outreach")

    def test_import_establishes_inspectable_task_and_participants(self):
        student = self.core.create_student("Test Student", "student@163.com")
        source = master(self.directory / "master.xlsx", [
            ["Example University", "Dr Alex Green", "alex@example.edu", "https://example.edu/people/alex"],
        ])
        result = self.core.import_master(self.campaign["id"], student["id"], source)
        task = self.core.get_task(result["task_ids"][0])
        self.assertEqual(task["student"]["name"], "Test Student")
        self.assertEqual(task["mailbox"]["address"], "student@163.com")
        self.assertEqual(task["supervisor"]["name"], "Dr Alex Green")
        self.assertEqual(task["supervisor"]["addresses"], ["alex@example.edu"])
        self.assertEqual(task["institution"]["name"], "Example University")
        self.assertEqual(task["campaign"], self.campaign)
        self.assertEqual(self.core.list_tasks(self.campaign["id"])[0]["id"], task["id"])
        self.assertEqual(task["source_associations"][0]["row"], 2)
        self.assertEqual(task["exceptions"], [])

    def test_reordered_alias_columns_and_merged_institutions_keep_cell_evidence(self):
        student = self.core.create_student("Test Student", "student@163.com")
        source = master(self.directory / "master.xlsx", [
            [" a@example.edu\n", "Example University", "Dr Alex Green"],
            ["b@example.edu", None, "Dr Blair Blue"],
        ], headers=["邮箱", "院校", "导师姓名"], merges=["B2:B3"])
        result = self.core.import_master(self.campaign["id"], student["id"], source)
        tasks = [self.core.get_task(i) for i in result["task_ids"]]
        self.assertEqual([t["institution"]["name"] for t in tasks], ["Example University"] * 2)
        self.assertEqual(tasks[0]["supervisor"]["addresses"], ["a@example.edu"])
        evidence = tasks[1]["source_associations"][0]["evidence"]
        self.assertEqual(evidence["field_cells"]["institution"], "B2")
        self.assertEqual(evidence["raw_cells"]["B3"], None)

    def test_bundle_sources_and_tasks_survive_restart_and_original_removal(self):
        student = self.core.create_student("Test Student", "student@163.com")
        source = master(self.directory / "master.xlsx", [["University", "Alex", "a@example.edu", ""]])
        bundle = self.directory / "sample.zip"
        with zipfile.ZipFile(bundle, "w") as archive:
            archive.write(source, "学生/名单.xlsx")
            archive.writestr("学生/CV.docx", b"original document bytes")
        original = source.read_bytes()
        result = self.core.import_master(self.campaign["id"], student["id"], bundle)
        source.unlink()
        bundle.unlink()
        with SmartMail(self.home) as restarted:
            imported = restarted.get_import(result["id"])
            self.assertEqual(len(imported["sources"]), 3)
            workbook = next(s for s in imported["sources"] if s["name"].endswith(".xlsx"))
            self.assertEqual(restarted.read_source(workbook["id"]), original)
            opened = restarted.materialize_source(workbook["id"])
            self.assertEqual(opened.read_bytes(), original)
            opened.write_bytes(b"operator edits the opened copy")
            self.assertEqual(restarted.materialize_source(workbook["id"]).read_bytes(), original)
            self.assertEqual(restarted.get_task(result["task_ids"][0])["campaign"], self.campaign)

    def test_profile_url_in_email_column_becomes_a_persisted_blocker(self):
        student = self.core.create_student("Test Student", "student@163.com")
        source = master(self.directory / "master.xlsx", [[
            "University", "Prof Alex", "https://example.edu/people/alex/#", "https://example.edu/people/alex/",
        ]])
        result = self.core.import_master(self.campaign["id"], student["id"], source)
        with SmartMail(self.home) as restarted:
            task = restarted.get_task(result["task_ids"][0])
            self.assertEqual(task["supervisor"]["addresses"], [])
            self.assertEqual(task["exceptions"][0]["code"], "invalid_recipient")
            self.assertTrue(task["exceptions"][0]["blocking"])
            self.assertEqual(task["source_associations"][0]["evidence"]["raw_cells"]["C2"], "https://example.edu/people/alex/#")

    def test_same_profile_evidence_shares_supervisor_and_task_across_known_addresses(self):
        student = self.core.create_student("Test Student", "student@163.com")
        source = master(self.directory / "master.xlsx", [
            ["University", "Dr Alex Green", "a@example.edu", "https://example.edu/people/alex/"],
            ["University", "Alex Green", "alternate@example.edu", "https://example.edu/people/alex/#"],
        ])
        first = self.core.import_master(self.campaign["id"], student["id"], source)
        second = self.core.import_master(self.campaign["id"], student["id"], source)
        self.assertEqual(first["task_ids"], second["task_ids"])
        self.assertEqual(len(first["task_ids"]), 1)
        task = self.core.get_task(first["task_ids"][0])
        self.assertEqual(task["supervisor"]["addresses"], ["a@example.edu", "alternate@example.edu"])
        self.assertEqual(len(task["source_associations"]), 4)
        other_campaign = self.core.create_campaign("2028 outreach")
        other = self.core.import_master(other_campaign["id"], student["id"], source)
        self.assertNotEqual(first["task_ids"], other["task_ids"])
        self.assertEqual(self.core.get_task(other["task_ids"][0])["supervisor"]["id"], task["supervisor"]["id"])
        other_student = self.core.create_student("Another Student", "another@163.com")
        separate = self.core.import_master(self.campaign["id"], other_student["id"], source)
        self.assertNotEqual(first["task_ids"], separate["task_ids"])

    def test_unreliable_identity_matches_remain_separate_and_block_both_tasks(self):
        student = self.core.create_student("Test Student", "student@163.com")
        source = master(self.directory / "master.xlsx", [
            ["University", "Alex Green", "a@example.edu", ""],
            ["University", "Alex Green", "b@example.edu", ""],
        ])
        result = self.core.import_master(self.campaign["id"], student["id"], source)
        with SmartMail(self.home) as restarted:
            tasks = [restarted.get_task(i) for i in result["task_ids"]]
            self.assertEqual(len({t["supervisor"]["id"] for t in tasks}), 2)
            for task in tasks:
                self.assertIn("identity_ambiguity", [e["code"] for e in task["exceptions"]])
                self.assertEqual(len(task["supervisor"]["addresses"]), 1)

    def test_shared_addresses_do_not_override_conflicting_profile_evidence(self):
        student = self.core.create_student("Test Student", "student@163.com")
        source = master(self.directory / "master.xlsx", [
            ["University", "Alex Green", "shared@example.edu", "https://example.edu/people/alex-one"],
            ["University", "Alex Green", "shared@example.edu", "https://example.edu/people/alex-two"],
            ["Other University", "Blair Blue", "shared@example.edu", "https://other.edu/blair"],
        ])
        result = self.core.import_master(self.campaign["id"], student["id"], source)
        self.assertEqual(len(result["task_ids"]), 3)
        for task_id in result["task_ids"]:
            self.assertIn("identity_ambiguity", [e["code"] for e in self.core.get_task(task_id)["exceptions"]])

    def test_unsupported_or_ambiguous_layouts_reject_without_partial_import(self):
        student = self.core.create_student("Test Student", "student@163.com")
        for headers, rows in [
            (["大学", "导师", "邮箱", "Email"], [["University", "Alex", "a@example.edu", "b@example.edu"]]),
            (["大学", "导师", "邮箱"], [["University", "Alex", "a@example.edu"], [None, "Blair", "b@example.edu"]]),
            (["大学", "导师", "邮箱"], [["University", "=A2", "a@example.edu"]]),
        ]:
            with self.subTest(headers=headers, rows=rows):
                source = master(self.directory / "master.xlsx", rows, headers=headers)
                with self.assertRaises(SmartMailError):
                    self.core.import_master(self.campaign["id"], student["id"], source)
                self.assertEqual(self.core.list_tasks(self.campaign["id"]), [])
                self.assertEqual(self.core.list_imports(self.campaign["id"]), [])

    def test_reimport_of_the_same_unresolved_source_row_keeps_task_identity(self):
        student = self.core.create_student("Test Student", "student@163.com")
        source = master(self.directory / "master.xlsx", [["University", "Alex Green", "", ""]])
        first = self.core.import_master(self.campaign["id"], student["id"], source)
        second = self.core.import_master(self.campaign["id"], student["id"], source)
        self.assertEqual(first["task_ids"], second["task_ids"])
        self.assertEqual(len(self.core.list_tasks(self.campaign["id"])), 1)
        task = self.core.get_task(first["task_ids"][0])
        self.assertEqual({e["code"] for e in task["exceptions"]}, {"invalid_recipient"})

    def test_new_profile_evidence_is_retained_for_later_address_matching(self):
        student = self.core.create_student("Test Student", "student@163.com")
        source = master(self.directory / "master.xlsx", [
            ["University", "Alex Green", "a@example.edu", ""],
            ["University", "Alex Green", "a@example.edu", "https://example.edu/alex"],
            ["University", "Alex Green", "b@example.edu", "https://example.edu/alex"],
        ])
        result = self.core.import_master(self.campaign["id"], student["id"], source)
        self.assertEqual(len(result["task_ids"]), 1)
        self.assertEqual(self.core.get_task(result["task_ids"][0])["exceptions"], [])

    def test_campaign_selection_and_task_summary_expose_unfinished_work(self):
        student = self.core.create_student("Test Student", "student@163.com")
        source = master(self.directory / "master.xlsx", [["University", "Alex Green", "", ""]])
        for campaign_id, student_id in [(None, student["id"]), (self.campaign["id"], "unknown")]:
            with self.assertRaises(SmartMailError):
                self.core.import_master(campaign_id, student_id, source)
        self.assertEqual(self.core.list_imports(self.campaign["id"]), [])
        result = self.core.import_master(self.campaign["id"], student["id"], source)
        summary = self.core.list_tasks(self.campaign["id"])[0]
        self.assertEqual(summary["id"], result["task_ids"][0])
        self.assertEqual(summary["student_name"], "Test Student")
        self.assertEqual(summary["supervisor_name"], "Alex Green")
        self.assertEqual(summary["institution_name"], "University")
        self.assertEqual(summary["exception_count"], 1)
        empty = self.core.create_campaign("Separate campaign")
        self.assertEqual(self.core.list_tasks(empty["id"]), [])

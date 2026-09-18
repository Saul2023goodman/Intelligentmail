"""Smoke check: an observed draft becomes Source Material and a Preparation."""
import tempfile
import unittest
from pathlib import Path

from smartmail import SmartMail
from smartmail.mailbox import ControlledMailbox

DRAFT = {
    "status": "complete",
    "mailbox_address": "student@163.com",
    "observed_at": "2026-09-18T02:00:00+00:00",
    "detail": "controlled draft observation",
    "coverage": {"complete": False, "folders": []},
    "messages": [
        {
            "direction": "outbound", "folder": "drafts", "platform_reference": "draft-1",
            "counterpart": "chen@state.edu", "subject": "PhD supervision inquiry",
            "observed_time": "2026年9月18日 10:00", "status": "draft", "ambiguity": "",
            "content": {"fetched": True, "text": "Dear Professor Chen,\n\nI write to ask…"},
            "attachments": [
                {"name": "cv.pdf", "size": 20480, "content_type": "application/pdf", "part": "2"},
            ],
            "compose": {
                "to": [{"address": "chen@state.edu", "name": "Prof. Chen"}],
                "cc": [], "bcc": [], "is_html": False,
                "body_html": "<div>Dear Professor Chen,<br><br>I write to ask…</div>",
                "body_text": "Dear Professor Chen,\n\nI write to ask…",
                "scheduled_draft": False, "schedule_date": "",
                "attachments": [{"name": "cv.pdf", "size": 20480, "part": "2"}],
            },
            "evidence": {"source": "controlled"},
        },
        {
            "direction": "outbound", "folder": "drafts", "platform_reference": "draft-2",
            "counterpart": "nobody@example.org", "subject": "Unaddressed draft",
            "observed_time": "2026年9月18日 11:00", "status": "draft", "ambiguity": "",
            "content": {"fetched": True, "text": "Draft without a recorded supervisor."},
            "compose": {"to": [{"address": "nobody@example.org", "name": ""}], "cc": [], "bcc": [],
                        "body_text": "Draft without a recorded supervisor.",
                        "scheduled_draft": False, "attachments": []},
            "evidence": {"source": "controlled"},
        },
    ],
}


class DraftImportSmoke(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "state"
        self.core = SmartMail(self.home, mailbox=ControlledMailbox(observations=[DRAFT]))
        self.addCleanup(self.core.__exit__, None, None, None)
        student = self.core.create_student("Smoke Student", "student@163.com")
        self.student_id = student["id"]
        self.campaign_id = student["campaign_id"]
        with self.core._db:
            institution = self.core._db.execute(
                "INSERT INTO institutions VALUES (?, ?) RETURNING id", ("inst-1", "State University")
            ).fetchone()["id"]
            supervisor = self.core._db.execute(
                "INSERT INTO supervisors VALUES (?, ?, ?, ?) RETURNING id",
                ("sup-1", "Prof. Chen", institution, "")).fetchone()["id"]
            self.core._db.execute(
                "INSERT INTO supervisor_addresses VALUES (?, ?)", (supervisor, "chen@state.edu"))
            self.core._db.execute(
                "INSERT INTO tasks VALUES (?, ?, ?, ?)",
                ("task-1", self.student_id, supervisor, self.campaign_id))

    def test_draft_material_is_persisted_and_importable(self):
        self.core.refresh_mailbox(self.student_id)
        candidates = self.core.draft_material_candidates(self.campaign_id, self.student_id)

        self.assertEqual(len(candidates), 2)
        first = candidates[0]
        self.assertEqual(first["recipient"], "chen@state.edu")
        self.assertTrue(first["body_available"])
        self.assertEqual(first["attachment_count"], 1)
        self.assertEqual(first["attachments_available"], 0)
        self.assertEqual(first["task_id"], "task-1")
        self.assertEqual(candidates[1]["task_id"], "")

        result = self.core.import_mailbox_drafts(
            self.campaign_id, self.student_id, [first["observation_id"]])
        self.assertEqual(len(result["imported"]), 1)
        preparation = self.core.get_preparation(result["imported"][0]["preparation_id"])
        self.assertEqual(preparation["recipient"], "chen@state.edu")
        self.assertEqual(preparation["subject"], "PhD supervision inquiry")
        self.assertIn("Dear Professor Chen", preparation["body"])
        self.assertIn("draft_imported",
                      [entry["code"] for entry in preparation["transformations"]])
        self.assertIn("draft_attachments_observed",
                      [entry["code"] for entry in preparation["transformations"]])

        again = self.core.import_mailbox_drafts(
            self.campaign_id, self.student_id, [first["observation_id"]])
        self.assertEqual(again["imported"], [])
        self.assertIn("already imported", again["skipped"][0]["reason"])

        unmatched = self.core.import_mailbox_drafts(
            self.campaign_id, self.student_id, [candidates[1]["observation_id"]])
        self.assertEqual(unmatched["imported"], [])
        self.assertIn("No Outreach Task", unmatched["skipped"][0]["reason"])

    def test_evidence_keeps_the_captured_material(self):
        self.core.refresh_mailbox(self.student_id)
        row = self.core._db.execute(
            "SELECT evidence FROM mailbox_message_observations WHERE folder = 'drafts' "
            "ORDER BY rowid LIMIT 1").fetchone()
        material = __import__("json").loads(row["evidence"])["material"]
        self.assertIn("Dear Professor Chen", material["compose"]["body_text"])
        self.assertEqual(material["attachments"][0]["name"], "cv.pdf")
        self.assertFalse(material["attachments"][0]["available"])
        self.assertTrue(material["content"]["fetched"])


if __name__ == "__main__":
    unittest.main()

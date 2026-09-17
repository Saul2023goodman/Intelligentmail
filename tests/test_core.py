import sqlite3
import tempfile
import unittest
from pathlib import Path

from smartmail import SmartMail, SmartMailError


class CampaignTests(unittest.TestCase):
    def test_mailbox_owner_is_explicit_and_cannot_silently_change(self):
        with tempfile.TemporaryDirectory() as directory:
            with SmartMail(Path(directory)) as core:
                for name, address in [("", "student@163.com"), ("Student", "invalid")]:
                    with self.assertRaises(SmartMailError):
                        core.create_student(name, address)
                student = core.create_student("Student", "student@163.com")
                self.assertEqual(core.create_student("Student", "student@163.com"), student)
                with self.assertRaisesRegex(SmartMailError, "Mailbox already belongs"):
                    core.create_student("Someone Else", "student@163.com")
                self.assertEqual(core.list_students(), [student])

    def test_blank_campaign_name_is_rejected_without_creating_a_campaign(self):
        with tempfile.TemporaryDirectory() as directory:
            with SmartMail(Path(directory)) as core:
                with self.assertRaisesRegex(SmartMailError, "Campaign name is required"):
                    core.create_campaign("  ")
                self.assertEqual(core.list_campaigns(), [])

    def test_operator_can_create_and_select_a_campaign_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            with SmartMail(Path(directory)) as core:
                campaign = core.create_campaign("Autumn outreach")

            with SmartMail(Path(directory)) as restarted:
                self.assertEqual(restarted.list_campaigns(), [campaign])
                self.assertEqual(campaign["name"], "Autumn outreach")
                self.assertEqual(restarted.get_campaign(campaign["id"]), campaign)

    def test_student_owns_one_campaign_and_names_never_decide_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            with SmartMail(Path(directory)) as core:
                standalone = core.create_campaign("2027 outreach")
                first = core.create_student("Same Name", "first@163.com")
                second = core.create_student("Same Name", "second@163.com")
                self.assertTrue(first["campaign_id"])
                self.assertNotEqual(first["campaign_id"], second["campaign_id"])
                self.assertNotEqual(first["campaign_id"], standalone["id"])
                self.assertEqual(core.get_campaign(standalone["id"])["student_id"], None)
                self.assertEqual(core.get_campaign(first["campaign_id"])["name"], "Same Name")
                self.assertEqual([mailbox["campaign_id"] for mailbox in core.list_mailboxes()],
                                 [first["campaign_id"], second["campaign_id"]])
                self.assertEqual(
                    core.create_student("Same Name", "first@163.com")["campaign_id"],
                    first["campaign_id"])

            with SmartMail(Path(directory)) as restarted:
                self.assertEqual(restarted.get_student(first["id"])["campaign_id"],
                                 first["campaign_id"])
                self.assertEqual(restarted.get_campaign(first["campaign_id"])["student_id"],
                                 first["id"])

    def test_existing_store_recovers_the_campaign_link_recorded_only_by_name(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            db = sqlite3.connect(home / "smartmail.sqlite3")
            db.execute("CREATE TABLE campaigns (id TEXT PRIMARY KEY, name TEXT NOT NULL)")
            db.execute("CREATE TABLE students (id TEXT PRIMARY KEY, name TEXT NOT NULL)")
            db.execute("CREATE TABLE mailboxes (id TEXT PRIMARY KEY, student_id TEXT NOT NULL, "
                       "address TEXT NOT NULL UNIQUE)")
            db.execute("INSERT INTO campaigns VALUES ('c1', 'Legacy Student')")
            db.execute("INSERT INTO campaigns VALUES ('c2', '2027 outreach')")
            db.execute("INSERT INTO students VALUES ('s1', 'Legacy Student')")
            db.execute("INSERT INTO mailboxes VALUES ('m1', 's1', 'legacy@163.com')")
            db.commit()
            db.close()

            with SmartMail(home) as core:
                self.assertEqual(core.get_student("s1")["campaign_id"], "c1")
                self.assertEqual(core.get_campaign("c2")["student_id"], None)


if __name__ == "__main__":
    unittest.main()

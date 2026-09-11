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


if __name__ == "__main__":
    unittest.main()

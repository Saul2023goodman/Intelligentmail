"""Sending Plans: deterministic proposals, operator adjustment and batch Confirmation."""

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from openpyxl import Workbook

from smartmail import SmartMail, SmartMailError
from smartmail.mailbox import ControlledMailbox

ROOT = Path(__file__).resolve().parent.parent
DECLARATION = "I have attached my CV and would welcome the opportunity to discuss my background."
SUBJECT = "PhD supervision enquiry"
DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
WEEKDAYS = DAYS[:5]
# Monday 14 September 2026, 08:00 in Asia/Shanghai: before that day's 09:00 window.
NOW = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
SHANGHAI = "Asia/Shanghai"
SUPERVISORS = [
    ("Dr Alex Green", "alex@example.edu"),
    ("Dr Blair Blue", "blair@example.edu"),
    ("Dr Casey Cyan", "casey@example.edu"),
    ("Dr Dana Dove", "dana@example.edu"),
    ("Dr Ellis Elm", "ellis@example.edu"),
    ("Dr Fran Fern", "fran@example.edu"),
    ("Dr Gale Gray", "gale@example.edu"),
    ("Dr Harper Hill", "harper@example.edu"),
]


def master(path, rows, headers=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers or ["大学", "导师", "邮箱📮", "URL"])
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()
    return path


def draft_paragraphs(recipient, salutation, body):
    lines = [f"Email: {recipient}", "", "", "", salutation, ""]
    for paragraph in body:
        lines.extend([paragraph, ""])
    lines += ["Yours sincerely,", "Sipei Yao"]
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


class PlanTestCase(unittest.TestCase):
    """Shared fixtures: an explicitly selected Campaign, Student and controlled time."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "state"
        self.now = NOW
        self.mailbox = ControlledMailbox()
        self.core = SmartMail(self.home, mailbox=self.mailbox, clock=lambda: self.now)
        self.addCleanup(self.core.__exit__)
        self.campaign = self.core.create_campaign("2027 outreach")
        self.student = self.core.create_student("Test Student", "student@163.com")

    def advance(self, **delta):
        self.now = self.now + timedelta(**delta)

    def configure(self, **overrides):
        settings = {
            "timezone": SHANGHAI,
            "windows": ["MON-FRI 09:00-10:00"],
            "spacing_minutes": 30,
            "daily_limit": 2,
            "horizon_days": 3,
        }
        settings.update(overrides)
        return self.core.configure_plan(self.campaign["id"], **settings)

    def cv_contents(self):
        return "Test Student - CV.docx", self.cv_content

    def proposed(self, count=2, **overrides):
        preparation_ids = self.ready_preparations(count)
        self.configure(**overrides)
        return preparation_ids, self.core.propose_plan(self.campaign["id"])

    def times(self, plan):
        return [proposal["scheduled_at"] for proposal in plan["proposals"]]

    def import_bundle(self, documents, master_rows, extra=()):
        master_path = master(self.directory / "master.xlsx", master_rows)
        members = [("master.xlsx", master_path)]
        for index, (name, paragraphs) in enumerate(documents):
            members.append((name, document(self.directory / f"draft-{index}.docx", paragraphs)))
        for name, item in extra:
            members.append((name, item))
        source = bundle(self.directory / "bundle.zip", members)
        return self.core.import_master(self.campaign["id"], self.student["id"], source)

    def ready_preparations(self, count=1, subject=SUBJECT, attach=True):
        """Ready Preparations in a fixed order, one per Supervisor, with a confirmed CV."""
        supervisors = SUPERVISORS[:count]
        rows = [["Example University", name, address, ""] for name, address in supervisors]
        cv_path = document(self.directory / "cv.docx", ["Test Student", "E-mail: student@163.com"])
        self.cv_content = cv_path.read_bytes()
        documents = [
            (f"Example University_{name}.docx",
             draft_paragraphs(address, "Dear Dr,", [DECLARATION]))
            for name, address in supervisors
        ]
        imported = self.import_bundle(documents, rows, extra=[("Test Student - CV.docx", cv_path)])
        preparation_ids = self.core.prepare_from_documents(imported["id"])["preparation_ids"]
        self.assertEqual(len(preparation_ids), count)
        for preparation_id in preparation_ids:
            if subject is not None:
                self.core.set_subject(preparation_id, subject)
            if attach:
                slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
                self.core.confirm_attachment(preparation_id, slot["id"])
        return preparation_ids


class PlanConfigurationTests(PlanTestCase):
    def test_default_configuration_is_reproducible_and_persisted(self):
        configuration = self.core.configure_plan(self.campaign["id"])

        self.assertEqual(configuration["campaign_id"], self.campaign["id"])
        self.assertEqual(configuration["timezone"], "UTC")
        self.assertEqual(configuration["spacing_minutes"], 15)
        self.assertEqual(configuration["daily_limit"], 20)
        self.assertEqual(configuration["horizon_days"], 14)
        self.assertEqual(configuration["windows"],
                         [{"days": WEEKDAYS, "start": "09:00", "end": "17:00"}])

        self.assertEqual(self.core.configure_plan(self.campaign["id"]), configuration)
        with SmartMail(self.home) as restarted:
            self.assertEqual(restarted.configure_plan(self.campaign["id"]), configuration)

    def test_configure_windows_timezone_spacing_and_limits(self):
        configuration = self.core.configure_plan(
            self.campaign["id"], timezone=SHANGHAI,
            windows=["MON-FRI 09:00-12:00", "MON,TUE 13:00-17:00"],
            spacing_minutes=30, daily_limit=5, horizon_days=3)

        self.assertEqual(configuration["timezone"], SHANGHAI)
        self.assertEqual(configuration["spacing_minutes"], 30)
        self.assertEqual(configuration["daily_limit"], 5)
        self.assertEqual(configuration["horizon_days"], 3)
        self.assertEqual(configuration["windows"], [
            {"days": WEEKDAYS, "start": "09:00", "end": "12:00"},
            {"days": ["MON", "TUE"], "start": "13:00", "end": "17:00"},
        ])

        updated = self.core.configure_plan(self.campaign["id"], daily_limit=4)

        self.assertEqual(updated["daily_limit"], 4)
        self.assertEqual(updated["spacing_minutes"], 30)
        self.assertEqual(updated["windows"], configuration["windows"])

    def test_an_unsupported_configuration_is_refused(self):
        for argument, match in (
            ({"timezone": "Mars/Olympus"}, "timezone"),
            ({"windows": ["MON 09:00"]}, "window"),
            ({"windows": ["FUN 09:00-10:00"]}, "window"),
            ({"windows": ["MON 10:00-09:00"]}, "window"),
            ({"windows": ["MON 24:00-25:00"]}, "window"),
            ({"windows": []}, "window"),
            ({"spacing_minutes": 0}, "spacing"),
            ({"daily_limit": 0}, "daily limit"),
            ({"horizon_days": 0}, "horizon"),
        ):
            with self.subTest(argument=argument):
                with self.assertRaisesRegex(SmartMailError, match):
                    self.core.configure_plan(self.campaign["id"], **argument)

    def test_configuration_requires_a_known_campaign(self):
        with self.assertRaises(SmartMailError):
            self.core.configure_plan("unknown")


class ProposalTests(PlanTestCase):
    def test_proposals_honour_the_configured_window_spacing_and_daily_limit(self):
        preparation_ids = self.ready_preparations(3)
        self.configure()

        plan = self.core.propose_plan(self.campaign["id"])

        self.assertEqual(plan["campaign_id"], self.campaign["id"])
        self.assertEqual(plan["status"], "proposed")
        self.assertEqual(plan["configuration"]["timezone"], SHANGHAI)
        self.assertEqual(
            [proposal["preparation_id"] for proposal in plan["proposals"]], preparation_ids)
        # Monday 09:00 and 09:30 reach the daily limit of two; the third moves to Tuesday.
        self.assertEqual(self.times(plan), [
            "2026-09-14T09:00:00+08:00",
            "2026-09-14T09:30:00+08:00",
            "2026-09-15T09:00:00+08:00",
        ])
        for proposal in plan["proposals"]:
            self.assertEqual(proposal["timezone"], SHANGHAI)
            self.assertEqual(proposal["status"], "scheduled")
            self.assertEqual(proposal["confirmation_id"], None)
            self.assertEqual(proposal["task_id"],
                             self.core.get_preparation(proposal["preparation_id"])["task_id"])

    def test_reproposing_the_same_configuration_produces_the_same_times(self):
        self.ready_preparations(3)
        self.configure()

        first = self.core.propose_plan(self.campaign["id"])
        second = self.core.propose_plan(self.campaign["id"])

        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual(self.times(second), self.times(first))
        statuses = {plan["id"]: plan["status"] for plan in self.core.list_plans(self.campaign["id"])}
        self.assertEqual(statuses[first["id"]], "superseded")
        self.assertEqual(statuses[second["id"]], "proposed")
        self.assertEqual(self.core.get_plan(first["id"])["status"], "superseded")

    def test_spacing_is_enforced_between_times_across_adjacent_windows(self):
        self.ready_preparations(4)
        self.configure(windows=["MON 09:00-10:00", "MON 10:10-11:00"],
                       spacing_minutes=30, daily_limit=5, horizon_days=1)

        plan = self.core.propose_plan(self.campaign["id"])

        # 10:10 is only ten minutes after 10:00, so the next action moves to 10:40.
        self.assertEqual(self.times(plan), [
            "2026-09-14T09:00:00+08:00",
            "2026-09-14T09:30:00+08:00",
            "2026-09-14T10:00:00+08:00",
            "2026-09-14T10:40:00+08:00",
        ])

    def test_proposing_for_an_unknown_campaign_is_refused(self):
        with self.assertRaises(SmartMailError):
            self.core.propose_plan("unknown")
        with self.assertRaises(SmartMailError):
            self.core.get_plan("unknown")
        with self.assertRaises(SmartMailError):
            self.core.list_plans("unknown")


class PlanReviewTests(PlanTestCase):
    def test_the_plan_reviews_every_field_needed_before_batch_confirmation(self):
        preparation_ids = self.ready_preparations(2)
        self.configure()

        plan = self.core.propose_plan(self.campaign["id"])
        first = plan["proposals"][0]
        _, cv_bytes = self.cv_contents()

        self.assertEqual(first["preparation_id"], preparation_ids[0])
        self.assertEqual(first["sender"], "student@163.com")
        self.assertEqual(first["recipient"], "alex@example.edu")
        self.assertEqual(first["subject"], SUBJECT)
        self.assertTrue(first["ready"])
        self.assertEqual(first["readiness_findings"], [])
        self.assertEqual([a["label"] for a in first["attachments"]], ["Student CV"])
        attachment = first["attachments"][0]
        self.assertEqual(attachment["name"], "Test Student - CV.docx")
        self.assertEqual(attachment["size"], len(cv_bytes))
        self.assertEqual(len(attachment["sha256"]), 64)
        self.assertEqual(self.core.read_attachment(attachment["id"]), cv_bytes)
        self.assertIn("Dear Dr,", first["message"])
        self.assertIn("To: alex@example.edu", first["message"])
        self.assertIn(f"Subject: {SUBJECT}", first["message"])

    def test_actions_that_cannot_be_confirmed_are_listed_with_their_reason(self):
        preparation_ids = self.ready_preparations(2, subject=None)
        self.configure()

        plan = self.core.propose_plan(self.campaign["id"])

        self.assertEqual(plan["proposals"], [])
        self.assertEqual(
            [(entry["preparation_id"], entry["reason"]) for entry in plan["unavailable"]],
            [(preparation_ids[0], "not_ready"), (preparation_ids[1], "not_ready")])
        self.assertIn("missing_subject", plan["unavailable"][0]["detail"])
        self.assertEqual([finding["code"] for finding in plan["unavailable"][0]["readiness_findings"]],
                         ["missing_subject"])

    def test_an_already_sent_preparation_is_never_proposed_again(self):
        preparation_ids = self.ready_preparations(2)
        confirmation = self.core.confirm(preparation_ids[0])
        self.core.run_execution([confirmation["id"]])
        self.configure()

        plan = self.core.propose_plan(self.campaign["id"])

        self.assertEqual([proposal["preparation_id"] for proposal in plan["proposals"]],
                         [preparation_ids[1]])
        self.assertEqual(
            [(entry["preparation_id"], entry["reason"]) for entry in plan["unavailable"]],
            [(preparation_ids[0], "already_sent")])


class ImpossibleProposalTests(PlanTestCase):
    def test_actions_beyond_the_configured_capacity_are_surfaced_not_crowded_in(self):
        self.ready_preparations(5)
        self.configure(windows=["MON-FRI 09:00-10:00"], spacing_minutes=15,
                       daily_limit=2, horizon_days=1)

        plan = self.core.propose_plan(self.campaign["id"])

        self.assertEqual(self.times(plan), ["2026-09-14T09:00:00+08:00", "2026-09-14T09:15:00+08:00"])
        self.assertEqual(len(plan["impossible"]), 3)
        for entry in plan["impossible"]:
            self.assertEqual(entry["reason"], "no_available_slot")
            self.assertEqual(entry["constraint"], "daily_limit")
            self.assertEqual(entry["scheduled_at"], "")
            self.assertIn("2", entry["detail"])
            self.assertIn("5", entry["detail"])

    def test_a_horizon_without_an_allowed_window_surfaces_every_action(self):
        self.ready_preparations(2)
        self.configure(windows=["SAT,SUN 09:00-10:00"], horizon_days=1, daily_limit=5)

        plan = self.core.propose_plan(self.campaign["id"])

        self.assertEqual(plan["proposals"], [])
        self.assertEqual(len(plan["impossible"]), 2)
        self.assertEqual({entry["constraint"] for entry in plan["impossible"]}, {"windows"})

    def test_no_proposal_ever_violates_the_configured_constraints(self):
        self.ready_preparations(8)
        self.configure(windows=["MON-FRI 09:00-09:45", "MON-FRI 14:00-15:00"],
                       spacing_minutes=20, daily_limit=3, horizon_days=2)

        plan = self.core.propose_plan(self.campaign["id"])

        self.assertEqual(len(plan["proposals"]), 6)
        self.assertEqual(len(plan["impossible"]), 2)
        instants = sorted(datetime.fromisoformat(proposal["scheduled_at"])
                          for proposal in plan["proposals"])
        allowed_days = {day for window in plan["configuration"]["windows"]
                        for day in window["days"]}
        per_day: dict = {}
        for instant in instants:
            local = instant.astimezone(ZoneInfo(SHANGHAI))
            per_day[local.date()] = per_day.get(local.date(), 0) + 1
            self.assertIn(DAYS[local.weekday()], allowed_days)
            self.assertTrue(
                any(window["start"] <= local.strftime("%H:%M") <= window["end"]
                    for window in plan["configuration"]["windows"]),
                f"{local} is outside every allowed window")
        self.assertTrue(all(count <= 3 for count in per_day.values()), per_day)
        gaps = [(later - earlier).total_seconds() / 60
                for earlier, later in zip(instants, instants[1:])]
        self.assertTrue(all(gap >= 20 for gap in gaps), gaps)


class PlanAdjustmentTests(PlanTestCase):
    def test_an_operator_can_move_one_action_to_another_allowed_time(self):
        preparation_ids, plan = self.proposed()

        adjusted = self.core.adjust_plan(plan["id"], preparation_ids[1], "2026-09-15T09:30:00")

        by_preparation = {proposal["preparation_id"]: proposal
                          for proposal in adjusted["proposals"]}
        self.assertEqual(by_preparation[preparation_ids[0]]["scheduled_at"],
                         "2026-09-14T09:00:00+08:00")
        self.assertEqual(by_preparation[preparation_ids[1]]["scheduled_at"],
                         "2026-09-15T09:30:00+08:00")
        self.assertEqual(by_preparation[preparation_ids[1]]["scheduled_utc"],
                         "2026-09-15T01:30:00+00:00")
        self.assertEqual(adjusted["status"], "proposed")
        self.assertEqual(self.core.get_plan(plan["id"]), adjusted)

    def test_an_adjustment_may_state_the_time_in_another_zone(self):
        preparation_ids, plan = self.proposed(1)

        adjusted = self.core.adjust_plan(plan["id"], preparation_ids[0], "2026-09-14T01:30:00Z")

        self.assertEqual(adjusted["proposals"][0]["scheduled_at"], "2026-09-14T09:30:00+08:00")

    def test_an_adjustment_that_would_break_a_configured_constraint_is_refused(self):
        preparation_ids, plan = self.proposed()
        for value, match, changes in (
            ("2026-09-14T08:30:00", "window", "outside the 09:00-10:00 window"),
            ("2026-09-19T09:00:00", "window", "Saturday is not an allowed day"),
            ("2026-09-14T09:15:00", "spacing", "only fifteen minutes after the 09:00 action"),
        ):
            with self.subTest(value=value, changes=changes):
                with self.assertRaisesRegex(SmartMailError, match):
                    self.core.adjust_plan(plan["id"], preparation_ids[1], value)
        self.assertEqual(self.core.get_plan(plan["id"]), plan)

    def test_an_adjustment_that_exceeds_the_daily_limit_is_refused(self):
        preparation_ids, plan = self.proposed(3, daily_limit=2, windows=["MON-FRI 09:00-17:00"])
        # Monday holds 09:00 and 09:30; the third action was proposed for Tuesday.
        self.assertEqual(self.times(plan), [
            "2026-09-14T09:00:00+08:00",
            "2026-09-14T09:30:00+08:00",
            "2026-09-15T09:00:00+08:00",
        ])

        with self.assertRaisesRegex(SmartMailError, "daily limit"):
            self.core.adjust_plan(plan["id"], preparation_ids[2], "2026-09-14T16:00:00")

    def test_an_adjustment_into_the_past_is_refused(self):
        preparation_ids, plan = self.proposed(1, windows=["MON-FRI 00:00-10:00"])
        self.assertEqual(self.times(plan), ["2026-09-14T08:30:00+08:00"])

        with self.assertRaisesRegex(SmartMailError, "future"):
            self.core.adjust_plan(plan["id"], preparation_ids[0], "2026-09-14T07:00:00")

    def test_an_adjustment_requires_an_exact_time_and_a_planned_action(self):
        preparation_ids, plan = self.proposed(1)

        with self.assertRaisesRegex(SmartMailError, "time"):
            self.core.adjust_plan(plan["id"], preparation_ids[0], "next Tuesday")
        with self.assertRaises(SmartMailError):
            self.core.adjust_plan(plan["id"], "unknown", "2026-09-15T09:00:00")
        with self.assertRaises(SmartMailError):
            self.core.adjust_plan("unknown", preparation_ids[0], "2026-09-15T09:00:00")

    def test_an_action_that_cannot_be_confirmed_cannot_be_adjusted_into_the_plan(self):
        preparation_ids = self.ready_preparations(2, subject=None)
        self.configure()
        plan = self.core.propose_plan(self.campaign["id"])

        self.assertEqual([entry["reason"] for entry in plan["unavailable"]],
                         ["not_ready", "not_ready"])
        with self.assertRaisesRegex(SmartMailError, "not Ready"):
            self.core.adjust_plan(plan["id"], preparation_ids[0], "2026-09-15T09:00:00")


class PlanConfirmationTests(PlanTestCase):
    def test_batch_confirmation_binds_each_exact_preparation_and_time(self):
        preparation_ids, plan = self.proposed(2)

        confirmed = self.core.confirm_plan(plan["id"])

        self.assertEqual(confirmed["status"], "confirmed")
        for proposal, preparation_id in zip(confirmed["proposals"], preparation_ids):
            self.assertEqual(proposal["preparation_id"], preparation_id)
            self.assertIsNotNone(proposal["confirmation_id"])
            confirmation = self.core.get_confirmation(proposal["confirmation_id"])
            self.assertEqual(confirmation["preparation_id"], preparation_id)
            self.assertEqual(confirmation["status"], "active")
            self.assertEqual(confirmation["execution"], {
                "kind": "scheduled", "scheduled_at": proposal["scheduled_at"],
                "timezone": SHANGHAI})
        self.assertEqual([confirmation["id"] for confirmation
                          in self.core.list_confirmations(self.campaign["id"])],
                         [proposal["confirmation_id"] for proposal in confirmed["proposals"]])
        review = self.core.review_confirmation(preparation_ids[0])
        self.assertEqual(review["execution"]["kind"], "scheduled")
        self.assertEqual(review["execution"]["scheduled_at"],
                         confirmed["proposals"][0]["scheduled_at"])

    def test_confirming_a_plan_makes_no_external_request(self):
        _, plan = self.proposed(2)

        self.core.confirm_plan(plan["id"])

        self.assertEqual(self.mailbox.requests, [])
        self.assertEqual(self.core.list_execution_attempts(self.campaign["id"]), [])
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "idle")

    def test_reconfirming_unchanged_work_is_idempotent_and_a_content_change_renews(self):
        preparation_ids, plan = self.proposed(1)
        first = self.core.confirm_plan(plan["id"])["proposals"][0]["confirmation_id"]

        again = self.core.confirm_plan(plan["id"])
        self.assertEqual(again["proposals"][0]["confirmation_id"], first)

        self.core.set_subject(preparation_ids[0], "A revised subject")
        renewed = self.core.confirm_plan(plan["id"])

        self.assertNotEqual(renewed["proposals"][0]["confirmation_id"], first)
        self.assertEqual(self.core.get_confirmation(first)["status"], "invalidated")
        self.assertEqual(self.core.get_confirmation(first)["invalidated_reason"], "renewed")
        self.assertEqual(renewed["status"], "confirmed")

    def test_moving_a_confirmed_time_invalidates_that_confirmation_until_renewed(self):
        preparation_ids, plan = self.proposed(1)
        original = self.core.confirm_plan(plan["id"])["proposals"][0]["confirmation_id"]

        adjusted = self.core.adjust_plan(plan["id"], preparation_ids[0], "2026-09-15T09:00:00")

        self.assertEqual(adjusted["status"], "proposed")
        self.assertIsNone(adjusted["proposals"][0]["confirmation_id"])
        self.assertEqual(self.core.get_confirmation(original)["status"], "invalidated")
        self.assertEqual(self.core.get_confirmation(original)["invalidated_reason"], "adjusted")

        renewed = self.core.confirm_plan(plan["id"])

        self.assertEqual(renewed["status"], "confirmed")
        self.assertEqual(renewed["proposals"][0]["scheduled_at"], "2026-09-15T09:00:00+08:00")
        self.assertNotEqual(renewed["proposals"][0]["confirmation_id"], original)

    def test_confirmation_refuses_a_plan_whose_work_is_no_longer_ready(self):
        preparation_ids, plan = self.proposed(2)
        self.core.set_recipient(preparation_ids[0], "someone.else@example.edu")

        with self.assertRaisesRegex(SmartMailError, "recipient_conflict"):
            self.core.confirm_plan(plan["id"])

        self.assertEqual(self.core.list_confirmations(self.campaign["id"]), [])
        self.assertEqual(self.core.get_plan(plan["id"])["status"], "proposed")
        self.assertEqual(self.mailbox.requests, [])

    def test_a_superseded_plan_cannot_be_confirmed(self):
        preparation_ids, first = self.proposed(1)

        second = self.core.propose_plan(self.campaign["id"])

        with self.assertRaisesRegex(SmartMailError, "superseded"):
            self.core.confirm_plan(first["id"])
        self.assertEqual(self.core.confirm_plan(second["id"])["status"], "confirmed")
        self.assertEqual([proposal["preparation_id"] for proposal in second["proposals"]],
                         preparation_ids)

    def test_a_plan_with_nothing_to_confirm_is_refused(self):
        self.ready_preparations(1, subject=None)
        self.configure()

        plan = self.core.propose_plan(self.campaign["id"])

        self.assertEqual(plan["proposals"], [])
        with self.assertRaises(SmartMailError):
            self.core.confirm_plan(plan["id"])


class PlanExpiryTests(PlanTestCase):
    def test_an_elapsed_time_is_refused_and_needs_an_explicit_replacement(self):
        preparation_ids, plan = self.proposed(1)
        self.assertEqual(self.times(plan), ["2026-09-14T09:00:00+08:00"])
        # Monday 10:00 in Shanghai: the proposed 09:00 has already passed.
        self.advance(hours=2)

        with self.assertRaisesRegex(SmartMailError, "elapsed"):
            self.core.confirm_plan(plan["id"])

        self.assertEqual(self.core.list_confirmations(self.campaign["id"]), [])
        with self.assertRaisesRegex(SmartMailError, "future"):
            self.core.adjust_plan(plan["id"], preparation_ids[0], "2026-09-14T09:30:00")

        replacement = self.core.adjust_plan(plan["id"], preparation_ids[0], "2026-09-15T09:00:00")
        self.assertEqual(replacement["proposals"][0]["scheduled_at"], "2026-09-15T09:00:00+08:00")
        confirmed = self.core.confirm_plan(plan["id"])
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(self.core.review_confirmation(preparation_ids[0])["execution"], {
            "kind": "scheduled", "scheduled_at": "2026-09-15T09:00:00+08:00", "timezone": SHANGHAI})

    def test_a_confirmed_time_that_elapses_requires_a_new_time_and_never_sends(self):
        _, plan = self.proposed(1)
        self.core.confirm_plan(plan["id"])
        self.advance(hours=2)

        resumed = self.core.resume_execution(self.campaign["id"])

        self.assertTrue(resumed["paused"])
        status = self.core.execution_status(self.campaign["id"])
        self.assertEqual(status["state"], "paused")
        self.assertEqual(status["reason"], "confirmation_expired")
        self.assertIn("replacement", status["detail"])
        self.assertEqual(self.mailbox.requests, [])
        self.assertEqual(self.core.list_execution_attempts(self.campaign["id"]), [])
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])

    def test_a_scheduled_confirmation_is_never_executed_as_an_immediate_send(self):
        _, plan = self.proposed(1)
        confirmation_id = self.core.confirm_plan(plan["id"])["proposals"][0]["confirmation_id"]

        with self.assertRaisesRegex(SmartMailError, "scheduling"):
            self.core.run_execution([confirmation_id])

        self.assertEqual(self.mailbox.requests, [])
        self.assertEqual(self.core.list_execution_attempts(self.campaign["id"]), [])
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "idle")
        self.assertEqual(self.core.get_confirmation(confirmation_id)["status"], "active")
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])

    def test_resume_refuses_an_unexpired_scheduled_confirmation(self):
        _, plan = self.proposed(1)
        self.core.confirm_plan(plan["id"])

        with self.assertRaisesRegex(SmartMailError, "scheduling"):
            self.core.resume_execution(self.campaign["id"])

        self.assertEqual(self.mailbox.requests, [])
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "idle")


class PlanPersistenceTests(PlanTestCase):
    def test_configuration_plan_and_confirmations_survive_restart(self):
        preparation_ids, plan = self.proposed(2)
        configuration = self.core.configure_plan(self.campaign["id"])
        confirmed = self.core.confirm_plan(plan["id"])

        with SmartMail(self.home, mailbox=ControlledMailbox(),
                       clock=lambda: self.now) as restarted:
            self.assertEqual(restarted.configure_plan(self.campaign["id"]), configuration)
            self.assertEqual(restarted.get_plan(plan["id"]), confirmed)
            self.assertEqual(restarted.get_plan(plan["id"])["status"], "confirmed")
            self.assertEqual([entry["id"] for entry in restarted.list_plans(self.campaign["id"])],
                             [plan["id"]])
            self.assertEqual(
                [restarted.get_confirmation(proposal["confirmation_id"])["execution"]
                 for proposal in confirmed["proposals"]],
                [{"kind": "scheduled", "scheduled_at": proposal["scheduled_at"],
                  "timezone": SHANGHAI} for proposal in confirmed["proposals"]])
            self.assertEqual(
                [proposal["preparation_id"] for proposal in confirmed["proposals"]],
                preparation_ids)


class TimezoneTests(PlanTestCase):
    def test_the_same_local_window_resolves_to_the_configured_zone(self):
        self.ready_preparations(1)
        window = ["MON-FRI 09:00-10:00"]

        utc = self.core.propose_plan(self.campaign["id"])
        self.configure(timezone=SHANGHAI, windows=window)
        shanghai = self.core.propose_plan(self.campaign["id"])

        self.assertEqual(self.times(utc), ["2026-09-14T09:00:00+00:00"])
        self.assertEqual(self.times(shanghai), ["2026-09-14T09:00:00+08:00"])
        self.assertEqual(shanghai["proposals"][0]["scheduled_utc"], "2026-09-14T01:00:00+00:00")

    def test_the_planned_day_is_the_local_day_of_the_configured_zone(self):
        self.ready_preparations(1)
        # Monday 23:30 UTC is already Tuesday 07:30 in Shanghai.
        self.now = datetime(2026, 9, 14, 23, 30, tzinfo=timezone.utc)
        self.configure(timezone=SHANGHAI, windows=["MON-FRI 09:00-10:00"], horizon_days=1)

        plan = self.core.propose_plan(self.campaign["id"])

        self.assertEqual(self.times(plan), ["2026-09-15T09:00:00+08:00"])

    def test_a_local_wall_time_skipped_by_a_dst_change_is_never_scheduled(self):
        self.ready_preparations(3)
        # America/New_York springs forward at 02:00 on Sunday 14 March 2027.
        self.now = datetime(2027, 3, 14, 5, 0, tzinfo=timezone.utc)
        self.configure(timezone="America/New_York", windows=["SUN 01:00-04:00"],
                       spacing_minutes=60, daily_limit=5, horizon_days=1)

        plan = self.core.propose_plan(self.campaign["id"])

        self.assertEqual(self.times(plan), [
            "2027-03-14T01:00:00-05:00",
            "2027-03-14T03:00:00-04:00",
            "2027-03-14T04:00:00-04:00",
        ])
        self.assertEqual([proposal["scheduled_utc"] for proposal in plan["proposals"]], [
            "2027-03-14T06:00:00+00:00",
            "2027-03-14T07:00:00+00:00",
            "2027-03-14T08:00:00+00:00",
        ])


class TerminalPlanTests(unittest.TestCase):
    """The terminal shell: the same Sending Plan behavior through the command boundary."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "state-terminal"

    def run_cli(self, *arguments, now="2026-09-14T00:00:00+00:00"):
        prefix = [sys.executable, "-m", "smartmail", "--home", str(self.home)]
        if now:
            prefix += ["--now", now]
        return subprocess.run(
            [*prefix, *arguments], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def build_store(self):
        campaign = json.loads(self.run_cli("campaign", "create", "2027 outreach").stdout)
        student = json.loads(self.run_cli(
            "student", "create", "Test Student", "--mailbox", "student@163.com").stdout)
        supervisors = SUPERVISORS[:2]
        rows = [["Example University", name, address, ""] for name, address in supervisors]
        members = [
            ("master.xlsx", master(self.directory / "master.xlsx", rows)),
            ("Test Student - CV.docx",
             document(self.directory / "cv.docx", ["Test Student", "E-mail: student@163.com"])),
        ]
        for index, (name, address) in enumerate(supervisors):
            members.append((f"Example University_{name}.docx", document(
                self.directory / f"draft-{index}.docx",
                draft_paragraphs(address, "Dear Dr,", [DECLARATION]))))
        source = bundle(self.directory / "bundle.zip", members)
        imported = json.loads(self.run_cli(
            "import", str(source), "--campaign", campaign["id"], "--student", student["id"]).stdout)
        preparation_ids = json.loads(
            self.run_cli("prepare", "--import", imported["id"]).stdout)["preparation_ids"]
        for preparation_id in preparation_ids:
            self.run_cli("preparation", "set-subject", preparation_id, SUBJECT)
            slot = json.loads(self.run_cli(
                "preparation", "show", preparation_id).stdout)["attachment_slots"][0]
            self.run_cli("preparation", "confirm", preparation_id, "--slot", slot["id"])
        return campaign, preparation_ids

    def test_terminal_configures_proposes_adjusts_and_confirms_a_plan(self):
        campaign, preparation_ids = self.build_store()
        configured = json.loads(self.run_cli(
            "plan", "configure", "--campaign", campaign["id"], "--timezone", SHANGHAI,
            "--window", "MON-FRI 09:00-10:00", "--spacing", "30", "--daily-limit", "2",
            "--horizon-days", "3").stdout)
        self.assertEqual(configured["timezone"], SHANGHAI)
        self.assertEqual(configured["windows"],
                         [{"days": WEEKDAYS, "start": "09:00", "end": "10:00"}])
        self.assertEqual(json.loads(self.run_cli(
            "plan", "configure", "--campaign", campaign["id"]).stdout), configured)

        proposed = json.loads(self.run_cli("plan", "propose", "--campaign", campaign["id"]).stdout)
        self.assertEqual([proposal["scheduled_at"] for proposal in proposed["proposals"]],
                         ["2026-09-14T09:00:00+08:00", "2026-09-14T09:30:00+08:00"])
        shown = json.loads(self.run_cli("plan", "show", proposed["id"]).stdout)
        self.assertEqual(shown, proposed)
        self.assertIn("Dear Dr,", shown["proposals"][0]["message"])

        adjusted = json.loads(self.run_cli(
            "plan", "adjust", proposed["id"], "--preparation", preparation_ids[0],
            "--time", "2026-09-14T10:00:00").stdout)
        self.assertEqual(adjusted["proposals"][0]["scheduled_at"], "2026-09-14T10:00:00+08:00")

        confirmed = json.loads(self.run_cli("plan", "confirm", proposed["id"]).stdout)
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertTrue(all(entry["confirmation_id"] for entry in confirmed["proposals"]))

        refused = self.run_cli("execution", "run", confirmed["proposals"][0]["confirmation_id"])
        self.assertEqual(refused.returncode, 2)
        self.assertIn("scheduling", json.loads(refused.stderr)["error"])

        listed = json.loads(self.run_cli("plan", "list", "--campaign", campaign["id"]).stdout)
        self.assertEqual([entry["id"] for entry in listed], [proposed["id"]])

    def test_terminal_reports_a_plan_error_as_json_and_exit_code_two(self):
        campaign, preparation_ids = self.build_store()
        proposed = json.loads(self.run_cli("plan", "propose", "--campaign", campaign["id"]).stdout)

        refused = self.run_cli("plan", "adjust", proposed["id"], "--preparation",
                              preparation_ids[0], "--time", "2026-09-19T09:00:00")

        self.assertEqual(refused.returncode, 2)
        self.assertIn("window", json.loads(refused.stderr)["error"])
        missing = self.run_cli("plan", "show", "unknown")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("error", json.loads(missing.stderr))
        bad_time = self.run_cli("plan", "propose", "--campaign", campaign["id"],
                                now="yesterday afternoon")
        self.assertEqual(bad_time.returncode, 2)
        self.assertIn("--now", json.loads(bad_time.stderr)["error"])


if __name__ == "__main__":
    unittest.main()

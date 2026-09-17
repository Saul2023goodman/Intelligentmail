"""Seed a deterministic demo store for the read-only Records evidence workspace.

Run from the repository root:

    python scripts/seed_records_demo.py

The store defaults to ``.smartmail`` (the same default ``npm run dev`` uses);
override it with ``SMARTMAIL_HOME``. The existing SmartMail SQLite store in that
home is replaced so the ledger is reproducible. Every mailbox interaction is
served by ControlledMailbox fixtures, so nothing is ever really sent.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smartmail import SmartMail
from smartmail.mailbox import ControlledMailbox
from tests.test_execution import (
    DECLARATION,
    DRAFT_NAME,
    bundle,
    document,
    draft_paragraphs,
    master,
)

SUBJECT = "PhD supervision enquiry"
STUDENT = "Sipei Yao"
MAILBOX = "student@163.com"


class Clock:
    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> datetime:
        self.now += timedelta(**delta)
        return self.now


def make_ready(core, prep_id: str, subject: str = SUBJECT):
    """Set the subject and confirm the imported CV slot for a Preparation."""
    core.set_subject(prep_id, subject)
    slot = core.get_preparation(prep_id)["attachment_slots"][0]
    core.confirm_attachment(prep_id, slot["id"])
    return core.get_preparation(prep_id)


def scheduled(core, prep_id: str, hours_ahead: int):
    return core.confirm(prep_id, {
        "kind": "scheduled",
        "scheduled_utc": (core._instant() + timedelta(hours=hours_ahead)).isoformat(),
    })


def main() -> None:
    home = Path(os.environ.get("SMARTMAIL_HOME", ROOT / ".smartmail"))
    store = home / "smartmail.sqlite3"
    if store.exists():
        store.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = home / f"smartmail.sqlite3{suffix}"
        if sidecar.exists():
            sidecar.unlink()
    home.mkdir(parents=True, exist_ok=True)

    clock = Clock(datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc))
    core = SmartMail(home, mailbox=ControlledMailbox(), clock=clock)

    campaign_a = core.create_campaign("2027 PhD outreach")
    student = core.create_student(STUDENT, MAILBOX)
    work = ROOT / ".scratch" / "seed"
    work.mkdir(parents=True, exist_ok=True)

    # --- Campaign A: four outreach tasks with a full evidence ledger -------
    rows = [
        ["Example University", "Dr Alex Green", "alex@example.edu", ""],
        ["Example University", "Dr Blair Blue", "blair@example.edu", ""],
        ["Tsinghua University", "Dr Chen Wei", "chen@example.edu", ""],
        ["Peking University", "Dr Erin Tao", "erin@example.edu", ""],
    ]
    cv_path = document(
        work / "cv.docx",
        [STUDENT, "E-mail: student@163.com", "MSc Computer Science, GPA 3.9/4.0"],
    )
    docs = [
        (DRAFT_NAME,
         draft_paragraphs("alex@example.edu", "Dear Dr Green,", [DECLARATION])),
        ("Example University_Dr Blair Blue.docx",
         draft_paragraphs("blair@example.edu", "Dear Dr Blue,",
                          ["I am writing to ask whether you will take a PhD student next year.",
                           DECLARATION])),
        ("Tsinghua University_Dr Chen Wei.docx",
         draft_paragraphs("chen@example.edu", "Dear Prof Chen,", [DECLARATION])),
        ("Peking University_Dr Erin Tao.docx",
         draft_paragraphs("erin@example.edu", "Dear Prof Tao,", [DECLARATION])),
    ]
    members = [("master.xlsx", master(work / "master.xlsx", rows))]
    for index, (name, paragraphs) in enumerate(docs):
        members.append((name, document(work / f"draft-{index}.docx", paragraphs)))
    bundle_path = bundle(work / "bundle.zip", members + [("Sipei Yao - CV.docx", cv_path)])
    imported = core.import_master(campaign_a["id"], student["id"], bundle_path)
    prep_green, prep_blue, prep_chen, prep_tao = \
        core.prepare_from_documents(imported["id"])["preparation_ids"]

    # Task 1: clean immediate send, then a linked follow-up.
    make_ready(core, prep_green)
    core.check_duplicate(prep_green)
    clock.advance(hours=1)
    confirmed_green = core.confirm(prep_green)
    core.run_execution([confirmed_green["id"]])

    core.configure_follow_up_rule(
        campaign_a["id"],
        delay_days=0,
        maximum_count=2,
        subject_template="Re: {original_subject}",
        body_template=(
            "Dear {supervisor_name},\n\nThank you for considering my enquiry. I would be glad "
            "to share more details about my background.\n\nBest regards,\n{student_name}"
        ),
    )
    clock.advance(days=2)
    [follow_action] = core.prepare_follow_ups(campaign_a["id"])
    follow_confirmation = core.confirm(follow_action["preparation_id"])
    clock.advance(hours=3)
    core.run_execution([follow_confirmation["id"]])

    # Task 2: v1 authorized then Rewritten; v2 is the version that sent.
    make_ready(core, prep_blue)
    clock.advance(hours=1)
    core.confirm(prep_blue)
    clock.advance(hours=2)
    blue_source = core.get_preparation(prep_blue)["source"]["id"]
    prep_blue_v2 = core.rewrite(prep_blue, blue_source)["id"]
    make_ready(core, prep_blue_v2, subject="PhD supervision enquiry (updated materials)")
    confirmed_blue_v2 = core.confirm(prep_blue_v2)
    clock.advance(hours=2)
    core.run_execution([confirmed_blue_v2["id"]])

    # Task 3: an external schedule that is later Replaced (Task 4's Preparation).
    core.mailbox = ControlledMailbox(allow_schedule=True)
    make_ready(core, prep_chen)
    scheduled_chen = scheduled(core, prep_chen, hours_ahead=96)
    clock.advance(hours=1)
    schedule_one = core.place_schedule(scheduled_chen["id"])["schedule"]["id"]

    # Task 4: its confirmed schedule replaces Task 3's, then is itself Cancelled.
    make_ready(core, prep_tao)
    scheduled_tao = scheduled(core, prep_tao, hours_ahead=144)
    clock.advance(hours=2)
    replacement = core.confirm_schedule_replacement(schedule_one, scheduled_tao["id"])
    core.mailbox = ControlledMailbox(
        schedule_outcomes=["scheduled"], cancel_outcomes=["removed"], allow_schedule=True)
    core.run_schedule_replacement(replacement["confirmation"]["id"])
    task_tao = core.get_preparation(prep_tao)["task_id"]
    schedule_two = next(
        item["id"] for item in core.list_external_schedules(task_id=task_tao)
        if item["replaces_schedule_id"] == schedule_one
    )

    clock.advance(hours=5)
    core.mailbox = ControlledMailbox(cancel_outcomes=["removed"], allow_schedule=True)
    cancellation = core.confirm_schedule_cancellation(schedule_two)
    core.run_schedule_cancellation(cancellation["confirmation"]["id"])

    # External observation: the mailbox shows both sends and an inbound reply.
    clock.advance(days=1)
    observation = {
        "status": "complete",
        "mailbox_address": MAILBOX,
        "observed_at": clock.now.isoformat(),
        "detail": "controlled first-page observation",
        "coverage": {
            "complete": False,
            "folders": [
                {"folder": "inbox", "page_scope": "first_visible_page",
                 "pages_observed": 1, "messages_observed": 1, "complete": False},
                {"folder": "sent", "page_scope": "first_visible_page",
                 "pages_observed": 1, "messages_observed": 2, "complete": False},
            ],
        },
        "messages": [
            {"direction": "inbound", "folder": "inbox", "platform_reference": "in-91",
             "counterpart": "alex@example.edu", "subject": "Re: PhD supervision enquiry",
             "observed_time": "2026年9月11日 14:00", "status": "received",
             "evidence": {"aria_label": "Re: PhD supervision enquiry 发件人 ： Dr Green 时间： ..."}},
            {"direction": "outbound", "folder": "sent", "platform_reference": "out-91",
             "counterpart": "alex@example.edu", "subject": SUBJECT,
             "observed_time": "2026年9月8日 12:00", "status": "sent",
             "evidence": {"aria_label": "PhD supervision enquiry 收件人 ： alex 时间： ...",
                          "marker": "发送成功"}},
            {"direction": "outbound", "folder": "sent", "platform_reference": "out-92",
             "counterpart": "blair@example.edu",
             "subject": "PhD supervision enquiry (updated materials)",
             "observed_time": "2026年9月8日 18:00", "status": "sent",
             "evidence": {"marker": "发送成功"}},
        ],
    }
    core.mailbox = ControlledMailbox(observations=[observation])
    core.refresh_mailbox(student["id"])
    core.check_duplicate(prep_green)

    # --- Campaign B: an unresolved unknown outcome pauses the flow --------
    campaign_b = core.create_campaign("2028 winter round")
    rows_b = [["Oxford University", "Dr Dana Reid", "dana@example.edu", ""]]
    members_b = [
        ("master.xlsx", master(work / "master-b.xlsx", rows_b)),
        ("Oxford University_Dr Dana Reid.docx",
         document(work / "reid.docx",
                  draft_paragraphs("dana@example.edu", "Dear Dr Reid,", [DECLARATION]))),
        ("Sipei Yao - CV.docx", cv_path),
    ]
    bundle_b = bundle(work / "bundle-b.zip", members_b)
    imported_b = core.import_master(campaign_b["id"], student["id"], bundle_b)
    [prep_reid] = core.prepare_from_documents(imported_b["id"])["preparation_ids"]
    make_ready(core, prep_reid)
    core.mailbox = ControlledMailbox(["unknown"])
    confirmed_reid = core.confirm(prep_reid)
    clock.advance(hours=4)
    core.run_execution([confirmed_reid["id"]])

    core.__exit__(None, None, None)
    print(f"Seeded records store at {home}")
    print(f"  Campaigns: {campaign_a['name']}, {campaign_b['name']}")
    print("  Open the Records page (#records) and select a task to inspect the lineage.")


if __name__ == "__main__":
    main()

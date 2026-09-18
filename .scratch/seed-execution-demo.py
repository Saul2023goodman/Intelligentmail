"""Seed the dev store with a two-institution campaign so the timeline grid has shape."""
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from smartmail import SmartMail  # noqa: E402

HOME = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "frontend" / ".smartmail"
TMP = ROOT / ".scratch" / "seed-out"
TMP.mkdir(parents=True, exist_ok=True)

HEADERS = ["大学", "导师", "邮箱📮", "URL"]
DECLARATION = ("I have attached my CV and would welcome the opportunity to discuss "
               "my background.")
SUBJECT = "PhD supervision enquiry"
ADVISORS = [
    ("River University", "Dr Alex Green", "alex@river.edu"),
    ("River University", "Dr Blair Blue", "blair@river.edu"),
    ("River University", "Dr Casey Cyan", "casey@river.edu"),
    ("Hill College", "Dr Dana Dove", "dana@hill.edu"),
    ("Hill College", "Dr Ellis Elm", "ellis@hill.edu"),
    ("Hill College", "Dr Fran Fern", "fran@hill.edu"),
    ("Hill College", "Dr Gale Gray", "gale@hill.edu"),
]


def document(path, paragraphs):
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'
        for text in paragraphs)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{namespace}"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return path


def draft_paragraphs(recipient):
    lines = [f"Email: {recipient}", "", "", "", "Dear Dr,", "", DECLARATION,
             "", "Yours sincerely,", "Sipei Yao"]
    return lines


def master(path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    for school, name, address in ADVISORS:
        sheet.append([school, name, address, ""])
    workbook.save(path)
    workbook.close()
    return path


def bundle(path, members):
    with zipfile.ZipFile(path, "w") as archive:
        for name, item in members:
            archive.write(item, name)
    return path


with SmartMail(HOME) as core:
    student = core.create_student("Pacing Demo", "demo@163.com")
    campaign_id = student["campaign_id"]

    master_path = master(TMP / "master.xlsx")
    cv_path = document(TMP / "cv.docx", ["Pacing Demo", "E-mail: demo@163.com"])
    members = [("master.xlsx", master_path), ("Pacing Demo - CV.docx", cv_path)]
    for index, (school, name, address) in enumerate(ADVISORS):
        members.append((f"{school}_{name}.docx",
                        document(TMP / f"draft-{index}.docx", draft_paragraphs(address))))
    source = bundle(TMP / "bundle.zip", members)

    imported = core.import_master(campaign_id, student["id"], source)
    preparation_ids = core.prepare_from_documents(imported["id"])["preparation_ids"]
    for preparation_id in preparation_ids:
        core.set_subject(preparation_id, SUBJECT)
        slot = core.get_preparation(preparation_id)["attachment_slots"][0]
        core.confirm_attachment(preparation_id, slot["id"])

    configured = core.configure_plan(
        campaign_id, timezone="Asia/Shanghai",
        windows=["MON-FRI 09:00-10:00"], spacing_minutes=15,
        daily_limit=9, horizon_days=6, institution_limit=1)
    plan = core.propose_plan(campaign_id)

    print("campaign", campaign_id)
    print("student", student["id"])
    print("config", configured)
    print("preparations", len(preparation_ids))
    for proposal in plan["proposals"]:
        print(f"  {proposal['scheduled_at'][:16]}  {proposal['institution_name']:20s} "
              f"{proposal['supervisor_name']}")
    print("impossible", len(plan["impossible"]), "unavailable", len(plan["unavailable"]))

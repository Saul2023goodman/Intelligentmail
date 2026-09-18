import sys, tempfile, zipfile
from pathlib import Path
sys.path.insert(0, '.')
from smartmail import SmartMail
from tests.test_recognition import docx_bytes, DRAFT_WITHOUT_ENVELOPE

home = Path(tempfile.mkdtemp()) / "store"
core = SmartMail(home)
campaign = core.create_campaign("No-master flow")
student = core.create_student("Shen Hui", "shenhui@163.com")

# Single name-only draft, no master workbook at all
tmp = Path(tempfile.mkdtemp())
draft = tmp / "Ping Tan.docx"
draft.write_bytes(docx_bytes(DRAFT_WITHOUT_ENVELOPE))
setzip = tmp / "set.zip"
with zipfile.ZipFile(setzip, "w") as z:
    z.write(draft, "Ping Tan.docx")

imported = core.import_source_set(campaign["id"], student["id"], setzip, master_name="")
print("rows:", imported["summary"]["rows"], "tasks:", len(imported["task_ids"]))
prepared = core.prepare_from_documents(imported["id"])
print("preparations:", prepared["preparation_ids"])
task = core.report_task(core.list_tasks(campaign["id"])[0]["id"])
print("supervisor:", task["task"]["supervisor"]["name"], task["task"]["supervisor"]["addresses"])
print("institution:", repr(task["task"]["institution"]["name"]))
print("exceptions:", [e["code"] for e in task["task"]["exceptions"]])
p = core.get_preparation(prepared["preparation_ids"][0])
print("prep recipient:", repr(p["recipient"]), "body starts:", p["body"][:40])
print("readiness:", [f["code"] for f in p["readiness_findings"] if f["blocking"]])

# multi-bundle without master: build small bundle docx
bundle = tmp / "letters.docx"
paragraphs = [
    "2.", "Daniel Lock — Loughborough University London",
    "Subject: PhD Application Fall 2027 — Junhao Jiao｜Sports",
    "Dear Prof. Lock,",
    "I hope this email finds you well. My name is Junhao Jiao and I am writing to express interest.",
    "Your work is inspiring. My CV is attached.",
    "Yours sincerely,", "Junhao Jiao",
    "📧 monica.chien@example.edu",
    "3.", "Monica Chien — University of Queensland",
    "Subject: PhD Application — Consumer Behaviour",
    "Dear Prof. Chien,",
    "I hope this email finds you well. My name is Junhao Jiao and I am writing to inquire.",
    "Your research resonates. My CV is attached.",
    "Yours sincerely,", "Junhao Jiao",
]
bundle.write_bytes(docx_bytes(paragraphs))
bzip = tmp / "bundle-set.zip"
with zipfile.ZipFile(bzip, "w") as z:
    z.write(bundle, "letters.docx")
campaign2 = core.create_campaign("Bundle flow")
student2 = core.create_student("Junhao Jiao", "junhao@163.com")
imported2 = core.import_source_set(campaign2["id"], student2["id"], bzip, master_name="")
prepared2 = core.prepare_from_documents(imported2["id"])
print("\nbundle preps:", len(prepared2["preparation_ids"]), prepared2["unassociated_source_ids"])
for t in core.list_tasks(campaign2["id"]):
    r = core.report_task(t["id"])
    print(" -", r["task"]["supervisor"]["name"], "|", r["task"]["institution"]["name"],
          "|", r["task"]["supervisor"]["addresses"])
for pid in prepared2["preparation_ids"]:
    p = core.get_preparation(pid)
    print("  subj:", repr(p["subject"]), "| findings:", [f["code"] for f in p["readiness_findings"] if f["blocking"]])
print("bundle findings:", [(f["code"], f["source"]["name"]) for f in core.list_unassociated_documents(imported2["id"])])

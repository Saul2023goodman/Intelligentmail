"""Read-side intake workspace and bounded browser-upload import commands.

The UI may transport bytes, but supported-pattern recognition, source retention,
Task creation and Preparation association remain Core operations.
"""

import base64
import binascii
import tempfile
from pathlib import Path, PurePath
from zipfile import ZIP_DEFLATED, ZipFile

from .errors import SmartMailError


MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_UPLOAD_FILES = 100


def intake_workspace(core, campaign_id=None, student_id=None):
    campaigns = core.list_campaigns()
    students = core.list_students()
    mailboxes = core.list_mailboxes()
    if campaign_id:
        campaign = core.get_campaign(campaign_id)
    else:
        campaign = campaigns[0] if campaigns else None
        campaign_id = campaign["id"] if campaign else None
    if student_id:
        student = core.get_student(student_id)
    else:
        student = students[0] if students else None
        student_id = student["id"] if student else None

    imports = []
    source_categories = {}
    if campaign_id:
        for imported in core.list_imports(campaign_id):
            if student_id and imported["student_id"] != student_id:
                continue
            full = core.get_import(imported["id"])
            findings = core.list_unassociated_documents(imported["id"])
            imports.append({**full, "findings": findings})
            for source in full["sources"]:
                source_categories[source["id"]] = _source_category(core, source)

    tasks = []
    if campaign_id:
        for task in core.list_tasks(campaign_id):
            if student_id and task["student_id"] != student_id:
                continue
            tasks.append(core.report_task(task["id"]))

    return {
        "campaigns": campaigns,
        "students": [
            {**entry,
             "mailbox": next((mailbox["address"] for mailbox in mailboxes
                              if mailbox["student_id"] == entry["id"]), "")}
            for entry in students
        ],
        "campaign": campaign,
        "student": student,
        "imports": imports,
        "source_categories": source_categories,
        "tasks": tasks,
    }


def import_uploaded_sources(core, campaign_id, student_id, files):
    """Import one browser-selected source set, then run supported Preparation mapping."""
    core.get_campaign(campaign_id)
    core.get_student(student_id)
    if not isinstance(files, list) or not files or len(files) > MAX_UPLOAD_FILES:
        raise SmartMailError(f"Select between 1 and {MAX_UPLOAD_FILES} source files")

    decoded = []
    total = 0
    names = set()
    for item in files:
        if not isinstance(item, dict):
            raise SmartMailError("Each uploaded source must include a name and content")
        name = item.get("name")
        content = item.get("content")
        if not isinstance(name, str) or not name.strip() or not isinstance(content, str):
            raise SmartMailError("Each uploaded source must include a name and content")
        safe_name = PurePath(name.replace("\\", "/")).name
        if safe_name != name.replace("\\", "/") or safe_name in (".", ".."):
            raise SmartMailError(f"Use a plain source filename without folders: {name}")
        key = safe_name.casefold()
        if key in names:
            raise SmartMailError(f"Source filenames must be unique: {safe_name}")
        names.add(key)
        try:
            payload = base64.b64decode(content, validate=True)
        except (binascii.Error, ValueError) as error:
            raise SmartMailError(f"Uploaded source is not valid base64: {safe_name}") from error
        total += len(payload)
        if total > MAX_UPLOAD_BYTES:
            raise SmartMailError("The selected source set exceeds the 25 MB intake limit")
        decoded.append((safe_name, payload))

    with tempfile.TemporaryDirectory(prefix="smartmail-intake-") as directory:
        root = Path(directory)
        if len(decoded) == 1 and Path(decoded[0][0]).suffix.casefold() in (".zip", ".xlsx"):
            source_path = root / decoded[0][0]
            source_path.write_bytes(decoded[0][1])
        else:
            source_path = root / "browser-sources.zip"
            with ZipFile(source_path, "w", ZIP_DEFLATED) as archive:
                for name, payload in decoded:
                    archive.writestr(name, payload)
        imported = core.import_master(campaign_id, student_id, source_path)
        prepared = core.prepare_from_documents(imported["id"])

    return {
        "import": imported,
        "preparation": prepared,
        "workspace": intake_workspace(core, campaign_id, student_id),
    }


def _source_category(core, source):
    name = source["name"].casefold()
    if name.endswith((".xlsx", ".csv")):
        return "master"
    preparation = core._db.execute(
        "SELECT 1 FROM preparations WHERE source_id = ?", (source["id"],)).fetchone()
    if preparation:
        return "drafts"
    candidate = core._db.execute(
        "SELECT 1 FROM attachment_slots WHERE suggested_source_id = ?", (source["id"],)).fetchone()
    if candidate:
        return "attachments"
    finding = core._db.execute(
        "SELECT 1 FROM document_findings WHERE source_id = ?", (source["id"],)).fetchone()
    if finding:
        return "unresolved"
    if name.endswith((".docx", ".pdf")):
        return "attachments"
    return "records"

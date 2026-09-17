"""Read-side intake workspace and bounded browser-upload import commands.

The UI may transport bytes, but supported-pattern recognition, source retention,
Task creation and Preparation association remain Core operations.
"""

import base64
import binascii
import json
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

from .errors import SmartMailError
from .recognition import BUNDLE, TYPE_PROFILES, recognize_bytes, recognize_collection


MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_UPLOAD_FILES = 100

#: Maps a recognized source type onto the intake board's stable categories.
#: Material that creates or feeds outreach work lands on master/drafts/
#: attachments/records; everything reference-only or unresolved stays on the
#: unresolved column instead of being promoted by its file extension.
RECOGNITION_CATEGORY = {
    "supervisor_master": "master",
    "outreach_draft": "drafts",
    "multi_draft_bundle": "drafts",
    "bulk_import": "drafts",
    "applicant_cv": "attachments",
    "tracking_sheet": "records",
    "scholar_cv": "unresolved",
    "program_reference": "unresolved",
    "planning_document": "unresolved",
    "maintenance_log": "unresolved",
    "unrelated": "unresolved",
    "unknown": "unresolved",
    "ambiguous": "unresolved",
    "bundle": "unresolved",
}


def decode_uploads(files):
    """Validate and base64-decode browser uploads into (name, bytes) pairs."""
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
        safe_name = PurePosixPath(name.replace("\\", "/")).name
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
        decoded.append({"name": safe_name, "data": payload,
                        "revised_type": item.get("type") if isinstance(item.get("type"), str) else None})
    return decoded


def recognize_uploaded_sources(core, files):
    """Classify browser-selected files from structural evidence, without importing."""
    decoded = decode_uploads(files)
    collection = recognize_collection([(item["name"], item["data"]) for item in decoded])
    return collection


def _compact_detail(result, effective_type=None):
    """The persisted recognition detail: identity hints, never full letter bodies."""
    effective_type = effective_type or result["type"]
    profile = TYPE_PROFILES.get(effective_type, TYPE_PROFILES["unknown"])
    identities = result.get("identities") or {}
    compact = {"label": profile["label"], "actionable": bool(profile["actionable"])}
    if result["type"] in ("outreach_draft",):
        compact["identities"] = {
            key: identities.get(key) for key in ("student", "subject") if identities.get(key)}
        addressee = identities.get("addressee") or {}
        if addressee.get("name") or addressee.get("email"):
            compact["identities"]["addressee"] = {
                key: addressee.get(key) for key in ("name", "email") if addressee.get(key)}
    elif result["type"] in ("applicant_cv", "scholar_cv"):
        compact["identities"] = {
            key: identities.get(key)
            for key in ("person", "cv_role", "contact_email") if identities.get(key)}
    elif result["type"] == "supervisor_master":
        compact["identities"] = {
            key: identities.get(key) for key in ("row_count", "email_count") if identities.get(key)}
    elif result["type"] == "bulk_import":
        compact["identities"] = {
            key: identities.get(key) for key in ("row_count", "recipient_count") if identities.get(key)}
    elif result["type"] == "multi_draft_bundle":
        compact["identities"] = {"student": identities.get("student", ""),
                                 "segment_count": len(result.get("segments") or [])}
    return compact


def _recognition_by_sha(decoded):
    """Flatten upload recognition (including zip members) keyed by content hash."""
    by_sha = {}
    revisions = {}
    for item in decoded:
        result = recognize_bytes(item["name"], item["data"])
        results = result.get("members") if result["type"] == BUNDLE else [result]
        for member in results:
            by_sha[member["sha256"]] = member
        if item["revised_type"]:
            revisions[result["sha256"]] = item["revised_type"]
    return by_sha, revisions


def _persist_recognition(core, import_id, by_sha, revisions):
    for source in core.get_import(import_id)["sources"]:
        result = by_sha.get(source["sha256"])
        if result is None:
            continue
        recognized = result["type"]
        revised_type = revisions.get(source["sha256"])
        effective = revised_type if revised_type in TYPE_PROFILES and revised_type != recognized else recognized
        core._db.execute(
            "INSERT INTO source_recognition "
            "(source_id, recognized_type, effective_type, confidence, revised, reasons, cautions, detail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source_id) DO UPDATE SET "
            "recognized_type = excluded.recognized_type, effective_type = excluded.effective_type, "
            "confidence = excluded.confidence, revised = excluded.revised, "
            "reasons = excluded.reasons, cautions = excluded.cautions, detail = excluded.detail",
            (source["id"], recognized, effective, result.get("confidence", "low"),
             1 if effective != recognized else 0,
             json.dumps(result.get("reasons", []), ensure_ascii=False),
             json.dumps(result.get("cautions", []), ensure_ascii=False),
             json.dumps(_compact_detail(result, effective), ensure_ascii=False)))
    core._db.commit()


def intake_workspace(core, campaign_id=None, student_id=None):
    campaigns = core.list_campaigns()
    students = core.list_students()
    mailboxes = core.list_mailboxes()
    student = core.get_student(student_id) if student_id else (students[0] if students else None)
    student_id = student["id"] if student else None
    if campaign_id:
        campaign = core.get_campaign(campaign_id)
    elif student is not None:
        # One Student owns exactly one Campaign, so the Student selects the intake scope.
        campaign = core.get_campaign(student["campaign_id"]) if student["campaign_id"] else None
        campaign_id = campaign["id"] if campaign else None
    else:
        campaign = campaigns[0] if campaigns else None
        campaign_id = campaign["id"] if campaign else None

    imports = []
    source_categories = {}
    source_recognition = {}
    if campaign_id:
        for imported in core.list_imports(campaign_id):
            if student_id and imported["student_id"] != student_id:
                continue
            full = core.get_import(imported["id"])
            findings = core.list_unassociated_documents(imported["id"])
            imports.append({**full, "findings": findings})
            for source in full["sources"]:
                annotation = _recognition_annotation(core, source["id"])
                if annotation is not None:
                    source_recognition[source["id"]] = annotation
                    source_categories[source["id"]] = RECOGNITION_CATEGORY.get(
                        annotation["type"], "unresolved")
                else:
                    source_categories[source["id"]] = _legacy_category(core, source)

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
        "source_recognition": source_recognition,
        "tasks": tasks,
    }


def import_uploaded_sources(core, campaign_id, student_id, files):
    """Import one browser-selected source set, then run supported Preparation mapping."""
    core.get_campaign(campaign_id)
    core.get_student(student_id)
    decoded = decode_uploads(files)
    pairs = [(item["name"], item["data"]) for item in decoded]

    with tempfile.TemporaryDirectory(prefix="smartmail-intake-") as directory:
        root = Path(directory)
        if len(pairs) == 1 and Path(pairs[0][0]).suffix.casefold() in (".zip", ".xlsx"):
            source_path = root / pairs[0][0]
            source_path.write_bytes(pairs[0][1])
        else:
            source_path = root / "browser-sources.zip"
            with ZipFile(source_path, "w", ZIP_DEFLATED) as archive:
                for name, payload in pairs:
                    archive.writestr(name, payload)
        imported = core.import_master(campaign_id, student_id, source_path)
        prepared = core.prepare_from_documents(imported["id"])
        by_sha, revisions = _recognition_by_sha(decoded)
        _persist_recognition(core, imported["id"], by_sha, revisions)

    return {
        "import": imported,
        "preparation": prepared,
        "workspace": intake_workspace(core, campaign_id, student_id),
    }


def _recognition_annotation(core, source_id):
    row = core._db.execute(
        "SELECT recognized_type, effective_type, confidence, revised, reasons, cautions, detail "
        "FROM source_recognition WHERE source_id = ?", (source_id,)).fetchone()
    if row is None:
        return None
    try:
        detail = json.loads(row["detail"])
    except (ValueError, TypeError):
        detail = {}

    def _loads(value):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return []

    return {"type": row["effective_type"], "recognized_type": row["recognized_type"],
            "confidence": row["confidence"], "revised": bool(row["revised"]),
            "reasons": _loads(row["reasons"]), "cautions": _loads(row["cautions"]),
            **detail}


def _legacy_category(core, source):
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

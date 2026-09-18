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
from .intake import read_archive_members
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
    """Validate and base64-decode browser uploads into structured selection items.

    Every reviewed file carries an ``included`` decision; zip files carry the
    per-member ``members`` decisions from the expanded recognition review.
    """
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
        members = item.get("members")
        if members is not None and not isinstance(members, list):
            raise SmartMailError("Zip member selections must be a list")
        decoded.append({
            "name": safe_name,
            "data": payload,
            "included": bool(item.get("included", True)),
            "revised_type": item.get("type") if isinstance(item.get("type"), str) else None,
            "members": members,
        })
    return decoded


def _selected_members(item):
    """Expand one reviewed upload into its approved (name, bytes, revised) members."""
    name, data = item["name"], item["data"]
    if name.lower().endswith(".zip"):
        try:
            archive_members = read_archive_members(data)
        except Exception as error:
            raise SmartMailError(f"Cannot expand archive {name}: {error}") from error
        selections = item.get("members")
        if isinstance(selections, list) and selections:
            chosen = {
                PurePosixPath(str(choice.get("name", "")).replace("\\", "/")).name:
                    choice.get("type") if isinstance(choice.get("type"), str) else None
                for choice in selections if isinstance(choice, dict)}
        else:
            chosen = {member_name: None for member_name, _member_data in archive_members}
        expanded = []
        for member_name, member_data in archive_members:
            if member_name in chosen:
                expanded.append((member_name, member_data, chosen[member_name]))
        return expanded
    return [(name, data, item.get("revised_type"))]


def _all_members(item):
    """Every supported member of one reviewed upload (zip expanded, else itself)."""
    if item["name"].lower().endswith(".zip"):
        return [(member_name, member_data, item["name"])
                for member_name, member_data in read_archive_members(item["data"])]
    return [(item["name"], item["data"], "")]


def recognize_uploaded_sources(core, files):
    """Classify browser-selected files from structural evidence, without importing.

    Zip archives are transport: the response flattens every supported member
    into its own classified row keyed by ``container``; no source is retained.
    """
    decoded = decode_uploads(files)
    pairs = []
    containers = {}
    for item in decoded:
        for member_name, member_data, container in _all_members(item):
            pairs.append((member_name, member_data))
            containers[member_name] = container
    collection = recognize_collection(pairs)
    for source in collection["sources"]:
        source["container"] = containers.get(source["name"], "")
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


def _recognition_by_sha(members):
    """Recognize flattened import members and key results by content hash."""
    by_sha = {}
    revisions = {}
    for name, data, revised_type in members:
        result = recognize_bytes(name, data)
        by_sha[result["sha256"]] = result
        if revised_type and revised_type in TYPE_PROFILES and revised_type != result["type"]:
            revisions[result["sha256"]] = revised_type
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

    tasks = _task_summaries(core, campaign_id, student_id) if campaign_id else []

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


def _task_summaries(core, campaign_id, student_id):
    """Return only the fields needed by the intake task list.

    Full message bodies, source evidence, Exceptions and attachment metadata are
    deliberately left to the existing per-Task drill-down command.
    """
    report = core.operations_report(campaign_id, student_id=student_id)
    summaries = []
    for row in report["tasks"]:
        addresses = [entry["address"] for entry in core._db.execute(
            "SELECT address FROM supervisor_addresses WHERE supervisor_id = ? ORDER BY address",
            (row["supervisor_id"],))]
        preparation = core._db.execute(
            "SELECT p.id, p.subject, src.name AS source_name, "
            "(SELECT count(*) FROM attachments a JOIN attachment_slots s ON s.id = a.slot_id "
            " WHERE s.preparation_id = p.id) AS attachment_count "
            "FROM preparations p JOIN sources src ON src.id = p.source_id "
            "WHERE p.task_id = ? AND p.superseded_by IS NULL ORDER BY p.rowid DESC LIMIT 1",
            (row["task_id"],)).fetchone()
        summaries.append({
            "task_id": row["task_id"],
            "supervisor_name": row["supervisor_name"],
            "institution_name": row["institution_name"],
            "recipient_addresses": addresses,
            "message_status": row["message_status"],
            "preparation": dict(preparation) if preparation else None,
        })
    return summaries


def import_uploaded_sources(core, campaign_id, student_id, files):
    """Import the reviewed source set, expanding archives into their members.

    The supervisor master workbook is optional: when none is selected, draft
    letters establish their own Outreach Tasks in prepare_from_documents.
    """
    core.get_campaign(campaign_id)
    core.get_student(student_id)
    decoded = decode_uploads(files)
    included = [item for item in decoded if item["included"]]
    if not included:
        raise SmartMailError("Select at least one source to import")
    members = []
    seen_names = set()
    for item in included:
        for name, data, revised_type in _selected_members(item):
            if name in seen_names:
                raise SmartMailError(
                    f"Member name {name} occurs in more than one archive; rename it first")
            seen_names.add(name)
            members.append((name, data, revised_type))
    if not members:
        raise SmartMailError("The selected archives contain no supported members")
    effective_master = ""
    master_workbooks = 0
    for name, data, revised in members:
        if not name.lower().endswith(".xlsx"):
            continue
        effective_type = revised or recognize_bytes(name, data)["type"]
        if effective_type == "supervisor_master":
            effective_master = name
            master_workbooks += 1
        elif effective_type in ("unknown", "ambiguous"):
            raise SmartMailError(f"Resolve the type of {name} before importing")
    if master_workbooks > 1:
        raise SmartMailError(
            "Include one supervisor master workbook per import; exclude or revise the others")

    with tempfile.TemporaryDirectory(prefix="smartmail-intake-") as directory:
        root = Path(directory)
        if len(members) == 1 and members[0][0].lower().endswith(".xlsx"):
            source_path = root / members[0][0]
            source_path.write_bytes(members[0][1])
        else:
            source_path = root / "browser-sources.zip"
            with ZipFile(source_path, "w", ZIP_DEFLATED) as archive:
                for name, data, _revised in members:
                    archive.writestr(name, data)
        imported = core.import_source_set(
            campaign_id, student_id, source_path,
            master_name=effective_master or "")
        prepared = core.prepare_from_documents(imported["id"])
        by_sha, revisions = _recognition_by_sha(members)
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

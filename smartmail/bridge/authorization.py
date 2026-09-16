"""Recheck persisted Confirmation without initializing or recovering the store."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from ..snapshots import content_digest, attachments_digest
from . import BridgeError


#: Operation -> the kind recorded in the Confirmation's execution detail.
EXTERNAL_OPERATION_KINDS = {
    "submit": "immediate",
    "schedule": "scheduled",
    "cancel_schedule": "cancellation",
    "recall": "recall",
}


def validate_command(home, operation, payload):
    """Dispatch a transport permit check to the matching persisted authority."""
    if operation == "submit":
        validate_submission(home, payload)
    elif operation == "schedule":
        validate_schedule(home, payload)
    elif operation == "cancel_schedule":
        validate_external_operation(home, payload, "cancellation")
    elif operation == "recall":
        validate_external_operation(home, payload, "recall")
    else:
        raise BridgeError(f"Unsupported permit operation: {operation}")


def _load_authorized_attempt(home, payload):
    """Shared persisted identity checks for every single-click external permit."""
    binding = payload.get("binding", {})
    request = {key: value for key, value in payload.items() if key != "binding"}
    path = Path(home).resolve() / "smartmail.sqlite3"
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        attempt = db.execute("SELECT * FROM execution_attempts WHERE id = ?",
                             (binding.get("attempt_id"),)).fetchone()
        if (not attempt or attempt["state"] != "in_progress"
                or attempt["confirmation_id"] != binding.get("confirmation_id")
                or json.loads(attempt["request"]) != request):
            raise BridgeError("Operation no longer matches an active Execution Attempt")
        confirmation = db.execute("SELECT * FROM confirmations WHERE id = ?",
                                  (attempt["confirmation_id"],)).fetchone()
        preparation = db.execute("SELECT * FROM preparations WHERE id = ?",
                                 (attempt["preparation_id"],)).fetchone()
        if not confirmation or confirmation["status"] != "active":
            raise BridgeError("Confirmation is no longer active")
        if db.execute("SELECT 1 FROM execution_flow f JOIN tasks t ON t.campaign_id = f.campaign_id "
                      "WHERE t.id = ? AND f.state = 'paused'",
                      (attempt["task_id"],)).fetchone():
            raise BridgeError("Execution Flow is paused")
        return db, attempt, confirmation, preparation, request


def validate_submission(home, payload):
    binding = payload.get("binding", {})
    request = {key: value for key, value in payload.items() if key != "binding"}
    path = Path(home).resolve() / "smartmail.sqlite3"
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            attempt = db.execute("SELECT * FROM execution_attempts WHERE id = ?",
                                 (binding.get("attempt_id"),)).fetchone()
            if (not attempt or attempt["state"] != "in_progress"
                    or attempt["confirmation_id"] != binding.get("confirmation_id")
                    or json.loads(attempt["request"]) != request):
                raise BridgeError("Submission no longer matches an active Execution Attempt")
            confirmation = db.execute("SELECT * FROM confirmations WHERE id = ?",
                                      (attempt["confirmation_id"],)).fetchone()
            preparation = db.execute("SELECT * FROM preparations WHERE id = ?",
                                     (attempt["preparation_id"],)).fetchone()
            if not confirmation or confirmation["status"] != "active" or not preparation or preparation["superseded_by"]:
                raise BridgeError("Confirmation is no longer active")
            if (content_digest(preparation) != confirmation["content_digest"]
                    or content_digest(request) != confirmation["content_digest"]):
                raise BridgeError("Preparation content changed after Confirmation")
            attachments = [dict(row) for row in db.execute(
                "SELECT s.label, a.name, a.sha256, length(a.content) AS size FROM attachment_slots s "
                "JOIN attachments a ON a.slot_id = s.id WHERE s.preparation_id = ? ORDER BY s.rowid",
                (preparation["id"],))]
            if attachments_digest(attachments) != confirmation["attachments_digest"] or attachments != request["attachments"]:
                raise BridgeError("Attachments changed after Confirmation")
            if db.execute("SELECT 1 FROM readiness_findings WHERE preparation_id = ? AND blocking = 1",
                          (preparation["id"],)).fetchone():
                raise BridgeError("Preparation now has a Blocker")
            if db.execute("SELECT 1 FROM sent_records WHERE preparation_id = ?", (preparation["id"],)).fetchone():
                raise BridgeError("Preparation has already been sent")
            if db.execute("SELECT 1 FROM execution_flow f JOIN tasks t ON t.campaign_id = f.campaign_id "
                          "WHERE t.id = ? AND f.state = 'paused'", (attempt["task_id"],)).fetchone():
                raise BridgeError("Execution Flow is paused")
            execution = json.loads(confirmation["execution_detail"])
            if execution.get("kind") != "immediate":
                raise BridgeError("Only immediate Confirmation can grant a submission permit")
            expiry = next((execution.get(key) for key in (
                "expires_at", "valid_until", "confirmation_expires_at", "confirmed_until", "confirmed_time"
            ) if execution.get(key)), None)
            if expiry:
                parsed = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
                parsed = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
                if parsed <= datetime.now(timezone.utc):
                    raise BridgeError("Confirmation expired before extension submission")
    except (sqlite3.Error, KeyError, TypeError, ValueError) as error:
        raise BridgeError(f"Cannot authorize extension submission: {error}") from error


def validate_schedule(home, payload):
    """Grant a schedule placement permit only for a confirmed future native schedule."""
    try:
        with closing(sqlite3.connect(
                (Path(home).resolve() / "smartmail.sqlite3").as_uri() + "?mode=ro",
                uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            binding = payload.get("binding", {})
            request = {key: value for key, value in payload.items() if key != "binding"}
            attempt = db.execute("SELECT * FROM execution_attempts WHERE id = ?",
                                 (binding.get("attempt_id"),)).fetchone()
            if (not attempt or attempt["state"] != "in_progress"
                    or attempt["confirmation_id"] != binding.get("confirmation_id")
                    or json.loads(attempt["request"]) != request):
                raise BridgeError("Schedule placement no longer matches an active Execution Attempt")
            confirmation = db.execute("SELECT * FROM confirmations WHERE id = ?",
                                      (attempt["confirmation_id"],)).fetchone()
            preparation = db.execute("SELECT * FROM preparations WHERE id = ?",
                                     (attempt["preparation_id"],)).fetchone()
            if not confirmation or confirmation["status"] != "active" or not preparation \
                    or preparation["superseded_by"]:
                raise BridgeError("Confirmation is no longer active")
            if (content_digest(preparation) != confirmation["content_digest"]
                    or content_digest(request) != confirmation["content_digest"]):
                raise BridgeError("Preparation content changed after Confirmation")
            attachments = [dict(row) for row in db.execute(
                "SELECT s.label, a.name, a.sha256, length(a.content) AS size FROM attachment_slots s "
                "JOIN attachments a ON a.slot_id = s.id WHERE s.preparation_id = ? ORDER BY s.rowid",
                (preparation["id"],))]
            if attachments_digest(attachments) != confirmation["attachments_digest"] \
                    or attachments != request["attachments"]:
                raise BridgeError("Attachments changed after Confirmation")
            if db.execute("SELECT 1 FROM readiness_findings WHERE preparation_id = ? AND blocking = 1",
                          (preparation["id"],)).fetchone():
                raise BridgeError("Preparation now has a Blocker")
            if db.execute("SELECT 1 FROM sent_records WHERE preparation_id = ?",
                          (preparation["id"],)).fetchone():
                raise BridgeError("Preparation has already been sent")
            if db.execute(
                    "SELECT 1 FROM external_schedules WHERE preparation_id = ? "
                    "AND state IN ('externally_scheduled', 'sent')",
                    (preparation["id"],)).fetchone():
                raise BridgeError("An external schedule for this Preparation is already active")
            if db.execute("SELECT 1 FROM execution_flow f JOIN tasks t ON t.campaign_id = f.campaign_id "
                          "WHERE t.id = ? AND f.state = 'paused'",
                          (attempt["task_id"],)).fetchone():
                raise BridgeError("Execution Flow is paused")
            execution = json.loads(confirmation["execution_detail"])
            if execution.get("kind") != "scheduled":
                raise BridgeError("Only a scheduled Confirmation can grant a schedule permit")
            scheduled = next((execution.get(key) for key in (
                "scheduled_utc", "scheduled_at", "scheduled_time") if execution.get(key)), None)
            parsed = datetime.fromisoformat(str(scheduled).replace("Z", "+00:00")) \
                if scheduled else None
            if parsed is None:
                raise BridgeError("Confirmation is not bound to an exact schedule time")
            parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            if parsed <= datetime.now(timezone.utc):
                raise BridgeError("The confirmed schedule time has elapsed")
    except (sqlite3.Error, KeyError, TypeError, ValueError) as error:
        raise BridgeError(f"Cannot authorize extension schedule placement: {error}") from error


def validate_external_operation(home, payload, expected_kind):
    """Permit an explicit cancellation/Replacement sequencing or Recall.

    A Scheduled Replacement Confirmation authorizes removal of exactly the
    external identity it binds; the replacement submission is a separate
    scheduled Confirmation with its own permit.
    """
    allowed = {expected_kind}
    if expected_kind == "cancellation":
        allowed.add("replacement")
    try:
        with closing(sqlite3.connect(
                (Path(home).resolve() / "smartmail.sqlite3").as_uri() + "?mode=ro",
                uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            binding = payload.get("binding", {})
            request = {key: value for key, value in payload.items() if key != "binding"}
            attempt = db.execute("SELECT * FROM execution_attempts WHERE id = ?",
                                 (binding.get("attempt_id"),)).fetchone()
            if (not attempt or attempt["state"] != "in_progress"
                    or attempt["confirmation_id"] != binding.get("confirmation_id")
                    or json.loads(attempt["request"]) != request):
                raise BridgeError(f"The {expected_kind} no longer matches an active Execution Attempt")
            confirmation = db.execute("SELECT * FROM confirmations WHERE id = ?",
                                      (attempt["confirmation_id"],)).fetchone()
            if not confirmation or confirmation["status"] != "active":
                raise BridgeError("Confirmation is no longer active")
            execution = json.loads(confirmation["execution_detail"])
            if execution.get("kind") not in allowed:
                raise BridgeError(
                    f"Only an explicit {expected_kind} Confirmation can grant this permit")
            if execution.get("kind") == "replacement" \
                    and execution.get("external_id") != payload.get("external_id"):
                raise BridgeError(
                    "Replacement Confirmation is bound to a different external schedule")
            if db.execute("SELECT 1 FROM execution_flow f JOIN tasks t ON t.campaign_id = f.campaign_id "
                          "WHERE t.id = ? AND f.state = 'paused'",
                          (attempt["task_id"],)).fetchone():
                raise BridgeError("Execution Flow is paused")
    except (sqlite3.Error, KeyError, TypeError, ValueError) as error:
        raise BridgeError(f"Cannot authorize extension {expected_kind}: {error}") from error

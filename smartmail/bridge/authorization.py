"""Recheck persisted Confirmation without initializing or recovering the store."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from ..snapshots import content_digest, attachments_digest
from . import BridgeError


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

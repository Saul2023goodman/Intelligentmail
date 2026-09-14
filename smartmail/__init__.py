"""SmartMail's persistent command/query boundary for local outreach operations."""

import sqlite3
import hashlib
import json
import re
import shutil
import tempfile
from datetime import datetime, time, timedelta, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .documents import DocumentError, association_key, attachment_declarations, parse_draft, read_paragraphs
from .intake import read_master, read_bundle
from .identity import email_address, person_name, profile_url
from .mailbox import DisabledMailbox, MailboxCapabilityError


class SmartMailError(ValueError):
    """An operator-visible command or query error."""


_PAUSE_REASONS = {"failed": "execution_failed", "unknown": "unknown_outcome"}
_REVIEW_FINDINGS = {"repeat_execution", "duplicate_suspicion", "ambiguous_match"}
_PLAN_DAY_TOKENS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
_PLAN_CONSTRAINT_LABELS = {
    "windows": "allowed windows",
    "spacing_minutes": "spacing",
    "daily_limit": "daily limit",
}
#: Deterministic defaults for a Campaign that has not configured a Sending Plan.
PLAN_DEFAULTS = {
    "timezone": "UTC",
    "windows": [{"days": list(_PLAN_DAY_TOKENS[:5]), "start": "09:00", "end": "17:00"}],
    "spacing_minutes": 15,
    "daily_limit": 20,
    "horizon_days": 14,
}


class SmartMail:
    def __init__(self, home: Path, mailbox=None, clock=None):
        self.home = Path(home).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.mailbox = mailbox if mailbox is not None else DisabledMailbox()
        #: The controlled time this store reasons with. Replacing it makes every
        #: date-dependent decision (planning windows, expiry) reproducible.
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._db = sqlite3.connect(self.home / "smartmail.sqlite3")
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS campaigns (id TEXT PRIMARY KEY, name TEXT NOT NULL)"
        )
        self._db.commit()
        self._db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        self._migrate()

    def _migrate(self) -> None:
        """Keep an existing local store usable as the versioned Preparation schema grows."""
        columns = {row["name"] for row in self._db.execute("PRAGMA table_info(preparations)")}
        if "superseded_by" not in columns:
            self._db.execute(
                "ALTER TABLE preparations ADD COLUMN superseded_by TEXT REFERENCES preparations(id)")
            self._db.commit()
        for table, column, definition in (
            ("preparations", "action_kind", "action_kind TEXT NOT NULL DEFAULT 'initial'"),
            ("preparations", "linked_sent_record_id",
             "linked_sent_record_id TEXT REFERENCES sent_records(id)"),
            ("sent_records", "action_kind", "action_kind TEXT NOT NULL DEFAULT 'initial'"),
            ("sent_records", "follows_sent_record_id",
             "follows_sent_record_id TEXT REFERENCES sent_records(id)"),
            ("execution_attempts", "phase",
             "phase TEXT NOT NULL DEFAULT 'legacy'"),
            ("execution_attempts", "intent_at",
             "intent_at TEXT NOT NULL DEFAULT ''"),
            ("execution_attempts", "submission_started_at",
             "submission_started_at TEXT NOT NULL DEFAULT ''"),
            ("execution_attempts", "outcome_observed_at",
             "outcome_observed_at TEXT NOT NULL DEFAULT ''"),
            ("execution_attempts", "updated_at",
             "updated_at TEXT NOT NULL DEFAULT ''"),
            ("confirmations", "confirmed_at",
             "confirmed_at TEXT NOT NULL DEFAULT ''"),
        ):
            existing = {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                self._db.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
                self._db.commit()
        self._recover_unfinished_execution()

    def _instant(self) -> datetime:
        """The store's controlled instant, always timezone-aware."""
        now = self._clock()
        return now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now

    def _now(self) -> str:
        return self._instant().isoformat()

    @staticmethod
    def _parse_timestamp(value):
        if isinstance(value, datetime):
            parsed = value
        elif value:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed

    def _recover_unfinished_execution(self) -> None:
        """Turn a process-boundary interruption into an explicit Unknown Outcome.

        An attempt persisted as ``in_progress`` may have crossed the mailbox
        boundary even when the local process did not get an adapter response.
        It is therefore never retried automatically after restart.  The
        operator must reconcile mailbox evidence before continuing.
        """
        rows = list(self._db.execute(
            "SELECT a.*, t.campaign_id FROM execution_attempts a "
            "JOIN tasks t ON t.id = a.task_id "
            "WHERE a.state IN ('in_progress', 'sent') ORDER BY a.rowid"))
        if not rows:
            return
        recovered_at = self._now()
        for row in rows:
            if row["state"] == "sent":
                existing_sent = self._db.execute(
                    "SELECT id FROM sent_records WHERE attempt_id = ?", (row["id"],)).fetchone()
                if existing_sent:
                    self._db.execute(
                        "UPDATE confirmations SET status = 'consumed' WHERE id = ? "
                        "AND status = 'active'", (row["confirmation_id"],))
                    evidence = json.loads(row["evidence"]) if row["evidence"] else {}
                    evidence.update({
                        "phase": "recorded",
                        "recovered_sent_record": True,
                        "sent_record_id": existing_sent["id"],
                    })
                    self._db.execute(
                        "UPDATE execution_attempts SET evidence = ?, phase = 'recorded', "
                        "updated_at = ? WHERE id = ?",
                        (json.dumps(evidence, ensure_ascii=False), recovered_at, row["id"]))
                    continue
                evidence = json.loads(row["evidence"]) if row["evidence"] else {}
                request = json.loads(row["request"])
                try:
                    confirmation = self.get_confirmation(row["confirmation_id"])
                    self._record_sent(confirmation, row["id"], request, evidence)
                    self._db.execute(
                        "UPDATE confirmations SET status = 'consumed' WHERE id = ? "
                        "AND status = 'active'", (row["confirmation_id"],))
                    evidence["phase"] = "recorded"
                    evidence["recovered_sent_record"] = True
                    self._db.execute(
                        "UPDATE execution_attempts SET evidence = ?, phase = 'recorded', "
                        "updated_at = ? WHERE id = ?",
                        (json.dumps(evidence, ensure_ascii=False), recovered_at, row["id"]))
                except Exception as error:
                    evidence.update({
                        "phase": "recovery_required",
                        "recovered_after_restart": True,
                        "detail": str(error) or "Sent Record recovery failed",
                    })
                    self._db.execute(
                        "UPDATE execution_attempts SET evidence = ?, phase = 'recovery_required', "
                        "updated_at = ? WHERE id = ?",
                        (json.dumps(evidence, ensure_ascii=False), recovered_at, row["id"]))
                    self._pause_flow_if_idle(row["campaign_id"], "recovery_required", evidence)
                continue
            evidence = json.loads(row["evidence"]) if row["evidence"] else {}
            evidence.update({
                "outcome": "unknown",
                "recovered_after_restart": True,
                "recovered_at": recovered_at,
                "phase": "recovery_required",
                "detail": (
                    "The process stopped while external submission was in progress; "
                    "reconcile mailbox evidence before continuing"
                ),
            })
            self._db.execute(
                "UPDATE execution_attempts SET state = 'unknown', evidence = ?, "
                "phase = 'recovery_required', outcome_observed_at = ?, updated_at = ? "
                "WHERE id = ?",
                (json.dumps(evidence, ensure_ascii=False), recovered_at, recovered_at, row["id"]))
            self._pause_flow_if_idle(
                row["campaign_id"], "recovery_required", evidence)
        self._db.commit()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._db.close()

    def create_campaign(self, name: str) -> dict:
        campaign = {"id": str(uuid4()), "name": name.strip()}
        if not campaign["name"]:
            raise SmartMailError("Campaign name is required")
        with self._db:
            self._db.execute(
                "INSERT INTO campaigns VALUES (:id, :name)", campaign
            )
        return campaign

    def list_campaigns(self) -> list[dict]:
        return [dict(row) for row in self._db.execute("SELECT * FROM campaigns ORDER BY rowid")]

    def get_campaign(self, campaign_id: str) -> dict:
        row = self._db.execute(
            "SELECT * FROM campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
        if row is None:
            raise SmartMailError(f"Campaign not found: {campaign_id}")
        return dict(row)

    def create_student(self, name: str, mailbox_address: str) -> dict:
        name = name.strip()
        address = email_address(mailbox_address)
        if not name or not address:
            raise SmartMailError("Student name and a valid Mailbox address are required")
        existing = self._db.execute(
            "SELECT s.* FROM students s JOIN mailboxes m ON m.student_id = s.id WHERE m.address = ?", (address,)).fetchone()
        if existing:
            if existing["name"] != name:
                raise SmartMailError(f"Mailbox already belongs to Student {existing['id']}; select that Student or resolve ownership")
            return dict(existing)
        student_id = str(uuid4())
        with self._db:
            self._db.execute("INSERT INTO students VALUES (?, ?)", (student_id, name.strip()))
            self._db.execute("INSERT INTO mailboxes VALUES (?, ?, ?)",
                             (str(uuid4()), student_id, address))
        return self.get_student(student_id)

    def list_students(self) -> list[dict]:
        return [dict(r) for r in self._db.execute("SELECT * FROM students ORDER BY rowid")]

    def get_student(self, student_id: str) -> dict:
        row = self._db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Student not found: {student_id}")
        return dict(row)

    def mailbox_capabilities(self) -> dict:
        """Availability is reported per operation; read access grants no write authority."""
        return {
            "adapter": getattr(self.mailbox, "name", "unavailable"),
            "capabilities": self.mailbox.capabilities(),
        }

    def refresh_mailbox(self, student_id: str) -> dict:
        """Observe read-only mailbox evidence and persist a manual Reconciliation."""
        mailbox = self._mailbox_for_student(student_id)
        capabilities = self.mailbox_capabilities()
        try:
            observed = self.mailbox.observe(mailbox["address"])
        except MailboxCapabilityError as error:
            raise SmartMailError(str(error)) from error
        if not isinstance(observed, dict):
            raise SmartMailError("Mailbox adapter returned an unsupported observation")

        allowed_statuses = {
            "complete", "partial", "authentication_required", "wrong_mailbox",
            "unsupported", "ambiguous", "failed",
        }
        status = str(observed.get("status", "ambiguous"))
        detail = str(observed.get("detail", ""))
        if status not in allowed_statuses:
            detail = f"Unsupported observation status from adapter: {status}"
            status = "ambiguous"
        actual_address = email_address(str(observed.get("mailbox_address", "")))
        messages = observed.get("messages", [])
        if not isinstance(messages, list):
            messages = []
            status = "ambiguous"
            detail = "Mailbox adapter returned an unsupported messages collection"
        if status in ("complete", "partial") and not actual_address:
            status = "ambiguous"
            detail = "Adapter did not establish the authenticated Mailbox address"
            messages = []
        if actual_address and actual_address != mailbox["address"]:
            status = "wrong_mailbox"
            detail = (
                f"Observed {actual_address}; intended Mailbox is {mailbox['address']}")
            messages = []
        coverage = observed.get("coverage", {"folders": [], "complete": False})
        if not isinstance(coverage, dict):
            coverage = {"folders": [], "complete": False,
                        "limitation": "Adapter returned unsupported Evidence Coverage"}
            status = "ambiguous"
        coverage.setdefault("complete", False)
        observed_at = str(observed.get("observed_at") or datetime.now(timezone.utc).isoformat())
        run_id = str(uuid4())
        with self._db:
            self._db.execute(
                "INSERT INTO mailbox_observation_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, mailbox["id"], capabilities["adapter"], observed_at, status, detail,
                 json.dumps(coverage, ensure_ascii=False),
                 json.dumps(capabilities["capabilities"], ensure_ascii=False)))
            for message in messages:
                self._store_message_observation(run_id, message)
            reconciliation_id = self._reconcile_observation(mailbox, run_id, observed_at)
        return {
            "observation": self.get_mailbox_observation(run_id),
            "reconciliation": self.get_reconciliation(reconciliation_id),
        }

    def _mailbox_for_student(self, student_id: str):
        self.get_student(student_id)
        row = self._db.execute(
            "SELECT * FROM mailboxes WHERE student_id = ?", (student_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Mailbox not found for Student: {student_id}")
        return dict(row)

    def _store_message_observation(self, run_id: str, message) -> str:
        message = message if isinstance(message, dict) else {}
        direction = str(message.get("direction", "ambiguous"))
        folder = str(message.get("folder", ""))
        status = str(message.get("status", "ambiguous"))
        ambiguity = str(message.get("ambiguity", ""))
        if direction not in ("inbound", "outbound"):
            ambiguity = ambiguity or "Direction is unsupported or ambiguous"
            direction = "ambiguous"
        if not folder:
            ambiguity = ambiguity or "Folder is unavailable"
        if status not in ("received", "sent", "draft", "deleted", "spam", "ambiguous"):
            ambiguity = ambiguity or f"Unsupported observed message status: {status}"
            status = "ambiguous"
        evidence = message.get("evidence", {})
        if not isinstance(evidence, dict):
            evidence = {"raw": str(evidence)}
            ambiguity = ambiguity or "Evidence has an unsupported structure"
        observation_id = str(uuid4())
        self._db.execute(
            "INSERT INTO mailbox_message_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (observation_id, run_id, direction, folder,
             str(message.get("platform_reference", "")),
             str(message.get("counterpart", "")), str(message.get("subject", "")),
             str(message.get("observed_time", "")), status, ambiguity,
             json.dumps(evidence, ensure_ascii=False)))
        return observation_id

    def _reconcile_observation(self, mailbox: dict, run_id: str, observed_at: str) -> str:
        """Compare evidence without replacing SmartMail's local system of record."""
        reconciliation_id = str(uuid4())
        run = self._db.execute(
            "SELECT * FROM mailbox_observation_runs WHERE id = ?", (run_id,)).fetchone()
        summary = {
            "observation_status": run["status"],
            "messages_observed": 0,
            "matched_sent_records": 0,
            "matched_execution_attempts": 0,
            "ambiguous": 0,
            "unassociated": 0,
            "local_state_changed": False,
        }
        self._db.execute(
            "INSERT INTO reconciliations VALUES (?, ?, ?, ?, ?)",
            (reconciliation_id, mailbox["id"], run_id, observed_at,
             json.dumps(summary, ensure_ascii=False)))

        messages = list(self._db.execute(
            "SELECT * FROM mailbox_message_observations WHERE run_id = ? ORDER BY rowid",
            (run_id,)))
        summary["messages_observed"] = len(messages)
        if not messages:
            self._insert_reconciliation_finding(
                reconciliation_id, None, "observation_unavailable", detail=run["detail"])
            summary["unassociated"] += 1

        sent_rows = list(self._db.execute(
            "SELECT s.* FROM sent_records s JOIN tasks t ON t.id = s.task_id "
            "WHERE t.student_id = ? ORDER BY s.rowid", (mailbox["student_id"],)))
        attempt_rows = list(self._db.execute(
            "SELECT a.* FROM execution_attempts a JOIN tasks t ON t.id = a.task_id "
            "WHERE t.student_id = ? AND a.state IN ('in_progress', 'unknown') ORDER BY a.rowid",
            (mailbox["student_id"],)))

        for message in messages:
            if message["ambiguity"] or message["status"] == "ambiguous":
                self._insert_reconciliation_finding(
                    reconciliation_id, message["id"], "ambiguous_observation",
                    detail=message["ambiguity"] or "Observed status is ambiguous")
                summary["ambiguous"] += 1
                continue
            if message["status"] in ("draft", "deleted", "spam"):
                self._insert_reconciliation_finding(
                    reconciliation_id, message["id"], "observed_non_delivery_state",
                    detail=(
                        f"Observed in {message['folder']} with status {message['status']}; "
                        "this is not evidence of delivery"))
                summary["unassociated"] += 1
                continue
            if message["direction"] == "inbound":
                self._insert_reconciliation_finding(
                    reconciliation_id, message["id"], "unassociated_inbound",
                    detail="Reply association is outside this verified reconciliation slice")
                summary["unassociated"] += 1
                continue

            sent_matches = [
                sent for sent in sent_rows
                if message["platform_reference"] and sent["reference"]
                and message["platform_reference"] == sent["reference"]]
            sent_basis = "platform_reference"
            if not sent_matches:
                sent_matches = [sent for sent in sent_rows
                                if self._list_fields_match(message, json.loads(sent["content"]))]
                sent_basis = "exact_recipient_and_subject"
            if len(sent_matches) == 1:
                self._insert_reconciliation_finding(
                    reconciliation_id, message["id"], "matched_sent_record",
                    "sent_record", sent_matches[0]["id"], sent_basis)
                summary["matched_sent_records"] += 1
                continue
            if len(sent_matches) > 1:
                self._insert_reconciliation_finding(
                    reconciliation_id, message["id"], "ambiguous_local_match",
                    basis=sent_basis,
                    detail="Multiple Sent Records match the available list-page fields")
                summary["ambiguous"] += 1
                continue

            attempt_matches = [attempt for attempt in attempt_rows
                               if self._list_fields_match(message, json.loads(attempt["request"]))]
            if len(attempt_matches) == 1:
                self._insert_reconciliation_finding(
                    reconciliation_id, message["id"], "matched_unresolved_attempt",
                    "execution_attempt", attempt_matches[0]["id"],
                    "exact_recipient_and_subject",
                    "Evidence is linked for inspection; resolving the attempt is a separate operation")
                summary["matched_execution_attempts"] += 1
            elif len(attempt_matches) > 1:
                self._insert_reconciliation_finding(
                    reconciliation_id, message["id"], "ambiguous_local_match",
                    basis="exact_recipient_and_subject",
                    detail="Multiple unresolved Execution Attempts match the available list-page fields")
                summary["ambiguous"] += 1
            else:
                self._insert_reconciliation_finding(
                    reconciliation_id, message["id"], "unassociated_outbound",
                    detail="No exact local match within the available Evidence Coverage")
                summary["unassociated"] += 1

        self._db.execute(
            "UPDATE reconciliations SET summary = ? WHERE id = ?",
            (json.dumps(summary, ensure_ascii=False), reconciliation_id))
        return reconciliation_id

    @staticmethod
    def _list_fields_match(message, local_content: dict) -> bool:
        if message["subject"] != str(local_content.get("subject", "")):
            return False
        observed = email_address(message["counterpart"])
        local = email_address(str(local_content.get("recipient", "")))
        if observed and local:
            return observed == local
        return message["counterpart"].strip().casefold() == \
            str(local_content.get("recipient", "")).strip().casefold()

    def _insert_reconciliation_finding(self, reconciliation_id: str,
                                       observation_id: str | None, finding: str,
                                       local_kind: str = "", local_id: str = "",
                                       basis: str = "", detail: str = "") -> None:
        self._db.execute(
            "INSERT INTO reconciliation_findings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid4()), reconciliation_id, observation_id, finding,
             local_kind, local_id, basis, detail))

    def get_mailbox_observation(self, observation_id: str) -> dict:
        row = self._db.execute(
            "SELECT r.*, m.address AS mailbox_address, m.student_id "
            "FROM mailbox_observation_runs r JOIN mailboxes m ON m.id = r.mailbox_id "
            "WHERE r.id = ?", (observation_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Mailbox observation not found: {observation_id}")
        messages = [
            {"id": message["id"], "direction": message["direction"],
             "folder": message["folder"],
             "platform_reference": message["platform_reference"],
             "counterpart": message["counterpart"], "subject": message["subject"],
             "observed_time": message["observed_time"], "status": message["status"],
             "ambiguity": message["ambiguity"], "evidence": json.loads(message["evidence"])}
            for message in self._db.execute(
                "SELECT * FROM mailbox_message_observations WHERE run_id = ? ORDER BY rowid",
                (observation_id,))]
        reconciliation = self._db.execute(
            "SELECT id FROM reconciliations WHERE observation_run_id = ?", (observation_id,)).fetchone()
        return {
            "id": row["id"], "student_id": row["student_id"],
            "mailbox_address": row["mailbox_address"], "adapter": row["adapter"],
            "observed_at": row["observed_at"], "status": row["status"],
            "detail": row["detail"],
            "evidence_coverage": json.loads(row["evidence_coverage"]),
            "capabilities": json.loads(row["capabilities"]), "messages": messages,
            "reconciliation_id": reconciliation["id"] if reconciliation else None,
        }

    def list_mailbox_observations(self, student_id: str) -> list[dict]:
        mailbox = self._mailbox_for_student(student_id)
        return [self.get_mailbox_observation(row["id"]) for row in self._db.execute(
            "SELECT id FROM mailbox_observation_runs WHERE mailbox_id = ? ORDER BY rowid",
            (mailbox["id"],))]

    def get_reconciliation(self, reconciliation_id: str) -> dict:
        row = self._db.execute(
            "SELECT r.*, m.address AS mailbox_address, m.student_id "
            "FROM reconciliations r JOIN mailboxes m ON m.id = r.mailbox_id WHERE r.id = ?",
            (reconciliation_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Reconciliation not found: {reconciliation_id}")
        findings = [dict(finding) for finding in self._db.execute(
            "SELECT id, message_observation_id, finding, local_kind, local_id, basis, detail "
            "FROM reconciliation_findings WHERE reconciliation_id = ? ORDER BY rowid",
            (reconciliation_id,))]
        return {
            "id": row["id"], "student_id": row["student_id"],
            "mailbox_address": row["mailbox_address"],
            "observation_id": row["observation_run_id"],
            "observed_at": row["observed_at"], "summary": json.loads(row["summary"]),
            "findings": findings,
        }

    def list_reconciliations(self, student_id: str) -> list[dict]:
        mailbox = self._mailbox_for_student(student_id)
        return [self.get_reconciliation(row["id"]) for row in self._db.execute(
            "SELECT id FROM reconciliations WHERE mailbox_id = ? ORDER BY rowid",
            (mailbox["id"],))]

    def reconcile_and_continue(self, attempt_id: str,
                               confirmation_ids: list[str] | None = None,
                               *, acknowledge: bool = False) -> dict:
        """Observe a manual or interrupted action before resolving or continuing it.

        An operator acknowledgment is deliberately not treated as evidence of
        sending.  Only a mailbox observation with an outbound ``sent`` state
        can resolve the attempt and create its immutable Sent Record.
        """
        row = self._db.execute(
            "SELECT * FROM execution_attempts WHERE id = ?", (attempt_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Execution Attempt not found: {attempt_id}")
        if row["state"] not in ("in_progress", "unknown"):
            raise SmartMailError(
                f"Execution Attempt cannot be reconciled from state {row['state']}")
        task = self.get_task(row["task_id"])
        refreshed = self.refresh_mailbox(task["student_id"])
        resolved = self._resolve_attempt_from_observation(attempt_id, refreshed)
        if not resolved:
            # Keep the attempt unresolved even when the operator explicitly
            # acknowledges the manual step.  The acknowledgment is inspectable
            # evidence, never a substitute for mailbox confirmation.
            if acknowledge:
                evidence = json.loads(row["evidence"]) if row["evidence"] else {}
                evidence["operator_acknowledged"] = True
                self._db.execute(
                    "UPDATE execution_attempts SET evidence = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(evidence, ensure_ascii=False), self._now(), attempt_id))
                self._db.commit()
            self._pause_flow_if_idle(
                task["campaign_id"], "reconcile_required",
                {"detail": "Mailbox evidence did not establish that the action was Sent"})
            self._db.commit()
        continued = None
        if resolved and confirmation_ids:
            continued = self.run_execution(confirmation_ids)
        return {
            "resolved": resolved,
            "attempt": self.get_execution_attempt(attempt_id),
            "reconciliation": self.get_reconciliation(refreshed["reconciliation"]["id"]),
            "continued": continued,
        }

    def _resolve_attempt_from_observation(self, attempt_id: str, refreshed: dict) -> bool:
        """Resolve one unresolved attempt only from unique mailbox-confirmed Sent evidence."""
        row = self._db.execute(
            "SELECT * FROM execution_attempts WHERE id = ?", (attempt_id,)).fetchone()
        if row is None or row["state"] not in ("in_progress", "unknown"):
            return False
        request = json.loads(row["request"])
        candidates = [message for message in refreshed["observation"]["messages"]
                      if message["direction"] == "outbound"
                      and message["status"] == "sent"
                      and not message["ambiguity"]
                      and self._list_fields_match(message, request)]
        if len(candidates) != 1:
            return False
        message = candidates[0]
        observed_at = self._now()
        evidence = json.loads(row["evidence"]) if row["evidence"] else {}
        evidence.update({
            "outcome": "sent",
            "reference": message["platform_reference"] or evidence.get(
                "reference", f"reconciled-{message['id']}"),
            "reconciled": True,
            "reconciliation_id": refreshed["reconciliation"]["id"],
            "mailbox_observation_id": refreshed["observation"]["id"],
            "outcome_observed_at": observed_at,
            "detail": "Mailbox evidence established Sent after an unresolved attempt",
        })
        with self._db:
            self._db.execute(
                "UPDATE execution_attempts SET state = 'sent', evidence = ?, "
                "phase = 'outcome_observed', outcome_observed_at = ?, updated_at = ? "
                "WHERE id = ?",
                (json.dumps(evidence, ensure_ascii=False), observed_at, observed_at, attempt_id))
            sent = self._db.execute(
                "SELECT id FROM sent_records WHERE attempt_id = ?", (attempt_id,)).fetchone()
            if sent is None:
                confirmation = self.get_confirmation(row["confirmation_id"])
                sent_id = self._record_sent(confirmation, attempt_id, request, evidence)
            else:
                sent_id = sent["id"]
            self._db.execute(
                "UPDATE confirmations SET status = 'consumed' WHERE id = ? "
                "AND status = 'active'", (row["confirmation_id"],))
            evidence["sent_record_id"] = sent_id
            self._db.execute(
                "UPDATE execution_attempts SET evidence = ?, phase = 'recorded', updated_at = ? "
                "WHERE id = ?", (json.dumps(evidence, ensure_ascii=False), self._now(), attempt_id))
            summary_row = self._db.execute(
                "SELECT summary FROM reconciliations WHERE id = ?",
                (refreshed["reconciliation"]["id"],)).fetchone()
            summary = json.loads(summary_row["summary"])
            summary["local_state_changed"] = True
            summary["resolved_execution_attempts"] = summary.get(
                "resolved_execution_attempts", 0) + 1
            self._db.execute(
                "UPDATE reconciliations SET summary = ? WHERE id = ?",
                (json.dumps(summary, ensure_ascii=False), refreshed["reconciliation"]["id"]))
            self._clear_recovery_pause_if_resolved(row["task_id"])
        return True

    def check_duplicate(self, preparation_id: str) -> dict:
        """Detect Repeat Execution and repeated initial outreach from available evidence."""
        preparation = self.get_preparation(preparation_id)
        task = self.get_task(preparation["task_id"])
        coverage = self._duplicate_coverage(task)
        matches, finding, basis, detail = self._duplicate_findings(task, preparation)
        check_id = str(uuid4())
        with self._db:
            self._db.execute(
                "INSERT INTO duplicate_checks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (check_id, task["id"], preparation_id,
                 datetime.now(timezone.utc).isoformat(), finding,
                 1 if finding in _REVIEW_FINDINGS else 0, basis, detail,
                 json.dumps(coverage, ensure_ascii=False),
                 json.dumps(matches, ensure_ascii=False)))
        return self.get_duplicate_check(check_id)

    def _duplicate_coverage(self, task: dict) -> dict:
        """The sources and available history inspected for this duplicate check."""
        campaign_sends = self._db.execute(
            "SELECT count(*) FROM sent_records s JOIN tasks t ON t.id = s.task_id "
            "WHERE t.campaign_id = ?", (task["campaign_id"],)).fetchone()[0]
        mailbox = self._db.execute(
            "SELECT id FROM mailboxes WHERE student_id = ?", (task["student_id"],)).fetchone()
        runs = list(self._db.execute(
            "SELECT id, evidence_coverage FROM mailbox_observation_runs "
            "WHERE mailbox_id = ? ORDER BY rowid", (mailbox["id"],)))
        observed = self._db.execute(
            "SELECT count(*) FROM mailbox_message_observations o "
            "JOIN mailbox_observation_runs r ON r.id = o.run_id "
            "WHERE r.mailbox_id = ? AND o.direction = 'outbound'", (mailbox["id"],)).fetchone()[0]
        mailbox_complete = bool(runs)
        for run in runs:
            recorded = json.loads(run["evidence_coverage"])
            if not (recorded.get("supported_scope_complete") or recorded.get("complete")):
                mailbox_complete = False
        limitations = []
        if not runs:
            limitations.append(
                "No mailbox observation has established history coverage for this Mailbox")
        elif not mailbox_complete:
            limitations.append(
                "Mailbox history is not complete for the declared observation scope")
        limitations.append(
            "No match is not proof that no prior send exists outside the inspected coverage")
        addresses = [row[0] for row in self._db.execute(
            "SELECT address FROM supervisor_addresses WHERE supervisor_id = ? ORDER BY address",
            (task["supervisor_id"],))]
        return {
            "student_id": task["student_id"], "supervisor_id": task["supervisor_id"],
            "campaign_id": task["campaign_id"], "supervisor_addresses": addresses,
            "sources": [
                {"source": "sent_records", "scope": "campaign",
                 "inspected": campaign_sends, "complete": True},
                {"source": "mailbox_observations", "scope": "student_mailbox",
                 "inspected": observed, "complete": mailbox_complete,
                 "observation_run_ids": [run["id"] for run in runs]},
            ],
            "complete": mailbox_complete,
            "limitations": limitations,
        }

    def _duplicate_findings(self, task: dict, preparation: dict) -> tuple[list, str, str, str]:
        """Deterministic matches against recorded sends; ambiguous evidence requires review."""
        own = list(self._db.execute(
            "SELECT * FROM sent_records WHERE task_id = ? AND preparation_id = ? ORDER BY rowid",
            (task["id"], preparation["id"])))
        if own:
            matches = [self._sent_evidence(row, "same_action") for row in own]
            return (matches, "repeat_execution", "same_action",
                    "This Communication Action has already been executed")
        if preparation["action_kind"] != "initial":
            return ([], "linked_follow_up", "linked_follow_up",
                    "This Communication Action is a linked Follow-up Action; repeated "
                    "initial outreach does not apply")
        return self._observed_duplicates(task)

    def _observed_duplicates(self, task: dict) -> tuple[list, str, str, str]:
        """Compare supported mailbox observations against the Supervisor's known addresses.

        The Mailbox account identifies the Student and the recipient identifies the
        Supervisor, so an observed outbound send to a known address of this Task's
        Supervisor is repeated initial outreach for the same Student and Supervisor.
        """
        addresses = [row[0] for row in self._db.execute(
            "SELECT address FROM supervisor_addresses WHERE supervisor_id = ? ORDER BY address",
            (task["supervisor_id"],))]
        known = {address.casefold() for address in addresses}
        identity_conflict = self._db.execute(
            "SELECT 1 FROM exceptions WHERE task_id = ? AND code = 'identity_ambiguity' "
            "AND blocking = 1", (task["id"],)).fetchone()
        matches: list[dict] = []
        ambiguous: list[dict] = []
        for observation in self._db.execute(
                "SELECT o.* FROM mailbox_message_observations o "
                "JOIN mailbox_observation_runs r ON r.id = o.run_id "
                "JOIN mailboxes m ON m.id = r.mailbox_id "
                "WHERE m.student_id = ? AND o.direction = 'outbound' ORDER BY o.rowid",
                (task["student_id"],)):
            if observation["status"] != "sent":
                continue
            recipient = email_address(observation["counterpart"])
            if not recipient or recipient.casefold() not in known:
                continue
            if identity_conflict:
                ambiguous.append(self._observation_evidence(observation, "conflicting_identity"))
            elif observation["ambiguity"]:
                ambiguous.append(self._observation_evidence(observation, "incomplete_evidence"))
            else:
                matches.append(self._observation_evidence(observation, "known_supervisor_address"))
        if matches:
            return (matches, "duplicate_suspicion", "known_supervisor_address",
                    "A prior outbound send to a known Supervisor address was recorded in the "
                    "Mailbox; repeated initial outreach requires resolution")
        if ambiguous:
            return (ambiguous, "ambiguous_match", ambiguous[0]["basis"],
                    "Prior-send evidence is incomplete or conflicting; review is required")
        return [], "no_duplicate_found", "", ""

    def link_follow_up(self, preparation_id: str, sent_record_id: str | None = None) -> dict:
        """Mark a Communication Action as a Follow-up Action linked to earlier outreach.

        A linked Follow-up Action is a separate Communication Action, not repeated
        initial outreach. The link is optional: earlier outreach may be evidenced
        outside SmartMail's Sent Records.
        """
        preparation = self._db.execute(
            "SELECT p.id, p.task_id, p.superseded_by, p.action_kind, t.student_id "
            "FROM preparations p JOIN tasks t ON t.id = p.task_id WHERE p.id = ?",
            (preparation_id,)).fetchone()
        if preparation is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        if preparation["superseded_by"] is not None:
            raise SmartMailError(f"Cannot link a Superseded Preparation: {preparation_id}")
        if sent_record_id is not None:
            earlier = self._db.execute(
                "SELECT s.id FROM sent_records s JOIN tasks t ON t.id = s.task_id "
                "WHERE s.id = ? AND t.student_id = ?",
                (sent_record_id, preparation["student_id"])).fetchone()
            if earlier is None:
                raise SmartMailError(
                    f"Earlier outreach not found for this Student: {sent_record_id}")
        with self._db:
            self._db.execute(
                "UPDATE preparations SET action_kind = 'follow_up', linked_sent_record_id = ? "
                "WHERE id = ?", (sent_record_id, preparation_id))
        return self.get_preparation(preparation_id)

    def _observation_evidence(self, row, basis: str) -> dict:
        return {
            "source": "mailbox_observation", "id": row["id"], "run_id": row["run_id"],
            "folder": row["folder"], "platform_reference": row["platform_reference"],
            "recipient": row["counterpart"], "subject": row["subject"],
            "observed_time": row["observed_time"], "basis": basis,
            "detail": row["ambiguity"] or "Observed in the Mailbox as an outbound sent message",
        }

    def _sent_evidence(self, row, basis: str) -> dict:
        content = json.loads(row["content"])
        return {
            "source": "sent_record", "id": row["id"], "task_id": row["task_id"],
            "preparation_id": row["preparation_id"],
            "recipient": content.get("recipient", ""), "subject": content.get("subject", ""),
            "reference": row["reference"], "basis": basis,
            "detail": "Already executed by a recorded send to "
                      f"{content.get('recipient', '')}",
        }

    def _duplicate_view(self, row) -> dict:
        return {
            "id": row["id"], "task_id": row["task_id"],
            "preparation_id": row["preparation_id"], "checked_at": row["checked_at"],
            "finding": row["finding"], "review_required": bool(row["review_required"]),
            "basis": row["basis"], "detail": row["detail"],
            "evidence_coverage": json.loads(row["evidence_coverage"]),
            "matches": json.loads(row["matches"]),
        }

    def get_duplicate_check(self, check_id: str) -> dict:
        row = self._db.execute(
            "SELECT * FROM duplicate_checks WHERE id = ?", (check_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Duplicate Check not found: {check_id}")
        return self._duplicate_view(row)

    def list_duplicate_checks(self, campaign_id: str) -> list[dict]:
        self.get_campaign(campaign_id)
        return [self._duplicate_view(row) for row in self._db.execute(
            "SELECT c.* FROM duplicate_checks c JOIN tasks t ON t.id = c.task_id "
            "WHERE t.campaign_id = ? ORDER BY c.rowid", (campaign_id,))]

    def import_master(self, campaign_id: str, student_id: str, path: Path) -> dict:
        self.get_campaign(campaign_id)
        self.get_student(student_id)
        try:
            sources, master_index = read_bundle(Path(path))
            rows = read_master(sources[master_index][1])
        except (ValueError, OSError, KeyError, BadZipFile, ParseError) as error:
            raise SmartMailError(f"Cannot import Source Material: {error}") from error
        import_id = str(uuid4())
        source_ids = [str(uuid4()) for _ in sources]
        source_id = source_ids[master_index]
        task_ids = []
        with self._db:
            self._db.execute("INSERT INTO imports VALUES (?, ?, ?)", (import_id, campaign_id, student_id))
            for sid, (name, data) in zip(source_ids, sources):
                self._db.execute("INSERT INTO sources VALUES (?, ?, ?, ?, ?)",
                                 (sid, import_id, name, data, hashlib.sha256(data).hexdigest()))
            for row in rows:
                values = row["values"]
                institution = self._db.execute("SELECT id FROM institutions WHERE name = ?",
                                               (values["institution"],)).fetchone()
                institution_id = institution["id"] if institution else str(uuid4())
                if institution is None:
                    self._db.execute("INSERT INTO institutions VALUES (?, ?)", (institution_id, values["institution"]))
                address = email_address(values["address"])
                profile = profile_url(values["profile"])
                candidates = list(self._db.execute(
                    "SELECT DISTINCT s.* FROM supervisors s LEFT JOIN supervisor_addresses a ON a.supervisor_id = s.id "
                    "WHERE s.institution_id = ? AND ((s.profile = ? AND s.profile != '') OR a.address = ?)",
                    (institution_id, profile, address)))
                matches = [s for s in candidates if person_name(s["name"]) == person_name(values["name"])
                           and not (profile and s["profile"] and profile != s["profile"])]
                prior_row = list(self._db.execute(
                    "SELECT DISTINCT s.* FROM supervisors s JOIN tasks t ON t.supervisor_id = s.id "
                    "JOIN source_associations a ON a.task_id = t.id JOIN sources m ON m.id = a.source_id "
                    "WHERE m.sha256 = ? AND a.sheet = ? AND a.row = ?",
                    (hashlib.sha256(sources[master_index][1]).hexdigest(), row["sheet"], row["row"])))
                if len(prior_row) == 1:
                    matches = prior_row
                supervisor_id = matches[0]["id"] if len(matches) == 1 else str(uuid4())
                if len(matches) != 1:
                    self._db.execute("INSERT INTO supervisors VALUES (?, ?, ?, ?)",
                                     (supervisor_id, values["name"], institution_id, profile))
                elif profile and not matches[0]["profile"]:
                    self._db.execute("UPDATE supervisors SET profile = ? WHERE id = ?", (profile, supervisor_id))
                if address:
                    self._db.execute("INSERT OR IGNORE INTO supervisor_addresses VALUES (?, ?)", (supervisor_id, address))
                existing = self._db.execute("SELECT id FROM tasks WHERE student_id = ? AND supervisor_id = ? AND campaign_id = ?",
                                            (student_id, supervisor_id, campaign_id)).fetchone()
                task_id = existing["id"] if existing else str(uuid4())
                if not existing:
                    self._db.execute("INSERT INTO tasks VALUES (?, ?, ?, ?)",
                                     (task_id, student_id, supervisor_id, campaign_id))
                ambiguous = []
                for s in self._db.execute("SELECT * FROM supervisors WHERE id != ?", (supervisor_id,)).fetchall():
                    shared_address = address and self._db.execute(
                        "SELECT 1 FROM supervisor_addresses WHERE supervisor_id = ? AND address = ?", (s["id"], address)).fetchone()
                    if (shared_address or (profile and s["profile"] == profile)
                            or (s["institution_id"] == institution_id and person_name(s["name"]) == person_name(values["name"]))):
                        ambiguous.append(s["id"])
                if ambiguous:
                    affected = [supervisor_id, *ambiguous]
                    detail = "Unresolved Supervisor identity; candidates: " + ", ".join(affected)
                    for candidate in affected:
                        for affected_task in self._db.execute("SELECT id FROM tasks WHERE supervisor_id = ?", (candidate,)).fetchall():
                            self._db.execute("INSERT INTO exceptions VALUES (?, ?, ?, ?, ?, 1)",
                                             (str(uuid4()), affected_task["id"], source_id, "identity_ambiguity", detail))
                if not address:
                    self._db.execute("INSERT INTO exceptions VALUES (?, ?, ?, ?, ?, 1)",
                                     (str(uuid4()), task_id, source_id, "invalid_recipient",
                                      f"{row['sheet']}!{row['row']}: Email is missing or unsupported: {values['address']}"))
                self._db.execute("INSERT INTO source_associations VALUES (?, ?, ?, ?, ?)",
                                 (task_id, source_id, row["sheet"], row["row"], json.dumps(row["evidence"], ensure_ascii=False, default=str)))
                if task_id not in task_ids:
                    task_ids.append(task_id)
        return {"id": import_id, "task_ids": task_ids}

    def get_import(self, import_id: str) -> dict:
        row = self._db.execute("SELECT * FROM imports WHERE id = ?", (import_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Import not found: {import_id}")
        return {**dict(row), "sources": [dict(r) for r in self._db.execute(
            "SELECT id, name, sha256, length(content) AS size FROM sources WHERE import_id = ? ORDER BY rowid", (import_id,))]}

    def list_imports(self, campaign_id: str) -> list[dict]:
        self.get_campaign(campaign_id)
        return [dict(r) for r in self._db.execute("SELECT * FROM imports WHERE campaign_id = ? ORDER BY rowid", (campaign_id,))]

    def read_source(self, source_id: str) -> bytes:
        row = self._db.execute("SELECT content FROM sources WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Source Material not found: {source_id}")
        return bytes(row["content"])

    def materialize_source(self, source_id: str) -> Path:
        content = self.read_source(source_id)
        name = self._db.execute("SELECT name FROM sources WHERE id = ?", (source_id,)).fetchone()[0]
        destination = self.home / "opened" / str(uuid4()) / Path(name).name
        destination.parent.mkdir(parents=True)
        destination.write_bytes(content)
        return destination

    def list_tasks(self, campaign_id: str) -> list[dict]:
        self.get_campaign(campaign_id)
        return [dict(row) for row in self._db.execute(
            "SELECT t.*, st.name AS student_name, s.name AS supervisor_name, i.name AS institution_name, "
            "(SELECT count(*) FROM exceptions e WHERE e.task_id = t.id) AS exception_count "
            "FROM tasks t JOIN students st ON st.id = t.student_id JOIN supervisors s ON s.id = t.supervisor_id "
            "JOIN institutions i ON i.id = s.institution_id WHERE t.campaign_id = ? ORDER BY t.rowid", (campaign_id,))]

    def get_task(self, task_id: str) -> dict:
        row = self._db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Outreach Task not found: {task_id}")
        task = dict(row)
        task["student"] = self.get_student(task["student_id"])
        task["campaign"] = self.get_campaign(task["campaign_id"])
        task["mailbox"] = dict(self._db.execute("SELECT * FROM mailboxes WHERE student_id = ?", (task["student_id"],)).fetchone())
        supervisor = dict(self._db.execute("SELECT * FROM supervisors WHERE id = ?", (task["supervisor_id"],)).fetchone())
        supervisor["addresses"] = [r[0] for r in self._db.execute("SELECT address FROM supervisor_addresses WHERE supervisor_id = ? ORDER BY address", (supervisor["id"],))]
        task["supervisor"] = supervisor
        task["institution"] = dict(self._db.execute("SELECT * FROM institutions WHERE id = ?", (supervisor["institution_id"],)).fetchone())
        task["source_associations"] = [
            {**dict(r), "evidence": json.loads(r["evidence"])} for r in self._db.execute(
                "SELECT source_id, sheet, row, evidence FROM source_associations WHERE task_id = ? ORDER BY rowid", (task_id,))
        ]
        task["exceptions"] = [dict(r) for r in self._db.execute("SELECT * FROM exceptions WHERE task_id = ? ORDER BY rowid", (task_id,))]
        return task

    def confirm_task_identity(self, task_id: str) -> dict:
        """Explicitly confirm a Task's recorded Supervisor identity, clearing its ambiguity Blocker."""
        if self._db.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is None:
            raise SmartMailError(f"Outreach Task not found: {task_id}")
        ambiguous = list(self._db.execute(
            "SELECT id FROM exceptions WHERE task_id = ? AND code = 'identity_ambiguity'", (task_id,)))
        if not ambiguous:
            raise SmartMailError(
                f"Outreach Task has no unresolved Supervisor identity ambiguity: {task_id}")
        with self._db:
            self._db.execute(
                "DELETE FROM exceptions WHERE task_id = ? AND code = 'identity_ambiguity'", (task_id,))
            for preparation in self._db.execute(
                    "SELECT id FROM preparations WHERE task_id = ?", (task_id,)):
                self._revalidate(preparation["id"])
        return self.get_task(task_id)

    def list_exceptions(self, campaign_id: str) -> list[dict]:
        """Blocking and non-blocking Exceptions with their source evidence and readiness findings."""
        self.get_campaign(campaign_id)
        return [self._exception_view(row) for row in self._db.execute(
            "SELECT e.*, s.name AS supervisor_name FROM exceptions e "
            "JOIN tasks t ON t.id = e.task_id JOIN supervisors s ON s.id = t.supervisor_id "
            "WHERE t.campaign_id = ? ORDER BY e.rowid", (campaign_id,))]

    def get_exception(self, exception_id: str) -> dict:
        row = self._db.execute(
            "SELECT e.*, s.name AS supervisor_name FROM exceptions e "
            "JOIN tasks t ON t.id = e.task_id JOIN supervisors s ON s.id = t.supervisor_id "
            "WHERE e.id = ?", (exception_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Exception not found: {exception_id}")
        return self._exception_view(row)

    def _exception_view(self, row) -> dict:
        source = self._db.execute(
            "SELECT id, name, sha256 FROM sources WHERE id = ?", (row["source_id"],)).fetchone()
        task = self._db.execute("SELECT student_id FROM tasks WHERE id = ?", (row["task_id"],)).fetchone()
        return {
            "id": row["id"], "code": row["code"], "detail": row["detail"],
            "blocking": bool(row["blocking"]), "task_id": row["task_id"],
            "student_id": task["student_id"], "supervisor_name": row["supervisor_name"],
            "source": dict(source) if source else None,
            "preparation_ids": [r["id"] for r in self._db.execute(
                "SELECT id FROM preparations WHERE task_id = ? AND superseded_by IS NULL ORDER BY rowid",
                (row["task_id"],))],
            "readiness_findings": [dict(r) for r in self._db.execute(
                "SELECT code, detail, blocking FROM readiness_findings WHERE preparation_id IN "
                "(SELECT id FROM preparations WHERE task_id = ? AND superseded_by IS NULL) ORDER BY rowid",
                (row["task_id"],))],
        }

    def prepare_from_documents(self, import_id: str) -> dict:
        """Associate supported draft documents with Outreach Tasks and prepare local messages."""
        imported = self.get_import(import_id)
        sender = self._db.execute(
            "SELECT address FROM mailboxes WHERE student_id = ?", (imported["student_id"],)).fetchone()["address"]
        tasks = list(self._db.execute(
            "SELECT t.id AS task_id, s.id AS supervisor_id, s.name AS supervisor_name, "
            "i.name AS institution_name "
            "FROM tasks t JOIN supervisors s ON s.id = t.supervisor_id JOIN institutions i ON i.id = s.institution_id "
            "WHERE t.campaign_id = ? AND t.student_id = ?",
            (imported["campaign_id"], imported["student_id"])))
        preparation_ids: list[str] = []
        unassociated_source_ids: list[str] = []
        with self._db:
            for source in self._db.execute(
                    "SELECT id, name FROM sources WHERE import_id = ? ORDER BY rowid", (import_id,)):
                if not source["name"].casefold().endswith(".docx"):
                    continue
                try:
                    parsed = parse_draft(read_paragraphs(self.read_source(source["id"])))
                except DocumentError as error:
                    self._record_document_finding(source["id"], "unsupported_document", str(error))
                    unassociated_source_ids.append(source["id"])
                    continue
                if parsed is None:
                    continue
                key = association_key(source["name"])
                matches = [task for task in tasks if key
                           and task["institution_name"].strip().casefold() == key[0].casefold()
                           and person_name(task["supervisor_name"]) == person_name(key[1])]
                if len(matches) != 1:
                    self._record_document_finding(
                        source["id"],
                        "unassociated_document" if not matches else "ambiguous_document",
                        f"{source['name']}: expected one Outreach Task, matched {len(matches)}")
                    unassociated_source_ids.append(source["id"])
                    continue
                task = matches[0]
                active = self._db.execute(
                    "SELECT id FROM preparations WHERE task_id = ? AND superseded_by IS NULL",
                    (task["task_id"],)).fetchone()
                already_active = self._db.execute(
                    "SELECT 1 FROM preparations WHERE task_id = ? AND source_id = ? AND superseded_by IS NULL",
                    (task["task_id"], source["id"])).fetchone()
                if active is not None and already_active is None:
                    self._record_document_finding(
                        source["id"], "replacement_requires_rewrite",
                        f"{source['name']}: Outreach Task already has active Preparation "
                        f"{active['id']}; replace it with an explicit Rewrite")
                    unassociated_source_ids.append(source["id"])
                    continue
                preparation_ids.append(self._store_preparation(task, source, parsed, sender, key))
        for preparation_id in preparation_ids:
            self.suggest_attachment_slots(preparation_id)
        return {"preparation_ids": preparation_ids, "unassociated_source_ids": unassociated_source_ids}

    def suggest_attachment_slots(self, preparation_id: str) -> list[dict]:
        """Create or refresh the advisory attachment slots declared by the message body.

        Suggestions never finalize an association and never affect readiness.
        """
        preparation = self._db.execute(
            "SELECT id, body, source_id FROM preparations WHERE id = ?", (preparation_id,)).fetchone()
        if preparation is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        import_id = self._db.execute(
            "SELECT import_id FROM sources WHERE id = ?", (preparation["source_id"],)).fetchone()["import_id"]
        with self._db:
            for declared in attachment_declarations(preparation["body"]):
                label = f"Student {declared}"
                basis = f'Attachment declared in the message body: "I have attached my {declared}"'
                candidates = self._attachment_candidates(import_id, declared, preparation["source_id"])
                suggested = candidates[0]["id"] if len(candidates) == 1 else None
                existing = self._db.execute(
                    "SELECT id, suggested_source_id FROM attachment_slots WHERE preparation_id = ? AND label = ?",
                    (preparation_id, label)).fetchone()
                if existing is None:
                    self._db.execute(
                        "INSERT INTO attachment_slots VALUES (?, ?, ?, ?, ?, ?)",
                        (str(uuid4()), preparation_id, label, declared, basis, suggested))
                elif self._db.execute(
                        "SELECT 1 FROM attachments WHERE slot_id = ?", (existing["id"],)).fetchone() is None:
                    self._db.execute(
                        "UPDATE attachment_slots SET basis = ?, suggested_source_id = ? WHERE id = ?",
                        (basis, suggested, existing["id"]))
        return self.list_attachment_slots(preparation_id)

    def _attachment_candidates(self, import_id: str, declared: str, exclude_source_id: str) -> list[dict]:
        """Preserved .docx Source Materials whose filename carries the declared attachment label."""
        wanted = {token.casefold() for token in re.split(r"[^0-9A-Za-z]+", declared) if token}
        candidates = []
        for row in self._db.execute(
                "SELECT id, name, sha256 FROM sources WHERE import_id = ? ORDER BY rowid", (import_id,)):
            if row["id"] == exclude_source_id or not row["name"].casefold().endswith(".docx"):
                continue
            stem = PurePosixPath(row["name"]).name[:-5]
            tokens = {token.casefold() for token in re.split(r"[^0-9A-Za-z]+", stem) if token}
            if wanted and wanted <= tokens:
                candidates.append(dict(row))
        return candidates

    def confirm_attachment(self, preparation_id: str, slot_id: str) -> dict:
        """Confirm the slot's single suggested candidate; suggestions are never finalized automatically."""
        slot = self._db.execute(
            "SELECT * FROM attachment_slots WHERE id = ? AND preparation_id = ?",
            (slot_id, preparation_id)).fetchone()
        if slot is None:
            raise SmartMailError(f"Attachment slot not found: {slot_id}")
        if slot["suggested_source_id"] is None:
            raise SmartMailError(
                "This slot has no single suggested candidate; select a file explicitly")
        return self.set_attachment(preparation_id, slot_id, source_id=slot["suggested_source_id"])

    def set_attachment(self, preparation_id: str, slot_id: str, source_id: str | None = None,
                       path: Path | None = None) -> dict:
        """Confirm or replace a slot's file, snapshotting its bytes without conversion or merging."""
        if (source_id is None) == (path is None):
            raise SmartMailError("Provide exactly one of a preserved Source Material or a file path")
        slot = self._require_slot(preparation_id, slot_id)
        name, content, digest = self._attachment_payload(source_id, path)
        with self._db:
            self._store_attachment(preparation_id, slot, name, content, digest)
        return self.get_preparation(preparation_id)

    def add_attachment_slot(self, preparation_id: str, label: str, source_id: str | None = None,
                            path: Path | None = None) -> dict:
        """Add an operator-defined slot, optionally confirming a file at the same time."""
        label = label.strip()
        if not label:
            raise SmartMailError("An attachment slot label is required")
        if self._db.execute(
                "SELECT 1 FROM preparations WHERE id = ?", (preparation_id,)).fetchone() is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        if self._db.execute(
                "SELECT 1 FROM attachment_slots WHERE preparation_id = ? AND label = ?",
                (preparation_id, label)).fetchone():
            raise SmartMailError(f"Attachment slot already exists: {label}")
        if source_id is not None and path is not None:
            raise SmartMailError("Provide exactly one of a preserved Source Material or a file path")
        payload = self._attachment_payload(source_id, path) if (source_id or path) else None
        with self._db:
            slot = {"id": str(uuid4()), "label": label}
            self._db.execute(
                "INSERT INTO attachment_slots VALUES (?, ?, ?, ?, ?, ?)",
                (slot["id"], preparation_id, label, label,
                 f"Added by the operator: {label}", None))
            if payload is not None:
                self._store_attachment(preparation_id, slot, *payload)
        return self.get_preparation(preparation_id)

    def remove_attachment_slot(self, preparation_id: str, slot_id: str) -> dict:
        slot = self._require_slot(preparation_id, slot_id)
        with self._db:
            self._db.execute("DELETE FROM attachments WHERE slot_id = ?", (slot["id"],))
            self._db.execute("DELETE FROM attachment_slots WHERE id = ?", (slot["id"],))
        return self.get_preparation(preparation_id)

    def _require_slot(self, preparation_id: str, slot_id: str):
        slot = self._db.execute(
            "SELECT * FROM attachment_slots WHERE id = ? AND preparation_id = ?",
            (slot_id, preparation_id)).fetchone()
        if slot is None:
            raise SmartMailError(f"Attachment slot not found: {slot_id}")
        return slot

    def _attachment_payload(self, source_id: str | None, path: Path | None) -> tuple[str, bytes, str]:
        if source_id is not None:
            source = self._db.execute(
                "SELECT name, content FROM sources WHERE id = ?", (source_id,)).fetchone()
            if source is None:
                raise SmartMailError(f"Source Material not found: {source_id}")
            name, content = PurePosixPath(source["name"]).name, bytes(source["content"])
        else:
            path = Path(path)
            if not path.is_file():
                raise SmartMailError(f"Attachment file not found: {path}")
            name, content = path.name, path.read_bytes()
        return name, content, hashlib.sha256(content).hexdigest()

    def _store_attachment(self, preparation_id: str, slot: dict, name: str,
                          content: bytes, digest: str) -> None:
        prior_row = self._db.execute(
            "SELECT name, sha256 FROM attachments WHERE slot_id = ?", (slot["id"],)).fetchone()
        prior = prior_row["name"] if prior_row and prior_row["sha256"] != digest else ""
        if prior_row is None:
            self._db.execute("INSERT INTO attachments VALUES (?, ?, ?, ?, ?)",
                             (str(uuid4()), slot["id"], name, content, digest))
        else:
            self._db.execute(
                "UPDATE attachments SET name = ?, content = ?, sha256 = ? WHERE slot_id = ?",
                (name, content, digest, slot["id"]))
        if prior or prior_row is None:
            self._record_correction(preparation_id, f"attachment:{slot['label']}", name, prior)

    def read_attachment(self, attachment_id: str) -> bytes:
        row = self._db.execute("SELECT content FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Attachment not found: {attachment_id}")
        return bytes(row["content"])

    def list_attachment_slots(self, preparation_id: str) -> list[dict]:
        """The Preparation's attachment slots: advisory candidates plus any confirmed file."""
        preparation = self._db.execute(
            "SELECT source_id FROM preparations WHERE id = ?", (preparation_id,)).fetchone()
        if preparation is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        import_id = self._db.execute(
            "SELECT import_id FROM sources WHERE id = ?", (preparation["source_id"],)).fetchone()["import_id"]
        slots = []
        for row in self._db.execute(
                "SELECT * FROM attachment_slots WHERE preparation_id = ? ORDER BY rowid", (preparation_id,)):
            attachment = self._db.execute(
                "SELECT id, name, sha256, length(content) AS size FROM attachments WHERE slot_id = ?",
                (row["id"],)).fetchone()
            slots.append({
                "id": row["id"], "label": row["label"], "declared": row["declared"],
                "basis": row["basis"],
                "suggested_source_id": row["suggested_source_id"],
                "candidates": self._attachment_candidates(
                    import_id, row["declared"], preparation["source_id"]),
                "attachment": dict(attachment) if attachment else None,
            })
        return slots

    def _record_document_finding(self, source_id: str, code: str, detail: str, blocking: bool = True) -> None:
        if self._db.execute("SELECT 1 FROM document_findings WHERE source_id = ? AND code = ?",
                            (source_id, code)).fetchone():
            return
        self._db.execute("INSERT INTO document_findings VALUES (?, ?, ?, ?, ?)",
                         (str(uuid4()), source_id, code, detail, 1 if blocking else 0))

    def list_unassociated_documents(self, import_id: str) -> list[dict]:
        self.get_import(import_id)
        return [
            {"id": row["id"], "source": {"id": row["source_id"], "name": row["source_name"]},
             "code": row["code"], "detail": row["detail"], "blocking": bool(row["blocking"])}
            for row in self._db.execute(
                "SELECT f.id, f.source_id, f.code, f.detail, f.blocking, s.name AS source_name "
                "FROM document_findings f JOIN sources s ON s.id = f.source_id "
                "WHERE s.import_id = ? ORDER BY s.rowid", (import_id,))]

    def _store_preparation(self, task: dict, source: dict, parsed: dict, sender: str, key: tuple) -> str:
        existing = self._db.execute(
            "SELECT id FROM preparations WHERE task_id = ? AND source_id = ? AND superseded_by IS NULL",
            (task["task_id"], source["id"])).fetchone()
        if existing:
            return existing["id"]
        return self._insert_preparation(task, source, parsed, sender, key)

    def _insert_preparation(self, task: dict, source: dict, parsed: dict, sender: str, key: tuple) -> str:
        preparation_id = str(uuid4())
        subject = ""
        recipient = email_address(parsed["recipient"])
        recorded = [row[0] for row in self._db.execute(
            "SELECT address FROM supervisor_addresses WHERE supervisor_id = ? ORDER BY address",
            (task["supervisor_id"],))]
        evidence = json.dumps(
            {"source": source["name"], "institution": key[0], "supervisor": key[1]}, ensure_ascii=False)
        self._db.execute(
            "INSERT INTO preparations (id, task_id, source_id, sender, recipient, subject, body, "
            "internal_note, association_evidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (preparation_id, task["task_id"], source["id"], sender,
             recipient or parsed["recipient"], subject, parsed["body"], parsed["internal_note"], evidence))
        self._record_transformation(
            preparation_id, "recipient_extracted",
            f"Recipient declared in {source['name']}: {parsed['recipient']}")
        self._record_transformation(
            preparation_id, "body_restructured",
            "Message body retained from the greeting through the sign-off; spacing normalized")
        if parsed["note_separated"]:
            self._record_transformation(
                preparation_id, "internal_note_separated",
                f"Internal note removed from the message body: {parsed['internal_note']}")
        if recipient and not recorded:
            self._record_transformation(
                preparation_id, "recipient_filled_missing_address",
                f"Recipient {recipient} taken from {source['name']}; no usable address was recorded")
        self._revalidate(preparation_id)
        return preparation_id

    def rewrite(self, preparation_id: str, source_id: str) -> dict:
        """Replace an active Preparation with a fresh one, keeping the prior version inspectable."""
        prior = self._db.execute(
            "SELECT id, task_id, superseded_by FROM preparations WHERE id = ?",
            (preparation_id,)).fetchone()
        if prior is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        if prior["superseded_by"] is not None:
            raise SmartMailError(f"Preparation is already superseded: {preparation_id}")
        if self._db.execute(
                "SELECT 1 FROM execution_attempts WHERE preparation_id = ? "
                "AND state IN ('in_progress', 'unknown')", (preparation_id,)).fetchone():
            raise SmartMailError(
                "An Execution Attempt for this Preparation is unresolved; stop or resolve it "
                "before rewriting")
        if self._db.execute(
                "SELECT 1 FROM sent_records WHERE preparation_id = ?",
                (preparation_id,)).fetchone():
            raise SmartMailError(
                "Sent content is frozen; prepare a new linked Communication Action instead "
                "of rewriting")
        task = self._db.execute(
            "SELECT t.id AS task_id, t.supervisor_id, s.name AS supervisor_name, i.name AS institution_name, "
            "(SELECT address FROM mailboxes WHERE student_id = t.student_id) AS sender "
            "FROM tasks t JOIN supervisors s ON s.id = t.supervisor_id "
            "JOIN institutions i ON i.id = s.institution_id WHERE t.id = ?", (prior["task_id"],)).fetchone()
        source = self._db.execute("SELECT id, name FROM sources WHERE id = ?", (source_id,)).fetchone()
        if source is None:
            raise SmartMailError(f"Source Material not found: {source_id}")
        try:
            parsed = parse_draft(read_paragraphs(self.read_source(source_id)))
        except DocumentError as error:
            raise SmartMailError(f"Cannot rewrite from Source Material: {error}") from error
        key = association_key(source["name"])
        if parsed is None or key is None or key[0].strip().casefold() != task["institution_name"].strip().casefold() \
                or person_name(key[1]) != person_name(task["supervisor_name"]):
            raise SmartMailError(
                f"Source Material does not describe this Outreach Task: {source['name']}")
        with self._db:
            fresh_id = self._insert_preparation(task, source, parsed, task["sender"], key)
            self._db.execute(
                "UPDATE preparations SET superseded_by = ? WHERE id = ?", (fresh_id, preparation_id))
            self._db.execute(
                "UPDATE confirmations SET status = 'invalidated', invalidated_reason = 'rewrite' "
                "WHERE preparation_id = ? AND status = 'active'", (preparation_id,))
            self._db.execute(
                "DELETE FROM document_findings WHERE source_id = ? AND code = 'replacement_requires_rewrite'",
                (source_id,))
        self.suggest_attachment_slots(fresh_id)
        return self.get_preparation(fresh_id)

    def _revalidate(self, preparation_id: str) -> None:
        """Recompute the complete Preparation's readiness findings from its current local state."""
        preparation = self._db.execute(
            "SELECT * FROM preparations WHERE id = ?", (preparation_id,)).fetchone()
        if preparation is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        self._db.execute("DELETE FROM readiness_findings WHERE preparation_id = ?", (preparation_id,))
        recorded = [row[0] for row in self._db.execute(
            "SELECT a.address FROM supervisor_addresses a JOIN tasks t ON t.supervisor_id = a.supervisor_id "
            "WHERE t.id = ? ORDER BY a.address", (preparation["task_id"],))]
        recipient = email_address(preparation["recipient"])
        if not preparation["subject"].strip():
            self._record_finding(
                preparation_id, "missing_subject",
                "No authoritative subject is available for this Preparation")
        if recipient is None:
            self._record_finding(
                preparation_id, "invalid_recipient",
                f"Draft recipient is not a usable address: {preparation['recipient']}")
        elif recorded and recipient.casefold() not in {address.casefold() for address in recorded}:
            self._record_finding(
                preparation_id, "recipient_conflict",
                f"Draft recipient {recipient} differs from recorded Supervisor address(es): "
                f"{', '.join(recorded)}")
        if self._db.execute(
                "SELECT 1 FROM exceptions WHERE task_id = ? AND code = 'identity_ambiguity' AND blocking = 1",
                (preparation["task_id"],)).fetchone():
            self._record_finding(
                preparation_id, "identity_conflict",
                "The associated Outreach Task has an unresolved Supervisor identity conflict")

    def set_subject(self, preparation_id: str, subject: str) -> dict:
        """Record an explicit operator subject as the field's Authoritative Source."""
        subject = subject.strip()
        if not subject:
            raise SmartMailError("A non-blank subject is required; SmartMail never invents one")
        with self._db:
            self._correct_field(preparation_id, "subject", subject)
        return self.get_preparation(preparation_id)

    def set_recipient(self, preparation_id: str, address: str) -> dict:
        """Record an explicit operator recipient; the value is normalized, never guessed."""
        normalized = email_address(address)
        if normalized is None:
            raise SmartMailError("A usable email address is required; SmartMail never guesses a recipient")
        with self._db:
            self._correct_field(preparation_id, "recipient", normalized)
        return self.get_preparation(preparation_id)

    def _correct_field(self, preparation_id: str, field: str, value: str) -> None:
        row = self._db.execute(
            f"SELECT {field} FROM preparations WHERE id = ?", (preparation_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        prior = row[field]
        if prior == value:
            return
        self._db.execute(f"UPDATE preparations SET {field} = ? WHERE id = ?", (value, preparation_id))
        self._record_correction(preparation_id, field, value, prior)
        self._revalidate(preparation_id)

    def _record_correction(self, preparation_id: str, field: str, value: str, prior: str) -> None:
        self._db.execute("INSERT INTO corrections VALUES (?, ?, ?, ?, ?)",
                         (str(uuid4()), preparation_id, field, value, prior))

    def _record_transformation(self, preparation_id: str, code: str, detail: str) -> None:
        self._db.execute("INSERT INTO transformations VALUES (?, ?, ?, ?)",
                         (str(uuid4()), preparation_id, code, detail))

    def _record_finding(self, preparation_id: str, code: str, detail: str, blocking: bool = True) -> None:
        self._db.execute("INSERT INTO readiness_findings VALUES (?, ?, ?, ?, ?)",
                         (str(uuid4()), preparation_id, code, detail, 1 if blocking else 0))

    def list_preparations(self, campaign_id: str) -> list[dict]:
        self.get_campaign(campaign_id)
        return [dict(row) for row in self._db.execute(
            "SELECT p.id, p.task_id, p.sender, p.recipient, p.subject, p.source_id, t.student_id, "
            "s.name AS supervisor_name, st.name AS student_name, src.name AS source_name, "
            "(SELECT count(*) FROM readiness_findings f WHERE f.preparation_id = p.id AND f.blocking = 1) "
            "AS blocking_count "
            "FROM preparations p JOIN tasks t ON t.id = p.task_id "
            "JOIN supervisors s ON s.id = t.supervisor_id JOIN students st ON st.id = t.student_id "
            "JOIN sources src ON src.id = p.source_id "
            "WHERE t.campaign_id = ? AND p.superseded_by IS NULL ORDER BY t.rowid",
            (campaign_id,))]

    def preview_preparation(self, preparation_id: str) -> dict:
        """The full local message, with readiness and the separated internal note kept apart."""
        preparation = self.get_preparation(preparation_id)
        blocking = [finding["code"] for finding in preparation["readiness_findings"] if finding["blocking"]]
        readiness = "Blocked: " + ", ".join(blocking) if blocking else "Ready"
        subject = preparation["subject"] or "(no authoritative subject)"
        confirmed = [slot["attachment"]["name"] for slot in preparation["attachment_slots"]
                     if slot["attachment"]]
        suggested = [
            f"{slot['label']} \u2192 " + (slot["candidates"][0]["name"] if slot["suggested_source_id"]
                                          else "no single candidate")
            for slot in preparation["attachment_slots"] if not slot["attachment"]]
        lines = [
            f"From: {preparation['sender']}",
            f"To: {preparation['recipient']}",
            f"Subject: {subject}",
            f"Readiness: {readiness}",
            f"Source: {preparation['source']['name']}",
            f"Attachments: {', '.join(confirmed) if confirmed else '(none)'}",
        ]
        if suggested:
            lines.append(f"Suggested attachments: {'; '.join(suggested)}")
        text = "\n".join([*lines, "", preparation["body"]])
        return {"sender": preparation["sender"], "recipient": preparation["recipient"],
                "subject": preparation["subject"], "body": preparation["body"],
                "internal_note": preparation["internal_note"], "readiness": readiness,
                "attachments": confirmed, "suggested_attachments": suggested, "text": text}

    def get_preparation(self, preparation_id: str) -> dict:
        row = self._db.execute("SELECT * FROM preparations WHERE id = ?", (preparation_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        preparation = dict(row)
        preparation["source"] = dict(self._db.execute(
            "SELECT id, name, sha256 FROM sources WHERE id = ?", (row["source_id"],)).fetchone())
        preparation["association"] = json.loads(preparation.pop("association_evidence"))
        preparation["transformations"] = [dict(r) for r in self._db.execute(
            "SELECT code, detail FROM transformations WHERE preparation_id = ? ORDER BY rowid", (preparation_id,))]
        preparation["readiness_findings"] = [dict(r) for r in self._db.execute(
            "SELECT code, detail, blocking FROM readiness_findings WHERE preparation_id = ? ORDER BY rowid",
            (preparation_id,))]
        preparation["corrections"] = [dict(r) for r in self._db.execute(
            "SELECT field, value, prior FROM corrections WHERE preparation_id = ? ORDER BY rowid",
            (preparation_id,))]
        preparation["attachment_slots"] = self.list_attachment_slots(preparation_id)
        preparation["status"] = "superseded" if preparation["superseded_by"] else "active"
        preparation["ready"] = not any(finding["blocking"] for finding in preparation["readiness_findings"])
        return preparation

    def get_preparation_history(self, preparation_id: str) -> dict:
        """Every version of an Outreach Task's Preparation, newest first, with its evidence."""
        row = self._db.execute(
            "SELECT task_id FROM preparations WHERE id = ?", (preparation_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        versions = [self.get_preparation(r["id"]) for r in self._db.execute(
            "SELECT id FROM preparations WHERE task_id = ? ORDER BY rowid DESC", (row["task_id"],))]
        active_id = next((version["id"] for version in versions if version["status"] == "active"), None)
        return {"task_id": row["task_id"], "active_id": active_id, "versions": versions}

    def _content_digest(self, preparation: dict) -> str:
        """A stable fingerprint of the exact message content a Confirmation binds."""
        canonical = json.dumps(
            {"sender": preparation["sender"], "recipient": preparation["recipient"],
             "subject": preparation["subject"], "body": preparation["body"]},
            ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _attachments_digest(self, preparation: dict) -> str:
        """A stable fingerprint of the confirmed attachment bytes a Confirmation binds."""
        entries = [[slot["label"], slot["attachment"]["name"], slot["attachment"]["sha256"]]
                   for slot in preparation["attachment_slots"] if slot["attachment"]]
        return hashlib.sha256(json.dumps(entries, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _expired_detail(self) -> str:
        """Explain an elapsed confirmed time without ever implying an immediate send."""
        return (
            "The confirmed sending time has elapsed; an explicitly confirmed replacement time is "
            "required. SmartMail never substitutes an immediate send for an elapsed time")

    def _confirmation_expired(self, confirmation: dict) -> bool:
        """Whether the exact operator authorization has passed its validity time."""
        execution = confirmation.get("execution") or {}
        expiry = next((execution.get(key) for key in (
            "expires_at", "valid_until", "confirmation_expires_at", "confirmed_until"
        ) if execution.get(key)), None)
        if expiry is None and execution.get("confirmed_time"):
            expiry = execution["confirmed_time"]
        if expiry is None and execution.get("kind") != "immediate":
            expiry = next((execution.get(key) for key in (
                "scheduled_at", "scheduled_time"
            ) if execution.get(key)), None)
        parsed = self._parse_timestamp(expiry)
        return parsed is not None and parsed <= self._parse_timestamp(self._now())

    def review_confirmation(self, preparation_id: str) -> dict:
        """Everything an operator inspects before confirming: exact content and execution details."""
        preparation = self.get_preparation(preparation_id)
        attachments = [
            {"id": slot["attachment"]["id"], "label": slot["label"],
             "name": slot["attachment"]["name"], "sha256": slot["attachment"]["sha256"],
             "size": slot["attachment"]["size"]}
            for slot in preparation["attachment_slots"] if slot["attachment"]]
        sent = self._db.execute(
            "SELECT 1 FROM sent_records WHERE preparation_id = ?", (preparation_id,)).fetchone()
        active = self._db.execute(
            "SELECT * FROM confirmations WHERE preparation_id = ? AND status = 'active'",
            (preparation_id,)).fetchone()
        execution = json.loads(active["execution_detail"]) if active else {"kind": "immediate"}
        return {
            "preparation_id": preparation_id, "task_id": preparation["task_id"],
            "status": preparation["status"], "sender": preparation["sender"],
            "recipient": preparation["recipient"], "subject": preparation["subject"],
            "body": preparation["body"], "attachments": attachments,
            "readiness_findings": preparation["readiness_findings"],
            "ready": preparation["ready"], "execution": execution,
            "already_sent": sent is not None,
            "confirmation_id": active["id"] if active else None,
            "message": self.preview_preparation(preparation_id)["text"],
        }

    def confirm(self, preparation_id: str, execution: dict | None = None,
                *, confirmed_at: str | datetime | None = None) -> dict:
        """Authorize exactly one Ready Preparation for its bound execution details."""
        return self.confirm_preparations(
            [preparation_id], execution=execution, confirmed_at=confirmed_at)[0]

    def confirm_preparations(self, preparation_ids: list[str], execution: dict | None = None,
                             *, confirmed_at: str | datetime | None = None) -> list[dict]:
        """Confirm several Preparations in one operator action; each gets its own Confirmation."""
        confirmations = []
        execution_detail = dict(execution or {"kind": "immediate"})
        if not execution_detail.get("kind"):
            raise SmartMailError("Confirmation execution details require a kind")
        confirmed_at_value = confirmed_at or self._now()
        if isinstance(confirmed_at_value, datetime):
            confirmed_at_value = confirmed_at_value.isoformat()
        with self._db:
            for preparation_id in preparation_ids:
                preparation = self.get_preparation(preparation_id)
                if preparation["status"] != "active":
                    raise SmartMailError(
                        f"Cannot confirm a Superseded Preparation: {preparation_id}")
                if self._db.execute(
                        "SELECT 1 FROM sent_records WHERE preparation_id = ?",
                        (preparation_id,)).fetchone():
                    raise SmartMailError(
                        "Preparation has already been sent; prepare a new linked Communication "
                        f"Action instead: {preparation_id}")
                blocking = [f["code"] for f in preparation["readiness_findings"] if f["blocking"]]
                if blocking:
                    raise SmartMailError(
                        f"Preparation is not Ready; resolve: {', '.join(blocking)}")
                content_digest = self._content_digest(preparation)
                attachments_digest = self._attachments_digest(preparation)
                active = self._db.execute(
                    "SELECT * FROM confirmations WHERE preparation_id = ? AND status = 'active'",
                    (preparation_id,)).fetchone()
                active_execution = json.loads(active["execution_detail"]) if active else None
                active_view = self._confirmation_view(active) if active else None
                if active and active["content_digest"] == content_digest \
                        and active["attachments_digest"] == attachments_digest \
                        and active_execution == execution_detail \
                        and not self._confirmation_expired(active_view):
                    confirmations.append(self._confirmation_view(active))
                    continue
                if active:
                    invalidated_reason = (
                        "expired" if self._confirmation_expired(active_view) else "renewed")
                    self._db.execute(
                        "UPDATE confirmations SET status = 'invalidated', invalidated_reason = ? "
                        "WHERE id = ?", (invalidated_reason, active["id"]))
                confirmation_id = str(uuid4())
                self._db.execute(
                    "INSERT INTO confirmations "
                    "(id, preparation_id, task_id, execution_kind, execution_detail, "
                    "content_digest, attachments_digest, status, invalidated_reason, confirmed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', '', ?)",
                    (confirmation_id, preparation_id, preparation["task_id"], execution_detail["kind"],
                     json.dumps(execution_detail, ensure_ascii=False),
                     content_digest, attachments_digest, confirmed_at_value))
                confirmations.append(self.get_confirmation(confirmation_id))
                self._clear_confirmation_expired_pause(self._campaign_of_task(preparation["task_id"]))
        return confirmations

    def _confirmation_view(self, row) -> dict:
        return {
            "id": row["id"], "preparation_id": row["preparation_id"], "task_id": row["task_id"],
            "status": row["status"], "execution": json.loads(row["execution_detail"]),
            "content_digest": row["content_digest"],
            "attachments_digest": row["attachments_digest"],
            "invalidated_reason": row["invalidated_reason"],
            "confirmed_at": row["confirmed_at"],
        }

    def get_confirmation(self, confirmation_id: str) -> dict:
        row = self._db.execute(
            "SELECT * FROM confirmations WHERE id = ?", (confirmation_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Confirmation not found: {confirmation_id}")
        return self._confirmation_view(row)

    def list_confirmations(self, campaign_id: str) -> list[dict]:
        """Active operator authorizations for a Campaign; invalidated ones stay inspectable by ID."""
        self.get_campaign(campaign_id)
        return [self._confirmation_view(row) for row in self._db.execute(
            "SELECT c.* FROM confirmations c JOIN tasks t ON t.id = c.task_id "
            "WHERE t.campaign_id = ? AND c.status = 'active' ORDER BY c.rowid", (campaign_id,))]

    def resume_execution(self, campaign_id: str,
                         confirmation_ids: list[str] | None = None) -> dict:
        """Resume only active, still-valid Confirmations after persisted recovery checks."""
        self.get_campaign(campaign_id)
        flow = self._flow_state(campaign_id)
        if flow["state"] == "paused":
            return {"attempts": [], "paused": True, "flow": flow}
        confirmations = (
            [self.get_confirmation(confirmation_id) for confirmation_id in confirmation_ids]
            if confirmation_ids is not None else self.list_confirmations(campaign_id))
        for confirmation in confirmations:
            if self._campaign_of_task(confirmation["task_id"]) != campaign_id:
                raise SmartMailError(
                    f"Confirmation is outside Campaign {campaign_id}: {confirmation['id']}")
            if self._confirmation_expired(confirmation):
                detail = self._expired_detail()
                self._pause_flow(campaign_id, "confirmation_expired", {"detail": detail})
                self._db.commit()
                return {"attempts": [], "paused": True,
                        "flow": self._flow_state(campaign_id),
                        "expired_confirmation_id": confirmation["id"]}
        if not confirmations:
            return {"attempts": [], "paused": False, "flow": flow}
        return self.run_execution([confirmation["id"] for confirmation in confirmations])

    def recover_execution(self, campaign_id: str,
                          confirmation_ids: list[str] | None = None) -> dict:
        """Compatibility name for the operator-facing restart recovery operation."""
        return self.resume_execution(campaign_id, confirmation_ids)

    def run_execution(self, confirmation_ids: list[str]) -> dict:
        """Execute confirmed immediate sends in order through the adapter.

        The intent row is committed before submission, and the submission-start
        marker is committed separately.  A restart can therefore distinguish a
        request that was never started from one whose external outcome is
        unknown; only the former is safe to resume automatically.
        """
        if not confirmation_ids:
            raise SmartMailError("At least one Confirmation is required")
        attempts: list[dict] = []
        paused = False
        campaign_id = None
        for confirmation_id in confirmation_ids:
            confirmation = self.get_confirmation(confirmation_id)
            campaign_id = self._campaign_of_task(confirmation["task_id"])
            flow = self._flow_state(campaign_id)
            if flow["state"] == "paused":
                raise SmartMailError(
                    f"Execution Flow is paused ({flow['reason']}); resolve it before executing")
            request = self._authorized_request(confirmation)
            check = self.check_duplicate(confirmation["preparation_id"])
            if check["review_required"]:
                self._pause_flow(campaign_id, check["finding"], {"detail": check["detail"]})
                self._db.commit()
                paused = True
                break
            existing = self._db.execute(
                "SELECT * FROM execution_attempts WHERE confirmation_id = ? "
                "ORDER BY rowid DESC LIMIT 1", (confirmation["id"],)).fetchone()
            if existing and existing["state"] in ("in_progress", "unknown"):
                self._pause_flow_if_idle(
                    campaign_id, "recovery_required",
                    {"detail": "An unresolved Execution Attempt requires Reconciliation"})
                self._db.commit()
                raise SmartMailError(
                    "An unresolved Execution Attempt exists; reconcile it before retrying")

            now = self._now()
            if existing and existing["state"] == "not_attempted":
                attempt_id = existing["id"]
                evidence = json.loads(existing["evidence"]) if existing["evidence"] else {}
                evidence.update({"phase": "submission_started", "submission_started_at": now})
                self._db.execute(
                    "UPDATE execution_attempts SET state = 'in_progress', evidence = ?, "
                    "phase = 'submission_started', submission_started_at = ?, updated_at = ? "
                    "WHERE id = ?",
                    (json.dumps(evidence, ensure_ascii=False), now, now, attempt_id))
            else:
                attempt_id = str(uuid4())
                evidence = {
                    "outcome": "not_attempted",
                    "phase": "intent_recorded",
                    "intent_persisted_at": now,
                }
                self._db.execute(
                    "INSERT INTO execution_attempts "
                    "(id, confirmation_id, preparation_id, task_id, sequence, state, request, "
                    "evidence, phase, intent_at, submission_started_at, outcome_observed_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 'not_attempted', ?, ?, 'intent_recorded', ?, '', '', ?)",
                    (attempt_id, confirmation["id"], confirmation["preparation_id"],
                     confirmation["task_id"], self._next_sequence(confirmation["preparation_id"]),
                     json.dumps(request, ensure_ascii=False),
                     json.dumps(evidence, ensure_ascii=False), now, now))
                self._db.commit()
                evidence["phase"] = "submission_started"
                evidence["submission_started_at"] = now
                self._db.execute(
                    "UPDATE execution_attempts SET state = 'in_progress', evidence = ?, "
                    "phase = 'submission_started', submission_started_at = ?, updated_at = ? "
                    "WHERE id = ?",
                    (json.dumps(evidence, ensure_ascii=False), now, now, attempt_id))
            self._db.commit()

            attachment_files, cleanup_attachments = self._materialize_attachments(
                confirmation["preparation_id"])
            try:
                evidence = self._submit(request, attachment_files)
                if not isinstance(evidence, dict) or evidence.get("outcome") not in {
                        "sent", "failed", "unknown", "authentication_required"}:
                    raise SmartMailError("Mailbox adapter returned an unsupported execution outcome")
            except Exception as error:
                if getattr(error, "phase", "") == "before_submission":
                    evidence = dict(evidence)
                    evidence.pop("submission_started_at", None)
                    evidence.update({
                        "outcome": "not_attempted",
                        "phase": "intent_recorded",
                        "crash_phase": "before_submission",
                        "detail": str(error),
                    })
                    self._db.execute(
                        "UPDATE execution_attempts SET state = 'not_attempted', evidence = ?, "
                        "phase = 'intent_recorded', submission_started_at = '', updated_at = ? "
                        "WHERE id = ?",
                        (json.dumps(evidence, ensure_ascii=False), self._now(), attempt_id))
                    self._db.commit()
                    raise
                evidence = {
                    "outcome": "unknown",
                    "phase": "recovery_required",
                    "detail": str(error) or "External submission was interrupted",
                    "error_type": type(error).__name__,
                    "recovered_after_restart": False,
                }
                if getattr(error, "phase", ""):
                    evidence["crash_phase"] = error.phase
                failed_at = self._now()
                self._db.execute(
                    "UPDATE execution_attempts SET state = 'unknown', evidence = ?, "
                    "phase = 'recovery_required', outcome_observed_at = ?, updated_at = ? "
                    "WHERE id = ?",
                    (json.dumps(evidence, ensure_ascii=False), failed_at, failed_at, attempt_id))
                self._pause_flow(campaign_id, "recovery_required", evidence)
                self._db.commit()
                raise
            finally:
                cleanup_attachments()

            adapter_evidence = dict(evidence)
            state = adapter_evidence["outcome"]
            interruption = None
            if state == "authentication_required":
                interruption = state
                adapter_evidence["interruption"] = interruption
                adapter_evidence["outcome"] = "unknown"
                state = "unknown"
            observed_at = self._now()
            evidence = dict(adapter_evidence)
            evidence["outcome_observed_at"] = observed_at
            evidence["phase"] = "outcome_observed"
            self._db.execute(
                "UPDATE execution_attempts SET state = ?, evidence = ?, phase = 'outcome_observed', "
                "outcome_observed_at = ?, updated_at = ? WHERE id = ?",
                (state, json.dumps(evidence, ensure_ascii=False), observed_at, observed_at, attempt_id))
            # Persist the adapter's outcome before writing the Sent Record.  If
            # the process stops during record creation, restart can finish the
            # local record without another external request.
            self._db.commit()
            if state == "sent":
                try:
                    self._record_sent(confirmation, attempt_id, request, adapter_evidence)
                    self._db.execute(
                        "UPDATE confirmations SET status = 'consumed' WHERE id = ?",
                        (confirmation["id"],))
                    evidence["phase"] = "recorded"
                    self._db.execute(
                        "UPDATE execution_attempts SET evidence = ?, phase = 'recorded', "
                        "updated_at = ? WHERE id = ?",
                        (json.dumps(evidence, ensure_ascii=False), self._now(), attempt_id))
                except Exception as error:
                    evidence["phase"] = "recovery_required"
                    evidence["detail"] = str(error) or "Sent Record persistence was interrupted"
                    self._db.execute(
                        "UPDATE execution_attempts SET evidence = ?, phase = 'recovery_required', "
                        "updated_at = ? WHERE id = ?",
                        (json.dumps(evidence, ensure_ascii=False), self._now(), attempt_id))
                    self._pause_flow(campaign_id, "recovery_required", evidence)
                    self._db.commit()
                    raise
            else:
                self._pause_flow(
                    campaign_id,
                    interruption or _PAUSE_REASONS[state],
                    evidence)
                paused = True
            self._db.commit()
            attempts.append(self.get_execution_attempt(attempt_id))
            if paused:
                break
        return {"attempts": attempts, "paused": paused,
                "flow": self._flow_state(campaign_id)}

    def _authorized_request(self, confirmation: dict) -> dict:
        """The exact external request a Confirmation authorizes, or an operator-visible refusal."""
        preparation = self.get_preparation(confirmation["preparation_id"])
        if confirmation["status"] != "active":
            raise SmartMailError(
                f"Confirmation is not active ({confirmation['status']}); "
                "renew Confirmation before executing")
        if self._confirmation_expired(confirmation):
            campaign_id = self._campaign_of_task(confirmation["task_id"])
            detail = self._expired_detail()
            self._pause_flow(campaign_id, "confirmation_expired", {"detail": detail})
            self._db.commit()
            raise SmartMailError(detail)
        if preparation["status"] != "active":
            raise SmartMailError(
                "Preparation has been superseded; renew Confirmation before executing")
        if self._db.execute(
                "SELECT 1 FROM sent_records WHERE preparation_id = ?",
                (preparation["id"],)).fetchone():
            raise SmartMailError(
                "Preparation has already been sent; a new linked Communication Action is required")
        # A confirmed schedule is never carried out as an immediate send, whatever
        # adapter is enabled: placing a schedule is its own unverified capability.
        self._require_immediate_kind(confirmation["execution"])
        if not getattr(self.mailbox, "enabled", False):
            raise SmartMailError(
                "External execution is disabled: no verified mailbox capability is enabled")
        if self._content_digest(preparation) != confirmation["content_digest"] \
                or self._attachments_digest(preparation) != confirmation["attachments_digest"]:
            raise SmartMailError(
                "Preparation content changed after Confirmation; confirm the exact content again")
        blocking = [f["code"] for f in preparation["readiness_findings"] if f["blocking"]]
        if blocking:
            raise SmartMailError(f"Preparation is not Ready; resolve: {', '.join(blocking)}")
        return self._execution_request(preparation, confirmation["execution"])

    @staticmethod
    def _require_immediate_kind(execution: dict | None) -> None:
        """Only immediate execution is enabled; a confirmed schedule is not substituted."""
        execution = execution or {"kind": "immediate"}
        if execution.get("kind") != "immediate":
            raise SmartMailError(
                f"External execution kind is not enabled: {execution.get('kind', '')}; placing "
                "and running a confirmed schedule requires the native mailbox scheduling "
                "capability, which is not enabled")

    def _execution_request(self, preparation: dict, execution: dict | None = None) -> dict:
        execution = execution or {"kind": "immediate"}
        self._require_immediate_kind(execution)
        attachments = [
            {"label": slot["label"], "name": slot["attachment"]["name"],
             "sha256": slot["attachment"]["sha256"], "size": slot["attachment"]["size"]}
            for slot in preparation["attachment_slots"] if slot["attachment"]]
        return {"sender": preparation["sender"], "recipient": preparation["recipient"],
                "subject": preparation["subject"], "body": preparation["body"],
                "attachments": attachments, "kind": execution["kind"]}

    def _submit(self, request: dict, attachments=None) -> dict:
        try:
            return self.mailbox.submit(request, attachments)
        except MailboxCapabilityError as error:
            raise SmartMailError(str(error)) from error

    @staticmethod
    def _safe_attachment_name(name: str) -> str:
        candidate = Path(str(name)).name
        candidate = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", candidate).strip(" .")
        return candidate or "attachment"

    def _materialize_attachments(self, preparation_id: str):
        """Copy the confirmed attachment bytes to private files for the adapter.

        Only adapters that upload from disk need this.  Each attachment gets its
        own folder so the exact confirmed filename is preserved and colliding
        names cannot overwrite one another.  The copies are removed after the
        single submission; preserved bytes are never modified.
        """
        if not getattr(self.mailbox, "needs_attachment_files", False):
            return [], (lambda: None)
        preparation = self.get_preparation(preparation_id)
        confirmed = [slot for slot in preparation["attachment_slots"] if slot["attachment"]]
        if not confirmed:
            return [], (lambda: None)
        directory = tempfile.mkdtemp(prefix="smartmail-send-")
        paths = []
        for index, slot in enumerate(confirmed):
            folder = Path(directory) / f"slot{index}"
            folder.mkdir()
            target = folder / self._safe_attachment_name(slot["attachment"]["name"])
            target.write_bytes(self.read_attachment(slot["attachment"]["id"]))
            paths.append(target)
        return paths, (lambda: shutil.rmtree(directory, ignore_errors=True))

    def _record_sent(self, confirmation: dict, attempt_id: str, request: dict, evidence: dict) -> str:
        """Freeze the exact content and attachment bytes that the mailbox confirmed as sent."""
        sent_id = str(uuid4())
        content = json.dumps({"sender": request["sender"], "recipient": request["recipient"],
                              "subject": request["subject"], "body": request["body"]},
                             ensure_ascii=False)
        preparation_kind = self._db.execute(
            "SELECT action_kind, linked_sent_record_id FROM preparations WHERE id = ?",
            (confirmation["preparation_id"],)).fetchone()
        self._db.execute(
            "INSERT INTO sent_records (id, preparation_id, task_id, attempt_id, content, evidence, "
            "reference, action_kind, follows_sent_record_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sent_id, confirmation["preparation_id"], confirmation["task_id"], attempt_id,
             content, json.dumps(evidence, ensure_ascii=False), evidence["reference"],
             preparation_kind["action_kind"], preparation_kind["linked_sent_record_id"]))
        preparation = self.get_preparation(confirmation["preparation_id"])
        for slot in preparation["attachment_slots"]:
            if slot["attachment"]:
                attachment = slot["attachment"]
                self._db.execute(
                    "INSERT INTO sent_attachments VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid4()), sent_id, slot["label"], attachment["name"],
                     self.read_attachment(attachment["id"]), attachment["sha256"]))
        return sent_id

    def _attempt_view(self, row) -> dict:
        sent = self._db.execute(
            "SELECT id FROM sent_records WHERE attempt_id = ?", (row["id"],)).fetchone()
        return {"id": row["id"], "confirmation_id": row["confirmation_id"],
                "preparation_id": row["preparation_id"], "task_id": row["task_id"],
                "sequence": row["sequence"], "state": row["state"],
                "phase": row["phase"], "intent_at": row["intent_at"],
                "submission_started_at": row["submission_started_at"],
                "outcome_observed_at": row["outcome_observed_at"],
                "updated_at": row["updated_at"],
                "request": json.loads(row["request"]),
                "evidence": json.loads(row["evidence"]) if row["evidence"] else None,
                "sent_record_id": sent["id"] if sent else None}

    def list_execution_attempts(self, campaign_id: str) -> list[dict]:
        """The Execution Ledger: every observed attempt for a Campaign, in order."""
        self.get_campaign(campaign_id)
        return [self._attempt_view(row) for row in self._db.execute(
            "SELECT a.* FROM execution_attempts a JOIN tasks t ON t.id = a.task_id "
            "WHERE t.campaign_id = ? ORDER BY a.rowid", (campaign_id,))]

    def get_execution_attempt(self, attempt_id: str) -> dict:
        row = self._db.execute(
            "SELECT * FROM execution_attempts WHERE id = ?", (attempt_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Execution Attempt not found: {attempt_id}")
        return self._attempt_view(row)

    def get_sent_record(self, sent_record_id: str) -> dict:
        row = self._db.execute("SELECT * FROM sent_records WHERE id = ?", (sent_record_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Sent Record not found: {sent_record_id}")
        attachments = [
            {"id": r["id"], "label": r["label"], "name": r["name"],
             "sha256": r["sha256"], "size": len(r["content"])}
            for r in self._db.execute(
                "SELECT * FROM sent_attachments WHERE sent_record_id = ? ORDER BY rowid",
                (sent_record_id,))]
        return {"id": row["id"], "preparation_id": row["preparation_id"], "task_id": row["task_id"],
                "attempt_id": row["attempt_id"], **json.loads(row["content"]),
                "attachments": attachments, "evidence": json.loads(row["evidence"]),
                "reference": row["reference"]}

    def list_sent_records(self, campaign_id: str) -> list[dict]:
        self.get_campaign(campaign_id)
        return [self.get_sent_record(row["id"]) for row in self._db.execute(
            "SELECT s.id FROM sent_records s JOIN tasks t ON t.id = s.task_id "
            "WHERE t.campaign_id = ? ORDER BY s.rowid", (campaign_id,))]

    def read_sent_attachment(self, sent_attachment_id: str) -> bytes:
        row = self._db.execute(
            "SELECT content FROM sent_attachments WHERE id = ?", (sent_attachment_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Sent attachment not found: {sent_attachment_id}")
        return bytes(row["content"])

    def execution_status(self, campaign_id: str) -> dict:
        """The current Execution Flow state for a Campaign; absent means idle."""
        self.get_campaign(campaign_id)
        return self._flow_state(campaign_id)

    def stop_execution_attempt(self, attempt_id: str, detail: str = "") -> dict:
        """Stop an unresolved attempt so the Execution Flow can proceed under a fresh decision."""
        row = self._db.execute(
            "SELECT * FROM execution_attempts WHERE id = ?", (attempt_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Execution Attempt not found: {attempt_id}")
        if row["state"] not in ("in_progress", "unknown"):
            raise SmartMailError(
                f"Execution Attempt is not active ({row['state']}); "
                "reconciliation is required before it can be resolved")
        evidence = json.loads(row["evidence"]) if row["evidence"] else {}
        evidence["stopped"] = True
        if detail:
            evidence["detail"] = detail
        with self._db:
            self._db.execute(
                "UPDATE execution_attempts SET state = 'stopped', evidence = ? WHERE id = ?",
                (json.dumps(evidence, ensure_ascii=False), attempt_id))
            campaign_id = self._campaign_of_task(row["task_id"])
            flow = self._flow_state(campaign_id)
            if flow["state"] == "paused" and flow["reason"] in {
                    "unknown_outcome", "recovery_required", "reconcile_required",
                    "manual_takeover", "authentication_required"}:
                self._db.execute(
                    "DELETE FROM execution_flow WHERE campaign_id = ?", (campaign_id,))
        return self.get_execution_attempt(attempt_id)

    def take_over_execution(self, attempt_id: str, detail: str = "") -> dict:
        """Record an explicit Manual Takeover without asserting that it was Sent."""
        row = self._db.execute(
            "SELECT * FROM execution_attempts WHERE id = ?", (attempt_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Execution Attempt not found: {attempt_id}")
        if row["state"] not in ("in_progress", "unknown"):
            raise SmartMailError(
                f"Execution Attempt is not unresolved ({row['state']})")
        evidence = json.loads(row["evidence"]) if row["evidence"] else {}
        evidence["manual_takeover"] = True
        if detail:
            evidence["detail"] = detail
        evidence["phase"] = "manual_takeover"
        now = self._now()
        with self._db:
            self._db.execute(
                "UPDATE execution_attempts SET state = 'unknown', evidence = ?, "
                "phase = 'manual_takeover', updated_at = ? WHERE id = ?",
                (json.dumps(evidence, ensure_ascii=False), now, attempt_id))
            self._pause_flow_if_idle(
                self._campaign_of_task(row["task_id"]), "manual_takeover", evidence)
        return self.get_execution_attempt(attempt_id)

    def manual_takeover(self, attempt_id: str, detail: str = "") -> dict:
        """Alias using the domain noun for an explicit operator takeover."""
        return self.take_over_execution(attempt_id, detail)

    def reconcile_execution(self, attempt_id: str,
                            confirmation_ids: list[str] | None = None,
                            *, acknowledge: bool = False) -> dict:
        """Alias for explicit reconcile-and-continue at the core boundary."""
        return self.reconcile_and_continue(
            attempt_id, confirmation_ids, acknowledge=acknowledge)

    def _flow_state(self, campaign_id: str) -> dict:
        row = self._db.execute(
            "SELECT * FROM execution_flow WHERE campaign_id = ?", (campaign_id,)).fetchone()
        if row is None:
            return {"campaign_id": campaign_id, "state": "idle", "reason": "", "detail": ""}
        return {"campaign_id": campaign_id, "state": row["state"],
                "reason": row["reason"], "detail": row["detail"]}

    def _pause_flow(self, campaign_id: str, reason: str, evidence: dict) -> None:
        detail = evidence.get("detail", "") if isinstance(evidence, dict) else ""
        self._db.execute(
            "INSERT INTO execution_flow VALUES (?, 'paused', ?, ?) "
            "ON CONFLICT(campaign_id) DO UPDATE SET state = 'paused', "
            "reason = excluded.reason, detail = excluded.detail",
            (campaign_id, reason, detail))

    def _pause_flow_if_idle(self, campaign_id: str, reason: str, evidence: dict) -> None:
        """Add a recovery pause without replacing an existing operator blocker."""
        if self._flow_state(campaign_id)["state"] == "idle":
            self._pause_flow(campaign_id, reason, evidence)

    def _clear_recovery_pause_if_resolved(self, task_id: str) -> None:
        """Release only a recovery pause once every unresolved attempt is resolved."""
        campaign_id = self._campaign_of_task(task_id)
        flow = self._flow_state(campaign_id)
        if flow["reason"] not in {
            "recovery_required", "unknown_outcome", "reconcile_required",
                "manual_takeover", "authentication_required"}:
            return
        unresolved = self._db.execute(
            "SELECT 1 FROM execution_attempts a JOIN tasks t ON t.id = a.task_id "
            "WHERE t.campaign_id = ? AND a.state IN ('in_progress', 'unknown') LIMIT 1",
            (campaign_id,)).fetchone()
        if unresolved is None:
            self._db.execute("DELETE FROM execution_flow WHERE campaign_id = ?", (campaign_id,))

    def _clear_confirmation_expired_pause(self, campaign_id: str) -> None:
        flow = self._flow_state(campaign_id)
        if flow["reason"] == "confirmation_expired":
            self._db.execute("DELETE FROM execution_flow WHERE campaign_id = ?", (campaign_id,))

    def _campaign_of_task(self, task_id: str) -> str:
        row = self._db.execute(
            "SELECT campaign_id FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Outreach Task not found: {task_id}")
        return row["campaign_id"]

    def _next_sequence(self, preparation_id: str) -> int:
        return self._db.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM execution_attempts WHERE preparation_id = ?",
            (preparation_id,)).fetchone()[0]

    # -- Sending Plans: allowed windows, timezone, spacing and daily limits ----

    def configure_plan(self, campaign_id: str, *, timezone: str | None = None,
                       windows=None, spacing_minutes: int | None = None,
                       daily_limit: int | None = None,
                       horizon_days: int | None = None) -> dict:
        """Configure the allowed windows, timezone, spacing and daily limits of a Campaign.

        Only the supplied fields change; an unconfigured Campaign starts from the
        deterministic defaults, so a proposal can always be reproduced.
        """
        self.get_campaign(campaign_id)
        current = self._plan_configuration(campaign_id)
        candidate = {
            "timezone": current["timezone"] if timezone is None
            else self._plan_timezone(timezone),
            "windows": current["windows"] if windows is None else self._plan_windows(windows),
            "spacing_minutes": current["spacing_minutes"] if spacing_minutes is None
            else self._plan_positive(spacing_minutes, "spacing", "minutes between actions"),
            "daily_limit": current["daily_limit"] if daily_limit is None
            else self._plan_positive(daily_limit, "daily limit", "actions per day"),
            "horizon_days": current["horizon_days"] if horizon_days is None
            else self._plan_positive(horizon_days, "planning horizon", "days to search"),
        }
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO plan_configurations "
                "(campaign_id, timezone, windows, spacing_minutes, daily_limit, horizon_days) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (campaign_id, candidate["timezone"],
                 json.dumps(candidate["windows"], ensure_ascii=False),
                 candidate["spacing_minutes"], candidate["daily_limit"],
                 candidate["horizon_days"]))
        return self._plan_configuration(campaign_id)

    def _plan_configuration(self, campaign_id: str) -> dict:
        """The Campaign's configuration, falling back to the deterministic defaults."""
        row = self._db.execute(
            "SELECT * FROM plan_configurations WHERE campaign_id = ?", (campaign_id,)).fetchone()
        if row is None:
            return {"campaign_id": campaign_id, **{key: (
                list(value) if key == "windows" else value
            ) for key, value in PLAN_DEFAULTS.items()}}
        return {
            "campaign_id": row["campaign_id"], "timezone": row["timezone"],
            "windows": json.loads(row["windows"]),
            "spacing_minutes": row["spacing_minutes"],
            "daily_limit": row["daily_limit"], "horizon_days": row["horizon_days"],
        }

    @staticmethod
    def _plan_timezone(name) -> str:
        name = str(name).strip()
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
            raise SmartMailError(
                f"Unknown timezone: {name or '(empty)'}; use an IANA name such as "
                "Asia/Shanghai") from error
        return name

    @staticmethod
    def _plan_positive(value, label: str, unit: str) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError) as error:
            raise SmartMailError(f"A positive integer {label} is required ({unit})") from error
        if number < 1:
            raise SmartMailError(f"A positive integer {label} is required ({unit})")
        return number

    @classmethod
    def _plan_windows(cls, specifications) -> list[dict]:
        if isinstance(specifications, (str, dict)):
            specifications = [specifications]
        if not specifications:
            raise SmartMailError(
                "At least one allowed window is required, for example 'MON-FRI 09:00-17:00'")
        return [cls._plan_window(specification) for specification in specifications]

    @classmethod
    def _plan_window(cls, specification) -> dict:
        if isinstance(specification, dict):
            specification = dict(specification)
            days = specification.pop("days", None)
            start, end = specification.pop("start", ""), specification.pop("end", "")
            if specification or days is None:
                raise SmartMailError(
                    f"Unsupported window {specification}: use "
                    "{'days': ['MON'], 'start': '09:00', 'end': '17:00'}")
        else:
            tokens = str(specification).split()
            if len(tokens) < 2:
                raise SmartMailError(
                    f"Unsupported window {specification}: use '<DAYS> HH:MM-HH:MM'")
            days, start, end = tokens[:-1], "", tokens[-1]
            start, separator, end = end.partition("-")
            if not separator:
                raise SmartMailError(
                    f"Unsupported window {specification}: use '<DAYS> HH:MM-HH:MM'")
        window_days = cls._plan_days(days, specification)
        opens = cls._plan_time(start, specification)
        closes = cls._plan_time(end, specification)
        if closes <= opens:
            raise SmartMailError(
                f"Unsupported window {specification}: the window end must be after its start")
        return {"days": window_days, "start": opens, "end": closes}

    @classmethod
    def _plan_days(cls, days, specification) -> list[str]:
        if isinstance(days, str):
            days = [days]
        tokens: list[str] = []
        for item in days or ():
            tokens.extend(str(item).replace(",", " ").split())
        normalized: list[str] = []
        for item in tokens:
            token = str(item).strip().upper()
            if token in _PLAN_DAY_TOKENS:
                span = [token]
            elif "-" in token:
                first, _, last = token.partition("-")
                first, last = first.strip().upper(), last.strip().upper()
                if first not in _PLAN_DAY_TOKENS or last not in _PLAN_DAY_TOKENS \
                        or _PLAN_DAY_TOKENS.index(first) > _PLAN_DAY_TOKENS.index(last):
                    raise SmartMailError(f"Unsupported day range {token} in an allowed window")
                span = list(_PLAN_DAY_TOKENS[_PLAN_DAY_TOKENS.index(first):_PLAN_DAY_TOKENS.index(last) + 1])
            else:
                raise SmartMailError(f"Unsupported day {token} in an allowed window")
            for day in span:
                if day not in normalized:
                    normalized.append(day)
        if not normalized:
            raise SmartMailError(f"At least one day is required in the window {specification}")
        return normalized

    @staticmethod
    def _plan_time(value, specification) -> str:
        try:
            parsed = datetime.strptime(str(value).strip(), "%H:%M").time()
        except ValueError as error:
            raise SmartMailError(
                f"Unsupported window {specification}: times must use HH:MM") from error
        return f"{parsed.hour:02d}:{parsed.minute:02d}"

    @staticmethod
    def _plan_clock(value) -> time:
        hour, _, minute = str(value).partition(":")
        return time(int(hour), int(minute))

    def propose_plan(self, campaign_id: str) -> dict:
        """Propose sending times for a Campaign under its configured constraints.

        The proposal is deterministic: the same configuration, work and controlled
        time produce the same times.  Earlier proposals that were never confirmed
        are superseded so that only one proposed plan stays current.
        """
        self.get_campaign(campaign_id)
        configuration = self._plan_configuration(campaign_id)
        slots = self._plan_slots(configuration)
        assigned: list[datetime] = []
        proposals = self._plan_entries(campaign_id)
        plannable = [proposal for proposal in proposals if proposal["status"] == "scheduled"]
        for proposal in plannable:
            slot = self._next_plan_slot(slots, assigned, configuration)
            if slot is None:
                proposal["status"] = "impossible"
                proposal["reason"] = "no_available_slot"
                continue
            assigned.append(slot)
            proposal["slot"] = slot
        not_placed = [proposal for proposal in plannable
                      if proposal["status"] == "impossible"]
        if not_placed:
            capacity = self._plan_capacity(slots, configuration)
            constraint = self._plan_binding_constraint(slots, configuration)
            detail = (
                f"The configured windows, spacing and limits provide {capacity} usable sending "
                f"time(s) within the {configuration['horizon_days']}-day horizon for "
                f"{len(plannable)} Ready action(s); this action was left unscheduled rather than "
                f"violating the {_PLAN_CONSTRAINT_LABELS[constraint]} constraint")
            for proposal in not_placed:
                proposal["constraint"] = constraint
                proposal["detail"] = detail
        plan_id = str(uuid4())
        with self._db:
            self._db.execute(
                "UPDATE sending_plans SET status = 'superseded' "
                "WHERE campaign_id = ? AND status = 'proposed'", (campaign_id,))
            self._db.execute(
                "INSERT INTO sending_plans VALUES (?, ?, ?, 'proposed', ?, ?, ?, ?, ?)",
                (plan_id, campaign_id, self._now(), configuration["timezone"],
                 json.dumps(configuration["windows"], ensure_ascii=False),
                 configuration["spacing_minutes"], configuration["daily_limit"],
                 configuration["horizon_days"]))
            for sequence, proposal in enumerate(proposals, start=1):
                self._store_plan_proposal(plan_id, sequence, proposal, configuration)
        return self.get_plan(plan_id)

    def _plan_candidates(self, campaign_id: str) -> list[dict]:
        """Active Preparations in the Campaign's deterministic Task order."""
        return [self.get_preparation(row["id"])
                for row in self._db.execute(
                    "SELECT p.id FROM preparations p JOIN tasks t ON t.id = p.task_id "
                    "WHERE t.campaign_id = ? AND p.superseded_by IS NULL ORDER BY t.rowid",
                    (campaign_id,))]

    def _plan_entries(self, campaign_id: str) -> list[dict]:
        """One plan entry per active Preparation, before any sending time is assigned."""
        entries = []
        for preparation in self._plan_candidates(campaign_id):
            if self._db.execute("SELECT 1 FROM sent_records WHERE preparation_id = ?",
                                (preparation["id"],)).fetchone():
                entries.append({
                    "preparation": preparation, "slot": None, "status": "already_sent",
                    "reason": "already_sent", "constraint": "", "detail": (
                        "This Communication Action has already been executed; further "
                        "communication is a new linked action")})
                continue
            blocking = [finding["code"] for finding in preparation["readiness_findings"]
                        if finding["blocking"]]
            if blocking:
                entries.append({
                    "preparation": preparation, "slot": None, "status": "not_ready",
                    "reason": "not_ready", "constraint": "",
                    "detail": f"Preparation is not Ready; resolve: {', '.join(blocking)}"})
                continue
            entries.append({"preparation": preparation, "slot": None, "status": "scheduled",
                            "reason": "", "constraint": "", "detail": ""})
        return entries

    def _plan_slots_per_day(self, slots, configuration: dict) -> dict:
        """How many allowed instants each local day of the horizon offers."""
        zone = ZoneInfo(configuration["timezone"])
        per_day: dict = {}
        for slot in slots:
            day = slot.astimezone(zone).date()
            per_day[day] = per_day.get(day, 0) + 1
        return per_day

    def _plan_capacity(self, slots, configuration: dict) -> int:
        """How many actions the configured constraints can actually accommodate."""
        per_day = self._plan_slots_per_day(slots, configuration)
        return sum(min(count, configuration["daily_limit"]) for count in per_day.values())

    def _plan_binding_constraint(self, slots, configuration: dict) -> str:
        """The configured constraint that prevents the remaining actions from being placed."""
        per_day = self._plan_slots_per_day(slots, configuration)
        if not per_day:
            return "windows"
        if max(per_day.values()) > configuration["daily_limit"]:
            return "daily_limit"
        return "spacing_minutes"

    def _store_plan_proposal(self, plan_id: str, sequence: int, proposal: dict,
                             configuration: dict) -> None:
        preparation = proposal["preparation"]
        slot = proposal["slot"]
        self._db.execute(
            "INSERT INTO sending_plan_proposals "
            "(id, plan_id, preparation_id, task_id, sequence, status, reason, "
            "constraint_name, detail, scheduled_at, scheduled_utc, confirmation_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (str(uuid4()), plan_id, preparation["id"], preparation["task_id"], sequence,
             proposal["status"], proposal["reason"], proposal["constraint"],
             proposal["detail"],
             slot.isoformat() if slot else "",
             slot.astimezone(timezone.utc).isoformat() if slot else ""))

    def _plan_slots(self, configuration: dict) -> list[datetime]:
        """Every allowed instant inside the configured windows, in chronological order."""
        zone = ZoneInfo(configuration["timezone"])
        now = self._instant().astimezone(zone)
        spacing = timedelta(minutes=configuration["spacing_minutes"])
        slots: list[datetime] = []
        seen: set[datetime] = set()
        for offset in range(configuration["horizon_days"]):
            date = now.date() + timedelta(days=offset)
            weekday = _PLAN_DAY_TOKENS[date.weekday()]
            for window in configuration["windows"]:
                if weekday not in window["days"]:
                    continue
                slot = datetime.combine(date, self._plan_clock(window["start"]), tzinfo=zone)
                closes = datetime.combine(date, self._plan_clock(window["end"]), tzinfo=zone)
                while slot <= closes:
                    instant = slot.astimezone(timezone.utc)
                    if slot > now and instant not in seen and self._plan_wall_time_exists(slot):
                        seen.add(instant)
                        slots.append(slot)
                    slot += spacing
        slots.sort()
        return slots

    @staticmethod
    def _plan_wall_time_exists(slot: datetime) -> bool:
        """Refuse a local wall time that the configured zone skips.

        A daylight-saving jump makes some clock readings nonexistent; silently
        shifting one would place an action at an instant the operator never chose.
        """
        resolved = slot.astimezone(timezone.utc).astimezone(slot.tzinfo)
        return (resolved.year, resolved.month, resolved.day, resolved.hour, resolved.minute) == \
            (slot.year, slot.month, slot.day, slot.hour, slot.minute)

    def _next_plan_slot(self, slots, assigned, configuration: dict):
        """The next allowed instant that keeps the spacing and daily limits intact."""
        zone = ZoneInfo(configuration["timezone"])
        spacing = timedelta(minutes=configuration["spacing_minutes"])
        counts: dict = {}
        for instant in assigned:
            day = instant.astimezone(zone).date()
            counts[day] = counts.get(day, 0) + 1
        previous = assigned[-1] if assigned else None
        taken = set(assigned)
        for slot in slots:
            if slot in taken:
                continue
            if previous is not None and slot - previous < spacing:
                continue
            day = slot.astimezone(zone).date()
            if counts.get(day, 0) >= configuration["daily_limit"]:
                continue
            return slot
        return None

    def get_plan(self, plan_id: str) -> dict:
        """The Sending Plan as batch review: exact content, times and exclusions."""
        row = self._db.execute("SELECT * FROM sending_plans WHERE id = ?", (plan_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Sending Plan not found: {plan_id}")
        configuration = {
            "timezone": row["timezone"], "windows": json.loads(row["windows"]),
            "spacing_minutes": row["spacing_minutes"], "daily_limit": row["daily_limit"],
            "horizon_days": row["horizon_days"],
        }
        views = []
        for proposal in self._db.execute(
                "SELECT * FROM sending_plan_proposals WHERE plan_id = ? ORDER BY sequence",
                (plan_id,)):
            views.append(self._plan_proposal_view(proposal, row["timezone"]))
        return {
            "id": row["id"], "campaign_id": row["campaign_id"], "created_at": row["created_at"],
            "status": row["status"], "configuration": configuration,
            "proposals": [view for view in views if view["status"] == "scheduled"],
            "unavailable": [view for view in views
                            if view["status"] in ("not_ready", "already_sent")],
            "impossible": [view for view in views if view["status"] == "impossible"],
        }

    def _plan_proposal_view(self, proposal, timezone_name: str) -> dict:
        """One planned action with everything an operator reviews before Confirmation."""
        preparation = self.get_preparation(proposal["preparation_id"])
        attachments = [
            {"id": slot["attachment"]["id"], "label": slot["label"],
             "name": slot["attachment"]["name"], "sha256": slot["attachment"]["sha256"],
             "size": slot["attachment"]["size"]}
            for slot in preparation["attachment_slots"] if slot["attachment"]]
        return {
            "preparation_id": proposal["preparation_id"], "task_id": proposal["task_id"],
            "status": proposal["status"], "reason": proposal["reason"],
            "constraint": proposal["constraint_name"], "detail": proposal["detail"],
            "scheduled_at": proposal["scheduled_at"], "timezone": timezone_name,
            "scheduled_utc": proposal["scheduled_utc"],
            "confirmation_id": proposal["confirmation_id"],
            "sender": preparation["sender"], "recipient": preparation["recipient"],
            "subject": preparation["subject"], "ready": preparation["ready"],
            "readiness_findings": preparation["readiness_findings"],
            "attachments": attachments,
            "message": self.preview_preparation(proposal["preparation_id"])["text"],
        }

    def list_plans(self, campaign_id: str) -> list[dict]:
        self.get_campaign(campaign_id)
        return [self.get_plan(row["id"]) for row in self._db.execute(
            "SELECT id FROM sending_plans WHERE campaign_id = ? ORDER BY rowid", (campaign_id,))]

    def adjust_plan(self, plan_id: str, preparation_id: str, scheduled_at) -> dict:
        """Set one planned action's exact time before Confirmation.

        The adjustment is validated against the plan's own configuration: an
        operator changes the configuration and re-proposes rather than smuggling
        a constraint violation into a confirmed Sending Plan.  Adjusting an
        already-confirmed action invalidates that Confirmation, because the
        authorization was bound to the previous exact time.
        """
        row = self._db.execute("SELECT * FROM sending_plans WHERE id = ?", (plan_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Sending Plan not found: {plan_id}")
        proposal = self._db.execute(
            "SELECT * FROM sending_plan_proposals WHERE plan_id = ? AND preparation_id = ?",
            (plan_id, preparation_id)).fetchone()
        if proposal is None:
            raise SmartMailError(
                f"Preparation is not part of this Sending Plan: {preparation_id}")
        if proposal["status"] in ("not_ready", "already_sent"):
            raise SmartMailError(
                f"This action cannot be scheduled for Confirmation: {proposal['detail']}")
        zone = ZoneInfo(row["timezone"])
        instant = self._plan_instant(scheduled_at, zone)
        self._validate_plan_instant(plan_id, proposal, instant, row)
        with self._db:
            if proposal["confirmation_id"]:
                self._db.execute(
                    "UPDATE confirmations SET status = 'invalidated', invalidated_reason = 'adjusted' "
                    "WHERE id = ? AND status = 'active'", (proposal["confirmation_id"],))
            self._db.execute(
                "UPDATE sending_plan_proposals SET status = 'scheduled', reason = '', "
                "constraint_name = '', detail = '', scheduled_at = ?, scheduled_utc = ?, "
                "confirmation_id = NULL WHERE id = ?",
                (instant.astimezone(zone).isoformat(),
                 instant.astimezone(timezone.utc).isoformat(), proposal["id"]))
            self._refresh_plan_status(plan_id)
        return self.get_plan(plan_id)

    def _plan_instant(self, value, zone: ZoneInfo) -> datetime:
        """An exact instant from an ISO-8601 local time or an explicit offset."""
        if isinstance(value, datetime):
            parsed = value
        else:
            text = str(value).strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError as error:
                raise SmartMailError(
                    f"Unsupported time {value!r}; use an exact ISO-8601 time such as "
                    "2026-09-15T09:00 or 2026-09-15T01:00:00Z") from error
        return parsed.replace(tzinfo=zone) if parsed.tzinfo is None else parsed

    def confirm_plan(self, plan_id: str, *, confirmed_at=None) -> dict:
        """Authorize every scheduled action of a Sending Plan in one operator action.

        Each action gets its own Confirmation, bound to its exact Preparation,
        content and execution time.  The whole batch is validated before anything
        is authorized, so a plan is never half-confirmed.
        """
        row = self._db.execute("SELECT * FROM sending_plans WHERE id = ?", (plan_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Sending Plan not found: {plan_id}")
        if row["status"] == "superseded":
            raise SmartMailError(
                "Sending Plan is superseded by a newer proposal; confirm the current plan")
        proposals = list(self._db.execute(
            "SELECT * FROM sending_plan_proposals WHERE plan_id = ? AND status = 'scheduled' "
            "ORDER BY sequence", (plan_id,)))
        if not proposals:
            raise SmartMailError("This Sending Plan has no scheduled action to confirm")
        now = self._instant()
        for proposal in proposals:
            preparation = self.get_preparation(proposal["preparation_id"])
            if preparation["status"] != "active":
                raise SmartMailError(
                    f"Preparation has been superseded; re-propose the Sending Plan: "
                    f"{proposal['preparation_id']}")
            blocking = [finding["code"] for finding in preparation["readiness_findings"]
                        if finding["blocking"]]
            if blocking:
                raise SmartMailError(
                    f"Preparation {proposal['preparation_id']} is not Ready; "
                    f"resolve: {', '.join(blocking)}")
            if self._db.execute("SELECT 1 FROM sent_records WHERE preparation_id = ?",
                                (proposal["preparation_id"],)).fetchone():
                raise SmartMailError(
                    "Preparation has already been sent; prepare a new linked Communication "
                    f"Action instead: {proposal['preparation_id']}")
            instant = self._plan_instant(proposal["scheduled_at"], ZoneInfo(row["timezone"]))
            if instant <= now:
                raise SmartMailError(
                    f"The sending time {proposal['scheduled_at']} has elapsed; confirm an "
                    "explicitly chosen replacement time (adjust the plan or re-propose it)")
        for proposal in proposals:
            confirmation = self.confirm(proposal["preparation_id"], execution={
                "kind": "scheduled", "scheduled_at": proposal["scheduled_at"],
                "timezone": row["timezone"]}, confirmed_at=confirmed_at)
            with self._db:
                self._db.execute(
                    "UPDATE sending_plan_proposals SET confirmation_id = ? WHERE id = ?",
                    (confirmation["id"], proposal["id"]))
        with self._db:
            self._refresh_plan_status(plan_id)
        return self.get_plan(plan_id)

    def _refresh_plan_status(self, plan_id: str) -> None:
        """A plan is confirmed only while every scheduled action carries a Confirmation."""
        rows = list(self._db.execute(
            "SELECT status, confirmation_id FROM sending_plan_proposals WHERE plan_id = ?",
            (plan_id,)))
        scheduled = [row for row in rows if row["status"] == "scheduled"]
        status = ("confirmed" if scheduled and all(row["confirmation_id"] for row in scheduled)
                  else "proposed")
        self._db.execute(
            "UPDATE sending_plans SET status = ? WHERE id = ? AND status != 'superseded'",
            (status, plan_id))

    def _validate_plan_instant(self, plan_id: str, proposal, instant: datetime, plan) -> None:
        """Refuse an exact time that the plan's configured constraints cannot allow."""
        zone = ZoneInfo(plan["timezone"])
        local = instant.astimezone(zone)
        if not self._plan_wall_time_exists(local):
            raise SmartMailError(
                f"The time {instant.isoformat()} does not exist in {plan['timezone']}")
        if instant <= self._instant():
            raise SmartMailError(
                f"The time {instant.isoformat()} must be in the future; an elapsed time needs "
                "an explicitly confirmed replacement time")
        weekday = _PLAN_DAY_TOKENS[local.weekday()]
        allowed = [window for window in json.loads(plan["windows"])
                   if weekday in window["days"]
                   and window["start"] <= local.strftime("%H:%M") <= window["end"]]
        if not allowed:
            raise SmartMailError(
                f"The time {local.isoformat()} is outside every allowed window of this Sending "
                f"Plan ({weekday} {local.strftime('%H:%M')} in {plan['timezone']})")
        spacing = timedelta(minutes=plan["spacing_minutes"])
        others = list(self._db.execute(
            "SELECT preparation_id, scheduled_at FROM sending_plan_proposals "
            "WHERE plan_id = ? AND status = 'scheduled' AND id != ?",
            (plan_id, proposal["id"])))
        for other in others:
            if abs(instant - self._plan_instant(other["scheduled_at"], zone)) < spacing:
                raise SmartMailError(
                    f"The spacing of {plan['spacing_minutes']} minutes requires a later time: "
                    f"another action of this Sending Plan is already scheduled within it")
        day = local.date()
        same_day = sum(
            1 for other in others
            if self._plan_instant(other["scheduled_at"], zone).astimezone(zone).date() == day)
        if same_day + 1 > plan["daily_limit"]:
            raise SmartMailError(
                f"The daily limit of {plan['daily_limit']} action(s) is already reached on "
                f"{day.isoformat()}; this action needs another day")

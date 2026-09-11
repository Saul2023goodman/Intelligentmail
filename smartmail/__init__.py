"""SmartMail's persistent command/query boundary for local outreach operations."""

import sqlite3
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError

from .documents import DocumentError, association_key, attachment_declarations, parse_draft, read_paragraphs
from .intake import read_master, read_bundle
from .identity import email_address, person_name, profile_url
from .mailbox import DisabledMailbox, MailboxCapabilityError


class SmartMailError(ValueError):
    """An operator-visible command or query error."""


_PAUSE_REASONS = {"failed": "execution_failed", "unknown": "unknown_outcome"}


class SmartMail:
    def __init__(self, home: Path, mailbox=None):
        self.home = Path(home).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.mailbox = mailbox if mailbox is not None else DisabledMailbox()
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
            "SELECT id FROM confirmations WHERE preparation_id = ? AND status = 'active'",
            (preparation_id,)).fetchone()
        return {
            "preparation_id": preparation_id, "task_id": preparation["task_id"],
            "status": preparation["status"], "sender": preparation["sender"],
            "recipient": preparation["recipient"], "subject": preparation["subject"],
            "body": preparation["body"], "attachments": attachments,
            "readiness_findings": preparation["readiness_findings"],
            "ready": preparation["ready"], "execution": {"kind": "immediate"},
            "already_sent": sent is not None,
            "confirmation_id": active["id"] if active else None,
            "message": self.preview_preparation(preparation_id)["text"],
        }

    def confirm(self, preparation_id: str) -> dict:
        """Authorize exactly one Ready Preparation for its bound execution details."""
        return self.confirm_preparations([preparation_id])[0]

    def confirm_preparations(self, preparation_ids: list[str]) -> list[dict]:
        """Confirm several Preparations in one operator action; each gets its own Confirmation."""
        confirmations = []
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
                if active and active["content_digest"] == content_digest \
                        and active["attachments_digest"] == attachments_digest:
                    confirmations.append(self._confirmation_view(active))
                    continue
                if active:
                    self._db.execute(
                        "UPDATE confirmations SET status = 'invalidated', invalidated_reason = 'renewed' "
                        "WHERE id = ?", (active["id"],))
                confirmation_id = str(uuid4())
                self._db.execute(
                    "INSERT INTO confirmations VALUES (?, ?, ?, ?, ?, ?, ?, 'active', '')",
                    (confirmation_id, preparation_id, preparation["task_id"], "immediate",
                     json.dumps({"kind": "immediate"}, ensure_ascii=False),
                     content_digest, attachments_digest))
                confirmations.append(self.get_confirmation(confirmation_id))
        return confirmations

    def _confirmation_view(self, row) -> dict:
        return {
            "id": row["id"], "preparation_id": row["preparation_id"], "task_id": row["task_id"],
            "status": row["status"], "execution": json.loads(row["execution_detail"]),
            "content_digest": row["content_digest"],
            "attachments_digest": row["attachments_digest"],
            "invalidated_reason": row["invalidated_reason"],
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

    def run_execution(self, confirmation_ids: list[str]) -> dict:
        """Execute confirmed immediate sends in order through the adapter, pausing on failure."""
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
            attempt_id = str(uuid4())
            self._db.execute(
                "INSERT INTO execution_attempts VALUES (?, ?, ?, ?, ?, 'in_progress', ?, '')",
                (attempt_id, confirmation["id"], confirmation["preparation_id"],
                 confirmation["task_id"], self._next_sequence(confirmation["preparation_id"]),
                 json.dumps(request, ensure_ascii=False)))
            self._db.commit()
            evidence = self._submit(request)
            state = evidence["outcome"]
            self._db.execute(
                "UPDATE execution_attempts SET state = ?, evidence = ? WHERE id = ?",
                (state, json.dumps(evidence, ensure_ascii=False), attempt_id))
            if state == "sent":
                self._record_sent(confirmation, attempt_id, request, evidence)
                self._db.execute(
                    "UPDATE confirmations SET status = 'consumed' WHERE id = ?", (confirmation["id"],))
            else:
                self._pause_flow(campaign_id, _PAUSE_REASONS[state], evidence)
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
        if preparation["status"] != "active":
            raise SmartMailError(
                "Preparation has been superseded; renew Confirmation before executing")
        if self._db.execute(
                "SELECT 1 FROM sent_records WHERE preparation_id = ?",
                (preparation["id"],)).fetchone():
            raise SmartMailError(
                "Preparation has already been sent; a new linked Communication Action is required")
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
        return self._execution_request(preparation)

    def _execution_request(self, preparation: dict) -> dict:
        attachments = [
            {"label": slot["label"], "name": slot["attachment"]["name"],
             "sha256": slot["attachment"]["sha256"], "size": slot["attachment"]["size"]}
            for slot in preparation["attachment_slots"] if slot["attachment"]]
        return {"sender": preparation["sender"], "recipient": preparation["recipient"],
                "subject": preparation["subject"], "body": preparation["body"],
                "attachments": attachments, "kind": "immediate"}

    def _submit(self, request: dict) -> dict:
        try:
            return self.mailbox.submit(request)
        except MailboxCapabilityError as error:
            raise SmartMailError(str(error)) from error

    def _record_sent(self, confirmation: dict, attempt_id: str, request: dict, evidence: dict) -> str:
        """Freeze the exact content and attachment bytes that the mailbox confirmed as sent."""
        sent_id = str(uuid4())
        content = json.dumps({"sender": request["sender"], "recipient": request["recipient"],
                              "subject": request["subject"], "body": request["body"]},
                             ensure_ascii=False)
        self._db.execute("INSERT INTO sent_records VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (sent_id, confirmation["preparation_id"], confirmation["task_id"], attempt_id,
                          content, json.dumps(evidence, ensure_ascii=False), evidence["reference"]))
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
            if flow["state"] == "paused" and flow["reason"] == "unknown_outcome":
                self._db.execute(
                    "DELETE FROM execution_flow WHERE campaign_id = ?", (campaign_id,))
        return self.get_execution_attempt(attempt_id)

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

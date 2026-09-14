"""Read-only Mailbox observations and evidence-based Reconciliation."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from ..identity import email_address
from ..mailbox import MailboxCapabilityError
from ..errors import SmartMailError


class ReconciliationOperations:
    """Read-only Mailbox observations and evidence-based Reconciliation."""

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

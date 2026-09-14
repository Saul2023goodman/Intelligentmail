"""Duplicate Suspicion, Evidence Coverage and linked Follow-up Actions."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from ..identity import email_address
from ..errors import SmartMailError


_REVIEW_FINDINGS = {"repeat_execution", "duplicate_suspicion", "ambiguous_match"}


class DuplicateOperations:
    """Duplicate Suspicion, Evidence Coverage and linked Follow-up Actions."""

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

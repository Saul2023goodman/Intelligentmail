"""Deterministic association of inbound observations to Outreach Tasks.

Only supported evidence on observable fields is used: known Supervisor
addresses, confirmed-subject thread markers and timing after a recorded Sent
Record. Message body HTML and unrecognized custom folders stay outside the
read-only observation boundary, so the limits of that coverage are recorded
rather than guessed.
"""

import json
import re
from uuid import uuid4

from ..identity import email_address
from ..errors import SmartMailError


#: One leading reply/forward marker in English or Chinese, optionally numbered.
_REPLY_PREFIX = re.compile(
    r"^\s*(?:re|rec|fw|fwd|回复|回覆|答复|答覆)\s*[\[（(]?\d*[\]）)]?\s*[:：]\s*",
    re.IGNORECASE,
)

#: Supported machine-generated reply markers on observable subject text only.
_AUTO_SUBJECT = re.compile(
    r"^(?:automatic reply|automated reply|auto reply|auto|out of(?: the)? office|ooo)"
    r"(?=\b|[\s:\-])",
    re.IGNORECASE,
)
_AUTO_SUBJECT_TOKENS = (
    "自动回复", "自动回覆", "自动答复", "自動答覆", "休假中", "不在办公室", "不在辦公室",
)

_EXCLUDED_OBSERVATION_FIELDS = ["message_body_html", "unrecognized_custom_folders"]


class ReplyOperations:
    """Associated Replies, Recognized Automatic Replies and operator review."""

    def _associate_inbound_reply(self, mailbox: dict, message, reconciliation_id: str) -> str:
        """Persist the deterministic association for one inbound observation.

        Returns ``associated``, ``automatic``, ``ambiguous`` or ``unassociated``
        so the Reconciliation summary can count each outcome.
        """
        student_id = mailbox["student_id"]
        coverage = self._reply_coverage(message)
        sender = email_address(message["counterpart"])
        if sender is None:
            self._insert_reconciliation_finding(
                reconciliation_id, message["id"], "unassociated_inbound",
                detail="The inbound message has no usable known Supervisor address")
            return "unassociated"
        supervisor_rows = list(self._db.execute(
            "SELECT DISTINCT supervisor_id FROM supervisor_addresses WHERE address = ?",
            (sender,)))
        supervisor_ids = [row["supervisor_id"] for row in supervisor_rows]
        candidate_rows = list(self._db.execute(
            "SELECT t.id, t.supervisor_id, t.campaign_id, s.name AS supervisor_name, "
            "i.name AS institution_name FROM tasks t JOIN supervisors s ON s.id = t.supervisor_id "
            "JOIN institutions i ON i.id = s.institution_id "
            "WHERE t.student_id = ? AND t.supervisor_id IN (%s) ORDER BY t.rowid"
            % ",".join("?" for _ in supervisor_ids),
            (student_id, *supervisor_ids))) if supervisor_ids else []
        if not candidate_rows:
            self._insert_reconciliation_finding(
                reconciliation_id, message["id"], "unassociated_inbound",
                detail=f"No Outreach Task for this Student with the known address {sender}")
            return "unassociated"
        if len(set(supervisor_ids)) > 1:
            return self._record_ambiguous_reply(
                reconciliation_id, message, student_id, coverage,
                [row["id"] for row in candidate_rows], "shared_supervisor_address",
                f"The address {sender} is recorded for more than one Supervisor identity")
        if len(candidate_rows) == 1:
            task = candidate_rows[0]
            if self._db.execute(
                    "SELECT 1 FROM exceptions WHERE task_id = ? AND code = 'identity_ambiguity' "
                    "AND blocking = 1", (task["id"],)).fetchone():
                return self._record_ambiguous_reply(
                    reconciliation_id, message, student_id, coverage, [task["id"]],
                    "conflicting_identity",
                    "The Outreach Task has an unresolved Supervisor identity conflict")
            basis, anchors = self._single_task_thread_basis(task["id"], message, coverage)
            if basis is None:
                return self._record_ambiguous_reply(
                    reconciliation_id, message, student_id, coverage, [task["id"]],
                    "no_open_outreach_thread",
                    "No recorded Sent thread from this Student to that Supervisor supports "
                    "the message: the subject does not continue a Sent Record and the "
                    "observed time cannot prove it arrived after a send")
        else:
            matches = self._thread_matching_tasks(
                [row["id"] for row in candidate_rows], message)
            if len(matches) != 1:
                return self._record_ambiguous_reply(
                    reconciliation_id, message, student_id, coverage,
                    [row["id"] for row in candidate_rows], "multiple_candidate_tasks",
                    "The subject thread does not identify exactly one of the Student's Tasks "
                    "for this Supervisor")
            task = next(row for row in candidate_rows if row["id"] == matches[0])
            basis, anchors = (
                "known_supervisor_address+sent_thread_subject",
                {"matched_task_id": matches[0]})
        rule, rule_detail = self._automatic_reply_rule(message)
        reply_kind = "automatic" if rule else "ordinary"
        association_id = self._insert_reply_association(
            task["id"], student_id, message, coverage, [task["id"]], status="associated",
            reply_kind=reply_kind, basis=basis, matched_rule=rule,
            evidence={"anchors": anchors, "matched_rule_detail": rule_detail})
        self._insert_reconciliation_finding(
            reconciliation_id, message["id"],
            "associated_automatic_reply" if rule else "associated_reply",
            "reply_association", association_id, basis,
            rule_detail or "Inbound message reliably linked to the Outreach Task")
        return "automatic" if rule else "associated"

    def _single_task_thread_basis(self, task_id: str, message, coverage: dict):
        """The supported evidence anchoring one inbound message to one Task."""
        sent_rows = list(self._db.execute(
            "SELECT s.id, s.content, a.outcome_observed_at, a.intent_at "
            "FROM sent_records s LEFT JOIN execution_attempts a ON a.id = s.attempt_id "
            "WHERE s.task_id = ? ORDER BY s.rowid", (task_id,)))
        if not sent_rows:
            return None, {}
        thread_subject = self._thread_subject(message["subject"])
        for sent in sent_rows:
            if thread_subject and thread_subject == str(
                    json.loads(sent["content"]).get("subject", "")).casefold():
                return "known_supervisor_address+sent_thread_subject", \
                    {"matched_sent_record_id": sent["id"]}
        observed = self._parse_timestamp(message["observed_time"])
        if observed is not None and coverage["timing_available"]:
            for sent in sent_rows:
                sent_at = self._parse_timestamp(
                    sent["outcome_observed_at"] or sent["intent_at"])
                if sent_at is not None and observed >= sent_at:
                    return "known_supervisor_address+timing_after_sent_record", \
                        {"matched_sent_record_id": sent["id"]}
        # A known address alone is not reliable evidence: the message might predate
        # the outreach, and timing that cannot be parsed is not timing evidence.
        return None, {}

    def _thread_matching_tasks(self, task_ids: list[str], message) -> list:
        """Tasks whose recorded Sent subject continues the inbound subject thread."""
        thread_subject = self._thread_subject(message["subject"])
        if not thread_subject:
            return []
        matches = []
        for task_id in task_ids:
            subjects = [str(json.loads(row["content"]).get("subject", "")).casefold()
                        for row in self._db.execute(
                            "SELECT content FROM sent_records WHERE task_id = ?", (task_id,))]
            if thread_subject in subjects:
                matches.append(task_id)
        return matches

    @staticmethod
    def _thread_subject(subject: str) -> str:
        """The underlying conversation subject, stripping reply and auto-reply markers."""
        text = str(subject or "")
        for _ in range(4):
            stripped = _REPLY_PREFIX.sub("", text, count=1)
            trimmed = stripped.strip()
            advanced = False
            marker = _AUTO_SUBJECT.match(trimmed)
            if marker:
                trimmed = trimmed[marker.end():].lstrip(" \t:：-.—-–")
                advanced = True
            else:
                for token in _AUTO_SUBJECT_TOKENS:
                    if trimmed.startswith(token):
                        trimmed = trimmed[len(token):].lstrip(" \t:：-.—-–")
                        advanced = True
                        break
            if not advanced and trimmed == text.strip():
                break
            text = trimmed
        return text.strip().casefold()

    @staticmethod
    def _automatic_reply_rule(message) -> tuple[str, str]:
        """Supported explicit rules on observable fields; never body semantics."""
        raw_evidence = json.loads(message["evidence"]) if message["evidence"] else {}
        evidence = raw_evidence if isinstance(raw_evidence, dict) else {}
        header = str(evidence.get("auto_submitted", "")).strip().casefold().replace("-", "_")
        if header in {"auto_replied", "auto_generated"}:
            return "auto_submitted_header", f"Auto-Submitted: {evidence['auto_submitted']}"
        if evidence.get("automatic_reply") is True:
            return "explicit_automatic_marker", "Observation metadata explicitly marked the message automatic"
        subject = _REPLY_PREFIX.sub("", str(message["subject"] or "")).strip()
        marker = _AUTO_SUBJECT.match(subject)
        if marker:
            return "subject_marker", f"Subject begins with a supported automatic-reply marker: {marker.group(0)}"
        for token in _AUTO_SUBJECT_TOKENS:
            if token in subject:
                return "subject_marker", f"Subject contains the supported marker '{token}'"
        return "", ""

    def _reply_coverage(self, message) -> dict:
        """The Evidence Coverage of one association decision."""
        limitations = [
            "The read-only observation excludes message body HTML and unrecognized custom "
            "folders; detection uses header and list metadata only",
        ]
        observed_time = str(message["observed_time"] or "")
        timing_available = bool(observed_time) and self._parse_timestamp(observed_time) is not None
        if not observed_time:
            limitations.append("No observed time was reported for this message; timing evidence is unavailable")
        elif not timing_available:
            limitations.append(
                f"The observed time {observed_time!r} is not machine-readable; timing evidence "
                "could not be used and was not inferred")
        return {
            "observation_run_id": message["run_id"],
            "observed_fields": [
                "counterpart", "subject", "observed_time", "folder", "status", "metadata_evidence"],
            "excluded_fields": list(_EXCLUDED_OBSERVATION_FIELDS),
            "timing_available": timing_available,
            "limitations": limitations,
        }

    def _record_ambiguous_reply(self, reconciliation_id: str, message, student_id: str,
                                coverage: dict, candidate_task_ids: list[str],
                                basis: str, detail: str) -> str:
        association_id = self._insert_reply_association(
            None, student_id, message, coverage, candidate_task_ids, status="ambiguous",
            reply_kind="", basis=basis, matched_rule="",
            evidence={"candidate_task_ids": candidate_task_ids, "reason": detail})
        self._insert_reconciliation_finding(
            reconciliation_id, message["id"], "ambiguous_reply_association",
            "reply_association", association_id, basis, detail)
        return "ambiguous"

    def _insert_reply_association(self, task_id, student_id, message, coverage,
                                  candidate_task_ids: list[str], *,
                                  status: str, reply_kind: str, basis: str,
                                  matched_rule: str, evidence: dict) -> str:
        association_id = str(uuid4())
        snapshot = {
            "message_observation_id": message["id"],
            "platform_reference": message["platform_reference"],
            "counterpart": message["counterpart"], "subject": message["subject"],
            "observed_time": message["observed_time"], "folder": message["folder"],
            "status": message["status"],
            "metadata_evidence": json.loads(message["evidence"]) if message["evidence"] else {},
            **evidence,
        }
        self._db.execute(
            "INSERT INTO reply_associations (id, task_id, student_id, message_observation_id, "
            "status, reply_kind, basis, matched_rule, evidence, candidate_task_ids, "
            "evidence_coverage, resolved_by_operator, created_at, resolved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, '')",
            (association_id, task_id, student_id, message["id"], status, reply_kind, basis,
             matched_rule, json.dumps(snapshot, ensure_ascii=False),
             json.dumps(candidate_task_ids, ensure_ascii=False),
             json.dumps(coverage, ensure_ascii=False), self._now()))
        return association_id

    def resolve_reply_association(self, association_id: str, task_id: str | None = None,
                                  *, dismiss: bool = False) -> dict:
        """Resolve an ambiguous association inside SmartMail.

        Pinning to one candidate Task creates a reliable Associated Reply;
        dismissing records the operator's decision that it is not outreach
        correspondence. Neither outcome guesses at the message's meaning.
        """
        row = self._db.execute(
            "SELECT * FROM reply_associations WHERE id = ?", (association_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Reply association not found: {association_id}")
        if row["status"] != "ambiguous":
            raise SmartMailError(
                f"Reply association is already {row['status']}: {association_id}")
        message = self._db.execute(
            "SELECT * FROM mailbox_message_observations WHERE id = ?",
            (row["message_observation_id"],)).fetchone()
        if dismiss:
            status, reply_kind, basis, matched_rule = (
                "dismissed", "", "operator_dismissed", "")
            resolved_task = None
        else:
            if task_id is None:
                raise SmartMailError(
                    "Provide the Outreach Task this reply belongs to, or dismiss it")
            candidates = json.loads(row["candidate_task_ids"])
            if task_id not in candidates:
                raise SmartMailError(
                    f"Outreach Task {task_id} is not among the recorded candidates")
            rule, _ = self._automatic_reply_rule(message)
            status, reply_kind, matched_rule = (
                "associated", "automatic" if rule else "ordinary", rule)
            basis = "operator_resolved"
            resolved_task = task_id
        with self._db:
            self._db.execute(
                "UPDATE reply_associations SET task_id = ?, status = ?, reply_kind = ?, "
                "basis = ?, matched_rule = ?, resolved_by_operator = 1, resolved_at = ? "
                "WHERE id = ?",
                (resolved_task, status, reply_kind, basis, matched_rule,
                 self._now(), association_id))
        return self.get_reply_association(association_id)

    def get_reply_association(self, association_id: str) -> dict:
        row = self._db.execute(
            "SELECT * FROM reply_associations WHERE id = ?", (association_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Reply association not found: {association_id}")
        return self._reply_view(row)

    def list_reply_associations(self, campaign_id: str | None = None, *,
                                status: str | None = None,
                                student_id: str | None = None) -> list[dict]:
        """Reliable and ambiguous associations, newest in observation order."""
        if campaign_id is not None:
            self.get_campaign(campaign_id)
        rows = list(self._db.execute(
            "SELECT * FROM reply_associations ORDER BY rowid"))
        result = []
        for row in rows:
            if status is not None and row["status"] != status:
                continue
            if student_id is not None and row["student_id"] != student_id:
                continue
            if campaign_id is not None:
                in_campaign = row["task_id"] is not None and self._db.execute(
                    "SELECT 1 FROM tasks WHERE id = ? AND campaign_id = ?",
                    (row["task_id"], campaign_id)).fetchone()
                candidate_ids = json.loads(row["candidate_task_ids"])
                if not in_campaign and not any(
                        self._db.execute(
                            "SELECT 1 FROM tasks WHERE id = ? AND campaign_id = ?",
                            (candidate, campaign_id)).fetchone()
                        for candidate in candidate_ids):
                    continue
            result.append(self._reply_view(row))
        return result

    def _reply_view(self, row) -> dict:
        candidates = []
        for candidate_id in json.loads(row["candidate_task_ids"]):
            task_row = self._db.execute(
                "SELECT t.id, t.campaign_id, s.name AS supervisor_name, "
                "i.name AS institution_name FROM tasks t JOIN supervisors s ON s.id = t.supervisor_id "
                "JOIN institutions i ON i.id = s.institution_id WHERE t.id = ?",
                (candidate_id,)).fetchone()
            if task_row:
                candidates.append(dict(task_row))
        message = self._db.execute(
            "SELECT id, run_id, folder, platform_reference, counterpart, subject, observed_time, "
            "status, evidence FROM mailbox_message_observations WHERE id = ?",
            (row["message_observation_id"],)).fetchone()
        return {
            "id": row["id"], "task_id": row["task_id"], "student_id": row["student_id"],
            "status": row["status"], "reply_kind": row["reply_kind"],
            "basis": row["basis"], "matched_rule": row["matched_rule"],
            "resolved_by_operator": bool(row["resolved_by_operator"]),
            "created_at": row["created_at"], "resolved_at": row["resolved_at"],
            "candidate_task_ids": json.loads(row["candidate_task_ids"]),
            "candidates": candidates,
            "evidence": json.loads(row["evidence"]),
            "evidence_coverage": json.loads(row["evidence_coverage"]),
            "observation": {
                "id": message["id"], "run_id": message["run_id"], "folder": message["folder"],
                "platform_reference": message["platform_reference"],
                "counterpart": message["counterpart"], "subject": message["subject"],
                "observed_time": message["observed_time"], "status": message["status"],
                "evidence": json.loads(message["evidence"]) if message["evidence"] else {},
            },
        }

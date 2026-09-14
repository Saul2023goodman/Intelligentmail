"""Operational reporting: filtered summaries and evidence drill-down.

Reports are pure read-side queries over the persisted system of record, so
they stay available while an Execution Flow is paused and reproduce the same
counts after a restart with the same controlled clock. Message states are
distinct on purpose: a locally planned message, an externally scheduled one,
a recorded send, an observed failure and an unknown outcome must never be
counted as the same thing.
"""

from ..identity import email_address


_MESSAGE_STATES = [
    "locally_planned", "externally_scheduled", "sent",
    "observed_failure", "unknown_outcome", "intake_only",
]
_DUPLICATE_STATES = [
    "no_duplicate_found", "duplicate_suspicion", "ambiguous_match",
    "repeat_execution", "linked_follow_up", "unchecked",
]
_FOLLOW_UP_STATES = [
    "due", "waiting", "ordinary_reply_received", "reply_review_required",
    "maximum_reached", "no_initial_send", "follow_up_open", "rule_not_configured",
]


class ReportingOperations:
    """Campaign-level operational summaries and per-Task evidence drill-down."""

    def operations_report(self, campaign_id: str, *, student_id: str | None = None,
                          supervisor_id: str | None = None,
                          institution_id: str | None = None,
                          mailbox: str | None = None,
                          message_status: str | None = None,
                          duplicate_status: str | None = None,
                          exceptions: str | None = None,
                          follow_up: str | None = None) -> dict:
        """Summarize the Campaign's Tasks after applying the supported filters."""
        self.get_campaign(campaign_id)
        rule = self.get_follow_up_rule(campaign_id)
        follow_up_views = {
            view["task_id"]: view for view in self.follow_up_status(campaign_id)}
        rows = []
        for task in self.list_tasks(campaign_id):
            row = self._report_row(task, follow_up_views[task["id"]])
            if student_id is not None and row["student_id"] != student_id:
                continue
            if supervisor_id is not None and row["supervisor_id"] != supervisor_id:
                continue
            if institution_id is not None and row["institution_id"] != institution_id:
                continue
            if mailbox is not None and row["mailbox"].casefold() != mailbox.casefold():
                continue
            if message_status is not None and row["message_status"] != message_status:
                continue
            if duplicate_status is not None and row["duplicate_status"] != duplicate_status:
                continue
            if exceptions == "blocking" and row["exceptions"]["blocking"] == 0:
                continue
            if exceptions == "any" and row["exceptions"]["total"] == 0:
                continue
            if exceptions == "none" and row["exceptions"]["total"] != 0:
                continue
            if follow_up is not None and row["follow_up"] != follow_up:
                continue
            rows.append(row)
        return {
            "campaign": self.get_campaign(campaign_id),
            "generated_at": self._now(),
            "flow": self._flow_state(campaign_id),
            "filters": {
                "student_id": student_id, "supervisor_id": supervisor_id,
                "institution_id": institution_id, "mailbox": mailbox,
                "message_status": message_status, "duplicate_status": duplicate_status,
                "exceptions": exceptions, "follow_up": follow_up,
            },
            "rule": rule,
            "counts": self._report_counts(rows),
            "tasks": rows,
        }

    def _report_counts(self, rows: list[dict]) -> dict:
        message_counts = {state: 0 for state in _MESSAGE_STATES}
        duplicate_counts = {state: 0 for state in _DUPLICATE_STATES}
        follow_up_counts = {state: 0 for state in _FOLLOW_UP_STATES}
        exception_counts = {"any": 0, "blocking": 0, "none": 0}
        for row in rows:
            message_counts[row["message_status"] or "intake_only"] += 1
            duplicate_counts[row["duplicate_status"]] += 1
            if row["follow_up"]:
                follow_up_counts[row["follow_up"]] += 1
            if row["exceptions"]["blocking"]:
                exception_counts["blocking"] += 1
                exception_counts["any"] += 1
            elif row["exceptions"]["total"]:
                exception_counts["any"] += 1
            else:
                exception_counts["none"] += 1
        return {
            "tasks": len(rows),
            "message_status": message_counts,
            "duplicate_status": duplicate_counts,
            "exceptions": exception_counts,
            "follow_up": follow_up_counts,
        }

    def _report_row(self, task: dict, follow_up_view: dict) -> dict:
        latest_check = self._db.execute(
            "SELECT * FROM duplicate_checks WHERE task_id = ? ORDER BY rowid DESC LIMIT 1",
            (task["id"],)).fetchone()
        blocking = self._db.execute(
            "SELECT count(*) FROM exceptions WHERE task_id = ? AND blocking = 1",
            (task["id"],)).fetchone()[0]
        preparation_ids = [row[0] for row in self._db.execute(
            "SELECT id FROM preparations WHERE task_id = ? AND superseded_by IS NULL ORDER BY rowid",
            (task["id"],))]
        check_view = self._duplicate_view(latest_check) if latest_check else None
        institution = self._db.execute(
            "SELECT id FROM institutions WHERE id = (SELECT institution_id FROM supervisors "
            "WHERE id = ?)", (task["supervisor_id"],)).fetchone()
        mailbox = self._db.execute(
            "SELECT address FROM mailboxes WHERE student_id = ?",
            (task["student_id"],)).fetchone()
        return {
            "task_id": task["id"], "student_id": task["student_id"],
            "student_name": task["student_name"],
            "supervisor_id": task["supervisor_id"],
            "supervisor_name": task["supervisor_name"],
            "institution_id": institution["id"] if institution else "",
            "institution_name": task["institution_name"],
            "mailbox": mailbox["address"] if mailbox else "",
            "message_status": self._task_message_status(task["id"]),
            "duplicate_status": check_view["finding"] if check_view else "unchecked",
            "duplicate_coverage": check_view["evidence_coverage"] if check_view else None,
            "exceptions": {"total": task["exception_count"], "blocking": blocking},
            "follow_up": follow_up_view["state"],
            "preparation_ids": preparation_ids,
        }

    def _task_message_status(self, task_id: str) -> str:
        """The distinct operational state, without conflating evidence kinds.

        The latest terminal Execution Attempt decides, so a failed or unknown
        Follow-up Attempt is not hidden behind an earlier recorded send.
        """
        latest = self._db.execute(
            "SELECT state FROM execution_attempts WHERE task_id = ? "
            "AND state IN ('sent', 'failed', 'unknown') ORDER BY rowid DESC LIMIT 1",
            (task_id,)).fetchone()
        if latest is not None:
            return {"sent": "sent", "failed": "observed_failure",
                    "unknown": "unknown_outcome"}[latest["state"]]
        if self._scheduled_outbound_observation(task_id):
            return "externally_scheduled"
        if self._db.execute(
                "SELECT 1 FROM preparations WHERE task_id = ? AND superseded_by IS NULL LIMIT 1",
                (task_id,)).fetchone():
            return "locally_planned"
        return ""

    def _scheduled_outbound_observation(self, task_id: str) -> bool:
        addresses = {row[0].casefold() for row in self._db.execute(
            "SELECT a.address FROM supervisor_addresses a JOIN tasks t ON t.supervisor_id = a.supervisor_id "
            "WHERE t.id = ?", (task_id,))}
        if not addresses:
            return False
        for observation in self._db.execute(
                "SELECT counterpart FROM mailbox_message_observations o "
                "JOIN mailbox_observation_runs r ON r.id = o.run_id "
                "JOIN tasks t ON t.id = ? "
                "JOIN mailboxes m ON m.id = r.mailbox_id AND m.student_id = t.student_id "
                "WHERE o.direction = 'outbound' AND o.status = 'scheduled'", (task_id,)):
            recipient = email_address(observation["counterpart"])
            if recipient and recipient.casefold() in addresses:
                return True
        return False

    def report_task(self, task_id: str) -> dict:
        """Drill down into one Task: Preparation, source evidence and full history."""
        task = self.get_task(task_id)
        rule = self.get_follow_up_rule(task["campaign_id"])
        follow_up_view = next(
            view for view in self.follow_up_status(task["campaign_id"])
            if view["task_id"] == task_id)
        preparations = [self.get_preparation(row["id"]) for row in self._db.execute(
            "SELECT id FROM preparations WHERE task_id = ? ORDER BY rowid", (task_id,))]
        sources = []
        for association in task["source_associations"]:
            source = self._db.execute(
                "SELECT id, name, sha256, length(content) AS size, import_id "
                "FROM sources WHERE id = ?", (association["source_id"],)).fetchone()
            if source:
                sources.append({**dict(source), "sheet": association["sheet"],
                                "row": association["row"],
                                "evidence": association["evidence"]})
        attempts = [self._attempt_view(row) for row in self._db.execute(
            "SELECT * FROM execution_attempts WHERE task_id = ? ORDER BY rowid", (task_id,))]
        sent_records = [self.get_sent_record(row["id"]) for row in self._db.execute(
            "SELECT id FROM sent_records WHERE task_id = ? ORDER BY rowid", (task_id,))]
        duplicate_checks = [self._duplicate_view(row) for row in self._db.execute(
            "SELECT * FROM duplicate_checks WHERE task_id = ? ORDER BY rowid", (task_id,))]
        reply_associations = []
        for row in self._db.execute(
                "SELECT id FROM reply_associations WHERE task_id = ? "
                "OR status = 'ambiguous' ORDER BY rowid", (task_id,)):
            association = self.get_reply_association(row["id"])
            if association["task_id"] == task_id \
                    or task_id in association["candidate_task_ids"]:
                reply_associations.append(association)
        actions = [self.get_follow_up_action(row["id"]) for row in self._db.execute(
            "SELECT id FROM follow_up_actions WHERE task_id = ? ORDER BY sequence",
            (task_id,))]
        return {
            "task": task,
            "message_status": self._task_message_status(task_id),
            "preparations": preparations,
            "sources": sources,
            "execution_attempts": attempts,
            "sent_records": sent_records,
            "duplicate_checks": duplicate_checks,
            "reply_associations": reply_associations,
            "follow_up": {"rule": rule, "status": follow_up_view, "actions": actions},
        }

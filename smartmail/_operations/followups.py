"""Follow-up Rules, deterministic Follow-up Due eligibility and linked Follow-up Actions.

Eligibility is driven solely by reliable evidence: a linked Action becomes due
once the configured delay has elapsed after the latest recorded send, provided
no reliable Ordinary Reply has been associated. Recognized Automatic Replies
never stop eligibility, and unresolved ambiguous associations hold it pending
operator review rather than driving it silently.
"""

import json
import re
from datetime import timedelta
from uuid import uuid4

from ..documents import DocumentError, association_key, parse_draft, read_paragraphs
from ..identity import person_name
from ..errors import SmartMailError


#: Fields a Campaign template may reference; every value is recorded evidence.
_TEMPLATE_FIELDS = {"supervisor_name", "student_name", "institution", "original_subject"}
_TEMPLATE_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class FollowUpOperations:
    """Follow-up Rules, Follow-up Due eligibility and linked Follow-up Actions."""

    # --- Follow-up Rules -------------------------------------------------

    def configure_follow_up_rule(self, campaign_id: str, *, delay_days: int | None = None,
                                 maximum_count: int | None = None,
                                 subject_template: str | None = None,
                                 body_template: str | None = None) -> dict:
        """Configure follow-up timing, maximum count and optional templates.

        Partial updates preserve the other fields; unknown template fields are
        refused because SmartMail never invents substitution values.
        """
        self.get_campaign(campaign_id)
        if delay_days is not None and delay_days < 0:
            raise SmartMailError("Follow-up delay must be zero or more days")
        if maximum_count is not None and maximum_count < 1:
            raise SmartMailError("The maximum Follow-up Action count must be at least 1")
        existing = self._db.execute(
            "SELECT * FROM follow_up_rules WHERE campaign_id = ?", (campaign_id,)).fetchone()
        if existing is None and (delay_days is None or maximum_count is None):
            raise SmartMailError(
                "Configuring a Follow-up Rule requires both delay days and a maximum count")
        delay = delay_days if delay_days is not None else existing["delay_days"]
        maximum = maximum_count if maximum_count is not None else existing["maximum_count"]
        subject = existing["subject_template"] if existing else ""
        body = existing["body_template"] if existing else ""
        if subject_template is not None:
            subject = subject_template
        if body_template is not None:
            body = body_template
        for template, label in ((subject, "subject template"), (body, "body template")):
            unknown = set(_TEMPLATE_PLACEHOLDER.findall(template)) - _TEMPLATE_FIELDS
            if unknown:
                raise SmartMailError(
                    f"Unsupported field(s) in {label}: {', '.join(sorted(unknown))}; allowed: "
                    + ", ".join(sorted(_TEMPLATE_FIELDS)))
        with self._db:
            self._db.execute(
                "INSERT INTO follow_up_rules (campaign_id, delay_days, maximum_count, "
                "subject_template, body_template) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(campaign_id) DO UPDATE SET delay_days = excluded.delay_days, "
                "maximum_count = excluded.maximum_count, "
                "subject_template = excluded.subject_template, "
                "body_template = excluded.body_template",
                (campaign_id, delay, maximum, subject, body))
        return self.get_follow_up_rule(campaign_id)

    def get_follow_up_rule(self, campaign_id: str) -> dict | None:
        self.get_campaign(campaign_id)
        row = self._db.execute(
            "SELECT * FROM follow_up_rules WHERE campaign_id = ?", (campaign_id,)).fetchone()
        if row is None:
            return None
        return {
            "campaign_id": row["campaign_id"], "delay_days": row["delay_days"],
            "maximum_count": row["maximum_count"],
            "subject_template": row["subject_template"],
            "body_template": row["body_template"],
            "has_templates": bool(row["subject_template"].strip() and row["body_template"].strip()),
        }

    # --- Deterministic eligibility --------------------------------------

    def follow_up_status(self, campaign_id: str) -> list[dict]:
        """The reproducible Follow-up Due state of every Task in a Campaign."""
        rule = self.get_follow_up_rule(campaign_id)
        return [self._task_follow_up_view(task, rule) for task in self.list_tasks(campaign_id)]

    def _task_follow_up_view(self, task: dict, rule: dict | None) -> dict:
        sends = list(self._db.execute(
            "SELECT s.id, s.preparation_id, s.action_kind, s.content, "
            "a.outcome_observed_at, a.intent_at "
            "FROM sent_records s LEFT JOIN execution_attempts a ON a.id = s.attempt_id "
            "WHERE s.task_id = ? ORDER BY s.rowid", (task["id"],)))
        actions = list(self._db.execute(
            "SELECT * FROM follow_up_actions WHERE task_id = ? ORDER BY sequence",
            (task["id"],)))
        follow_up_sent = [row for row in sends if row["action_kind"] != "initial"]
        open_action = len(actions) > len(follow_up_sent)
        counts = self._reply_counts(task["id"])
        anchor = sends[-1] if sends else None
        due_at = self._due_at(anchor, rule) if (anchor and rule) else ""

        if rule is None:
            state = "rule_not_configured"
        elif not sends:
            state = "no_initial_send"
        elif counts["ordinary_replies"]:
            state = "ordinary_reply_received"
        elif counts["ambiguous"]:
            state = "reply_review_required"
        elif open_action:
            state = "follow_up_open"
        elif len(follow_up_sent) >= rule["maximum_count"]:
            state = "maximum_reached"
        elif self._parse_timestamp(due_at) and self._instant() >= self._parse_timestamp(due_at):
            state = "due"
        else:
            state = "waiting"
        return {
            "task_id": task["id"], "state": state, "eligible": state == "due",
            "due_at": due_at, "next_sequence": len(actions) + 1, "counts": {
                "ordinary_replies": counts["ordinary_replies"],
                "automatic_replies": counts["automatic_replies"],
                "ambiguous": counts["ambiguous"],
                "follow_up_sent": len(follow_up_sent),
                "follow_up_actions": len(actions),
                "open_follow_up": 1 if open_action else 0,
            },
            "rule": None if rule is None else {
                "delay_days": rule["delay_days"], "maximum_count": rule["maximum_count"],
                "has_templates": rule["has_templates"]},
        }

    def _reply_counts(self, task_id: str) -> dict:
        counts = {"ordinary_replies": 0, "automatic_replies": 0, "ambiguous": 0}
        for row in self._db.execute(
                "SELECT status, reply_kind FROM reply_associations "
                "WHERE task_id = ? AND status = 'associated'", (task_id,)):
            counts["ordinary_replies" if row["reply_kind"] == "ordinary"
                    else "automatic_replies"] += 1
        # Ambiguous rows are not pinned to a Task; membership is in their candidate list.
        for row in self._db.execute(
                "SELECT candidate_task_ids FROM reply_associations WHERE status = 'ambiguous'"):
            if task_id in json.loads(row["candidate_task_ids"]):
                counts["ambiguous"] += 1
        return counts

    def _due_at(self, anchor, rule: dict | None) -> str:
        sent_at = None
        if anchor is not None:
            sent_at = self._parse_timestamp(
                anchor["outcome_observed_at"] or anchor["intent_at"])
        if sent_at is None or rule is None:
            return ""
        return (sent_at + timedelta(days=rule["delay_days"])).isoformat()

    # --- Preparing linked Follow-up Actions -----------------------------

    def prepare_follow_ups(self, campaign_id: str, *, task_id: str | None = None) -> list[dict]:
        """Create due linked Follow-up Actions, auto-rendering when templates exist.

        Without a complete template pair the Action is marked due for operator
        preparation and no content is invented. Idempotent: an open Action keeps
        the Task out of the due state, so parallel follow-ups never stack.
        """
        rule = self.get_follow_up_rule(campaign_id)
        if rule is None:
            raise SmartMailError(
                f"Campaign has no Follow-up Rule: {campaign_id}")
        tasks = [self.get_task(task_id)] if task_id else self.list_tasks(campaign_id)
        if task_id and tasks[0]["campaign_id"] != campaign_id:
            raise SmartMailError(
                f"Outreach Task {task_id} does not belong to Campaign {campaign_id}")
        created = []
        for task in tasks:
            view = self._task_follow_up_view(task, rule)
            if view["state"] != "due":
                continue
            anchor = self._latest_sent(task["id"])
            with self._db:
                action_id = self._insert_action(
                    task["id"], campaign_id, view["next_sequence"], anchor["id"],
                    self._due_at(anchor, rule))
                if rule["has_templates"]:
                    rendered = self._render_templates(rule, task, anchor)
                    if rendered is not None:
                        self._store_prepared_action(
                            action_id, task, anchor, rendered["subject"], rendered["body"],
                            template_used=True, source_id=self._initial_source_id(task["id"]))
                    else:
                        self._set_action_detail(
                            action_id,
                            "Follow-up is due but a required template value is missing; "
                            "prepare the content from Source Material")
                else:
                    self._set_action_detail(
                        action_id,
                        "Follow-up is due but no content template is configured; the operator "
                        "prepares content from Source Material")
            created.append(self.get_follow_up_action(action_id))
        return created

    def prepare_follow_up_action(self, action_id: str, *, source_id: str) -> dict:
        """Prepare operator-supplied content for an Action due for preparation."""
        action = self._action_row(action_id)
        if action["status"] != "due_for_preparation":
            raise SmartMailError(
                f"Follow-up Action is {action['status']}, not due for operator preparation")
        source = self._db.execute(
            "SELECT id, name FROM sources WHERE id = ?", (source_id,)).fetchone()
        if source is None:
            raise SmartMailError(f"Source Material not found: {source_id}")
        task = self.get_task(action["task_id"])
        try:
            parsed = parse_draft(read_paragraphs(self.read_source(source_id)))
        except DocumentError as error:
            raise SmartMailError(f"Cannot prepare follow-up from Source Material: {error}") from error
        key = association_key(source["name"])
        if parsed is None or key is None \
                or key[0].strip().casefold() != task["institution"]["name"].strip().casefold() \
                or person_name(key[1]) != person_name(task["supervisor"]["name"]):
            raise SmartMailError(
                f"Source Material does not describe this Outreach Task: {source['name']}")
        with self._db:
            preparation_id = self._insert_follow_up_preparation(
                task["id"], source_id, subject="", body=parsed["body"],
                sender=self._task_mailbox_address(task["id"]),
                recipient=parsed["recipient"], anchor_id=action["follows_sent_record_id"],
                evidence_extra={"content_source": "operator_source_material",
                                "source": source["name"]})
            self._db.execute(
                "UPDATE follow_up_actions SET status = 'prepared', preparation_id = ? "
                "WHERE id = ?", (preparation_id, action_id))
        self.suggest_attachment_slots(preparation_id)
        return self.get_follow_up_action(action_id)

    def _render_templates(self, rule: dict, task: dict, anchor) -> dict | None:
        initial = self._db.execute(
            "SELECT content FROM sent_records WHERE task_id = ? ORDER BY rowid LIMIT 1",
            (task["id"],)).fetchone()
        original_subject = str(json.loads(initial["content"]).get("subject", "")) if initial else ""
        values = {
            "supervisor_name": task["supervisor_name"],
            "student_name": task["student_name"],
            "institution": task["institution_name"],
            "original_subject": original_subject,
        }
        if any(not str(value).strip() for value in values.values()):
            return None
        try:
            subject = rule["subject_template"].format_map(values).strip()
            body = rule["body_template"].format_map(values).strip()
        except (KeyError, IndexError, ValueError):
            return None
        if not subject or not body:
            return None
        return {"subject": subject, "body": body}

    def _latest_sent(self, task_id: str):
        return self._db.execute(
            "SELECT s.*, a.outcome_observed_at, a.intent_at FROM sent_records s "
            "LEFT JOIN execution_attempts a ON a.id = s.attempt_id "
            "WHERE s.task_id = ? ORDER BY s.rowid DESC LIMIT 1", (task_id,)).fetchone()

    def _initial_source_id(self, task_id: str) -> str:
        row = self._db.execute(
            "SELECT source_id FROM preparations WHERE task_id = ? ORDER BY rowid LIMIT 1",
            (task_id,)).fetchone()
        return row["source_id"]

    def _task_mailbox_address(self, task_id: str) -> str:
        return self._db.execute(
            "SELECT m.address FROM mailboxes m JOIN tasks t ON t.student_id = m.student_id "
            "WHERE t.id = ?", (task_id,)).fetchone()["address"]

    def _insert_action(self, task_id: str, campaign_id: str, sequence: int,
                       anchor_id: str, due_at: str) -> str:
        action_id = str(uuid4())
        self._db.execute(
            "INSERT INTO follow_up_actions (id, task_id, campaign_id, sequence, "
            "follows_sent_record_id, status, due_at, preparation_id, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'due_for_preparation', ?, NULL, '', ?)",
            (action_id, task_id, campaign_id, sequence, anchor_id, due_at, self._now()))
        return action_id

    def _set_action_detail(self, action_id: str, detail: str) -> None:
        self._db.execute(
            "UPDATE follow_up_actions SET detail = ? WHERE id = ?", (detail, action_id))

    def _store_prepared_action(self, action_id: str, task: dict, anchor,
                               subject: str, body: str, *, template_used: bool,
                               source_id: str) -> str:
        content = json.loads(anchor["content"])
        with self._db:
            preparation_id = self._insert_follow_up_preparation(
                task["id"], source_id, subject=subject, body=body,
                sender=content["sender"], recipient=content["recipient"],
                anchor_id=anchor["id"],
                evidence_extra={"content_source": "campaign_template" if template_used
                                else "operator_source_material"})
            self._db.execute(
                "UPDATE follow_up_actions SET status = 'prepared', preparation_id = ? "
                "WHERE id = ?", (preparation_id, action_id))
        return preparation_id

    def _insert_follow_up_preparation(self, task_id: str, source_id: str, *,
                                      subject: str, body: str, sender: str,
                                      recipient: str, anchor_id: str,
                                      evidence_extra: dict) -> str:
        preparation_id = str(uuid4())
        task = self.get_task(task_id)
        evidence = {
            "institution": task["institution"]["name"],
            "supervisor": task["supervisor"]["name"],
            "linked_follow_up_of": anchor_id,
            **evidence_extra,
        }
        self._db.execute(
            "INSERT INTO preparations (id, task_id, source_id, sender, recipient, subject, body, "
            "internal_note, association_evidence, action_kind, linked_sent_record_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, 'follow_up', ?)",
            (preparation_id, task_id, source_id, sender, recipient, subject, body,
             json.dumps(evidence, ensure_ascii=False), anchor_id))
        self._record_transformation(
            preparation_id, "follow_up_linked",
            f"Separate linked Follow-up Action for Sent Record {anchor_id}; it is never a "
            "re-execution of the original outreach")
        self._record_transformation(
            preparation_id,
            "follow_up_content_from_template" if evidence_extra.get("content_source")
            == "campaign_template" else "follow_up_operator_content",
            "Content rendered from the Campaign follow-up templates with recorded values"
            if evidence_extra.get("content_source") == "campaign_template"
            else "Content prepared by the operator from Source Material")
        self._revalidate(preparation_id)
        return preparation_id

    # --- Safeguard helpers used by Confirmation and Execution -----------

    def _ordinary_reply_for_task(self, task_id: str):
        return self._db.execute(
            "SELECT * FROM reply_associations WHERE task_id = ? AND status = 'associated' "
            "AND reply_kind = 'ordinary' ORDER BY rowid LIMIT 1", (task_id,)).fetchone()

    def _post_confirmation_reply_block(self, confirmation: dict):
        """A reliable Ordinary Reply associated after the Confirmation was given."""
        if self._parse_timestamp(confirmation.get("confirmed_at")) is None:
            return None
        return self._db.execute(
            "SELECT * FROM reply_associations WHERE task_id = ? AND status = 'associated' "
            "AND reply_kind = 'ordinary' AND created_at > ? ORDER BY rowid LIMIT 1",
            (confirmation["task_id"], confirmation["confirmed_at"])).fetchone()

    def _clear_follow_up_reply_pause_if_resolved(self, task_id: str) -> None:
        """Release the new-reply pause once no active follow-up Confirmation is blocked."""
        campaign_id = self._campaign_of_task(task_id)
        flow = self._flow_state(campaign_id)
        if flow["state"] != "paused" or flow["reason"] != "new_associated_reply":
            return
        blocked = self._db.execute(
            "SELECT 1 FROM reply_associations r JOIN tasks t ON t.id = r.task_id "
            "JOIN preparations p ON p.task_id = t.id AND p.action_kind != 'initial' "
            "AND p.superseded_by IS NULL "
            "JOIN confirmations c ON c.preparation_id = p.id AND c.status = 'active' "
            "WHERE t.campaign_id = ? AND r.status = 'associated' AND r.reply_kind = 'ordinary' "
            "AND r.created_at > c.confirmed_at LIMIT 1", (campaign_id,)).fetchone()
        if blocked is None:
            self._db.execute(
                "DELETE FROM execution_flow WHERE campaign_id = ? AND reason = 'new_associated_reply'",
                (campaign_id,))

    # --- Queries --------------------------------------------------------

    def _action_row(self, action_id: str):
        row = self._db.execute(
            "SELECT * FROM follow_up_actions WHERE id = ?", (action_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Follow-up Action not found: {action_id}")
        return row

    def get_follow_up_action(self, action_id: str) -> dict:
        row = self._action_row(action_id)
        preparation = None
        if row["preparation_id"]:
            full = self.get_preparation(row["preparation_id"])
            preparation = {
                "id": full["id"], "status": full["status"], "ready": full["ready"],
                "subject": full["subject"], "recipient": full["recipient"],
                "action_kind": full["action_kind"],
            }
        return {
            "id": row["id"], "task_id": row["task_id"], "campaign_id": row["campaign_id"],
            "sequence": row["sequence"], "follows_sent_record_id": row["follows_sent_record_id"],
            "status": row["status"], "due_at": row["due_at"],
            "preparation_id": row["preparation_id"], "preparation": preparation,
            "detail": row["detail"], "created_at": row["created_at"],
        }

    def list_follow_up_actions(self, campaign_id: str) -> list[dict]:
        self.get_campaign(campaign_id)
        return [self.get_follow_up_action(row["id"]) for row in self._db.execute(
            "SELECT id FROM follow_up_actions WHERE campaign_id = ? ORDER BY task_id, sequence",
            (campaign_id,))]

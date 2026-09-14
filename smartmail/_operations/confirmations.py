"""Exact-content Confirmation, expiry and operator review."""

import json
from datetime import datetime
from uuid import uuid4

from ..errors import SmartMailError
from ..snapshots import content_digest, attachments_digest


class ConfirmationOperations:
    """Exact-content Confirmation, expiry and operator review."""

    def _content_digest(self, preparation: dict) -> str:
        """A stable fingerprint of the exact message content a Confirmation binds."""
        return content_digest(preparation)

    def _attachments_digest(self, preparation: dict) -> str:
        """A stable fingerprint of the confirmed attachment bytes a Confirmation binds."""
        return attachments_digest([{**slot["attachment"], "label": slot["label"]}
                                   for slot in preparation["attachment_slots"] if slot["attachment"]])

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
                if preparation["action_kind"] != "initial" and \
                        self._ordinary_reply_for_task(preparation["task_id"]):
                    raise SmartMailError(
                        "A reliable Ordinary Reply is associated with this Outreach Task; the "
                        "linked Follow-up Action is no longer eligible")
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

"""Confirmed submission, Execution Attempts and immutable Sent Records."""

import json
import re
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from ..mailbox import MailboxCapabilityError
from ..errors import SmartMailError


_PAUSE_REASONS = {"failed": "execution_failed", "unknown": "unknown_outcome"}


class ExecutionOperations:
    """Confirmed submission, Execution Attempts and immutable Sent Records."""

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
            preparation = self.get_preparation(confirmation["preparation_id"])
            if preparation["action_kind"] != "initial":
                new_reply = self._post_confirmation_reply_block(confirmation)
                if new_reply is not None:
                    self._pause_flow(campaign_id, "new_associated_reply", {
                        "detail": "A reliable Ordinary Reply arrived after this Follow-up "
                                  f"Action was confirmed (association {new_reply['id']}); the "
                                  "confirmed follow-up would be obsolete",
                        "reply_association_id": new_reply["id"]})
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
                evidence = self._submit(request, attachment_files,
                                        confirmation_id=confirmation["id"], attempt_id=attempt_id)
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
                        "UPDATE follow_up_actions SET status = 'sent' WHERE preparation_id = ?",
                        (confirmation["preparation_id"],))
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

    def _submit(self, request: dict, attachments=None, *, confirmation_id, attempt_id) -> dict:
        try:
            if hasattr(self.mailbox, "submit_confirmed"):
                return self.mailbox.submit_confirmed(request, attachments,
                                                     confirmation_id=confirmation_id, attempt_id=attempt_id)
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
                "reference": row["reference"], "action_kind": row["action_kind"],
                "follows_sent_record_id": row["follows_sent_record_id"]}

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

    def _next_sequence(self, preparation_id: str) -> int:
        return self._db.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM execution_attempts WHERE preparation_id = ?",
            (preparation_id,)).fetchone()[0]

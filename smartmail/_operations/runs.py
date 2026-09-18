"""Execution Runs: one authorization, one ordered run, traceable batch results.

A run carries out already-confirmed Communication Actions through their own
single-action paths.  It never re-implements their safeguards, and it never
starts, resumes or retries itself.
"""

import json
from uuid import uuid4

from ..errors import SmartMailError


#: The four execution kinds a run may carry; a run has exactly one.
RUN_KINDS = ("immediate", "scheduled", "cancellation", "replacement")
#: One Confirmation's observed place in a run.
ITEM_OUTCOMES = ("sent", "observed_failure", "unknown_outcome", "refused", "not_reached",
                 # Non-immediate kinds report their own observed success: an externally
                 # scheduled draft is never Sent, and removal is never a send.
                 "externally_scheduled", "cancelled", "replaced")
#: Outcomes that stop the run: the operator must look before more is sent.
STOPPING_OUTCOMES = ("observed_failure", "unknown_outcome", "refused")

RUN_CAPABILITY = {
    "immediate": "immediate_send",
    "scheduled": "native_scheduling",
    "cancellation": "schedule_cancellation",
    "replacement": "schedule_cancellation",
}
RUN_CAPABILITY_BASIS = {
    "immediate": "Immediate sending",
    "scheduled": "Native scheduling",
    "cancellation": "Schedule cancellation",
    "replacement": "Schedule cancellation and native scheduling",
}

_ATTEMPT_OUTCOME = {
    "sent": "sent",
    "failed": "observed_failure",
    "unknown": "unknown_outcome",
}


class RunOperations:
    """Execution Runs: one authorization, one ordered run, traceable results."""

    # ------------------------------------------------------------------ command
    def run_batch(self, confirmation_ids: list[str], *, kind: str | None = None) -> dict:
        """Carry out a set of active Confirmations as one ordered Execution Run.

        The whole set is validated before anything external happens: one Campaign,
        one kind, every Confirmation active, the required capability available, no
        already-reached item, and an idle Execution Flow.  Each Confirmation then
        runs through its own single-action path and keeps its own Execution
        Attempt.  A pause or a refusal stops the run and every remaining item is
        recorded as ``not_reached``.
        """
        if not isinstance(confirmation_ids, (list, tuple)) or not confirmation_ids:
            raise SmartMailError("At least one Confirmation is required")
        identifiers = list(confirmation_ids)
        if len(identifiers) != len(set(identifiers)):
            raise SmartMailError("Select distinct Confirmations for one Execution Run")
        confirmations = [self.get_confirmation(identifier) for identifier in identifiers]
        campaigns = {self._campaign_of_task(c["task_id"]) for c in confirmations}
        if len(campaigns) != 1:
            raise SmartMailError("An Execution Run belongs to one Campaign")
        campaign_id = campaigns.pop()
        kinds = {c["execution"].get("kind", "") for c in confirmations}
        if len(kinds) != 1:
            raise SmartMailError(
                f"An Execution Run has exactly one kind; this selection mixes: "
                f"{', '.join(sorted(kinds))}")
        run_kind = kinds.pop()
        if kind is not None and kind != run_kind:
            raise SmartMailError(
                f"This selection is of kind {run_kind}, not {kind}")
        if run_kind not in RUN_KINDS:
            raise SmartMailError(f"Unsupported Execution Run kind: {run_kind}")
        for confirmation in confirmations:
            if confirmation["status"] != "active":
                raise SmartMailError(
                    f"Confirmation is not active ({confirmation['status']}); renew it before "
                    f"running: {confirmation['id']}")
            reached = self._reached_run_item(confirmation["id"])
            if reached:
                raise SmartMailError(
                    "This Confirmation was already reached by Execution Run "
                    f"{reached['run_id']} ({reached['outcome']}); a reached item is never "
                    "re-executed. Confirm again to authorize a new action")
        flow = self._flow_state(campaign_id)
        if flow["state"] == "paused":
            raise SmartMailError(
                f"Execution Flow is paused ({flow['reason']}); resolve it before running a batch")
        required = (RUN_CAPABILITY[run_kind],) if run_kind != "replacement" \
            else ("schedule_cancellation", "native_scheduling")
        capabilities = self.mailbox_capabilities()["capabilities"]
        for capability in required:
            if not capabilities.get(capability, {}).get("available"):
                raise SmartMailError(
                    f"{RUN_CAPABILITY_BASIS[run_kind]} is not available for this mailbox; it "
                    "must be enabled separately before this Execution Run")

        run_id = str(uuid4())
        self._db.execute(
            "INSERT INTO execution_runs (id, campaign_id, kind, state, requested_count, "
            "executed_count, started_at, finished_at, detail) "
            "VALUES (?, ?, ?, 'running', ?, 0, ?, '', '')",
            (run_id, campaign_id, run_kind, len(confirmations), self._now()))
        for sequence, confirmation in enumerate(confirmations, start=1):
            self._db.execute(
                "INSERT INTO execution_run_items "
                "(id, run_id, confirmation_id, sequence, attempt_id, outcome, detail) "
                "VALUES (?, ?, ?, ?, NULL, 'not_reached', '')",
                (str(uuid4()), run_id, confirmation["id"], sequence))
        self._db.commit()

        attempts: list[str] = []
        single_result: dict = {}
        for sequence, confirmation in enumerate(confirmations, start=1):
            try:
                result, outcome, detail, attempt_id = self._run_one(run_kind, confirmation)
            except SmartMailError as error:
                result, outcome, detail, attempt_id = {}, "refused", str(error), None
            except Exception as error:
                # A process-boundary interruption is not an observed outcome.  The run
                # stays ``running`` until restart recovery re-establishes each attempt,
                # so the interrupted attempt is bound to its item for that reconciliation.
                self._write_item(run_id, sequence, self._latest_attempt_id(confirmation["id"]),
                                 "unknown_outcome",
                                 str(error) or "External execution was interrupted")
                raise
            if attempt_id:
                attempts.append(attempt_id)
            single_result = result
            self._write_item(run_id, sequence, attempt_id, outcome, detail)
            flow = self._flow_state(campaign_id)
            if outcome in STOPPING_OUTCOMES or flow["state"] == "paused":
                reason = detail or (
                    f"Execution Flow is paused ({flow['reason']})" if flow["state"] == "paused"
                    else outcome)
                run = self._close_run(run_id, campaign_id, sequence, outcome, reason)
                return self._run_result(run, attempts, single_result)
        run = self._close_run(run_id, campaign_id, len(confirmations), "", "")
        return self._run_result(run, attempts, single_result)

    def _run_one(self, kind: str, confirmation: dict):
        """Carry out one Confirmation through its own single-action path."""
        if kind == "immediate":
            result = self.run_execution([confirmation["id"]])
            attempt = (result["attempts"] or [None])[-1]
            if attempt is None:
                return result, "refused", self._paused_or_silent_detail(confirmation), None
            outcome = self._attempt_outcome(attempt["state"])
            return result, outcome, human_detail(attempt["evidence"]) or outcome, attempt["id"]
        if kind == "scheduled":
            result = self.place_schedule(confirmation["id"])
            attempt = result["attempt"]
            if result.get("schedule"):
                return result, "externally_scheduled", "externally_scheduled", attempt["id"]
            outcome = self._attempt_outcome(attempt["state"])
            return result, outcome, human_detail(attempt["evidence"]) or outcome, attempt["id"]
        if kind == "cancellation":
            result = self.run_schedule_cancellation(confirmation["id"])
            attempt = result["attempt"]
            state = attempt["state"]
            outcome = {"cancelled": "cancelled", "sent": "sent"}.get(
                state, self._attempt_outcome(state))
            return result, outcome, human_detail(attempt["evidence"]) or outcome, attempt["id"]
        result = self.run_schedule_replacement(confirmation["id"])
        phase = result.get("phase")
        outcome = {"complete": "replaced", "original_sent": "sent"}.get(
            phase, "unknown_outcome")
        attempt = result.get("removal_attempt")
        return result, outcome, (
            f"Scheduled Replacement {phase}" if phase else ""), attempt["id"] if attempt else None

    @staticmethod
    def _attempt_outcome(state: str) -> str:
        return _ATTEMPT_OUTCOME.get(state, "unknown_outcome")

    def _latest_attempt_id(self, confirmation_id: str):
        row = self._db.execute(
            "SELECT id FROM execution_attempts WHERE confirmation_id = ? "
            "ORDER BY rowid DESC LIMIT 1", (confirmation_id,)).fetchone()
        return row["id"] if row else None

    def _paused_or_silent_detail(self, confirmation: dict) -> str:
        """Why a reached item produced no attempt: an operator-facing pause, or a refusal."""
        flow = self._flow_state(self._campaign_of_task(confirmation["task_id"]))
        if flow["state"] == "paused":
            return f"Execution Flow is paused ({flow['reason']})"
        return "Core recorded no Execution Attempt for this action"

    def _close_run(self, run_id, campaign_id, reached, outcome, detail) -> dict:
        self._finish_run(run_id, campaign_id, reached, outcome, detail)
        return self.get_execution_run(run_id)

    def _run_result(self, run: dict, attempts: list[str], single_result: dict) -> dict:
        """The run, plus the single-action shape a one-item run has always returned."""
        flow = self._flow_state(run["campaign_id"])
        result = {**run, "attempts": [self.get_execution_attempt(a) for a in attempts],
                  "paused": flow["state"] == "paused", "flow": flow}
        if run["requested_count"] == 1:
            result.update({key: value for key, value in single_result.items()
                           if key not in result})
        return result

    def _write_item(self, run_id, sequence, attempt_id, outcome, detail) -> None:
        self._db.execute(
            "UPDATE execution_run_items SET attempt_id = ?, outcome = ?, detail = ? "
            "WHERE run_id = ? AND sequence = ?",
            (attempt_id, outcome, detail or "", run_id, sequence))
        self._db.commit()

    def _reached_run_item(self, confirmation_id: str):
        return self._db.execute(
            "SELECT run_id, outcome FROM execution_run_items WHERE confirmation_id = ? "
            "AND outcome != 'not_reached' ORDER BY rowid DESC LIMIT 1",
            (confirmation_id,)).fetchone()

    def _finish_run(self, run_id, campaign_id, reached, outcome, detail) -> None:
        """Close a run: every item below ``reached`` stays ``not_reached``."""
        self._db.execute(
            "UPDATE execution_run_items SET outcome = 'not_reached', attempt_id = NULL, "
            "detail = 'The run stopped before reaching this action' "
            "WHERE run_id = ? AND sequence > ? AND outcome = 'not_reached'",
            (run_id, reached))
        stopped = bool(outcome)
        executed = self._db.execute(
            "SELECT count(*) FROM execution_run_items WHERE run_id = ? "
            "AND outcome != 'not_reached'", (run_id,)).fetchone()[0]
        self._db.execute(
            "UPDATE execution_runs SET state = ?, executed_count = ?, finished_at = ?, "
            "detail = ? WHERE id = ?",
            ("stopped" if stopped else "completed", executed, self._now(),
             detail if stopped else "", run_id))
        self._db.commit()

    # ------------------------------------------------------------------ queries
    def _run_view(self, row) -> dict:
        items = [self._item_view(item) for item in self._db.execute(
            "SELECT * FROM execution_run_items WHERE run_id = ? ORDER BY sequence",
            (row["id"],))]
        summary = {outcome: 0 for outcome in ITEM_OUTCOMES}
        for item in items:
            summary[item["outcome"]] += 1
        return {"id": row["id"], "campaign_id": row["campaign_id"], "kind": row["kind"],
                "state": row["state"], "requested_count": row["requested_count"],
                "executed_count": row["executed_count"], "started_at": row["started_at"],
                "finished_at": row["finished_at"], "detail": row["detail"],
                "items": items, "summary": summary,
                "reached_count": sum(1 for item in items if item["outcome"] != "not_reached"),
                "not_reached_count": summary["not_reached"]}

    def _item_view(self, row) -> dict:
        confirmation = self._db.execute(
            "SELECT preparation_id, task_id FROM confirmations WHERE id = ?",
            (row["confirmation_id"],)).fetchone()
        return {"id": row["id"], "run_id": row["run_id"],
                "confirmation_id": row["confirmation_id"], "sequence": row["sequence"],
                "attempt_id": row["attempt_id"], "outcome": row["outcome"],
                "detail": row["detail"],
                "preparation_id": confirmation["preparation_id"] if confirmation else None,
                "task_id": confirmation["task_id"] if confirmation else None}

    def get_execution_run(self, run_id: str) -> dict:
        row = self._db.execute(
            "SELECT * FROM execution_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Execution Run not found: {run_id}")
        return self._run_view(row)

    def list_execution_runs(self, campaign_id: str) -> list[dict]:
        """Every run a Campaign produced, newest first, with its items."""
        self.get_campaign(campaign_id)
        return [self._run_view(row) for row in self._db.execute(
            "SELECT * FROM execution_runs WHERE campaign_id = ? ORDER BY rowid DESC",
            (campaign_id,))]

    # ------------------------------------------------------- execution queue
    def execution_queue(self, campaign_id: str) -> list[dict]:
        """One row per active Preparation with its authorization state.

        Readiness is never reported as authorization: ``ready_to_authorize`` says
        an action may be confirmed, not that anything is authorized or sent.
        """
        self.get_campaign(campaign_id)
        rows = []
        for preparation in self.list_preparations(campaign_id):
            blocking = [finding["code"] for finding in
                        self.get_preparation(preparation["id"])["readiness_findings"]
                        if finding["blocking"]]
            sent = self._db.execute(
                "SELECT id FROM sent_records WHERE preparation_id = ?",
                (preparation["id"],)).fetchone()
            active = self._db.execute(
                "SELECT * FROM confirmations WHERE preparation_id = ? AND status = 'active' "
                "ORDER BY rowid DESC LIMIT 1", (preparation["id"],)).fetchone()
            schedule = self._db.execute(
                "SELECT id FROM external_schedules WHERE preparation_id = ? AND state IN "
                "('externally_scheduled', 'placement_unknown') ORDER BY rowid DESC LIMIT 1",
                (preparation["id"],)).fetchone()
            if sent:
                state, codes = "already_sent", []
            elif schedule:
                state, codes = "externally_scheduled", []
            elif blocking:
                state, codes = "not_ready", blocking
            elif active:
                state, codes = "awaiting_execution", []
            elif preparation["blocking_count"] == 0 and not blocking:
                state, codes = "ready_to_authorize", []
            else:
                state, codes = "not_ready", blocking
            rows.append({
                "preparation_id": preparation["id"], "task_id": preparation["task_id"],
                "supervisor_name": preparation["supervisor_name"],
                "recipient": preparation["recipient"], "subject": preparation["subject"],
                "state": state, "blocking_codes": codes,
                "confirmation_id": active["id"] if active else None,
                "confirmation_kind": (json.loads(active["execution_detail"]) or {}).get("kind")
                if active else None,
                "sent_record_id": sent["id"] if sent else None,
                "external_schedule_id": schedule["id"] if schedule else None,
            })
        return rows

    # ------------------------------------------------------------- recovery
    def _reconcile_running_runs(self) -> None:
        """Close runs a restart left open, from each attempt's re-established outcome.

        An unresolved attempt never becomes ``sent`` by default, so its item stays
        ``unknown_outcome`` and the run stops rather than completing.
        """
        rows = list(self._db.execute(
            "SELECT * FROM execution_runs WHERE state = 'running' ORDER BY rowid"))
        for row in rows:
            items = list(self._db.execute(
                "SELECT * FROM execution_run_items WHERE run_id = ? ORDER BY sequence",
                (row["id"],)))
            stopping = None
            for item in items:
                if item["outcome"] != "not_reached":
                    outcome = self._reconcile_item_outcome(item)
                    if outcome in STOPPING_OUTCOMES and stopping is None:
                        stopping = (item["sequence"], outcome, outcome)
                elif stopping is None:
                    stopping = (item["sequence"], "not_reached",
                                "The run stopped before reaching this action")
            if stopping is None:
                self._finish_run(row["id"], row["campaign_id"], len(items), "", "")
                continue
            sequence, outcome, detail = stopping
            self._finish_run(row["id"], row["campaign_id"], sequence, outcome, detail)

    def _note_resolved_attempt(self, attempt_id: str, outcome: str) -> None:
        """Keep a run item honest after Reconciliation re-establishes its attempt."""
        self._db.execute(
            "UPDATE execution_run_items SET outcome = ?, detail = ? WHERE attempt_id = ?",
            (outcome, f"Reconciliation re-established this outcome as {outcome}", attempt_id))

    def _reconcile_item_outcome(self, item) -> str:
        """Re-derive one item's outcome from the attempt recovery already performed."""
        if not item["attempt_id"]:
            return item["outcome"]
        attempt = self._db.execute(
            "SELECT state, evidence FROM execution_attempts WHERE id = ?",
            (item["attempt_id"],)).fetchone()
        if attempt is None:
            return item["outcome"]
        outcome = self._attempt_outcome(attempt["state"])
        if outcome == item["outcome"]:
            return outcome
        self._db.execute(
            "UPDATE execution_run_items SET outcome = ?, detail = ? WHERE id = ?",
            (outcome, human_detail(json.loads(attempt["evidence"] or "{}")), item["id"]))
        return outcome


def human_detail(evidence) -> str:
    """The operator-readable reason an attempt recorded, if it has one."""
    if not isinstance(evidence, dict):
        return ""
    for key in ("detail", "reason", "outcome"):
        value = evidence.get(key)
        if isinstance(value, str) and value:
            return value
    return ""

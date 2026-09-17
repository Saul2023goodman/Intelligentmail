"""Read-side Records workspace: the retained evidence ledger for inspection.

Composition only; every decision and record stays owned by Core operations.
Lists stay lean (no message bodies); full content appears in the Task
drill-down and in immutable Sent Records.
"""


def mailbox_summaries(core):
    summaries = []
    for mailbox in core.list_mailboxes():
        observations = core.list_mailbox_observations(mailbox["student_id"])
        latest = observations[-1] if observations else None
        summaries.append({**mailbox, "observation_count": len(observations),
                          "message_count": sum(len(run["messages"]) for run in observations),
                          "latest": {key: latest[key] for key in (
                              "id", "status", "observed_at", "detail", "evidence_coverage")}
                          if latest else None})
    return summaries


def _lean_attempt(attempt):
    """The ledger row without the message body; evidence and phases stay."""
    request = {key: value for key, value in attempt["request"].items() if key != "body"}
    return {**attempt, "request": request}


def _lean_proposal(view):
    return {key: view[key] for key in (
        "preparation_id", "task_id", "status", "reason", "constraint", "detail",
        "scheduled_at", "scheduled_utc", "confirmation_id", "recipient", "subject")}


def _lean_plan(plan):
    return {"id": plan["id"], "campaign_id": plan["campaign_id"],
            "status": plan["status"], "created_at": plan["created_at"],
            "configuration": plan["configuration"],
            "proposals": [_lean_proposal(view) for view in plan["proposals"]],
            "unavailable": [_lean_proposal(view) for view in plan["unavailable"]],
            "impossible": [_lean_proposal(view) for view in plan["impossible"]]}


def _lean_reply(reply):
    observation = reply.get("observation")
    return {
        "id": reply["id"], "task_id": reply["task_id"], "student_id": reply["student_id"],
        "status": reply["status"], "reply_kind": reply["reply_kind"],
        "basis": reply["basis"], "matched_rule": reply["matched_rule"],
        "resolved_by_operator": reply["resolved_by_operator"],
        "created_at": reply["created_at"], "resolved_at": reply["resolved_at"],
        "candidate_task_ids": reply["candidate_task_ids"],
        "candidates": reply.get("candidates", []),
        "observation": {key: observation[key] for key in (
            "id", "folder", "platform_reference", "counterpart", "subject",
            "observed_time", "status")} if observation else None,
    }


def records_workspace(core, campaign_id):
    """Campaign-wide evidence ledger: lineage, authorizations, attempts and outcomes."""
    report = core.operations_report(campaign_id)
    return {
        "campaign": report["campaign"],
        "generated_at": report["generated_at"],
        "flow": report["flow"],
        "rule": report["rule"],
        "counts": report["counts"],
        "tasks": report["tasks"],
        "confirmations": core.list_confirmation_history(campaign_id),
        "attempts": [_lean_attempt(attempt)
                     for attempt in core.list_execution_attempts(campaign_id)],
        "sent_records": core.list_sent_records(campaign_id),
        "schedules": core.list_external_schedules(campaign_id=campaign_id),
        "plans": [_lean_plan(plan) for plan in core.list_plans(campaign_id)],
        "duplicate_checks": core.list_duplicate_checks(campaign_id),
        "reply_associations": [_lean_reply(reply)
                               for reply in core.list_reply_associations(campaign_id)],
        "follow_up_actions": core.list_follow_up_actions(campaign_id),
        "mailboxes": mailbox_summaries(core),
    }


def records_task(core, task_id):
    """One Task's full evidence chain: versions, attempts, sent records and observations."""
    detail = core.report_task(task_id)
    task = detail["task"]
    return {
        **detail,
        "confirmations": [confirmation for confirmation in
                          core.list_confirmation_history(task["campaign_id"])
                          if confirmation["task_id"] == task_id],
        "schedules": core.list_external_schedules(task_id=task_id),
        "mailbox": {
            "observations": core.list_mailbox_observations(task["student_id"]),
            "reconciliations": core.list_reconciliations(task["student_id"]),
        },
    }

"""Follow-up automation read model for the local frontend."""


def follow_up_workspace(core, campaign_id: str) -> dict:
    campaign = core.get_campaign(campaign_id)
    tasks = {task["id"]: core.get_task(task["id"])
             for task in core.list_tasks(campaign_id)}
    confirmations = {item["preparation_id"]: item
                     for item in core.list_confirmation_history(campaign_id)}
    attempts = {item["confirmation_id"]: item
                for item in core.list_execution_attempts(campaign_id)}
    statuses = []
    for item in core.follow_up_status(campaign_id):
        task = tasks[item["task_id"]]
        statuses.append({
            **item,
            "supervisor_name": task["supervisor"]["name"],
            "institution_name": task["institution"]["name"],
            "recipient_addresses": task["supervisor"]["addresses"],
        })
    actions = []
    for action in core.list_follow_up_actions(campaign_id):
        confirmation = confirmations.get(action["preparation_id"])
        attempt = attempts.get(confirmation["id"]) if confirmation else None
        actions.append({**action, "confirmation": confirmation, "attempt": attempt})
    state_counts = {}
    for item in statuses:
        state_counts[item["state"]] = state_counts.get(item["state"], 0) + 1
    return {
        "campaign": campaign,
        "rule": core.get_follow_up_rule(campaign_id),
        "statuses": statuses,
        "actions": actions,
        "summary": {
            "tasks": len(statuses),
            "due": state_counts.get("due", 0),
            "waiting": state_counts.get("waiting", 0),
            "reply_stopped": state_counts.get("ordinary_reply_received", 0),
            "review_required": state_counts.get("reply_review_required", 0),
            "open_actions": sum(1 for item in actions if item["status"] != "sent"),
            "sent_actions": sum(1 for item in actions if item["status"] == "sent"),
            "states": state_counts,
        },
        "flow": core._flow_state(campaign_id),
        "availability": core.mailbox_capabilities()["capabilities"]["immediate_send"],
    }

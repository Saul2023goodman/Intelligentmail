"""Allowlisted batch workspace commands; Core retains execution authority."""
import hashlib
import json

from .errors import SmartMailError


def snapshot(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def review(core, request):
    kind = request["kind"]
    if kind == "plan":
        value = core.get_plan(request["plan_id"])
    elif kind == "immediate":
        ids = request["preparation_ids"]
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
            raise SmartMailError("Select distinct Preparations to confirm")
        value = [core.review_confirmation(item) for item in ids]
        campaigns = {core.get_task(item["task_id"])["campaign_id"] for item in value}
        if len(campaigns) != 1:
            raise SmartMailError("A batch must belong to one Campaign")
    elif kind in ("cancellation", "replacement"):
        value = core.review_schedule_cancellation(request["schedule_id"])
        if kind == "replacement":
            replacement = core.get_confirmation(request["replacement_confirmation_id"])
            if replacement["task_id"] != value["schedule"]["task_id"]:
                raise SmartMailError("Choose a replacement for the same Outreach Task")
            value["replacement"] = core.review_confirmation(replacement["preparation_id"])
            value["replacement_confirmation"] = replacement
    else:
        raise SmartMailError("Unsupported confirmation kind")
    return {"value": value, "token": snapshot(value)}


def dispatch_execution(core, request):
    command = request["command"]
    if command == "execution_workspace":
        campaign_id = request["campaign_id"]
        core.get_campaign(campaign_id)
        return {
            "configuration": core.get_plan_configuration(campaign_id),
            "plans": core.list_plans(campaign_id),
            "reviews": [core.review_confirmation(p["id"])
                        for p in core.list_preparations(campaign_id)],
            "confirmations": core.list_confirmations(campaign_id),
            "schedules": core.list_external_schedules(campaign_id=campaign_id),
            "attempts": core.list_execution_attempts(campaign_id),
        }
    if command == "execution_configure":
        return core.configure_plan(request["campaign_id"], **{
            key: request[key] for key in (
                "timezone", "windows", "spacing_minutes", "daily_limit", "horizon_days")
            if key in request})
    if command == "execution_propose":
        return core.propose_plan(request["campaign_id"])
    if command == "execution_adjust":
        return core.adjust_plan(request["plan_id"], request["preparation_id"], request["scheduled_at"])
    if command == "execution_review":
        return review(core, request)
    if command == "execution_confirm":
        current = review(core, request)
        if request.get("token") != current["token"]:
            raise SmartMailError("The reviewed content or execution details changed. Review again before confirming.")
        kind = request["kind"]
        if kind == "plan":
            return core.confirm_plan(request["plan_id"])
        if kind == "immediate":
            return core.confirm_preparations(request["preparation_ids"], {"kind": "immediate"})
        if kind == "cancellation":
            return core.confirm_schedule_cancellation(request["schedule_id"])
        return core.confirm_schedule_replacement(
            request["schedule_id"], request["replacement_confirmation_id"])
    if command == "execution_run":
        confirmation = core.get_confirmation(request["confirmation_id"])
        if confirmation["status"] != "active":
            raise SmartMailError("Confirmation is not active; review and confirm again before executing")
        kind = confirmation["execution"]["kind"]
        capability = {"immediate": "immediate_send", "scheduled": "native_scheduling",
                      "cancellation": "schedule_cancellation", "replacement": "schedule_cancellation"}.get(kind)
        capabilities = core.mailbox_capabilities()["capabilities"]
        if not capability or not capabilities[capability]["available"]:
            raise SmartMailError("This mailbox operation is disabled. Its capability must be enabled separately.")
        if kind == "replacement" and not capabilities["native_scheduling"]["available"]:
            raise SmartMailError("Replacement also requires native scheduling capability")
        if kind == "immediate":
            return core.run_execution([confirmation["id"]])
        if kind == "scheduled":
            return core.place_schedule(confirmation["id"])
        if kind == "cancellation":
            return core.run_schedule_cancellation(confirmation["id"])
        return core.run_schedule_replacement(confirmation["id"])
    raise SmartMailError("Unsupported UI command")

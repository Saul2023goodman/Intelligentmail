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


#: Each run kind needs its own capability; a disabled kind blocks only its own region.
KIND_CAPABILITY = {"immediate": "immediate_send", "scheduled": "native_scheduling",
                   "cancellation": "schedule_cancellation", "replacement": "schedule_cancellation"}


def run_kind_capability(core, kind):
    """Whether the mailbox reports this kind available, and why it is not when it is not."""
    capabilities = core.mailbox_capabilities()["capabilities"]
    if kind not in KIND_CAPABILITY:
        return {"kind": kind, "available": False, "capability": "",
                "basis": f"This execution kind is not supported by the batch page: {kind}"}
    required = [KIND_CAPABILITY[kind]]
    if kind == "replacement":
        required.append("native_scheduling")
    for capability in required:
        entry = capabilities.get(capability, {})
        if not entry.get("available"):
            return {"kind": kind, "available": False,
                    "capability": capability, "basis": entry.get("basis", "")}
    return {"kind": kind, "available": True, "capability": required[0], "basis": ""}


def confirmations_of(result):
    """The Confirmations an authorization produced, whatever its request kind was."""
    if isinstance(result, list):
        return result
    return list(result.get("confirmations") or [])


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
            "queue": core.execution_queue(campaign_id),
            "runs": core.list_execution_runs(campaign_id),
            "availability": {kind: run_kind_capability(core, kind)
                             for kind in KIND_CAPABILITY},
        }
    if command == "execution_runs":
        return {"runs": core.list_execution_runs(request["campaign_id"])}
    if command == "execution_run_show":
        return core.get_execution_run(request["run_id"])
    if command == "execution_configure":
        return core.configure_plan(request["campaign_id"], **{
            key: request[key] for key in (
                "timezone", "windows", "spacing_minutes", "daily_limit", "horizon_days",
                "institution_limit")
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
        # The batch page carries these Confirmations straight into a run, so one
        # authorization never needs a second selection or a second full review.
        if kind == "plan":
            plan = core.confirm_plan(request["plan_id"])
            return {**plan, "confirmations": [
                core.get_confirmation(proposal["confirmation_id"])
                for proposal in plan["proposals"] if proposal["confirmation_id"]]}
        if kind == "immediate":
            return core.confirm_preparations(request["preparation_ids"], {"kind": "immediate"})
        if kind == "cancellation":
            confirmed = core.confirm_schedule_cancellation(request["schedule_id"])
            return {**confirmed, "confirmations": [confirmed["confirmation"]]}
        confirmed = core.confirm_schedule_replacement(
            request["schedule_id"], request["replacement_confirmation_id"])
        return {**confirmed, "confirmations": [confirmed["confirmation"]]}
    if command == "execution_run":
        identifiers = request.get("confirmation_ids")
        if identifiers is None:
            identifiers = [request["confirmation_id"]]
        if not isinstance(identifiers, list) or not identifiers:
            raise SmartMailError("Select at least one Confirmation to execute")
        confirmations = [core.get_confirmation(identifier) for identifier in identifiers]
        for confirmation in confirmations:
            if confirmation["status"] != "active":
                raise SmartMailError(
                    "Confirmation is not active; review and confirm again before executing")
        reported = run_kind_capability(core, confirmations[0]["execution"]["kind"])
        if not reported["available"]:
            raise SmartMailError(
                f"This mailbox operation is disabled. {reported['basis'] or 'Its capability must be enabled separately.'}")
        return core.run_batch([confirmation["id"] for confirmation in confirmations])
    if command == "execution_queue":
        return {"queue": core.execution_queue(request["campaign_id"])}
    raise SmartMailError("Unsupported UI command")

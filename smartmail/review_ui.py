"""Composition for the readiness workbench; decisions remain in Core."""

from .errors import SmartMailError


def review_workspace(core, campaign_id):
    campaign = core.get_campaign(campaign_id)
    confirmations = core.list_confirmations(campaign_id)
    rows = []
    for report_row in core.operations_report(campaign_id)["tasks"]:
        detail = core.report_task(report_row["task_id"])
        task = detail["task"]
        for preparation in detail["preparations"]:
            if preparation["status"] == "superseded":
                continue
            sources = list(detail["sources"])
            if preparation["source"]["id"] not in {source["id"] for source in sources}:
                size = core._db.execute(
                    "SELECT length(content) FROM sources WHERE id = ?",
                    (preparation["source"]["id"],)).fetchone()[0]
                sources.append({**preparation["source"], "size": size, "sheet": "",
                                "row": 0, "evidence": preparation["association"]})
            rows.append({
                "task": task,
                "report": report_row,
                "preparation": preparation,
                "sources": sources,
                "duplicate_check": next(
                    (item for item in reversed(detail["duplicate_checks"])
                     if item["preparation_id"] == preparation["id"]), None),
                "confirmation": next(
                    (item for item in confirmations
                     if item["preparation_id"] == preparation["id"]), None),
            })
    return {"campaign": campaign, "rows": rows}


def resolve_review_exception(core, task_id, code):
    task = core.get_task(task_id)
    current = {item["code"] for item in task["exceptions"]}
    if code not in current:
        raise SmartMailError(f"Outreach Task has no unresolved {code} Exception")
    if code == "identity_ambiguity":
        return core.confirm_task_identity(task_id)
    if code == "prior_outreach_conflict":
        return core.resolve_prior_outreach(task_id)
    raise SmartMailError("This Exception requires a different supported correction")

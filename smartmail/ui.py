"""Local UI stdio bridge. Domain decisions stay in SmartMail operations.

One process owns one Core for its lifetime; requests never restart recovery.
Explicit observations, preparation and batch execution commands are exposed.
"""
import argparse
import json
import sys
from pathlib import Path

from .core import SmartMail
from .errors import SmartMailError
from .mailbox import NetEase163ExtensionMailbox
from .execution_ui import dispatch_execution
from .mailbox_ui import mailbox_workspace
from .records_ui import mailbox_summaries, records_workspace, records_task


def dispatch(core, request):
    command = request.get("command")
    if command == "mailbox_workspace":
        return mailbox_workspace(core, request["campaign_id"], request["student_id"])
    if command == "records_workspace":
        return records_workspace(core, request["campaign_id"])
    if command == "records_task":
        return records_task(core, request["task_id"])
    if isinstance(command, str) and command.startswith("execution_"):
        return dispatch_execution(core, request)
    if command == "workspace":
        campaigns = core.list_campaigns()
        campaign_id = request.get("campaign_id")
        if not campaign_id and campaigns:
            campaign_id = campaigns[0]["id"]
        return {
            "campaigns": campaigns,
            "report": core.operations_report(campaign_id) if campaign_id else None,
            "preparations": core.list_preparations(campaign_id) if campaign_id else [],
            "confirmations": core.list_confirmations(campaign_id) if campaign_id else [],
            "mailbox_capabilities": core.mailbox_capabilities(),
            "mailboxes": mailbox_summaries(core),
        }
    if command == "task":
        return {**core.report_task(request["task_id"]),
                "rewrite_sources": rewrite_sources(core, request["task_id"])}
    if command == "create_campaign":
        name = request.get("name")
        if not isinstance(name, str) or len(name) > 200:
            raise SmartMailError("Use a campaign name of 1–200 characters")
        return core.create_campaign(name)
    if command == "create_student":
        name = request.get("name")
        mailbox = request.get("mailbox")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
            raise SmartMailError("Use a student name of 1–200 characters")
        if not isinstance(mailbox, str):
            raise SmartMailError("A valid Student mailbox address is required")
        # On the workflow canvas a Student is the switchable workspace scope.
        student = core.create_student(name, mailbox)
        campaign = next((c for c in core.list_campaigns()
                         if c["name"] == student["name"]), None)
        if campaign is None:
            campaign = core.create_campaign(student["name"])
        address = next(m["address"] for m in core.list_mailboxes()
                       if m["student_id"] == student["id"])
        return {**student, "mailbox": address, "campaign_id": campaign["id"]}
    if command == "check_duplicate":
        return core.check_duplicate(request["preparation_id"])
    if command == "mailbox_history":
        return {"observations": core.list_mailbox_observations(request["student_id"]),
                "reconciliations": core.list_reconciliations(request["student_id"])}
    if command == "refresh_mailbox":
        if not core.mailbox_capabilities()["capabilities"]["read_history"]["available"]:
            raise SmartMailError("Connect the dedicated extension to the selected Student's 163 mailbox first")
        return core.refresh_mailbox(request["student_id"])
    if command == "update_preparation":
        return core.update_preparation_fields(request["preparation_id"], request["subject"], request["recipient"])
    if command == "rewrite":
        preparation = core.get_preparation(request["preparation_id"])
        if request["source_id"] not in {source["id"] for source in rewrite_sources(core, preparation["task_id"])}:
            raise SmartMailError("Choose an imported document belonging to this Student and Campaign")
        return core.rewrite_local_preparation(request["preparation_id"], request["source_id"])
    raise SmartMailError("Unsupported UI command")


def rewrite_sources(core, task_id):
    task = core.get_task(task_id)
    return [source for imported in core.list_imports(task["campaign_id"])
            if imported["student_id"] == task["student_id"]
            for source in core.get_import(imported["id"])["sources"]
            if source["name"].lower().endswith(".docx")]


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, default=Path(".smartmail"))
    args = parser.parse_args()
    with SmartMail(args.home, mailbox=NetEase163ExtensionMailbox(args.home, timeout=20)) as core:
        for line in sys.stdin:
            request = {}
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise ValueError("Expected a request object")
                response = {"result": dispatch(core, request)}
            except (SmartMailError, KeyError, ValueError, TypeError) as error:
                response = {"error": str(error)}
            except Exception:
                print("SmartMail UI request failed", file=sys.stderr)
                response = {"error": "Core request failed. Check the local store and retry."}
            response["id"] = request.get("id") if isinstance(request, dict) else None
            print(json.dumps(response, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()

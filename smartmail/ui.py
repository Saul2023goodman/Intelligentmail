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
from .intake_ui import intake_workspace, import_uploaded_sources, recognize_uploaded_sources
from .review_ui import review_workspace, resolve_review_exception
from .followup_ui import follow_up_workspace


def dispatch(core, request):
    command = request.get("command")
    if command == "intake_workspace":
        return intake_workspace(core, request.get("campaign_id"), request.get("student_id"))
    if command == "intake_import":
        return import_uploaded_sources(
            core, request["campaign_id"], request["student_id"], request["files"])
    if command == "draft_material":
        return {"candidates": core.draft_material_candidates(
            request["campaign_id"], request["student_id"])}
    if command == "intake_import_drafts":
        result = core.import_mailbox_drafts(
            request["campaign_id"], request["student_id"], request.get("observation_ids") or [])
        return {**result, "workspace": intake_workspace(
            core, request["campaign_id"], request["student_id"])}
    if command == "intake_recognize":
        return recognize_uploaded_sources(core, request["files"])
    if command == "review_workspace":
        return review_workspace(core, request["campaign_id"])
    if command == "confirm_attachment":
        return core.confirm_attachment(request["preparation_id"], request["slot_id"])
    if command == "set_attachment_source":
        return core.set_attachment(
            request["preparation_id"], request["slot_id"], source_id=request["source_id"])
    if command == "resolve_review_exception":
        return resolve_review_exception(core, request["task_id"], request["code"])
    if command == "mailbox_workspace":
        return mailbox_workspace(core, request["campaign_id"], request["student_id"])
    if command == "records_workspace":
        return records_workspace(core, request["campaign_id"])
    if command == "records_task":
        return records_task(core, request["task_id"])
    if command == "followup_workspace":
        return follow_up_workspace(core, request["campaign_id"])
    if command == "followup_configure":
        rule = core.configure_follow_up_rule(
            request["campaign_id"],
            delay_days=request.get("delay_days"),
            maximum_count=request.get("maximum_count"),
            subject_template=request.get("subject_template"),
            body_template=request.get("body_template"),
            enabled=request.get("enabled"),
            timezone_name=request.get("timezone"),
            send_time=request.get("send_time"),
        )
        return {"rule": rule, "workspace": follow_up_workspace(core, request["campaign_id"])}
    if command == "followup_process":
        result = core.process_follow_up_automation(request["campaign_id"])
        return {**result, "workspace": follow_up_workspace(core, request["campaign_id"])}
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
    if command == "gateway_status":
        return core.mailbox.gateway_status()
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
        # On the workflow canvas a Student is the switchable workspace scope, and the
        # Student owns exactly one Campaign: Core establishes both and states the link.
        student = core.create_student(name, mailbox)
        address = next(m["address"] for m in core.list_mailboxes()
                       if m["student_id"] == student["id"])
        return {**student, "mailbox": address}
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
    if command == "update_preparation_subjects":
        updates = request.get("updates")
        if not isinstance(updates, list):
            raise SmartMailError("A subject batch needs a list of Preparation updates")
        return core.update_preparation_subjects(updates)
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
    parser.add_argument("--enable-extension-send", action="store_true")
    parser.add_argument("--enable-extension-schedule", action="store_true")
    parser.add_argument("--enable-extension-recall", action="store_true")
    args = parser.parse_args()
    mailbox = NetEase163ExtensionMailbox(
        args.home,
        enable_send=args.enable_extension_send,
        enable_schedule=args.enable_extension_schedule,
        enable_recall=args.enable_extension_recall,
        timeout=20,
    )
    with SmartMail(args.home, mailbox=mailbox) as core:
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

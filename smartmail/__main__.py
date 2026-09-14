"""Terminal shell. All outreach decisions and persistence live in SmartMail."""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import SmartMail, SmartMailError
from .mailbox import ControlledMailbox, NetEase163Mailbox


def controlled_clock(value):
    """A fixed instant so planning and expiry decisions are reproducible."""
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise SmartMailError(f"Unsupported --now value: {value}") from error
    return lambda: moment


def main() -> int:
    parser = argparse.ArgumentParser(description="SmartMail: import and inspect local Outreach Tasks")
    parser.add_argument("--home", type=Path, default=Path(".smartmail"), help="Local store directory (default: .smartmail)")
    parser.add_argument("--adapter", choices=["disabled", "controlled", "163-browser"],
                        default="disabled",
                        help="Mailbox adapter; external execution is disabled by default")
    parser.add_argument("--adapter-script", type=Path,
                        help="Outcome script for the controlled adapter (development and testing)")
    parser.add_argument("--browser-session", default="smartmail-163",
                        help="Named Playwright CLI session used by the read-only 163 browser adapter")
    parser.add_argument("--now",
                        help="Controlled ISO-8601 time for reproducible planning and expiry acceptance")
    commands = parser.add_subparsers(dest="command", required=True)

    campaign = commands.add_parser("campaign", help="Create, list or inspect Campaigns").add_subparsers(dest="action", required=True)
    campaign.add_parser("create").add_argument("name")
    campaign.add_parser("list")
    campaign.add_parser("show").add_argument("id")

    student = commands.add_parser("student", help="Explicitly register a Student and Mailbox").add_subparsers(dest="action", required=True)
    create = student.add_parser("create")
    create.add_argument("name")
    create.add_argument("--mailbox", required=True)
    student.add_parser("list")
    student.add_parser("show").add_argument("id")

    intake = commands.add_parser("import", help="Import an existing .xlsx or .zip bundle")
    intake.add_argument("path", type=Path)
    intake.add_argument("--campaign", required=True, help="Explicit Campaign ID from campaign list/create")
    intake.add_argument("--student", required=True, help="Explicit Student ID from student list/create")

    imports = commands.add_parser("imports", help="Inspect an import and its preserved materials").add_subparsers(dest="action", required=True)
    imports.add_parser("list").add_argument("--campaign", required=True)
    imports.add_parser("show").add_argument("id")
    imports.add_parser("findings").add_argument("id", help="Documents that produced no single Preparation")

    prepare = commands.add_parser("prepare", help="Associate draft documents and prepare local messages")
    prepare.add_argument("--import", dest="import_id", required=True, help="Import ID from imports list")

    preparation = commands.add_parser("preparation", help="Inspect, correct and preview local Preparations").add_subparsers(dest="action", required=True)
    preparation.add_parser("list").add_argument("--campaign", required=True)
    preparation.add_parser("show").add_argument("id")
    preparation.add_parser("preview").add_argument("id", help="Print the full local message")
    subject = preparation.add_parser("set-subject", help="Correct the authoritative subject")
    subject.add_argument("id")
    subject.add_argument("subject")
    recipient = preparation.add_parser("set-recipient", help="Correct the recipient address")
    recipient.add_argument("id")
    recipient.add_argument("address")
    preparation.add_parser("suggest", help="Refresh advisory attachment slots").add_argument("id")
    confirm = preparation.add_parser("confirm", help="Confirm a slot's suggested attachment")
    confirm.add_argument("id")
    confirm.add_argument("--slot", required=True)
    attach = preparation.add_parser("attach", help="Confirm or replace a slot's file")
    attach.add_argument("id")
    attach.add_argument("--slot", required=True)
    attach.add_argument("--source", help="Source Material ID from imports show")
    attach.add_argument("--file", type=Path, help="A local file to snapshot verbatim")
    add = preparation.add_parser("add-attachment", help="Add an operator-defined attachment slot")
    add.add_argument("id")
    add.add_argument("--label", required=True)
    add.add_argument("--source", help="Source Material ID from imports show")
    add.add_argument("--file", type=Path, help="A local file to snapshot verbatim")
    remove = preparation.add_parser("remove-attachment", help="Remove an attachment slot")
    remove.add_argument("id")
    remove.add_argument("--slot", required=True)
    rewrite = preparation.add_parser("rewrite", help="Replace a Preparation with a fresh one from a revised Source Material")
    rewrite.add_argument("id")
    rewrite.add_argument("--source", required=True, help="Source Material ID from imports show")
    preparation.add_parser("history", help="Inspect the active and Superseded versions of a Preparation").add_argument("id")
    follow_up = preparation.add_parser(
        "link-follow-up", help="Mark a Preparation as a linked Follow-up Action")
    follow_up.add_argument("id")
    follow_up.add_argument("--sent", help="Sent Record ID of the earlier outreach")

    tasks = commands.add_parser("task", help="Inspect Outreach Tasks and Exceptions").add_subparsers(dest="action", required=True)
    tasks.add_parser("list").add_argument("--campaign", required=True)
    tasks.add_parser("show").add_argument("id")
    tasks.add_parser("confirm-identity", help="Confirm a Task's Supervisor identity").add_argument("id")

    exceptions = commands.add_parser("exceptions", help="List and inspect blocking Exceptions").add_subparsers(dest="action", required=True)
    exceptions.add_parser("list").add_argument("--campaign", required=True)
    exceptions.add_parser("show").add_argument("id")

    confirmation = commands.add_parser("confirmation", help="Review and confirm exact Preparations").add_subparsers(dest="action", required=True)
    confirmation.add_parser("review", help="Inspect the exact message before confirming").add_argument("id")
    confirm = confirmation.add_parser("confirm", help="Authorize one or more Ready Preparations")
    confirm.add_argument("ids", nargs="+")
    confirm.add_argument("--expires-at", help="Optional ISO-8601 Confirmation expiry")
    confirm.add_argument("--confirmed-at", help="Optional ISO-8601 operator confirmation time")
    confirmation.add_parser("list").add_argument("--campaign", required=True)
    confirmation.add_parser("show").add_argument("id")

    execution = commands.add_parser("execution", help="Execute confirmed work through the mailbox adapter").add_subparsers(dest="action", required=True)
    run = execution.add_parser("run", help="Execute one or more Confirmations in order")
    run.add_argument("ids", nargs="+")
    execution.add_parser("list").add_argument("--campaign", required=True)
    execution.add_parser("show").add_argument("id")
    execution.add_parser("status").add_argument("--campaign", required=True)
    resume = execution.add_parser(
        "resume", aliases=["recover"],
        help="Resume still-valid confirmed work after persisted recovery checks")
    resume.add_argument("--campaign", required=True)
    takeover = execution.add_parser(
        "takeover", aliases=["take-over"], help="Record an explicit Manual Takeover")
    takeover.add_argument("id")
    takeover.add_argument("--detail", default="")
    reconcile_continue = execution.add_parser(
        "reconcile-and-continue", aliases=["reconcile"],
        help="Observe mailbox evidence before resolving and continuing an attempt")
    reconcile_continue.add_argument("id", help="Unresolved Execution Attempt ID")
    reconcile_continue.add_argument(
        "confirmation_ids", nargs="*", help="Confirmed work to run after positive reconciliation")
    reconcile_continue.add_argument(
        "--acknowledge", action="store_true",
        help="Record operator acknowledgment; it never establishes Sent")
    stop = execution.add_parser("stop", help="Stop an unresolved Execution Attempt")
    stop.add_argument("id")
    stop.add_argument("--detail", default="")

    sent = commands.add_parser("sent", help="Inspect immutable Sent Records").add_subparsers(dest="action", required=True)
    sent.add_parser("list").add_argument("--campaign", required=True)
    sent.add_parser("show").add_argument("id")

    mailbox_commands = commands.add_parser(
        "mailbox", help="Inspect capabilities and manually refresh read-only mailbox evidence"
    ).add_subparsers(dest="action", required=True)
    mailbox_commands.add_parser("capabilities")
    refresh = mailbox_commands.add_parser(
        "refresh", help="Observe the intended Student's Mailbox and reconcile local records")
    refresh.add_argument("--student", required=True)
    observations = mailbox_commands.add_parser("observations")
    observations.add_argument("--student", required=True)
    mailbox_commands.add_parser("show").add_argument("id")

    reconciliation = commands.add_parser(
        "reconciliation", help="Inspect persisted manual Reconciliation results"
    ).add_subparsers(dest="action", required=True)
    reconciliations = reconciliation.add_parser("list")
    reconciliations.add_argument("--student", required=True)
    reconciliation.add_parser("show").add_argument("id")

    duplicate = commands.add_parser(
        "duplicate", help="Detect Repeat Execution and repeated initial outreach"
    ).add_subparsers(dest="action", required=True)
    duplicate.add_parser("check", help="Check one Preparation against available history").add_argument("id")
    duplicates = duplicate.add_parser("list", help="List recorded checks for a Campaign")
    duplicates.add_argument("--campaign", required=True)
    duplicate.add_parser("show").add_argument("id")

    plan = commands.add_parser(
        "plan", help="Configure, propose, adjust and confirm deterministic Sending Plans"
    ).add_subparsers(dest="action", required=True)
    plan_configure = plan.add_parser(
        "configure", help="Configure allowed windows, timezone, spacing and daily limits")
    plan_configure.add_argument("--campaign", required=True)
    plan_configure.add_argument("--timezone", help="IANA timezone such as Asia/Shanghai")
    plan_configure.add_argument("--window", action="append", dest="windows",
                                help="Repeatable allowed window, e.g. 'MON-FRI 09:00-17:00'")
    plan_configure.add_argument("--spacing", type=int, dest="spacing_minutes",
                                help="Minimum minutes between two actions")
    plan_configure.add_argument("--daily-limit", type=int)
    plan_configure.add_argument("--horizon-days", type=int)
    plan_propose = plan.add_parser(
        "propose", help="Propose sending times under the configured constraints")
    plan_propose.add_argument("--campaign", required=True)
    plan_list = plan.add_parser("list", help="List the Campaign's Sending Plans and their status")
    plan_list.add_argument("--campaign", required=True)
    plan.add_parser("show", help="Review every planned action before Confirmation").add_argument("id")
    plan_adjust = plan.add_parser(
        "adjust", help="Set one planned action's exact time before Confirmation")
    plan_adjust.add_argument("id")
    plan_adjust.add_argument("--preparation", required=True)
    plan_adjust.add_argument("--time", required=True, help="Exact ISO-8601 time in the plan timezone")
    plan.add_parser(
        "confirm", help="Authorize every scheduled action of a Sending Plan").add_argument("id")

    source = commands.add_parser("source", help="Open a fresh copy of preserved original bytes").add_subparsers(dest="action", required=True)
    opening = source.add_parser("open")
    opening.add_argument("id")
    opening.add_argument("--path-only", action="store_true", help="Materialize and print the path without launching a desktop app")

    args = parser.parse_args()
    try:
        mailbox = None
        if args.adapter == "controlled":
            mailbox = (ControlledMailbox.from_script(args.adapter_script) if args.adapter_script
                       else ControlledMailbox())
        elif args.adapter == "163-browser":
            mailbox = NetEase163Mailbox(session=args.browser_session)
        with SmartMail(args.home, mailbox=mailbox, clock=controlled_clock(args.now)) as core:
            if args.command == "campaign":
                if args.action == "create":
                    result = core.create_campaign(args.name)
                elif args.action == "list":
                    result = core.list_campaigns()
                else:
                    result = core.get_campaign(args.id)
            elif args.command == "student":
                if args.action == "create":
                    result = core.create_student(args.name, args.mailbox)
                elif args.action == "list":
                    result = core.list_students()
                else:
                    result = core.get_student(args.id)
            elif args.command == "import":
                result = core.import_master(args.campaign, args.student, args.path)
            elif args.command == "imports":
                if args.action == "list":
                    result = core.list_imports(args.campaign)
                elif args.action == "show":
                    result = core.get_import(args.id)
                else:
                    result = core.list_unassociated_documents(args.id)
            elif args.command == "prepare":
                result = core.prepare_from_documents(args.import_id)
            elif args.command == "preparation":
                if args.action == "list":
                    result = core.list_preparations(args.campaign)
                elif args.action == "show":
                    result = core.get_preparation(args.id)
                elif args.action == "preview":
                    print(core.preview_preparation(args.id)["text"])
                    return 0
                elif args.action == "set-subject":
                    result = core.set_subject(args.id, args.subject)
                elif args.action == "set-recipient":
                    result = core.set_recipient(args.id, args.address)
                elif args.action == "suggest":
                    result = core.suggest_attachment_slots(args.id)
                elif args.action == "confirm":
                    result = core.confirm_attachment(args.id, args.slot)
                elif args.action == "attach":
                    result = core.set_attachment(args.id, args.slot, source_id=args.source, path=args.file)
                elif args.action == "add-attachment":
                    result = core.add_attachment_slot(args.id, args.label, source_id=args.source, path=args.file)
                elif args.action == "rewrite":
                    result = core.rewrite(args.id, source_id=args.source)
                elif args.action == "history":
                    result = core.get_preparation_history(args.id)
                elif args.action == "link-follow-up":
                    result = core.link_follow_up(args.id, args.sent)
                else:
                    result = core.remove_attachment_slot(args.id, args.slot)
            elif args.command == "task":
                if args.action == "list":
                    result = core.list_tasks(args.campaign)
                elif args.action == "show":
                    result = core.get_task(args.id)
                else:
                    result = core.confirm_task_identity(args.id)
            elif args.command == "exceptions":
                result = core.list_exceptions(args.campaign) if args.action == "list" else core.get_exception(args.id)
            elif args.command == "confirmation":
                if args.action == "review":
                    result = core.review_confirmation(args.id)
                elif args.action == "confirm":
                    execution = {"kind": "immediate"}
                    if args.expires_at:
                        execution["expires_at"] = args.expires_at
                    result = core.confirm_preparations(
                        args.ids, execution=execution, confirmed_at=args.confirmed_at)
                elif args.action == "list":
                    result = core.list_confirmations(args.campaign)
                else:
                    result = core.get_confirmation(args.id)
            elif args.command == "execution":
                if args.action == "run":
                    result = core.run_execution(args.ids)
                elif args.action == "list":
                    result = core.list_execution_attempts(args.campaign)
                elif args.action == "show":
                    result = core.get_execution_attempt(args.id)
                elif args.action == "status":
                    result = core.execution_status(args.campaign)
                elif args.action in ("resume", "recover"):
                    result = core.resume_execution(args.campaign)
                elif args.action in ("takeover", "take-over"):
                    result = core.take_over_execution(args.id, detail=args.detail)
                elif args.action in ("reconcile-and-continue", "reconcile"):
                    result = core.reconcile_and_continue(
                        args.id, args.confirmation_ids or None, acknowledge=args.acknowledge)
                else:
                    result = core.stop_execution_attempt(args.id, detail=args.detail)
            elif args.command == "sent":
                result = (core.list_sent_records(args.campaign) if args.action == "list"
                          else core.get_sent_record(args.id))
            elif args.command == "mailbox":
                if args.action == "capabilities":
                    result = core.mailbox_capabilities()
                elif args.action == "refresh":
                    result = core.refresh_mailbox(args.student)
                elif args.action == "observations":
                    result = core.list_mailbox_observations(args.student)
                else:
                    result = core.get_mailbox_observation(args.id)
            elif args.command == "reconciliation":
                result = (core.list_reconciliations(args.student) if args.action == "list"
                          else core.get_reconciliation(args.id))
            elif args.command == "duplicate":
                if args.action == "check":
                    result = core.check_duplicate(args.id)
                elif args.action == "list":
                    result = core.list_duplicate_checks(args.campaign)
                else:
                    result = core.get_duplicate_check(args.id)
            elif args.command == "plan":
                if args.action == "configure":
                    result = core.configure_plan(
                        args.campaign, timezone=args.timezone, windows=args.windows,
                        spacing_minutes=args.spacing_minutes, daily_limit=args.daily_limit,
                        horizon_days=args.horizon_days)
                elif args.action == "propose":
                    result = core.propose_plan(args.campaign)
                elif args.action == "list":
                    result = core.list_plans(args.campaign)
                elif args.action == "adjust":
                    result = core.adjust_plan(args.id, args.preparation, args.time)
                elif args.action == "confirm":
                    result = core.confirm_plan(args.id)
                else:
                    result = core.get_plan(args.id)
            else:
                path = core.materialize_source(args.id)
                if not args.path_only:
                    if sys.platform == "win32":
                        os.startfile(path)
                    else:
                        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(path)], check=True)
                result = {"path": str(path)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (SmartMailError, OSError, sqlite3.Error, subprocess.CalledProcessError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())

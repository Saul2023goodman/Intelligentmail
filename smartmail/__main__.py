"""Terminal shell. All outreach decisions and persistence live in SmartMail."""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from . import SmartMail, SmartMailError


def main() -> int:
    parser = argparse.ArgumentParser(description="SmartMail: import and inspect local Outreach Tasks")
    parser.add_argument("--home", type=Path, default=Path(".smartmail"), help="Local store directory (default: .smartmail)")
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

    tasks = commands.add_parser("task", help="Inspect Outreach Tasks and Exceptions").add_subparsers(dest="action", required=True)
    tasks.add_parser("list").add_argument("--campaign", required=True)
    tasks.add_parser("show").add_argument("id")
    tasks.add_parser("confirm-identity", help="Confirm a Task's Supervisor identity").add_argument("id")

    exceptions = commands.add_parser("exceptions", help="List and inspect blocking Exceptions").add_subparsers(dest="action", required=True)
    exceptions.add_parser("list").add_argument("--campaign", required=True)
    exceptions.add_parser("show").add_argument("id")

    source = commands.add_parser("source", help="Open a fresh copy of preserved original bytes").add_subparsers(dest="action", required=True)
    opening = source.add_parser("open")
    opening.add_argument("id")
    opening.add_argument("--path-only", action="store_true", help="Materialize and print the path without launching a desktop app")

    args = parser.parse_args()
    try:
        with SmartMail(args.home) as core:
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

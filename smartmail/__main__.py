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

    tasks = commands.add_parser("task", help="Inspect Outreach Tasks and Exceptions").add_subparsers(dest="action", required=True)
    tasks.add_parser("list").add_argument("--campaign", required=True)
    tasks.add_parser("show").add_argument("id")

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
                result = core.list_imports(args.campaign) if args.action == "list" else core.get_import(args.id)
            elif args.command == "task":
                result = core.list_tasks(args.campaign) if args.action == "list" else core.get_task(args.id)
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

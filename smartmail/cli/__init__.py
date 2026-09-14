"""Terminal runtime: adapter selection, output and operator-visible errors."""

import json
import sqlite3
import subprocess
import sys
from datetime import datetime

from .. import SmartMail, SmartMailError
from ..mailbox import ControlledMailbox, NetEase163ExtensionMailbox
from .commands import dispatch
from .parser import build_parser


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
    args = build_parser().parse_args()
    try:
        mailbox = None
        if args.adapter == "controlled":
            mailbox = (ControlledMailbox.from_script(args.adapter_script) if args.adapter_script
                       else ControlledMailbox())
        elif args.adapter == "163-extension":
            mailbox = NetEase163ExtensionMailbox(args.home, enable_send=args.enable_extension_send)
        with SmartMail(args.home, mailbox=mailbox, clock=controlled_clock(args.now)) as core:
            result = dispatch(core, args)
        if args.command == "preparation" and args.action == "preview":
            print(result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (SmartMailError, OSError, sqlite3.Error, subprocess.CalledProcessError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2

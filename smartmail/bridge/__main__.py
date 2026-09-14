"""Install or inspect the bridge; browsers launch the framed host bootstrap."""

import argparse
import json
import os
import sys
from pathlib import Path

from . import BridgeError
from .install import install, uninstall
from .native import NativeSession
from .queue import CommandQueue


def serve(home, allowed_origin):
    # Chrome supplies the caller origin before --parent-window. Never trust a
    # caller-provided store path; the installed bootstrap fixes the store.
    if len(sys.argv) < 2 or sys.argv[1] != allowed_origin:
        raise SystemExit("Native host caller is not the installed extension")
    if sys.platform == "win32":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    try:
        NativeSession(CommandQueue(home)).serve(sys.stdin.buffer, sys.stdout.buffer)
    except (BridgeError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)


def main():
    parser = argparse.ArgumentParser(description="SmartMail dedicated extension bridge")
    parser.add_argument("--home", type=Path, default=Path(".smartmail"))
    commands = parser.add_subparsers(dest="command", required=True)
    adding = commands.add_parser("install")
    adding.add_argument("--extension-id", required=True)
    adding.add_argument("--browser", choices=["chrome", "edge"], required=True)
    removing = commands.add_parser("uninstall")
    removing.add_argument("--browser", choices=["chrome", "edge"], required=True)
    commands.add_parser("status")
    args = parser.parse_args()
    try:
        if args.command == "install":
            result = install(args.home, args.extension_id, args.browser)
        elif args.command == "uninstall":
            result = uninstall(args.browser)
        else:
            result = CommandQueue(args.home).status()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (BridgeError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Run the SmartMail terminal application."""

import sys

from .cli import controlled_clock, main


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())

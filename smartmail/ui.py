"""Local UI stdio bridge. Domain decisions stay in SmartMail operations.

One process owns one Core for its lifetime; requests never restart recovery.
No mailbox transport, execution, or arbitrary method dispatch is exposed.
"""
import argparse
import json
import sys
from pathlib import Path

from .core import SmartMail
from .errors import SmartMailError


def dispatch(core, request):
    command = request.get("command")
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
        }
    if command == "task":
        return core.report_task(request["task_id"])
    if command == "create_campaign":
        name = request.get("name")
        if not isinstance(name, str) or len(name) > 200:
            raise SmartMailError("Use a campaign name of 1–200 characters")
        return core.create_campaign(name)
    if command == "check_duplicate":
        return core.check_duplicate(request["preparation_id"])
    raise SmartMailError("Unsupported UI command")


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, default=Path(".smartmail"))
    args = parser.parse_args()
    with SmartMail(args.home) as core:
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

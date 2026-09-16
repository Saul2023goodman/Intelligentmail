"""Command-line arguments; no store access or business decisions."""

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SmartMail: import and inspect local Outreach Tasks")
    parser.add_argument("--home", type=Path, default=Path(".smartmail"), help="Local store directory (default: .smartmail)")
    parser.add_argument("--adapter", choices=["disabled", "controlled", "163-extension"],
                        default="disabled",
                        help="Mailbox adapter; external execution is disabled by default")
    parser.add_argument("--adapter-script", type=Path,
                        help="Outcome script for the controlled adapter (development and testing)")
    parser.add_argument("--enable-extension-send", action="store_true",
                        help="Opt into confirmed extension sending for live acceptance; disabled by default")
    parser.add_argument("--enable-extension-schedule", action="store_true",
                        help="Opt into native schedule placement/cancellation for live acceptance")
    parser.add_argument("--enable-extension-recall", action="store_true",
                        help="Separately opt into confirmed Recall; disabled by default")
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
    confirm.add_argument("--schedule-at",
                         help="Bind a native schedule: exact ISO-8601 time (naive implies --timezone)")
    confirm.add_argument("--timezone", default="Asia/Shanghai",
                         help="IANA timezone for a naive --schedule-at (default Asia/Shanghai)")
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

    reply = commands.add_parser(
        "reply", help="Review reliable, automatic and ambiguous reply associations"
    ).add_subparsers(dest="action", required=True)
    reply_list = reply.add_parser("list", help="List reply associations for a Campaign")
    reply_list.add_argument("--campaign", required=True)
    reply_list.add_argument(
        "--status", choices=["associated", "ambiguous", "dismissed"],
        help="Filter by association status")
    reply.add_parser("show", help="Inspect one association and its evidence").add_argument("id")
    reply_resolve = reply.add_parser(
        "resolve", help="Pin an ambiguous reply to an Outreach Task or dismiss it")
    reply_resolve.add_argument("id")
    reply_resolve.add_argument("--task", help="Outreach Task ID the reply belongs to")
    reply_resolve.add_argument(
        "--dismiss", action="store_true",
        help="Record that the message is not outreach correspondence")

    followup = commands.add_parser(
        "followup", help="Configure Follow-up Rules, review Follow-up Due and prepare actions"
    ).add_subparsers(dest="action", required=True)
    followup_configure = followup.add_parser(
        "configure", help="Configure follow-up timing, maximum count and optional templates")
    followup_configure.add_argument("--campaign", required=True)
    followup_configure.add_argument("--delay-days", type=int, dest="delay_days")
    followup_configure.add_argument("--max", type=int, dest="maximum_count")
    followup_configure.add_argument("--subject-template", dest="subject_template")
    followup_configure.add_argument("--body-template", dest="body_template")
    followup_status = followup.add_parser(
        "status", help="Compute deterministic Follow-up Due eligibility per Task")
    followup_status.add_argument("--campaign", required=True)
    followup_prepare = followup.add_parser(
        "prepare", help="Create due linked Follow-up Actions for a Campaign or Task")
    followup_prepare.add_argument("--campaign", required=True)
    followup_prepare.add_argument("--task", dest="task_id")
    followup_list = followup.add_parser("list", help="List linked Follow-up Actions")
    followup_list.add_argument("--campaign", required=True)
    followup.add_parser("show", help="Inspect one Follow-up Action").add_argument("id")
    followup_action = followup.add_parser(
        "prepare-action",
        help="Prepare content for a Follow-up Action marked due for operator preparation")
    followup_action.add_argument("id")
    followup_action.add_argument("--source", required=True, help="Source Material ID from imports show")

    report = commands.add_parser(
        "report", help="Operational summaries with task and evidence drill-down"
    ).add_subparsers(dest="action", required=True)
    report_show = report.add_parser("show", help="Summarize a Campaign's operations")
    report_show.add_argument("--campaign", required=True)
    report_show.add_argument("--student")
    report_show.add_argument("--supervisor")
    report_show.add_argument("--institution")
    report_show.add_argument("--mailbox")
    report_show.add_argument(
        "--message-status", dest="message_status",
        choices=["locally_planned", "externally_scheduled", "sent",
                 "observed_failure", "unknown_outcome"])
    report_show.add_argument(
        "--duplicate-status", dest="duplicate_status",
        choices=["no_duplicate_found", "duplicate_suspicion", "ambiguous_match",
                 "repeat_execution", "linked_follow_up", "unchecked"])
    report_show.add_argument(
        "--exceptions", choices=["blocking", "any", "none"])
    report_show.add_argument(
        "--follow-up", dest="follow_up",
        choices=["due", "waiting", "ordinary_reply_received", "reply_review_required",
                 "maximum_reached", "no_initial_send", "follow_up_open", "rule_not_configured"])
    report.add_parser("task", help="Drill down into one Outreach Task and its evidence"
                      ).add_argument("id")

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

    schedule = commands.add_parser(
        "schedule", help="Place, track, cancel and replace native external schedules"
    ).add_subparsers(dest="action", required=True)
    schedule.add_parser("place", help="Place a confirmed native schedule"
                        ).add_argument("confirmation_id")
    schedule_list = schedule.add_parser("list", help="List tracked external schedules")
    schedule_list.add_argument("--campaign")
    schedule_list.add_argument("--task")
    schedule_list.add_argument("--state", choices=sorted([
        "placement_unknown", "externally_scheduled", "sent",
        "cancelled", "cancel_unknown", "replaced"]))
    schedule.add_parser("show").add_argument("id")
    schedule.add_parser("cancel-review",
                        help="Inspect the external schedule before explicit Cancellation"
                        ).add_argument("id")
    schedule.add_parser("cancel-confirm",
                        help="Authorize removal of one external scheduled draft"
                        ).add_argument("id")
    schedule_run_cancel = schedule.add_parser(
        "cancel-run", help="Observe removal after a confirmed Cancellation")
    schedule_run_cancel.add_argument("confirmation_id")
    replace_confirm = schedule.add_parser(
        "replace-confirm",
        help="Confirm removal of an old schedule plus its exact replacement schedule")
    replace_confirm.add_argument("schedule_id")
    replace_confirm.add_argument("replacement_confirmation_id")
    replace_run = schedule.add_parser(
        "replace-run",
        help="Verify removal, then submit the replacement (never auto-restores)")
    replace_run.add_argument("confirmation_id")
    schedule_reconcile = schedule.add_parser(
        "reconcile", help="Observe mailbox evidence and reconcile tracked schedules")
    schedule_reconcile.add_argument("--student", required=True)

    recall = commands.add_parser(
        "recall", help="Conditional platform Recall; reported separately, never blocking"
    ).add_subparsers(dest="action", required=True)
    recall.add_parser("review").add_argument("sent_record_id")
    recall.add_parser("confirm").add_argument("sent_record_id")
    recall.add_parser("run").add_argument("confirmation_id")

    observe = commands.add_parser(
        "observation", help="Configure observation-only periodicity"
    ).add_subparsers(dest="action", required=True)
    observe_set = observe.add_parser("set-interval")
    observe_set.add_argument("--student", required=True)
    observe_set.add_argument("--seconds", type=int, required=True,
                            help="0 disables periodic observation; observation never mutates the mailbox")
    observe_get = observe.add_parser("show")
    observe_get.add_argument("--student", required=True)

    source = commands.add_parser("source", help="Open a fresh copy of preserved original bytes").add_subparsers(dest="action", required=True)
    opening = source.add_parser("open")
    opening.add_argument("id")
    opening.add_argument("--path-only", action="store_true", help="Materialize and print the path without launching a desktop app")
    return parser

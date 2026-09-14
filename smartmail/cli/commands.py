"""Translate parsed terminal commands into SmartMail calls."""

import os
import subprocess
import sys


def dispatch(core, args):
    """Return command output; Preparation preview returns plain text."""
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
            result = core.preview_preparation(args.id)["text"]
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
    elif args.command == "reply":
        if args.action == "list":
            result = core.list_reply_associations(
                args.campaign, status=args.status)
        elif args.action == "show":
            result = core.get_reply_association(args.id)
        else:
            result = core.resolve_reply_association(
                args.id, args.task, dismiss=args.dismiss)
    elif args.command == "followup":
        if args.action == "configure":
            result = core.configure_follow_up_rule(
                args.campaign, delay_days=args.delay_days,
                maximum_count=args.maximum_count,
                subject_template=args.subject_template,
                body_template=args.body_template)
        elif args.action == "status":
            result = core.follow_up_status(args.campaign)
        elif args.action == "prepare":
            result = core.prepare_follow_ups(args.campaign, task_id=args.task_id)
        elif args.action == "list":
            result = core.list_follow_up_actions(args.campaign)
        elif args.action == "prepare-action":
            result = core.prepare_follow_up_action(args.id, source_id=args.source)
        else:
            result = core.get_follow_up_action(args.id)
    elif args.command == "report":
        if args.action == "task":
            result = core.report_task(args.id)
        else:
            result = core.operations_report(
                args.campaign, student_id=args.student, supervisor_id=args.supervisor,
                institution_id=args.institution, mailbox=args.mailbox,
                message_status=args.message_status, duplicate_status=args.duplicate_status,
                exceptions=args.exceptions, follow_up=args.follow_up)
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
    return result

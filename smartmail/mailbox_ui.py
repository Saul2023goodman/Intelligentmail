"""Read-side mailbox workspace. Links come only from persisted Core findings."""


def mailbox_workspace(core, campaign_id, student_id):
    report = core.operations_report(campaign_id, student_id=student_id)
    observations = core.list_mailbox_observations(student_id)
    latest = observations[-1] if observations else None
    reconciliation = (core.get_reconciliation(latest['reconciliation_id'])
                      if latest and latest['reconciliation_id'] else None)
    records = {}
    for task in report['tasks']:
        detail = core.report_task(task['task_id'])
        preparations = {p['id']: p for p in detail['preparations']}
        represented = set()

        def add(kind, record, content, state, when=''):
            records[(kind, record['id'])] = {
                'id': record['id'], 'kind': kind, 'state': state,
                'subject': content.get('subject', ''),
                'recipient': content.get('recipient', ''), 'time': when,
                'task_id': task['task_id'], 'supervisor': task['supervisor_name'],
                'institution': task['institution_name'], 'evidence': record,
            }
            represented.add(record.get('preparation_id'))

        for sent in detail['sent_records']:
            add('sent_record', sent, sent, 'sent')
        for schedule in core.list_external_schedules(task_id=task['task_id']):
            add('external_schedule', schedule, preparations.get(schedule['preparation_id'], {}),
                schedule['state'], schedule['scheduled_utc'])
        for attempt in detail['execution_attempts']:
            if attempt['state'] in ('unknown', 'in_progress', 'failed'):
                add('execution_attempt', attempt, attempt['request'], attempt['state'])
        for reply in detail['reply_associations']:
            if reply['task_id'] == task['task_id']:
                add('reply_association', reply, {}, reply['status'])
        for preparation in preparations.values():
            if preparation['status'] != 'superseded' and preparation['id'] not in represented:
                add('preparation', preparation, preparation, 'locally_planned')

    messages = {m['id']: m for m in latest['messages']} if latest else {}
    rows, linked = [], set()
    for finding in reconciliation['findings'] if reconciliation else []:
        key = (finding['local_kind'], finding['local_id'])
        local = records.get(key)
        # Findings linked to another campaign are not presented as this campaign's work.
        if finding['local_id'] and local is None:
            continue
        message = messages.get(finding['message_observation_id'])
        rows.append({'id': finding['id'], 'local': local, 'observed': message,
                     'findings': [finding]})
        linked.add(key)
    # Suppress a generic external-schedule row when Core has a more specific link.
    linked_messages = {r['observed']['id'] for r in rows if r['local'] and r['observed']}
    rows = [r for r in rows if r['local'] or not r['observed']
            or r['observed']['id'] not in linked_messages]
    for key, local in records.items():
        if key not in linked:
            rows.append({'id': ':'.join(key), 'local': local, 'observed': None, 'findings': []})
    return {'rows': rows, 'observation': latest, 'reconciliation': reconciliation,
            'history': [{'id': o['id'], 'observed_at': o['observed_at'], 'status': o['status'],
                         'detail': o['detail'], 'evidence_coverage': o['evidence_coverage']}
                        for o in reversed(observations)],
            'flow': report['flow']}

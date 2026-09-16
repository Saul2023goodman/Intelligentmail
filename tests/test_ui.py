"""UI bridge acceptance against persisted Core operations, without mailbox writes."""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta

from smartmail.errors import SmartMailError
from smartmail.ui import dispatch
from tests.test_execution import ExecutionTestCase, ROOT
from tests.test_reconciliation import observed_history
from smartmail.mailbox import ControlledMailbox, DisabledMailbox


class UiBridgeTests(ExecutionTestCase):
    def test_rewrite_source_choices_stay_with_student_and_campaign(self):
        preparation, _ = self.ready_preparation()
        other_campaign = self.core.create_campaign('Other scope')
        imported = self.core.import_master(other_campaign['id'], self.student['id'], self.directory / 'bundle.zip')
        other_source = next(source for source in self.core.get_import(imported['id'])['sources']
                            if source['name'] == preparation['source']['name'])
        detail = dispatch(self.core, {'command': 'task', 'task_id': preparation['task_id']})
        self.assertIn(preparation['source']['id'], {source['id'] for source in detail['rewrite_sources']})
        self.assertNotIn(other_source['id'], {source['id'] for source in detail['rewrite_sources']})
        with self.assertRaises(SmartMailError):
            dispatch(self.core, {'command': 'rewrite', 'preparation_id': preparation['id'], 'source_id': other_source['id']})

    def test_unresolved_attempt_cannot_be_edited(self):
        preparation, _ = self.ready_preparation()
        self.core.mailbox = ControlledMailbox(['unknown'])
        confirmation = self.core.confirm(preparation['id'])
        self.core.run_execution([confirmation['id']])
        with self.assertRaises(SmartMailError):
            self.core.update_preparation_fields(preparation['id'], 'Changed', preparation['recipient'])
        with self.assertRaises(SmartMailError):
            dispatch(self.core, {'command': 'rewrite', 'preparation_id': preparation['id'],
                                'source_id': preparation['source']['id']})

    def test_external_schedule_requires_replacement_flow(self):
        preparation, _ = self.ready_preparation()
        self.core.mailbox = ControlledMailbox(allow_schedule=True)
        confirmation = self.core.confirm(preparation['id'], {
            'kind': 'scheduled', 'scheduled_utc': (self.core._instant() + timedelta(days=1)).isoformat()})
        self.core.place_schedule(confirmation['id'])
        for command in ('update_preparation', 'rewrite'):
            with self.assertRaises(SmartMailError):
                dispatch(self.core, {'command': command, 'preparation_id': preparation['id'],
                                    'subject': 'Changed', 'recipient': preparation['recipient'],
                                    'source_id': preparation['source']['id']})

    def test_external_read_persists_evidence_and_feeds_duplicate_check(self):
        preparation, _ = self.ready_preparation()
        observation = observed_history()
        observation['messages'][1]['counterpart'] = preparation['recipient']
        observation['messages'][1]['subject'] = preparation['subject']
        self.core.mailbox = ControlledMailbox(observations=[observation])
        result = dispatch(self.core, {'command': 'refresh_mailbox', 'student_id': self.student['id']})
        self.assertEqual(len(result['observation']['messages']), 2)
        workspace = dispatch(self.core, {'command': 'workspace'})
        self.assertEqual(workspace['mailboxes'][0]['observation_count'], 1)
        self.assertEqual(workspace['mailboxes'][0]['message_count'], 2)
        history = dispatch(self.core, {'command': 'mailbox_history', 'student_id': self.student['id']})
        self.assertEqual(history['reconciliations'][0]['id'], result['reconciliation']['id'])
        duplicate = dispatch(self.core, {'command': 'check_duplicate', 'preparation_id': preparation['id']})
        self.assertEqual(duplicate['finding'], 'duplicate_suspicion')
        self.assertEqual(self.core.get_preparation(preparation['id'])['body'], preparation['body'])
        self.assertEqual(self.core.mailbox.requests, [])

    def test_disconnected_read_is_not_reported_as_success(self):
        self.core.mailbox = DisabledMailbox()
        with self.assertRaises(SmartMailError):
            dispatch(self.core, {'command': 'refresh_mailbox', 'student_id': self.student['id']})
        self.assertEqual(self.core.list_mailbox_observations(self.student['id']), [])

    def test_reading_external_draft_does_not_replace_local_preparation(self):
        preparation, _ = self.ready_preparation()
        observation = observed_history()
        observation['messages'] = [{**observation['messages'][1], 'status': 'draft',
                                    'folder': 'drafts', 'subject': 'External changes'}]
        self.core.mailbox = ControlledMailbox(observations=[observation])
        dispatch(self.core, {'command': 'refresh_mailbox', 'student_id': self.student['id']})
        self.assertEqual(self.core.get_preparation(preparation['id'])['subject'], preparation['subject'])

    def test_draft_update_revalidates_and_invalidates_confirmation_atomically(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation['id'])
        with self.assertRaises(SmartMailError):
            dispatch(self.core, {'command': 'update_preparation', 'preparation_id': preparation['id'],
                                'subject': 'Should not persist', 'recipient': 'bad-address'})
        self.assertEqual(self.core.get_preparation(preparation['id'])['subject'], preparation['subject'])
        result = dispatch(self.core, {'command': 'update_preparation', 'preparation_id': preparation['id'],
                                     'subject': 'Updated subject', 'recipient': 'other@example.edu'})
        self.assertFalse(result['ready'])
        self.assertTrue(any(f['code'] == 'recipient_conflict' for f in result['readiness_findings']))
        self.assertEqual(self.core.get_confirmation(confirmation['id'])['status'], 'invalidated')
        self.assertEqual(len(result['corrections']), len(preparation['corrections']) + 2)
        self.assertEqual(self.mailbox.requests, [])

    def test_source_rewrite_preserves_history_and_drops_authorization(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation['id'])
        result = dispatch(self.core, {'command': 'rewrite', 'preparation_id': preparation['id'],
                                     'source_id': preparation['source']['id']})
        self.assertNotEqual(result['id'], preparation['id'])
        self.assertEqual(self.core.get_preparation(preparation['id'])['status'], 'superseded')
        self.assertEqual(self.core.get_confirmation(confirmation['id'])['status'], 'invalidated')
        with self.assertRaises(SmartMailError):
            dispatch(self.core, {'command': 'update_preparation', 'preparation_id': preparation['id'],
                                'subject': 'History', 'recipient': preparation['recipient']})

    def test_sent_preparation_cannot_be_edited_or_rewritten(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation['id'])
        self.core.run_execution([confirmation['id']])
        for command in ('update_preparation', 'rewrite'):
            with self.assertRaises(SmartMailError):
                dispatch(self.core, {'command': command, 'preparation_id': preparation['id'],
                                    'subject': 'Changed', 'recipient': preparation['recipient'],
                                    'source_id': preparation['source']['id']})

    def test_workspace_and_task_preserve_core_readiness_and_evidence(self):
        preparation, _ = self.ready_preparation(subject=None)
        workspace = dispatch(self.core, {"command": "workspace", "campaign_id": self.campaign["id"]})
        self.assertEqual(workspace["report"]["counts"]["tasks"], 1)
        self.assertGreater(workspace["preparations"][0]["blocking_count"], 0)
        detail = dispatch(self.core, {"command": "task", "task_id": preparation["task_id"]})
        self.assertFalse(detail["preparations"][0]["ready"])
        self.assertEqual(detail["preparations"][0]["body"], preparation["body"])
        self.assertTrue(detail["sources"])
        self.assertEqual(self.mailbox.requests, [])

    def test_duplicate_command_persists_core_coverage_without_execution(self):
        preparation, _ = self.ready_preparation()
        result = dispatch(self.core, {"command": "check_duplicate", "preparation_id": preparation["id"]})
        self.assertEqual(result["finding"], "no_duplicate_found")
        self.assertFalse(result["evidence_coverage"]["complete"])
        detail = dispatch(self.core, {"command": "task", "task_id": preparation["task_id"]})
        self.assertEqual(detail["duplicate_checks"][-1]["id"], result["id"])
        self.assertEqual(self.mailbox.requests, [])

    def test_explicit_campaign_scope_and_no_arbitrary_dispatch(self):
        self.ready_preparation()
        other = dispatch(self.core, {"command": "create_campaign", "name": "Separate scope"})
        self.assertEqual(dispatch(self.core, {"command": "workspace", "campaign_id": other["id"]})["report"]["counts"]["tasks"], 0)
        for command in ("run_execution", "confirm", "_db", "unknown"):
            with self.assertRaises(SmartMailError):
                dispatch(self.core, {"command": command})


class UiProtocolTests(unittest.TestCase):
    def test_stdio_handles_bad_input_and_keeps_store_across_requests(self):
        with tempfile.TemporaryDirectory() as home:
            requests = ['not json', '[]', json.dumps({"id": 1, "command": "create_campaign", "name": "研究 outreach"}, ensure_ascii=False), json.dumps({"id": 2, "command": "workspace"})]
            result = subprocess.run([sys.executable, '-m', 'smartmail.ui', '--home', home],
                                    input='\n'.join(requests) + '\n', capture_output=True,
                                    text=True, encoding='utf-8', cwd=ROOT, check=True)
            replies = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertIn('error', replies[0])
            self.assertIn('error', replies[1])
            self.assertEqual(replies[3]['id'], 2)
            self.assertEqual(replies[3]['result']['campaigns'][0]['name'], '研究 outreach')
            self.assertEqual(replies[3]['result']['report']['counts']['tasks'], 0)


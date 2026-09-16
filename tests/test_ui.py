"""UI bridge acceptance against persisted Core operations, without mailbox writes."""
import json
import subprocess
import sys
import tempfile
import unittest

from smartmail.errors import SmartMailError
from smartmail.ui import dispatch
from tests.test_execution import ExecutionTestCase, ROOT


class UiBridgeTests(ExecutionTestCase):
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


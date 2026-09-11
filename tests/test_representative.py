"""Opt-in pilot against the supplied private archive; it is never committed."""

import os
import tempfile
import unittest
from pathlib import Path

from smartmail import SmartMail


@unittest.skipUnless(os.environ.get("SMARTMAIL_SAMPLE_ZIP"), "Set SMARTMAIL_SAMPLE_ZIP to the supplied sample.zip")
class RepresentativeMaterialTests(unittest.TestCase):
    def test_supplied_master_import_and_restart_preserve_observed_records(self):
        with tempfile.TemporaryDirectory() as home:
            with SmartMail(Path(home)) as core:
                campaign = core.create_campaign("Representative pilot")
                student = core.create_student("Sipei Yao", "artsipei@163.com")
                result = core.import_master(campaign["id"], student["id"], Path(os.environ["SMARTMAIL_SAMPLE_ZIP"]))
            with SmartMail(Path(home)) as core:
                tasks = [core.get_task(t["id"]) for t in core.list_tasks(campaign["id"])]
                self.assertEqual(len(tasks), 59)
                self.assertEqual(len({t["institution"]["id"] for t in tasks}), 11)
                self.assertEqual(sum(len(t["supervisor"]["addresses"]) for t in tasks), 55)
                blocked_names = {t["supervisor"]["name"] for t in tasks if t["exceptions"]}
                self.assertEqual(blocked_names, {"Prof Terri Bird", "Professor Callum Morton", "Professor Kathy Temin", "Dr Joy Paton"})
                sources = core.get_import(result["id"])["sources"]
                self.assertEqual(len(sources), 22)
                self.assertEqual(sources[0]["sha256"], "f2e73a53d3503c3568cfeba730317ba232f4258636d9f5560e10dea77398f5e2")
                self.assertIn("姚思培/姚思培_60筛导初版.xlsx", [s["name"] for s in sources])

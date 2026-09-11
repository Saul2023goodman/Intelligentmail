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

    def test_supplied_drafts_produce_inspectable_local_preparations(self):
        with tempfile.TemporaryDirectory() as home:
            with SmartMail(Path(home)) as core:
                campaign = core.create_campaign("Representative pilot")
                student = core.create_student("Sipei Yao", "artsipei@163.com")
                imported = core.import_master(
                    campaign["id"], student["id"], Path(os.environ["SMARTMAIL_SAMPLE_ZIP"]))
                result = core.prepare_from_documents(imported["id"])
                self.assertEqual(len(result["preparation_ids"]), 17)

                findings = core.list_unassociated_documents(imported["id"])
                self.assertEqual(
                    {f["source"]["name"].rsplit("/", 1)[-1] for f in findings},
                    {"University of Technology Sydney_Nahum McLean.docx",
                     "University of Technology Sydney_Nga Wun Doris Li.docx"})
                self.assertTrue(all(f["code"] == "unassociated_document" for f in findings))

                preparations = [
                    core.get_preparation(p["id"]) for p in core.list_preparations(campaign["id"])]
                by_supervisor = {p["association"]["supervisor"]: p for p in preparations}
                self.assertEqual([p["id"] for p in preparations if p["ready"]], [])

                conflicts = [p for p in preparations if any(
                    f["code"] == "recipient_conflict" for f in p["readiness_findings"])]
                self.assertEqual(
                    [p["association"]["supervisor"] for p in conflicts], ["Susanna Castleden"])
                self.assertEqual(conflicts[0]["recipient"], "S.Castleden@exchange.curtin.edu.au")

                morton = by_supervisor["Callum Morton"]
                self.assertEqual(morton["recipient"], "callum.morton@monash.edu")
                self.assertIn("recipient_filled_missing_address",
                              {t["code"] for t in morton["transformations"]})

                laird = by_supervisor["Tessa Laird"]
                self.assertTrue(laird["body"].startswith("Dear Dr Laird,"))
                self.assertTrue(laird["body"].endswith("Sipei Yao"))
                self.assertNotIn("Research source", laird["body"])
                self.assertIn("Research source", laird["internal_note"])
                self.assertEqual({f["code"] for f in laird["readiness_findings"]}, {"missing_subject"})

    def test_supplied_drafts_suggest_the_student_cv_and_accept_corrections(self):
        with tempfile.TemporaryDirectory() as home:
            with SmartMail(Path(home)) as core:
                campaign = core.create_campaign("Representative pilot")
                student = core.create_student("Sipei Yao", "artsipei@163.com")
                imported = core.import_master(
                    campaign["id"], student["id"], Path(os.environ["SMARTMAIL_SAMPLE_ZIP"]))
                core.prepare_from_documents(imported["id"])
                cv = next(s for s in core.get_import(imported["id"])["sources"]
                          if s["name"].endswith("CV.docx"))

                preparations = [core.get_preparation(p["id"])
                                for p in core.list_preparations(campaign["id"])]
                self.assertEqual(len(preparations), 17)
                for preparation in preparations:
                    slots = preparation["attachment_slots"]
                    self.assertEqual([s["label"] for s in slots], ["Student CV"])
                    self.assertEqual([c["name"] for c in slots[0]["candidates"]], [cv["name"]])
                    self.assertEqual(slots[0]["suggested_source_id"], cv["id"])
                    self.assertIsNone(slots[0]["attachment"])
                self.assertEqual(
                    [p for p in preparations if p["attachment_slots"][0]["attachment"]], [])

                laird = next(p for p in preparations if p["association"]["supervisor"] == "Tessa Laird")
                self.assertFalse(laird["ready"])
                corrected = core.set_subject(laird["id"], "PhD supervision enquiry")
                self.assertTrue(corrected["ready"])
                self.assertEqual(core.preview_preparation(laird["id"])["readiness"], "Ready")

                attachment = core.confirm_attachment(
                    laird["id"], corrected["attachment_slots"][0]["id"]
                )["attachment_slots"][0]["attachment"]
                self.assertEqual(attachment["sha256"], cv["sha256"])
                self.assertEqual(core.read_attachment(attachment["id"]), core.read_source(cv["id"]))

                exceptions = core.list_exceptions(campaign["id"])
                self.assertEqual([e["code"] for e in exceptions], ["invalid_recipient"] * 4)
                self.assertTrue(all(e["blocking"] for e in exceptions))
                self.assertTrue(all(e["source"]["name"].endswith(".xlsx") for e in exceptions))
                morton = next(e for e in exceptions if "Morton" in e["supervisor_name"])
                self.assertEqual([f["code"] for f in morton["readiness_findings"]],
                                 ["missing_subject"])

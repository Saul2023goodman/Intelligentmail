"""Deterministic extension peer; no browser, credentials or external sends."""

import threading
import time
import base64

from smartmail.bridge.native import NativeSession
from smartmail.bridge.queue import CommandQueue
from tests.test_execution import SUBJECT


class FixtureExtension:
    def __init__(self, home, outcome=None, observation=None, before_permit=None, drop_result=False,
                 schedule_outcome=None, cancel_outcome=None, recall_outcome=None,
                 permit_reject=False):
        self.queue = CommandQueue(home)
        self.session = NativeSession(self.queue)
        self.call("connect", mailbox_address="student@163.com")
        self.outcome = outcome
        self.observation = observation
        self.before_permit = before_permit
        self.drop_result = drop_result
        self.schedule_outcome = schedule_outcome
        self.cancel_outcome = cancel_outcome
        self.recall_outcome = recall_outcome
        self.permit_reject = permit_reject
        self.requests = []
        self.schedule_requests = []
        self.cancel_requests = []
        self.recall_requests = []
        self.attachments = []
        self.errors = []
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def call(self, kind, **payload):
        return self.session.handle({"protocol": 1, "type": kind, **payload})

    def close(self):
        self.stopping.set()
        self.thread.join(timeout=3)
        self.queue.disconnect(self.session.id)

    def run(self):
        while not self.stopping.is_set():
            try:
                command = self.call("poll")["command"]
                if not command:
                    self.stopping.wait(0.01)
                    continue
                payload = command["payload"]
                if command["operation"] == "observe":
                    result = self.observation or observed_sent()
                else:
                    needs_attachments = command["operation"] in ("submit", "schedule")
                    if needs_attachments:
                        self.requests.append(payload)
                        content = []
                        for position in range(len(payload["attachments"])):
                            offset = 0
                            data = bytearray()
                            while True:
                                chunk = self.call("attachment", command_id=command["id"], position=position, offset=offset)
                                data.extend(base64.b64decode(chunk["data"]))
                                offset = chunk["next"]
                                if chunk["done"]:
                                    break
                            content.append(bytes(data))
                        self.attachments.append(content)
                    if self.before_permit:
                        self.before_permit()
                    permitted = False
                    try:
                        if self.permit_reject:
                            raise ValueError("scripted permit rejection")
                        self.call("authorize", command_id=command["id"])
                        permitted = True
                        if command["operation"] == "submit":
                            result = self.outcome or {
                                "outcome": "sent", "reference": "extension-sent-1", "mailbox_address": payload["sender"],
                                "evidence": {"folder": "sent", "new_reference": True,
                                             "recipient": payload["recipient"], "subject": payload["subject"]},
                            }
                        elif command["operation"] == "schedule":
                            self.schedule_requests.append(payload)
                            result = self.schedule_outcome or scheduled(payload)
                        elif command["operation"] == "cancel_schedule":
                            self.cancel_requests.append(payload)
                            result = self.cancel_outcome or {
                                "outcome": "removed", "reference": payload["external_id"],
                                "external_id": payload["external_id"], "mailbox_address": payload["sender"],
                                "evidence": {"folder_deleted": True, "external_id": payload["external_id"]}}
                        else:
                            self.recall_requests.append(payload)
                            result = self.recall_outcome or {
                                "outcome": "recalled", "reference": payload["external_id"],
                                "external_id": payload["external_id"], "mailbox_address": payload["sender"],
                                "evidence": {"response_code": "S_OK"}}
                    except ValueError as error:
                        # A denied permit is a pre-submission failure; an error after
                        # the permit is granted is Unknown (the click may have happened).
                        result = {"outcome": "unknown" if permitted else "failed",
                                  "detail": str(error)}
                if self.drop_result:
                    self.queue.disconnect(self.session.id)
                    return
                self.call("result", command_id=command["id"], result=result)
            except Exception as error:
                self.errors.append(error)
                return


def scheduled(payload):
    epoch = payload.get("scheduled_epoch_ms")
    stamp = ""
    if epoch:
        from datetime import datetime, timezone, timedelta
        stamp = datetime.fromtimestamp(epoch / 1000, tz=timezone(timedelta(hours=8))) \
            .strftime("%Y-%m-%d %H:%M:%S")
    return {
        "outcome": "scheduled", "reference": "761:ext-schedule-1",
        "external_id": "761:ext-schedule-1", "mailbox_address": payload["sender"],
        "evidence": {"folder": "drafts", "schedule_delivery": True,
                     "recipient": payload["recipient"], "subject": payload["subject"],
                     "scheduled_epoch_ms": epoch, "scheduled_beijing": stamp,
                     "msid": 761, "mid": "ext-schedule-1"},
    }


def observed_sent(counterpart="alex@example.edu", subject=SUBJECT, reference="163-sent-1"):
    return {
        "status": "complete",
        "mailbox_address": "student@163.com",
        "observed_at": "2026-09-11T07:30:00+00:00",
        "coverage": {"complete": False, "folders": []},
        "messages": [{
            "direction": "outbound", "folder": "sent", "platform_reference": reference,
            "counterpart": counterpart, "subject": subject,
            "observed_time": "2026年9月11日 16:00", "status": "sent", "ambiguity": "",
            "evidence": {"marker": "发送成功"},
        }],
    }

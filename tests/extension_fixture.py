"""Deterministic extension peer; no browser, credentials or external sends."""

import threading
import time
import base64

from smartmail.bridge.native import NativeSession
from smartmail.bridge.queue import CommandQueue
from tests.test_execution import SUBJECT


class FixtureExtension:
    def __init__(self, home, outcome=None, observation=None, before_permit=None, drop_result=False):
        self.queue = CommandQueue(home)
        self.session = NativeSession(self.queue)
        self.call("connect", mailbox_address="student@163.com")
        self.outcome = outcome
        self.observation = observation
        self.before_permit = before_permit
        self.drop_result = drop_result
        self.requests = []
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
                    try:
                        self.call("authorize", command_id=command["id"])
                        result = self.outcome or {
                            "outcome": "sent", "reference": "extension-sent-1", "mailbox_address": payload["sender"],
                            "evidence": {"folder": "sent", "new_reference": True,
                                         "recipient": payload["recipient"], "subject": payload["subject"]},
                        }
                    except ValueError as error:
                        result = {"outcome": "failed", "detail": str(error)}
                if self.drop_result:
                    self.queue.disconnect(self.session.id)
                    return
                self.call("result", command_id=command["id"], result=result)
            except Exception as error:
                self.errors.append(error)
                return


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

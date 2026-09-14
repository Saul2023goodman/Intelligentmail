"""Canonical digests shared by Confirmation and last-moment extension checks."""

import hashlib
import json


def content_digest(preparation):
    canonical = json.dumps({key: preparation[key] for key in ("sender", "recipient", "subject", "body")},
                           ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def attachments_digest(attachments):
    entries = [[item["label"], item["name"], item["sha256"]] for item in attachments]
    return hashlib.sha256(json.dumps(entries, ensure_ascii=False).encode("utf-8")).hexdigest()

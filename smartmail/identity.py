"""Conservative normalization; no name-only identity resolution."""

import re
from urllib.parse import urlsplit, urlunsplit


def person_name(value: str) -> str:
    return re.sub(r"^(?:(?:dr|prof|professor)\.?\s+)+", "", " ".join(value.split()).casefold())


def profile_url(value: str) -> str:
    url = urlsplit(value.strip())
    if url.scheme.lower() not in {"https", "http"} or not url.hostname:
        return ""
    return urlunsplit((url.scheme.lower(), url.netloc.lower(), url.path.rstrip("/"), url.query, url.fragment))


def email_address(value: str) -> str | None:
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}", value):
        return None
    local, domain = value.rsplit("@", 1)
    if local.startswith(".") or local.endswith(".") or ".." in value:
        return None
    return local + "@" + domain.lower()

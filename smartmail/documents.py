"""Deterministic extraction for the inspected outreach draft documents."""

import re
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PARAGRAPH = f"{{{WORD_NAMESPACE}}}p"
TEXT = f"{{{WORD_NAMESPACE}}}t"

# The observed draft layout: a single recipient declaration line, a greeting, the
# message body, a sign-off, and a trailing internal research note.
RECIPIENT_LINE = re.compile(r"^Email:\s*(\S.*?)\s*$", re.IGNORECASE)
SALUTATION = re.compile(r"^Dear\b")
INTERNAL_NOTE_MARKERS = ("research source:",)


class DocumentError(ValueError):
    """The document does not fit the documented draft pattern."""


def read_paragraphs(data: bytes) -> list[str]:
    try:
        with ZipFile(BytesIO(data)) as archive:
            xml = archive.read("word/document.xml")
    except (BadZipFile, KeyError) as error:
        raise DocumentError("Not a readable .docx document") from error
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as error:
        raise DocumentError("Malformed .docx document") from error
    return [
        "".join(node.text or "" for node in paragraph.iter(TEXT))
        for paragraph in root.iter(PARAGRAPH)
    ]


def parse_draft(paragraphs: list[str]) -> dict | None:
    """Parse the supported draft layout, or return None for material that is not a draft."""
    first = next((i for i, text in enumerate(paragraphs) if text.strip()), None)
    if first is None:
        return None
    recipient = RECIPIENT_LINE.match(paragraphs[first].strip())
    if recipient is None:
        return None
    salutation = next(
        (i for i in range(first + 1, len(paragraphs)) if SALUTATION.match(paragraphs[i].strip())), None
    )
    if salutation is None:
        return None
    note_start = next(
        (i for i in range(salutation, len(paragraphs))
         if paragraphs[i].strip().casefold().startswith(INTERNAL_NOTE_MARKERS)), None
    )
    end = note_start if note_start is not None else len(paragraphs)
    note = [text.strip() for text in paragraphs[end:] if text.strip()] if note_start is not None else []
    return {
        "recipient": recipient.group(1),
        "body": normalize_body(paragraphs[salutation:end]),
        "internal_note": "\n".join(note),
        "note_separated": note_start is not None,
    }


def normalize_body(paragraphs: list[str]) -> str:
    """Trim and collapse the observed blank-line spacing without inventing content."""
    lines = [text.strip() for text in paragraphs]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    result: list[str] = []
    for line in lines:
        if not line and result and not result[-1]:
            continue
        result.append(line)
    return "\n".join(result)


def association_key(filename: str) -> tuple[str, str] | None:
    """The supported document naming pattern: '<Institution>_<Supervisor name>.docx'."""
    stem = PurePosixPath(filename).name
    if stem.lower().endswith(".docx"):
        stem = stem[:-5]
    institution, separator, supervisor = stem.partition("_")
    institution, supervisor = institution.strip(), supervisor.strip()
    if not separator or not institution or not supervisor:
        return None
    return institution, supervisor


# The observed sentence that declares an enclosed attachment: "I have attached my CV".
ATTACHMENT_DECLARATION = re.compile(
    r"\bI(?:'ve| have)\s+attached\s+(?:my|the|a|an)\s+"
    r"(?P<label>[A-Za-z][A-Za-z0-9+#/&-]*(?:\s+[A-Za-z][A-Za-z0-9+#/&-]*){0,2})",
    re.IGNORECASE,
)
DECLARATION_STOP_WORDS = {
    "and", "or", "which", "that", "for", "to", "with", "as", "so", "but", "however",
    "in", "on", "at", "please", "would", "will", "is", "are", "was", "were", "the",
}


def attachment_declarations(body: str) -> list[str]:
    """Attachment labels declared in a supported body sentence, in order, without duplicates."""
    labels: list[str] = []
    for match in ATTACHMENT_DECLARATION.finditer(body):
        words: list[str] = []
        for word in match.group("label").split():
            if word.casefold() in DECLARATION_STOP_WORDS:
                break
            words.append(word)
        label = " ".join(words).strip()
        if label and label.casefold() not in {existing.casefold() for existing in labels}:
            labels.append(label)
    return labels

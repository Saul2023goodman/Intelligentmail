"""Deterministic source recognition.

The intake pipeline must decide what a dropped-in file *is* before any task,
preparation or attachment is created.  Earlier logic encoded that decision in
two narrow parsers (an ``.xlsx`` is a supervisor master; a ``.docx`` is a draft
only when it begins with an ``Email:`` line followed by ``Dear``).  File name
and extension carried the decision, so unrelated spreadsheets, planning
documents, maintenance logs and name-only draft files were either forced into
the wrong type or rejected without explanation.

This module classifies sources from structural evidence alone, organised along
five linguistic planes.  The planes are generalizable rather than tied to the
observed file names:

1. Layout / graphemic plane -- paragraphs versus tables, banner rows, blank
   separator rows, bullet glyphs, emoji markers, heading casing, column
   regularity, repeated row schemas.
2. Schematic plane (discourse genre moves) -- a recruitment letter realises a
   fixed move sequence (salutation, goodwill opener, sender self-introduction,
   purpose of writing, reference to the addressee's work, attachment mention,
   request, sign-off).  A CV, a log, a timeline and a catalogue each realise a
   different schema; repeating the letter schema marks a multi-draft bundle.
3. Register / lexical-field plane -- applicant-academic register ("apply for
   PhD", "CV attached") differs from scholar-faculty register ("Assistant
   Professor", "PI", grant amounts), workflow register ("套磁/跟进/筛选"),
   program-reference register ("项目名称/学位类型/学制/截止日期") and
   out-of-domain register (statutes, translation/collocation data).
4. Interpersonal / information-structure plane -- letters are dialogic
   I-to-you discourse with one addressee; CVs and logs are monologic
   entity/attribute catalogues; timelines are period-headed directive text.
   Topic words ("导师", "邮箱", "邮件") cannot cross this boundary.
5. Entity / role plane -- the same person string can be the sending student,
   the addressed supervisor, or a third party mentioned in a record.  Role is
   decided by *where* the name occurs (self-introduction/sign-off,
   salutation/recipient row, catalogue row), never by the file name.

Every rule emits positive reasons and cautions quoting counts or short
snippets, so a classification is inspectable.  When evidence is missing or
two hypotheses are equally supported the result stays unresolved (``unknown``
/ ``ambiguous``) instead of guessing.  The lexica and header alias sets below
are the extension points: a new genre is a new feature extractor plus a new
rule, not a new file-name branch.
"""

import csv
import hashlib
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from io import BytesIO, StringIO
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook

from .documents import DocumentError, read_paragraphs
from .identity import email_address


# ---------------------------------------------------------------------------
# Source taxonomy
# ---------------------------------------------------------------------------

OUTREACH_DRAFT = "outreach_draft"
MULTI_DRAFT_BUNDLE = "multi_draft_bundle"
APPLICANT_CV = "applicant_cv"
SCHOLAR_CV = "scholar_cv"
SUPERVISOR_MASTER = "supervisor_master"
TRACKING_SHEET = "tracking_sheet"
PROGRAM_REFERENCE = "program_reference"
BULK_IMPORT = "bulk_import"
PLANNING_DOCUMENT = "planning_document"
MAINTENANCE_LOG = "maintenance_log"
UNRELATED = "unrelated"
BUNDLE = "bundle"
UNKNOWN = "unknown"
AMBIGUOUS = "ambiguous"

#: Operational meaning of each type.  Only types that describe a sendable
#: message, a sendable batch or a person/task roster may create work.
TYPE_PROFILES = {
    OUTREACH_DRAFT: {
        "label": "Single supervisor outreach draft",
        "actionable": True,
        "description": "One letter addressed to one supervisor; can become one Preparation.",
    },
    MULTI_DRAFT_BUNDLE: {
        "label": "Multi-draft bundle",
        "actionable": True,
        "description": "One document containing several supervisor-specific letters; "
                       "it must be segmented rather than imported as one draft.",
    },
    BULK_IMPORT: {
        "label": "Structured outreach batch import",
        "actionable": True,
        "description": "Row-per-message table with recipient, subject, body, attachment "
                       "and schedule; creates one task per row.",
    },
    SUPERVISOR_MASTER: {
        "label": "Supervisor master list",
        "actionable": True,
        "description": "Rows identify supervisors, institutions and recipient addresses.",
    },
    APPLICANT_CV: {
        "label": "Applicant / student CV",
        "actionable": True,
        "description": "An applicant's own CV; an attachment candidate for the current student, "
                       "never auto-bound without the role evidence below.",
    },
    SCHOLAR_CV: {
        "label": "Scholar / faculty CV",
        "actionable": False,
        "description": "A supervisor's or scholar's CV; reference material, not a student attachment.",
    },
    TRACKING_SHEET: {
        "label": "Outreach tracking / template sheet",
        "actionable": False,
        "description": "Workflow status sheet or fill-in template; it tracks outreach but does "
                       "not identify send recipients by itself.",
    },
    PROGRAM_REFERENCE: {
        "label": "Program research / reference workbook",
        "actionable": False,
        "description": "Programs, requirements and deadlines; planning data, not a recipient roster.",
    },
    PLANNING_DOCUMENT: {
        "label": "Application planning document",
        "actionable": False,
        "description": "Period-headed application timeline; not a letter and not an attachment.",
    },
    MAINTENANCE_LOG: {
        "label": "Mail maintenance / log document",
        "actionable": False,
        "description": "Operational catalogue of mail and records; it references supervisors "
                       "without containing letters.",
    },
    UNRELATED: {
        "label": "Unrelated source",
        "actionable": False,
        "description": "Content domain is outside research outreach; no SmartMail role.",
    },
    BUNDLE: {
        "label": "Mixed source bundle",
        "actionable": False,
        "description": "Archive containing members of several types; inspect members individually.",
    },
    UNKNOWN: {
        "label": "Unrecognized source",
        "actionable": False,
        "description": "Insufficient structural evidence; held unresolved for operator review.",
    },
    AMBIGUOUS: {
        "label": "Ambiguous source",
        "actionable": False,
        "description": "Two classifications are equally supported; operator resolution required.",
    },
}

HIGH = "high"
MEDIUM = "medium"
LOW = "low"


class RecognitionError(ValueError):
    """The bytes cannot even be read as a recognizable container."""


# ---------------------------------------------------------------------------
# Shared lexical primitives
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://\S+|(?:arxiv|doi)\.org/\S+", re.I)
PHONE_RE = re.compile(r"\+?\d[\d ()\-]{7,}\d")

# Letter schema moves (Swales-style move analysis applied to recruitment mail).
SALUTATION_RE = re.compile(
    r"^(?:Dear|Hi|Hello|尊敬的)\s+"
    r"(?P<title>Professor|Prof\.?|Dr\.?|Mr\.?|Ms\.?|Mrs\.?|Miss|Sir|Madam|老师|教授)?\s*"
    r"(?P<name>[A-Z][A-Za-z'’`.\-]*(?:\s+[A-Z][A-Za-z'’`.\-]*)?|[一-龥]{2,4})\s*[:,，]?\s*$"
)
SIGNOFF_RE = re.compile(
    r"^(?:Yours sincerely|Yours faithfully|Best regards|Kind regards|Warm regards|"
    r"Best wishes|Sincerely(?: yours)?|Regards|Cheers|顺祝|此致)\b",
    re.I,
)
SUBJECT_RE = re.compile(r"^(?:Subject|主题)\s*[:：]\s*(?P<value>.+)$", re.I)
RECIPIENT_LINE_RE = re.compile(r"^(?:Email|邮箱|收件人)\s*[:：]\s*(?P<value>\S.*?)$", re.I)
SELF_INTRODUCTION_RE = re.compile(
    r"\b(?:I am|I'm|My name is)\s+"
    r"(?P<name>[A-Z][A-Za-z'’\-]+(?:\s+[A-Z][A-Za-z'’\-]+){0,3})"
)
OPENING_RE = re.compile(r"I hope this email finds you well", re.I)
PURPOSE_RE = re.compile(
    r"(?:I am writing to|writing to (?:express|inquire|ask|apply)|"
    r"apply(?:ing)? for (?:the |a )?(?:PhD|Ph\.D\.|doctoral|graduate|Master|MSc|MPhil)|"
    r"PhD programs? for (?:the )?(?:Fall|Spring|Autumn)|"
    r"express my (?:interest|enthusiasm))",
    re.I,
)
ADDRESSEE_WORK_RE = re.compile(
    r"\byour (?:recent |co-authored |latest )?"
    r"(?:article|work|paper|research|group|lab|publication|study|thesis)\b",
    re.I,
)
ATTACH_CV_RE = re.compile(
    r"(?:I(?:'ve| have)\s+attached\s+(?:my|the)\s+CV|My CV is attached|"
    r"CV (?:is )?attached for|attached my CV)",
    re.I,
)
NAME_HEADING_RE = re.compile(
    r"^(?:#{1,6}\s*)?(?:\d{1,2}[.、)]\s*)?"
    r"(?P<name>[A-Z][A-Za-z'’.\-]+(?:\s+[A-Z][A-Za-z'’.\-]+){0,2}"
    r"(?:\s*[（(][一-龥A-Za-z·.\- ]+[)）])?"
    r"|[一-龥]{2,4}(?:\s*[（(][一-龥A-Za-z·.\- ]+[)）])?)"
    r"\s*[—–-]\s*(?P<tail>.+?)\s*$"
)
SECTION_NUMBER_RE = re.compile(r"^\d{1,2}[.、)]?$")
ENVELOPE_EMAIL_RE = re.compile(r"(?:📧|✉|Email|邮箱)\s*[:：]?\s*([A-Za-z0-9._%+\-]+@\S+)?")

# CV schema.  Membership matching (case-insensitive, colon stripped) keeps
# short capitalized body sentences from being read as headings.
CV_HEADINGS = {
    "education", "research interests", "research experience", "publications",
    "manuscripts in preparation", "professional and teaching experience",
    "professional experience", "work experience", "employment", "internships",
    "teaching experience", "teaching", "technical skills", "skills",
    "awards and distinctions", "awards", "honors and awards", "honors",
    "fellowships", "funding", "grants", "academic appointments",
    "presentations", "conferences", "service", "academic service",
    "references", "languages", "certifications", "projects", "patents",
    "contact", "career", "education background",
}
# Headings that presuppose an established scholarly career rather than an
# application in progress.
SCHOLAR_HEADINGS = {
    "academic appointments", "funding", "grants", "teaching experience",
    "teaching", "references", "academic service", "service",
}
FACULTY_TITLE_RE = re.compile(
    r"\b(?:Presidential Frontier Faculty\s+)?"
    r"(?:Assistant|Associate|Full|Distinguished|Tenured?|Visiting|Adjunct)?\s*"
    r"Professor\b|\bSenior Lecturer\b|\bLecturer\b",
    re.I,
)
MONEY_RE = re.compile(r"[$€£￥]\s?[\d,]{4,}|\d{2,3}(?:,\d{3})+\s*(?:USD|EUR|GBP|RMB)?")
PI_RE = re.compile(r"\bPI\b|\bPrincipal Investigator\b", re.I)

# Planning / timeline schema.
PERIOD_HEADER_RE = re.compile(
    r"20\d{2}\s*年\s*\d{1,2}\s*月|"           # 2027 年 3 月
    r"20\d{2}\s*[.\-/]\s*\d{1,2}\s*[-–—~～至]\s*(?:20\d{2}\s*[.\-/年])?"  # 2027.3 - 2027.6
)
TIMELINE_TITLE_RE = re.compile(
    r"(?:时间规划|时间轴|时间线|申请规划|规划\b|timeline|time\s*plan|planning\b)", re.I
)
BULLET_RE = re.compile(r"^[•▪◦▶✦*]\s*|^[-–]\s+\S")
PHASE_MARKER_RE = re.compile(r"^[◆◇※★]")

# Maintenance / log schema.
LOG_NAV_MARKERS = ("📌", "👤", "总览", "维护", "日志", "打开邮件", "打开学生页", "打开主页")
LOG_CATALOGUE_LABELS = ("导师", "学校", "邮件", "作品", "链接", "邮件数", "定位")

# Workbook header semantic fields.  Exact, case-folded membership: compound
# labels such as 导师筛选 ("supervisor screening", a status column) must not
# match 导师 (a person column).
MASTER_INSTITUTION = {"大学", "学校", "院校", "institution", "university", "school",
                      "university name", "school name", "university/institution"}
MASTER_SUPERVISOR = {"导师", "导师姓名", "supervisor", "supervisor name", "professor",
                     "advisor", "supervisor full name", "name"}
MASTER_ADDRESS = {"邮箱📮", "邮箱", "电子邮箱", "email", "e-mail", "email address",
                  "e-mail address", "contact email", "mail"}
PROGRAM_FIELDS = {
    "项目名称", "学位类型", "学制", "培养模式", "英语要求", "学术要求", "项目方向简介",
    "截止说明", "截止日期", "项目主页", "其他材料/前置", "国家/地区", "项目方向",
    "program", "program name", "degree", "degree type", "duration",
    "english requirement", "language requirement", "deadline", "application deadline",
    "entry requirement",
}
WORKFLOW_FIELDS = {
    "套磁", "跟进", "状态", "导师筛选", "筛选", "优先级", "邮件状态", "回复状态",
    "是否回复", "已发送", "发送状态", "下一步", "outreach priority", "priority",
    "priority label", "status", "follow up", "follow-up", "next step", "replied",
}
BULK_RECIPIENT = {"收件人", "收件邮箱", "recipient", "recipient email", "to", "email"}
BULK_SUBJECT = {"主题", "邮件主题", "subject", "subject line", "title"}
BULK_BODY = {"正文", "邮件正文", "body", "content", "message", "message body"}
BULK_SCHEDULE = {"定时时间", "发送时间", "计划发送时间", "scheduled time", "scheduled at",
                 "send time", "planned send time"}
BULK_ATTACHMENT = {"附件", "附件名", "attachment", "attachments", "attachment name"}
BULK_ID = {"编号", "序号", "id", "no", "#", "number"}

PLACEHOLDER_RE = re.compile(r"【AI[^】]*】|\[AI[^\]]*\]|Need Verification|Replace the placeholders", re.I)
INSTRUCTION_SHEET_RE = re.compile(r"(?:指令|说明|instruction|guide|template|模板)", re.I)
COPY_READY_INSTRUCTION_RE = re.compile(r"(?:Copy-ready\s+Professional\s+Instruction|使用指令|使用前输入)", re.I)

# Out-of-domain (outreach-irrelevant) evidence.
LEGAL_ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百千零两0-9]+条|Article\s+\d+")
TRANSLATION_HEADER_RE = re.compile(
    r"chinese[_\s]?source|english[_\s]?translation|collocation|translation marked", re.I
)
EDUCATION_DOMAIN_RE = re.compile(
    r"导师|大学|学校|院校|申请|套磁|奖学金|邮箱|项目|学位|录取|PhD|Ph\.D|supervisor|"
    r"professor|university|application|scholarship|admission|program(?:me)?|outreach|"
    r"research\s+interest|CV|硕士|本科|雅思|IELTS|EOI",
    re.I,
)

SCHEDULE_VALUE_RE = re.compile(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}[\s T]\d{1,2}:\d{2}")
ATTACHMENT_VALUE_RE = re.compile(r"^[\w][\w\-. ()（）]+\.(?:pdf|docx?|xlsx?|zip|png|jpg|jpeg)$", re.I)

MAX_SHEET_ROWS = 5000
MAX_CELL_CHARS = 500


# ---------------------------------------------------------------------------
# Result construction
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    """One fired structural observation; ``supports`` names candidate types."""

    reason: str
    supports: str
    weight: int = 1
    caution: bool = False


@dataclass
class _Candidate:
    type: str
    signals: list[Signal] = field(default_factory=list)

    @property
    def score(self) -> int:
        return sum(s.weight for s in self.signals if not s.caution)

    @property
    def cautions(self) -> list[Signal]:
        return [s for s in self.signals if s.caution]


def _result(name, fmt, source_type, confidence, reasons, cautions,
            evidence, identities=None, segments=None, alternatives=None,
            sha256="", extra=None):
    profile = TYPE_PROFILES[source_type]
    result = {
        "name": name,
        "format": fmt,
        "type": source_type,
        "label": profile["label"],
        "confidence": confidence,
        "actionable": profile["actionable"],
        "reasons": reasons,
        "cautions": cautions,
        "evidence": evidence,
        "identities": identities or {},
        "segments": segments or [],
        "alternatives": alternatives or [],
        "sha256": sha256,
    }
    if extra:
        result.update(extra)
    return result


def _adjudicate(name, fmt, candidates, evidence, *, sha256="", identities=None,
                segments=None, unknown_reason=None):
    """Pick one candidate or return ambiguous/unknown; never force a match."""
    scored = sorted((c for c in candidates if c.score > 0),
                    key=lambda c: c.score, reverse=True)
    if not scored:
        return _result(
            name, fmt, UNKNOWN, LOW,
            [], [unknown_reason or "No supported structural schema was observed."],
            evidence, identities, segments, sha256=sha256)
    best = scored[0]
    reasons = [s.reason for s in best.signals if not s.caution]
    cautions = [s.reason for s in best.signals if s.caution]
    alternatives = [{"type": c.type, "score": c.score} for c in scored[1:]]
    if len(scored) > 1 and scored[1].score >= best.score:
        tied = [c for c in scored if c.score == best.score]
        return _result(
            name, fmt, AMBIGUOUS, LOW,
            reasons,
            [f"Equally supported types: {', '.join(sorted(c.type for c in tied))}."],
            evidence, identities, segments,
            alternatives=[{"type": c.type, "score": c.score} for c in scored],
            sha256=sha256)
    if len(scored) > 1 and scored[1].score >= best.score - 1 and best.score < 3:
        cautions.append(
            f"Competing type '{scored[1].type}' is nearly as supported "
            f"({scored[1].score} vs {best.score}).")
        confidence = MEDIUM
    else:
        confidence = HIGH if best.score >= 3 else MEDIUM
    return _result(
        name, fmt, best.type, confidence, reasons, cautions, evidence,
        identities, segments, alternatives=alternatives, sha256=sha256)


# ---------------------------------------------------------------------------
# Container extraction
# ---------------------------------------------------------------------------

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _container_kind(data: bytes) -> str:
    try:
        with ZipFile(BytesIO(data)) as archive:
            members = set(archive.namelist())
    except (BadZipFile, OSError):
        return ""
    if "word/document.xml" in members:
        return "docx"
    if "xl/workbook.xml" in members:
        return "xlsx"
    return "zip"


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def recognize_bytes(name: str, data: bytes) -> dict:
    """Classify one in-memory source from its structural evidence."""
    digest = _sha(data)
    suffix = PurePosixPath(name).suffix.lower()
    kind = _container_kind(data)
    if kind == "docx" or (suffix == ".docx" and kind in ("docx", "zip")):
        if kind != "docx":
            return _unreadable(name, "docx", digest, "container has no word/document.xml part")
        return _recognize_docx(name, data, digest)
    if kind == "xlsx" or (suffix == ".xlsx" and kind in ("xlsx", "zip")):
        if kind != "xlsx":
            return _unreadable(name, "xlsx", digest, "container has no xl/workbook.xml part")
        return _recognize_xlsx(name, data, digest)
    if kind == "zip":
        return _recognize_zip(name, data, digest)
    if suffix == ".csv":
        return _recognize_csv(name, data, digest)
    return _result(
        name, "unsupported", UNKNOWN, LOW, [],
        [f"Unsupported container '{suffix or 'no extension'}'."],
        {"size_bytes": len(data)}, sha256=digest)


def _unreadable(name, fmt, digest, detail):
    return _result(
        name, fmt, UNKNOWN, LOW, [],
        [f"Unreadable {fmt} container: {detail}."],
        {}, sha256=digest)


def recognize_file(path: str | Path) -> dict:
    path = Path(path)
    return recognize_bytes(path.name, path.read_bytes())


# ---------------------------------------------------------------------------
# DOCX feature extraction and rules
# ---------------------------------------------------------------------------

@dataclass
class _DocxFeatures:
    lines: list[str]
    salutations: list[tuple[int, str, str]]          # (index, title, addressee)
    signoffs: list[int]
    subjects: list[tuple[int, str]]
    recipient_lines: list[tuple[int, str]]
    self_introductions: list[tuple[int, str]]
    signers: list[tuple[int, str]]
    envelope_emails: list[tuple[int, str]]
    headings: set[str]
    opening: int
    purpose: int
    addressee_work: int
    attach_cv: int
    contact_lines: int
    period_headers: list[str]
    timeline_title: bool
    bullets: int
    phase_markers: int
    log_nav: list[str]
    log_label_hits: dict[str, int]
    urls: int
    money: int
    pi: int
    faculty_lines: list[str]
    emails: list[str]


def _looks_like_name(text: str) -> bool:
    # Drop quoted nicknames such as 'Peizhu “Pam” Qian'.
    text = re.sub(r"[“\"'][^“”\"]{1,20}[”\"']", " ", text).strip(" .,;:")
    text = re.sub(r"\s+", " ", text)
    if re.fullmatch(r"[A-Z][A-Za-z'’`.\-]+(?:\s+[A-Z][A-Za-z'’`.\-]+){0,3}", text):
        return len(text) <= 40
    return bool(re.fullmatch(r"[一-龥]{2,4}", text))


def _extract_docx(lines: list[str]) -> _DocxFeatures:
    salutations: list[tuple[int, str, str]] = []
    signoffs: list[int] = []
    subjects: list[tuple[int, str]] = []
    recipient_lines: list[tuple[int, str]] = []
    self_introductions: list[tuple[int, str]] = []
    signers: list[tuple[int, str]] = []
    envelope_emails: list[tuple[int, str]] = []
    headings: set[str] = set()
    period_headers: list[str] = []
    log_nav: list[str] = []
    log_label_hits: dict[str, int] = {}
    faculty_lines: list[str] = []

    joined = "\n".join(lines)
    opening = len(OPENING_RE.findall(joined))
    purpose = len(PURPOSE_RE.findall(joined))
    addressee_work = len(ADDRESSEE_WORK_RE.findall(joined))
    attach_cv = len(ATTACH_CV_RE.findall(joined))
    urls = len(URL_RE.findall(joined))
    money = len(MONEY_RE.findall(joined))
    pi = len(PI_RE.findall(joined))
    bullets = sum(1 for line in lines if BULLET_RE.match(line))
    phase_markers = sum(1 for line in lines if PHASE_MARKER_RE.match(line))

    for i, line in enumerate(lines):
        if match := SALUTATION_RE.match(line):
            salutations.append((i, (match.group("title") or "").strip(" ."), match.group("name")))
        if SIGNOFF_RE.match(line):
            signoffs.append(i)
            for after in lines[i + 1:i + 3]:
                if _looks_like_name(after):
                    signers.append((i, after.strip()))
                    break
        if match := SUBJECT_RE.match(line):
            subjects.append((i, match.group("value").strip()))
        if match := RECIPIENT_LINE_RE.match(line):
            recipient_lines.append((i, match.group("value").strip()))
        if ENVELOPE_EMAIL_RE.search(line):
            embedded = EMAIL_RE.search(line)
            if embedded:
                envelope_emails.append((i, embedded.group(0)))
        for match in SELF_INTRODUCTION_RE.finditer(line):
            self_introductions.append((i, match.group("name")))
        key = line.strip(":： *•▪◦▶").casefold()
        if key in CV_HEADINGS and len(line) <= 45:
            headings.add(key)
        if PERIOD_HEADER_RE.search(line) and len(line) <= 45:
            period_headers.append(line)
        for marker in LOG_NAV_MARKERS:
            if marker in line and marker not in log_nav:
                log_nav.append(marker)
        for label in LOG_CATALOGUE_LABELS:
            if line.strip() == label:
                log_label_hits[label] = log_label_hits.get(label, 0) + 1
        if len(line) <= 90 and FACULTY_TITLE_RE.search(line) and not SALUTATION_RE.match(line):
            faculty_lines.append(line)

    contact_zone = "\n".join(lines[:10])
    contact_lines = sum(bool(pattern.search(contact_zone)) for pattern in (
        EMAIL_RE, PHONE_RE,
        re.compile(r"linkedin|google scholar|researchgate|github|个人主页", re.I),
        re.compile(r"https?://|www\."),
        re.compile(r"[一-龥]{2,}(?:市|省|中国)|,\s*[A-Z][a-z]+(?:\s*,\s*[A-Z][a-z]+)?$"),
    ))
    timeline_title = any(TIMELINE_TITLE_RE.search(line) for line in lines[:3])

    return _DocxFeatures(
        lines=lines, salutations=salutations, signoffs=signoffs, subjects=subjects,
        recipient_lines=recipient_lines, self_introductions=self_introductions,
        signers=signers, envelope_emails=envelope_emails, headings=headings,
        opening=opening, purpose=purpose, addressee_work=addressee_work,
        attach_cv=attach_cv, contact_lines=contact_lines, period_headers=period_headers,
        timeline_title=timeline_title, bullets=bullets, phase_markers=phase_markers,
        log_nav=log_nav, log_label_hits=log_label_hits, urls=urls, money=money,
        pi=pi, faculty_lines=faculty_lines, emails=sorted(set(EMAIL_RE.findall(joined))))


def _letter_move_count(features: _DocxFeatures) -> int:
    """Distinct interpersonal moves realised in the text (planes 2 and 4)."""
    moves = 0
    if features.self_introductions:
        moves += 1
    if features.opening:
        moves += 1
    if features.purpose:
        moves += 1
    if features.addressee_work:
        moves += 1
    if features.attach_cv:
        moves += 1
    if features.subjects:
        moves += 1
    return moves


def _segment_letters(lines, features: _DocxFeatures) -> list[dict]:
    """Split a multi-letter document into supervisor-addressing segments.

    A segment starts at each salutation.  Its supervisor/institution heading,
    subject and envelope email are anchored to surrounding structural lines;
    an email marker placed immediately before the *next* heading belongs to
    that next section (the observed catalogue layout)."""
    anchors = [index for index, _t, _n in features.salutations]
    raw_segments: list[dict] = []
    for position, start in enumerate(anchors):
        end = anchors[position + 1] if position + 1 < len(anchors) else len(lines)
        title, addressee = features.salutations[position][1:]
        signer = next((name for index, name in features.signers
                       if start <= index < end), "")
        subject = next((value for index, value in reversed(features.subjects)
                        if start - 4 <= index < start), "")
        heading_name = institution = ""
        heading_index = None
        heading_emails: list[str] = []
        for previous in range(max(0, start - 5), start):
            candidate = lines[previous].strip()
            if SECTION_NUMBER_RE.match(candidate) or SUBJECT_RE.match(candidate):
                continue
            match = NAME_HEADING_RE.match(candidate)
            if match:
                heading_name = match.group("name").strip()
                tail = match.group("tail").strip()
                heading_emails = EMAIL_RE.findall(tail)
                institution = "" if heading_emails else tail
                heading_index = previous
                break
        supervisor = heading_name or addressee
        raw_segments.append({
            "index": position + 1,
            "supervisor": supervisor,
            "salutation_name": addressee,
            "title": title,
            "institution": institution,
            "subject": subject,
            "signer": signer,
            "emails": heading_emails,
            "start": start,
            "heading_index": heading_index,
        })
    # Email markers are anchored to structure, not to text position: a marker
    # immediately followed by a section heading introduces that next section;
    # any other marker belongs to the section currently open at its paragraph.
    for marker_index, address in features.envelope_emails:
        target = next(
            (segment for segment in raw_segments
             if segment["heading_index"] is not None
             and marker_index < segment["heading_index"] <= marker_index + 4),
            None)
        if target is None:
            target = next((segment for segment in reversed(raw_segments)
                           if segment["start"] <= marker_index), None)
        if target is not None and address not in target["emails"]:
            target["emails"].append(address)
    for segment in raw_segments:
        del segment["start"]
        del segment["heading_index"]
    return raw_segments


def _shared_student(features: _DocxFeatures, segments) -> str:
    names = [segment["signer"] for segment in segments if segment.get("signer")]
    names += [name for _i, name in features.self_introductions]
    if not names:
        return ""
    return max(set(names), key=names.count)


def _recognize_docx(name, data, digest):
    try:
        paragraphs = read_paragraphs(data)
    except DocumentError as error:
        return _unreadable(name, "docx", digest, str(error))
    lines = [p.strip() for p in paragraphs if p.strip()]
    if not lines:
        return _result(name, "docx", UNKNOWN, LOW, ["Document contains no text."],
                       ["Empty document; no genre schema can be assessed."],
                       {"nonempty_paragraphs": 0}, sha256=digest)
    features = _extract_docx(lines)
    evidence = {
        "nonempty_paragraphs": len(lines),
        "salutations": len(features.salutations),
        "signoffs": len(features.signoffs),
        "letter_moves": _letter_move_count(features),
        "cv_headings": sorted(features.headings),
        "period_headers": len(features.period_headers),
        "log_markers": features.log_nav,
        "urls": features.urls,
        "emails": len(features.emails),
    }

    # Letter family -- interpersonal envelope is the hard gate.  Topic words
    # about mail or supervisors can never substitute for an addressee schema.
    if features.salutations:
        return _recognize_letter_family(name, lines, features, evidence, digest)

    # Non-letter genres: CV, catalogue/log, timeline.  Each requires its own
    # positive schema; otherwise the file stays unresolved.
    candidates: list[_Candidate] = []

    heading_count = len(features.headings)
    if heading_count >= 3 or (heading_count >= 2 and features.contact_lines >= 2):
        cv = _Candidate(APPLICANT_CV)
        cv.signals.append(Signal(
            f"{heading_count} CV section headings in canonical position: "
            f"{', '.join(sorted(features.headings)[:6])}", APPLICANT_CV, 3))
        if features.contact_lines >= 2:
            cv.signals.append(Signal(
                f"{features.contact_lines} contact channels in the opening block "
                "(email/phone/profile/location)", APPLICANT_CV))
        cv.signals.append(Signal(
            "Fragment-style dated section layout without any letter salutation or sign-off",
            APPLICANT_CV))
        _classify_cv_role(cv, features)
        candidates.append(cv)

    if len(set(features.log_nav)) >= 2 and features.urls >= 3:
        log = _Candidate(MAINTENANCE_LOG)
        log.signals.append(Signal(
            f"Navigation/overview markers {sorted(set(features.log_nav))} "
            "frame the document as an operational console/log", MAINTENANCE_LOG, 2))
        log.signals.append(Signal(
            f"{features.urls} record links (doi/arxiv/http) in repeating catalogue rows",
            MAINTENANCE_LOG))
        recurring = [label for label, count in features.log_label_hits.items() if count >= 2]
        if recurring:
            log.signals.append(Signal(
                f"Repeated catalogue field labels {recurring} describe rows of people records",
                MAINTENANCE_LOG))
        log.signals.append(Signal(
            "Zero salutations and sign-offs: the document references mail but "
            "contains no letter discourse", MAINTENANCE_LOG))
        candidates.append(log)

    if len(features.period_headers) >= 3 and (features.timeline_title or features.bullets >= 3):
        planning = _Candidate(PLANNING_DOCUMENT)
        planning.signals.append(Signal(
            f"{len(features.period_headers)} repeated period headers such as "
            f"'{features.period_headers[0]}' form a timeline schema", PLANNING_DOCUMENT, 2))
        if features.timeline_title:
            planning.signals.append(Signal(
                "The opening title declares a planning/timeline document "
                f"('{lines[0][:50]}')", PLANNING_DOCUMENT))
        planning.signals.append(Signal(
            f"{features.bullets} bulleted phase tasks under the period sections",
            PLANNING_DOCUMENT))
        planning.signals.append(Signal(
            "Zero salutations/sign-offs: future-directed planning text, not a letter",
            PLANNING_DOCUMENT))
        candidates.append(planning)

    identities = _cv_identities(lines, features) if features.headings else {}
    return _adjudicate(
        name, "docx", candidates, evidence,
        identities=identities, sha256=digest,
        unknown_reason="No letter envelope, CV schema, log schema or timeline schema was observed.")


def _classify_cv_role(cv: _Candidate, features: _DocxFeatures) -> None:
    """Distinguish document *type* (it is a CV in either case) from social role.

    Applicant CV and faculty CV share the CV schema; career-stage markers
    decide whether it may bind to the current student."""
    scholar_categories = 0
    scholar_headings = features.headings & SCHOLAR_HEADINGS
    if scholar_headings:
        scholar_categories += 1
        cv.signals.append(Signal(
            f"Career-stage headings present: {sorted(scholar_headings)}",
            SCHOLAR_CV, 2))
    if features.money >= 2 or features.pi >= 2:
        scholar_categories += 1
        cv.signals.append(Signal(
            f"{features.money} grant-amount mentions and {features.pi} PI/"
            "Principal-Investigator roles describe an awarded scholar", SCHOLAR_CV, 2))
    if any(FACULTY_TITLE_RE.search(line) and re.search(r"present|20\d{2}\s*[-–]", line, re.I)
           for line in features.faculty_lines):
        scholar_categories += 1
        cv.signals.append(Signal(
            "A current faculty appointment line appears in the appointments block",
            SCHOLAR_CV))
    if scholar_categories >= 2:
        cv.type = SCHOLAR_CV
        cv.signals.append(Signal(
            "Scholar role evidence means this CV must not auto-bind as a student attachment",
            SCHOLAR_CV))
    elif scholar_categories == 1:
        cv.signals.append(Signal(
            "Applicant vs scholar role is not fully resolved; binding requires confirmation",
            APPLICANT_CV, caution=True))


def _cv_identities(lines, features: _DocxFeatures) -> dict:
    name = ""
    for line in lines[:3]:
        if _looks_like_name(line):
            name = re.sub(r"[“\"'][^“”\"]{1,20}[”\"']", " ", line).strip()
            name = re.sub(r"\s+", " ", name)
            break
    opening_text = "\n".join(lines[:10])
    opening_email = EMAIL_RE.search(opening_text)
    email = opening_email.group(0) if opening_email else (features.emails[0] if features.emails else "")
    role = "scholar" if (features.headings & SCHOLAR_HEADINGS or
                         features.money >= 2 or features.pi >= 2) else "applicant"
    return {"student": name if role == "applicant" else "",
            "person": name, "cv_role": role, "contact_email": email}


def _recognize_letter_family(name, lines, features, evidence, digest):
    salute_count = len(features.salutations)
    signoff_count = len(features.signoffs)
    moves = _letter_move_count(features)

    if salute_count >= 2:
        segments = _segment_letters(lines, features)
        missing_email = [s["index"] for s in segments if not s["emails"]]
        bundle = _Candidate(MULTI_DRAFT_BUNDLE)
        bundle.signals.append(Signal(
            f"{salute_count} salutations and {signoff_count} sign-offs repeat the "
            "complete letter envelope inside one document", MULTI_DRAFT_BUNDLE, 3))
        student = _shared_student(features, segments)
        if student:
            bundle.signals.append(Signal(
                f"The same sender '{student}' signs {len(segments)} sections; "
                "each section addresses a different supervisor", MULTI_DRAFT_BUNDLE, 2))
        if features.subjects:
            bundle.signals.append(Signal(
                f"{len(features.subjects)} section subject lines", MULTI_DRAFT_BUNDLE))
        if missing_email:
            bundle.signals.append(Signal(
                f"{len(missing_email)} of {len(segments)} sections have no recipient "
                "address and must stay unresolved", MULTI_DRAFT_BUNDLE, caution=True))
        identities = {"student": student}
        reasons = [s.reason for s in bundle.signals if not s.caution]
        cautions = [s.reason for s in bundle.signals if s.caution]
        evidence["segments"] = len(segments)
        return _result(name, "docx", MULTI_DRAFT_BUNDLE, HIGH, reasons, cautions,
                       evidence, identities=identities, segments=segments, sha256=digest)

    draft = _Candidate(OUTREACH_DRAFT)
    _t, addressee = features.salutations[0][1:]
    draft.signals.append(Signal(
        f"Letter envelope: salutation '{lines[features.salutations[0][0]][:40]}' "
        f"plus {signoff_count} sign-off", OUTREACH_DRAFT, 2))
    if features.self_introductions:
        draft.signals.append(Signal(
            f"Sender self-introduces as '{features.self_introductions[0][1]}' "
            "(student identity from discourse, not file name)", OUTREACH_DRAFT))
    if features.opening:
        draft.signals.append(Signal("Goodwill opener 'I hope this email finds you well'", OUTREACH_DRAFT))
    if features.purpose:
        draft.signals.append(Signal(
            f"{features.purpose} explicit application/purpose-of-writing statements", OUTREACH_DRAFT))
    if features.addressee_work:
        draft.signals.append(Signal(
            f"{features.addressee_work} references to the addressee's own work "
            "(I-to-you directed discourse)", OUTREACH_DRAFT))
    if features.attach_cv:
        draft.signals.append(Signal("The letter declares an attached CV", OUTREACH_DRAFT))

    recipient = ""
    if features.recipient_lines:
        candidate = features.recipient_lines[0][1].split()[0].strip()
        if email_address(candidate):
            recipient = candidate
            draft.signals.append(Signal(f"Explicit recipient declaration '{candidate}'", OUTREACH_DRAFT))
    elif features.emails:
        recipient = features.emails[0]
        draft.signals.append(Signal(f"Recipient address appears in the letter text: {recipient}", OUTREACH_DRAFT))
    if not recipient:
        draft.signals.append(Signal(
            "No recipient address in the document; supervisor name is known from the "
            "salutation but the task cannot be addressed yet", OUTREACH_DRAFT, caution=True))

    student = (features.self_introductions[0][1] if features.self_introductions
               else (features.signers[0][1] if features.signers else ""))
    if features.signoffs and not features.self_introductions:
        draft.signals.append(Signal(
            f"Sender inferred from sign-off line '{features.signers[0][1] if features.signers else ''}'",
            OUTREACH_DRAFT))
    subject = features.subjects[0][1] if features.subjects else ""
    if not subject:
        draft.signals.append(Signal("No subject line in the document", OUTREACH_DRAFT, caution=True))

    reasons = [s.reason for s in draft.signals if not s.caution]
    cautions = [s.reason for s in draft.signals if s.caution]
    # High confidence requires both halves of the interpersonal envelope
    # (opening schema AND closing schema); a truncated letter stays provisional.
    complete_envelope = bool(features.signoffs)
    confidence = HIGH if complete_envelope and moves >= 2 else MEDIUM
    identities = {
        "student": student,
        "addressee": {"name": addressee, "email": recipient,
                      "source": "recipient_line" if features.recipient_lines else
                                "body" if recipient else "salutation_only"},
        "subject": subject,
    }
    return _result(name, "docx", OUTREACH_DRAFT, confidence, reasons, cautions,
                   evidence, identities=identities, sha256=digest)


# ---------------------------------------------------------------------------
# XLSX feature extraction and rules
# ---------------------------------------------------------------------------

@dataclass
class _SheetFeatures:
    title: str
    rows: list[list[str]]
    header_row: int
    fields: dict[str, str]          # unique semantic field -> raw label
    program_labels: list[str]       # all program-schema header labels
    workflow_labels: list[str]      # all workflow-schema header labels
    data_rows: int
    emails: list[str]
    urls: int
    placeholders: int
    instruction_text: bool
    banner_title: bool


def _normalized_rows(data: bytes):
    workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    try:
        for worksheet in workbook.worksheets:
            rows: list[list[str]] = []
            for row in worksheet.iter_rows(values_only=True):
                cells = ["" if value is None else str(value).strip()[:MAX_CELL_CHARS]
                         for value in row]
                rows.append(cells)
                if len(rows) >= MAX_SHEET_ROWS:
                    break
            yield worksheet.title, rows
    finally:
        workbook.close()


def _field_hits(labels: set[str], *alias_sets: set[str]) -> dict[str, str]:
    hits: dict[str, str] = {}
    for aliases in alias_sets:
        overlap = labels & aliases
        if overlap:
            label = sorted(overlap, key=len, reverse=True)[0]
            hits[label] = label
    return hits


def _extract_sheet(title: str, rows: list[list[str]]) -> _SheetFeatures:
    best_row, best_labels = -1, set()
    for index, row in enumerate(rows[:5]):
        labels = {cell.casefold() for cell in row if cell}
        recognized = labels & (
            MASTER_INSTITUTION | MASTER_SUPERVISOR | MASTER_ADDRESS
            | PROGRAM_FIELDS | WORKFLOW_FIELDS | BULK_RECIPIENT | BULK_SUBJECT
            | BULK_BODY | BULK_SCHEDULE | BULK_ATTACHMENT | BULK_ID)
        if len(recognized) > len(best_labels):
            best_row, best_labels = index, recognized
    fields: dict[str, str] = {}
    if best_row >= 0:
        header = {cell.casefold(): cell for cell in rows[best_row] if cell}
        for semantic, aliases in (
            ("institution", MASTER_INSTITUTION), ("supervisor", MASTER_SUPERVISOR),
            ("address", MASTER_ADDRESS), ("program", PROGRAM_FIELDS),
            ("workflow", WORKFLOW_FIELDS), ("recipient", BULK_RECIPIENT),
            ("subject", BULK_SUBJECT), ("body", BULK_BODY),
            ("schedule", BULK_SCHEDULE), ("attachment", BULK_ATTACHMENT),
            ("id", BULK_ID),
        ):
            for key, raw in header.items():
                if key in aliases:
                    fields[semantic] = raw
                    break
    program_labels = sorted(header[key] for key in best_labels & PROGRAM_FIELDS) if best_row >= 0 else []
    workflow_labels = sorted(header[key] for key in best_labels & WORKFLOW_FIELDS) if best_row >= 0 else []
    body_rows = rows[best_row + 1:] if best_row >= 0 else []
    nonempty = [row for row in body_rows if any(row)]
    flat = [cell for row in nonempty for cell in row if cell]
    emails = [cell for cell in flat if email_address(cell)]
    urls = sum(1 for cell in flat if URL_RE.search(cell))
    placeholders = sum(1 for cell in flat if PLACEHOLDER_RE.search(cell))
    instruction_text = any(COPY_READY_INSTRUCTION_RE.search(cell) for cell in flat)
    banner_title = (
        best_row >= 2
        and any(cell.strip() for cell in rows[0])
        and not any(cell.strip() for cell in rows[1 if best_row > 1 else 0]))
    return _SheetFeatures(
        title=title, rows=rows, header_row=best_row, fields=fields,
        program_labels=program_labels, workflow_labels=workflow_labels,
        data_rows=len(nonempty), emails=emails, urls=urls,
        placeholders=placeholders, instruction_text=instruction_text,
        banner_title=banner_title)


def _recognize_xlsx(name, data, digest):
    try:
        sheets = [_extract_sheet(title, rows) for title, rows in _normalized_rows(data)]
    except Exception as error:  # openpyxl raises a variety of parse errors
        return _unreadable(name, "xlsx", digest, str(error))
    populated = sum(
        1 for sheet in sheets
        if sheet.data_rows or any(any(row) for row in sheet.rows[:5]))
    if not populated:
        return _result(name, "xlsx", UNKNOWN, LOW, ["Workbook has no populated sheets."],
                       ["No header schema or data rows to classify."],
                       {"sheets": [s.title for s in sheets]}, sha256=digest)

    total_emails = sum(len(s.emails) for s in sheets)
    total_placeholders = sum(s.placeholders for s in sheets)
    instruction_sheet = any(
        s.instruction_text or INSTRUCTION_SHEET_RE.search(s.title) for s in sheets)
    evidence = {
        "sheets": [{"title": s.title, "header_row": s.header_row + 1 if s.header_row >= 0 else 0,
                    "data_rows": s.data_rows, "fields": s.fields,
                    "program_labels": s.program_labels, "workflow_labels": s.workflow_labels,
                    "emails": len(s.emails), "placeholders": s.placeholders,
                    "banner_title": s.banner_title} for s in sheets],
        "total_emails": total_emails, "total_placeholder_cells": total_placeholders,
    }
    identities = {}
    candidates: list[_Candidate] = []

    bulk_sheet = next((s for s in sheets
                       if {"recipient", "subject", "body"} <= set(s.fields)), None)
    if bulk_sheet:
        candidate = _Candidate(BULK_IMPORT)
        candidate.signals.append(Signal(
            f"Sheet '{bulk_sheet.title}' header row {bulk_sheet.header_row + 1} carries the "
            f"outgoing-mail envelope columns {sorted(bulk_sheet.fields)}", BULK_IMPORT, 3))
        candidate.signals.append(Signal(
            f"{bulk_sheet.data_rows} message rows under the envelope header", BULK_IMPORT, 2))
        candidates.append(candidate)

    master_sheet = next((s for s in sheets
                         if {"institution", "supervisor", "address"} <= set(s.fields)), None)
    if master_sheet and total_emails >= 1 and master_sheet.data_rows >= 1:
        program_veto = sum(1 for s in sheets if "program" in s.fields)
        workflow_veto = any("workflow" in s.fields for s in sheets)
        if program_veto == 0 and not workflow_veto and total_placeholders == 0:
            master = _Candidate(SUPERVISOR_MASTER)
            master.signals.append(Signal(
                f"Sheet '{master_sheet.title}' header row {master_sheet.header_row + 1} "
                f"has institution/supervisor/address columns "
                f"({master_sheet.fields['institution']!r}, "
                f"{master_sheet.fields['supervisor']!r}, {master_sheet.fields['address']!r})",
                SUPERVISOR_MASTER, 3))
            master.signals.append(Signal(
                f"{master_sheet.data_rows} supervisor rows; {total_emails} well-formed "
                "recipient addresses identify send targets", SUPERVISOR_MASTER, 2))
            if "profile" in master_sheet.fields:
                master.signals.append(Signal("Supervisor profile/URL column corroborates the roster",
                                             SUPERVISOR_MASTER))
            candidates.append(master)
            identities = {"row_count": master_sheet.data_rows,
                           "email_count": total_emails,
                           "sheet": master_sheet.title}

    workflow_sheets = [s for s in sheets if "workflow" in s.fields]
    if workflow_sheets or total_placeholders or instruction_sheet:
        tracking = _Candidate(TRACKING_SHEET)
        for sheet in workflow_sheets:
            tracking.signals.append(Signal(
                f"Sheet '{sheet.title}' carries workflow/status columns "
                f"{sheet.workflow_labels}: the row entity is a tracked outreach, "
                "not a freshly identified recipient",
                TRACKING_SHEET, 2))
        if total_placeholders:
            tracking.signals.append(Signal(
                f"{total_placeholders} fill-in instruction cells "
                "(【AI填写】/Need Verification) show this is a template, not data",
                TRACKING_SHEET, 2))
        if instruction_sheet:
            tracking.signals.append(Signal(
                "A dedicated instruction/usage sheet accompanies the template",
                TRACKING_SHEET))
        tracking.signals.append(Signal(
            f"{total_emails} recipient addresses across the workbook "
            "(workflow templates do not themselves establish send targets)",
            TRACKING_SHEET, caution=True))
        candidates.append(tracking)

    program_sheets = [s for s in sheets if len(s.program_labels) >= 2]
    if program_sheets and total_emails == 0:
        reference = _Candidate(PROGRAM_REFERENCE)
        strongest = max(program_sheets, key=lambda s: len(s.program_labels))
        reference.signals.append(Signal(
            f"Sheet '{strongest.title}' header row {strongest.header_row + 1} describes "
            f"programs ({strongest.data_rows} rows) with fields such as "
            f"{strongest.program_labels[:6]}",
            PROGRAM_REFERENCE, 3))
        reference.signals.append(Signal(
            f"{sum(s.urls for s in program_sheets)} program/institution URLs but zero email "
            "addresses: the row entity is a degree program, not a contactable person",
            PROGRAM_REFERENCE, 2))
        if all(s.banner_title for s in program_sheets):
            reference.signals.append(Signal(
                "A banner title row precedes the real header (reference-catalogue layout)",
                PROGRAM_REFERENCE))
        candidates.append(reference)

    if not candidates:
        unrelated = _unrelated_workbook(sheets)
        if unrelated:
            candidates.append(unrelated)

    return _adjudicate(
        name, "xlsx", candidates, evidence, identities=identities, sha256=digest,
        unknown_reason="Headers and rows match neither supervisor, workflow, program "
                       "nor outgoing-mail schemas.")


def _unrelated_workbook(sheets: list[_SheetFeatures]) -> _Candidate | None:
    """Positive out-of-domain evidence is required; an odd spreadsheet stays unknown."""
    signals: list[str] = []
    data_cells = 0
    education_hits = 0
    legal_rows = 0
    translation_headers = 0
    for sheet in sheets:
        for row in sheet.rows:
            for cell in row:
                if not cell:
                    continue
                data_cells += 1
                if EDUCATION_DOMAIN_RE.search(cell):
                    education_hits += 1
                if LEGAL_ARTICLE_RE.search(cell):
                    legal_rows += 1
        for row in sheet.rows[:5]:
            for cell in row:
                if TRANSLATION_HEADER_RE.search(cell):
                    translation_headers += 1
    unrelated = _Candidate(UNRELATED)
    if translation_headers:
        unrelated.signals.append(Signal(
            f"{translation_headers} bilingual/collocation research headers "
            "(Chinese_Source/English_Translation/Collocation)", UNRELATED, 3))
    if legal_rows >= 3:
        unrelated.signals.append(Signal(
            f"{legal_rows} statute-article references (第X条 / Article N) with parallel "
            "translation data indicate a legal-linguistics dataset", UNRELATED, 2))
    if data_cells >= 30 and education_hits / max(data_cells, 1) < 0.01:
        unrelated.signals.append(Signal(
            f"{data_cells} populated cells with virtually no education/outreach vocabulary "
            f"({education_hits} hits)", UNRELATED))
    if unrelated.score >= 3:
        unrelated.signals.append(Signal(
            "No supervisor, program, workflow or mail-envelope header schema is present",
            UNRELATED))
        return unrelated
    return None


# ---------------------------------------------------------------------------
# CSV rules
# ---------------------------------------------------------------------------

def _recognize_csv(name, data, digest):
    text = _decode_text(data)
    try:
        rows = list(csv.reader(StringIO(text)))
    except csv.Error as error:
        return _unreadable(name, "csv", digest, str(error))
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if len(rows) < 2:
        return _result(name, "csv", UNKNOWN, LOW, [],
                       ["CSV has fewer than a header plus one data row."],
                       {"rows": len(rows)}, sha256=digest)
    header = [cell.strip().casefold() for cell in rows[0]]
    fields: dict[str, int] = {}
    for semantic, aliases in (
        ("recipient", BULK_RECIPIENT), ("subject", BULK_SUBJECT),
        ("body", BULK_BODY), ("schedule", BULK_SCHEDULE),
        ("attachment", BULK_ATTACHMENT), ("id", BULK_ID),
    ):
        for index, label in enumerate(header):
            if label in aliases:
                fields[semantic] = index
                break
    body_rows = rows[1:]
    evidence = {"rows": len(body_rows), "columns": len(header),
                "header": rows[0], "fields": fields}

    if {"recipient", "subject", "body"} <= set(fields):
        recipient_col = fields["recipient"]
        body_col = fields["body"]
        recipients = [(row[recipient_col].strip() if recipient_col < len(row) else "")
                      for row in body_rows]
        valid = [value for value in recipients if email_address(value)]
        bodies = [row[body_col] if body_col < len(row) else "" for row in body_rows]

        def _opens_with_salutation(body: str) -> bool:
            first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
            return bool(SALUTATION_RE.match(first_line))

        saluted = sum(1 for body in bodies if _opens_with_salutation(body))
        average_body = sum(len(body) for body in bodies) / max(len(bodies), 1)
        email_ratio = len(valid) / len(recipients)
        bulk = _Candidate(BULK_IMPORT)
        bulk.signals.append(Signal(
            "Header carries the outgoing-mail envelope: recipient + subject + body columns"
            + (", plus attachment and schedule columns" if {"attachment", "schedule"} & set(fields) else ""),
            BULK_IMPORT, 3))
        bulk.signals.append(Signal(
            f"{len(valid)} of {len(recipients)} rows carry well-formed recipient addresses "
            f"({email_ratio:.0%})", BULK_IMPORT, 2))
        bulk.signals.append(Signal(
            f"{saluted} message bodies open with a personal salutation and average "
            f"{average_body:.0f} characters: each row is a complete letter", BULK_IMPORT, 2))
        missing = [i + 2 for i, value in enumerate(recipients) if not value]
        cautions = []
        if missing:
            cautions.append(Signal(
                f"{len(missing)} rows lack a recipient address "
                f"(first rows: {missing[:5]}); they cannot be scheduled",
                BULK_IMPORT, caution=True))
        schedules = attachments = []
        if "schedule" in fields:
            schedules = [row[fields["schedule"]] for row in body_rows
                         if fields["schedule"] < len(row)
                         and SCHEDULE_VALUE_RE.search(row[fields["schedule"]])]
            if len(schedules) < len(body_rows):
                cautions.append(Signal(
                    f"{len(body_rows) - len(schedules)} rows have no parseable scheduled time",
                    BULK_IMPORT, caution=True))
        if "attachment" in fields:
            attachments = sorted({row[fields["attachment"]].strip() for row in body_rows
                                  if fields["attachment"] < len(row)
                                  and ATTACHMENT_VALUE_RE.match(row[fields["attachment"]].strip())})
        reasons = [s.reason for s in bulk.signals]
        confidence = HIGH if email_ratio >= 0.5 and saluted >= max(1, len(body_rows) // 2) else MEDIUM
        identities = {
            "row_count": len(body_rows), "recipient_count": len(valid),
            "attachments": attachments,
            "scheduled_rows": len(schedules),
        }
        return _result(name, "csv", BULK_IMPORT, confidence, reasons,
                       [s.reason for s in cautions], evidence,
                       identities=identities, sha256=digest)

    return _result(
        name, "csv", UNKNOWN, MEDIUM, [],
        ["CSV header does not carry an outgoing-mail envelope "
         "(recipient/subject/body); records exports are not outreach batches."],
        evidence, sha256=digest)


# ---------------------------------------------------------------------------
# Bundles and collection-level relations
# ---------------------------------------------------------------------------

def _recognize_zip(name, data, digest):
    members: list[dict] = []
    try:
        with ZipFile(BytesIO(data)) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                member_name = item.filename.replace("\\", "/")
                if PurePosixPath(member_name).is_absolute() or ".." in PurePosixPath(member_name).parts:
                    continue
                if member_name.lower().endswith((".docx", ".xlsx", ".csv")):
                    members.append(recognize_bytes(PurePosixPath(member_name).name,
                                                   archive.read(item)))
    except (BadZipFile, OSError) as error:
        return _unreadable(name, "zip", digest, str(error))
    counts: dict[str, int] = {}
    for member in members:
        counts[member["type"]] = counts.get(member["type"], 0) + 1
    if not members:
        return _result(name, "zip", UNKNOWN, LOW, ["Archive contains no supported members."],
                       ["Only .docx, .xlsx and .csv members are recognized."],
                       {"members": len(members)}, sha256=digest)
    return _result(
        name, "zip", BUNDLE, MEDIUM,
        [f"{count} member(s) recognized as {source_type}"
         for source_type, count in sorted(counts.items())],
        [], {"member_count": len(members), "type_counts": counts},
        extra={"members": members})


def recognize_collection(members) -> dict:
    """Recognize many (name, data) sources and detect cross-source relations."""
    sources = [recognize_bytes(name, data) for name, data in members]
    return {"sources": sources, "relations": detect_relations(members, sources)}


def _normalized_text(data: bytes) -> str:
    try:
        paragraphs = read_paragraphs(data)
    except DocumentError:
        return ""
    return re.sub(r"\s+", "", "".join(paragraphs))


def _shared_filename_stem(name_a: str, name_b: str) -> str:
    """The long common prefix of stems after stripping known version suffixes."""
    stem_a = PurePosixPath(name_a).stem
    stem_b = PurePosixPath(name_b).stem
    prefix = []
    for char_a, char_b in zip(stem_a, stem_b):
        if char_a != char_b:
            break
        prefix.append(char_a)
    return "".join(prefix).strip(" -_（()")


def detect_relations(members, recognitions=None) -> list[dict]:
    """Exact duplicates and near-duplicate/version pairs among docx sources.

    Exact identity uses bytes hash.  Near-duplicates require the same opening
    title plus either high text similarity, or an explicit file-name version
    marker together with substantial content overlap -- heavily rewritten
    revisions still share title, topic and version markers.  Relations are
    reported, never silently collapsed."""
    by_name = {name: data for name, data in members}
    sources = recognitions or [recognize_bytes(name, data) for name, data in members]
    relations: list[dict] = []
    seen_hashes: dict[str, str] = {}
    docs = []
    for source in sources:
        name = source["name"]
        data = by_name.get(name, b"")
        if source["sha256"] in seen_hashes:
            relations.append({"a": seen_hashes[source["sha256"]], "b": name,
                              "relation": "exact_duplicate", "similarity": 1.0,
                              "basis": ["identical sha256 content hash"]})
            continue
        seen_hashes[source["sha256"]] = name
        if source["format"] == "docx" and data:
            try:
                first = next((p.strip() for p in read_paragraphs(data) if p.strip()), "")
            except DocumentError:
                first = ""
            docs.append((name, _normalized_text(data), first))
    version_marker = re.compile(
        r"(原版备份|原版|备份|副本|backup|copy|revised?|修订版|定稿|修改版|v\d+|\(\d+\)|（\d+）)", re.I)
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            name_a, text_a, first_a = docs[i]
            name_b, text_b, first_b = docs[j]
            if not first_a or first_a != first_b or len(first_a) < 10:
                continue
            if min(len(text_a), len(text_b)) < 80:
                continue
            ratio = SequenceMatcher(None, text_a[:20000], text_b[:20000]).ratio()

            def _bigrams(text):
                return {text[k:k + 2] for k in range(len(text) - 1)}

            grams_a, grams_b = _bigrams(text_a), _bigrams(text_b)
            containment = len(grams_a & grams_b) / min(len(grams_a), len(grams_b)) \
                if grams_a and grams_b else 0.0
            marker_hits = [token for token in (name_a, name_b) if version_marker.search(token)]
            shared_stem = _shared_filename_stem(name_a, name_b)
            explicit_version = bool(marker_hits) and len(shared_stem) >= 10
            if not ((ratio >= 0.72 and containment >= 0.6)
                    or (explicit_version and (ratio >= 0.25 or containment >= 0.35))):
                continue
            basis = [f"identical opening title '{first_a[:40]}'",
                     f"normalized text similarity {ratio:.2f} "
                     f"(shared-content containment {containment:.2f})"]
            if explicit_version:
                basis.append(f"version markers in file name: {sorted(set(marker_hits))} "
                             f"on shared stem '{shared_stem[:30]}'")
            relations.append({"a": name_a, "b": name_b,
                              "relation": "near_duplicate",
                              "similarity": round(ratio, 3),
                              "containment": round(containment, 3),
                              "basis": basis})
    return relations

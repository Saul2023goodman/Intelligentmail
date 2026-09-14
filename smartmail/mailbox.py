"""The mailbox adapter boundary for external execution and read-only observation.

Every external send goes through an adapter. The default adapter has no enabled
capability, so nothing leaves the machine until a capability is separately
verified. A controlled adapter demonstrates outcomes deterministically without
real sends; the 163.com browser adapter attaches through this same boundary.
"""

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


class MailboxCapabilityError(ValueError):
    """The requested external execution capability is unavailable."""


class MailboxCrash(RuntimeError):
    """A controlled process-boundary interruption for recovery acceptance tests."""

    def __init__(self, phase: str):
        self.phase = phase
        super().__init__(f"controlled process crash: {phase}")


class MailboxCapability:
    """The adapter boundary: carry out one confirmed request, return observed evidence."""

    name = "unavailable"
    enabled = False

    _CAPABILITIES = (
        "read_history", "immediate_send", "native_scheduling",
        "schedule_cancellation", "recall",
    )

    def capabilities(self) -> dict:
        """Report each platform capability independently.

        ``enabled`` remains the execution-send guard used by ticket 05. Reading
        a mailbox never turns it on.
        """
        return {
            capability: {
                "available": False,
                "verified": False,
                "basis": "not enabled for this adapter",
            }
            for capability in self._CAPABILITIES
        }

    def observe(self, mailbox_address: str) -> dict:
        return {
            "status": "unsupported",
            "mailbox_address": mailbox_address,
            "detail": "Read-only mailbox history is not available for this adapter",
            "coverage": {"folders": [], "complete": False},
            "messages": [],
        }

    #: Whether an adapter needs the confirmed attachment bytes materialized to
    #: private files before submission. The controlled adapter does not; the
    #: live browser adapter uploads them from disk.
    needs_attachment_files = False

    def submit(self, request: dict, attachments=None) -> dict:
        raise MailboxCapabilityError("No external mailbox capability is enabled")


class DisabledMailbox(MailboxCapability):
    """The default adapter: every capability stays disabled until separately verified."""

    name = "disabled"
    enabled = False

    def submit(self, request: dict, attachments=None) -> dict:
        raise MailboxCapabilityError(
            "External execution is disabled: no verified mailbox capability is enabled")


class ControlledMailbox(MailboxCapability):
    """A deterministic adapter used to demonstrate outcomes without real sends.

    Each ``submit`` records the exact request it received and returns the next
    scripted outcome. Unsupported outcomes are rejected rather than guessed.
    """

    name = "controlled"
    enabled = True
    OUTCOMES = ("sent", "failed", "unknown", "authentication_required")

    def __init__(self, outcomes=None, default: str = "sent", observations=None):
        self._outcomes = list(outcomes or [])
        self._default = default
        self._observations = list(observations or [])
        self.requests: list[dict] = []
        self.observation_requests: list[str] = []

    def capabilities(self) -> dict:
        capabilities = super().capabilities()
        capabilities["read_history"] = {
            "available": bool(self._observations),
            "verified": False,
            "basis": "controlled fixture; not live platform verification",
        }
        capabilities["immediate_send"] = {
            "available": True,
            "verified": False,
            "basis": "controlled outcome fixture; no external send",
        }
        return capabilities

    def observe(self, mailbox_address: str) -> dict:
        self.observation_requests.append(mailbox_address)
        if not self._observations:
            return super().observe(mailbox_address)
        scripted = self._observations.pop(0)
        if not isinstance(scripted, dict):
            raise MailboxCapabilityError("Controlled observation must be a JSON object")
        return {"mailbox_address": mailbox_address, **scripted}

    def submit(self, request: dict, attachments=None) -> dict:
        scripted = self._outcomes.pop(0) if self._outcomes else self._default
        if isinstance(scripted, dict) and scripted.get("crash") == "before_submission":
            raise MailboxCrash("before_submission")
        self.requests.append(request)
        if isinstance(scripted, dict) and scripted.get("crash") == "during_submission":
            raise MailboxCrash("during_submission")
        if isinstance(scripted, dict) and scripted.get("crash") == "after_success":
            evidence = self.evidence(scripted)
            if evidence["outcome"] != "sent":
                raise MailboxCapabilityError(
                    "Controlled after_success crash requires a sent outcome")
            raise MailboxCrash("after_success")
        return self.evidence(scripted)

    @classmethod
    def evidence(cls, scripted) -> dict:
        if isinstance(scripted, str):
            scripted = {"outcome": scripted}
        outcome = scripted.get("outcome", "sent")
        if outcome not in cls.OUTCOMES:
            raise MailboxCapabilityError(f"Unsupported controlled outcome: {outcome}")
        return {"outcome": outcome,
                "reference": scripted.get("reference", f"controlled-{outcome}"),
                "detail": scripted.get("detail", "")}

    @classmethod
    def from_script(cls, path, default: str = "sent") -> "ControlledMailbox":
        """Build a deterministic adapter from an outcome script file (development/testing)."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return cls(data.get("outcomes", []), default=data.get("default", default),
                       observations=data.get("observations", []))
        return cls(data, default=default)


class NetEase163Mailbox(MailboxCapability):
    """Observe history and carry out confirmed immediate sends in an operator browser.

    The adapter intentionally uses the Playwright CLI session rather than
    storing mailbox credentials. If login, verification, or a CAPTCHA is
    required it opens a headed browser and returns ``authentication_required``;
    the operator completes that interaction and runs the command again.

    Read-only history enumerates canonical IDs from folder-level list requests
    and reads header/MIME metadata without fetching message-body HTML, whose
    endpoint changes unread state. Immediate sending opens the real compose
    interface for the exact confirmed content and only reports ``sent`` when
    the Sent folder confirms the message. Native scheduling, cancellation and
    Recall stay disabled: their verification is a separate capability.
    """

    name = "163-browser"
    enabled = True
    needs_attachment_files = True
    _SESSION_RE = re.compile(r"^[A-Za-z0-9_-]+$")

    def __init__(self, session: str = "smartmail-163", runner=None, profile=None):
        if not self._SESSION_RE.fullmatch(session):
            raise MailboxCapabilityError(
                "Browser session may contain only letters, digits, underscores, and hyphens")
        self.session = session
        self._runner = runner or subprocess.run
        self.profile = Path(profile) if profile else self._default_profile()

    @staticmethod
    def _default_profile() -> Path:
        """A stable user-data directory so the operator login survives restarts.

        Playwright's default context is incognito-like: cookies live only in
        memory and vanish the moment the browser closes.  A persistent profile
        keeps the authenticated session on disk across daemon restarts, so the
        operator logs in once and every later refresh/execution reuses it.
        """
        configured = os.environ.get("SMARTMAIL_BROWSER_PROFILE")
        return Path(configured) if configured else Path.cwd() / ".smartmail" / "browser-163"

    def capabilities(self) -> dict:
        capabilities = super().capabilities()
        capabilities["read_history"] = {
            "available": True,
            "verified": True,
            "basis": (
                "Live acceptance on 163.com webmail: DOM-discovered built-in folders, "
                "paginated canonical IDs, and metadata-only detail reads; message bodies "
                "remain excluded to preserve unread state"
            ),
        }
        capabilities["immediate_send"] = {
            "available": True,
            "verified": True,
            "basis": (
                "Confirmed operator execution opens and fills the real compose interface "
                "and reports Sent only after the Sent folder confirms the message"
            ),
        }
        for capability in ("native_scheduling", "schedule_cancellation", "recall"):
            capabilities[capability]["basis"] = (
                "Not enabled; immediate-send verification does not verify this capability")
        return capabilities

    def observe(self, mailbox_address: str) -> dict:
        collector = Path(__file__).with_name("netease_163_collector.js").read_text(encoding="utf-8")
        collector = collector.replace(
            "__INTENDED_MAILBOX__", json.dumps(mailbox_address.lower()))
        try:
            result = self._run_cli("--json", "run-code", collector)
        except subprocess.TimeoutExpired:
            return {
                "status": "failed", "mailbox_address": "",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "detail": "Read-only 163.com observation timed out",
                "coverage": {"folders": [], "complete": False}, "messages": [],
            }
        if result.returncode != 0:
            if "is not open" in (result.stdout + result.stderr):
                try:
                    self._open_browser()
                except subprocess.TimeoutExpired:
                    return {
                        "status": "failed", "mailbox_address": "",
                        "observed_at": datetime.now(timezone.utc).isoformat(),
                        "detail": "Opening the headed 163.com browser timed out",
                        "coverage": {"folders": [], "complete": False}, "messages": [],
                    }
                detail = (
                    "The headed 163.com browser is open. Complete login, verification, or "
                    "CAPTCHA as the operator, then run mailbox refresh again")
                status = "authentication_required"
            else:
                try:
                    detail = json.loads(result.stdout).get("error", "Browser observation failed")
                except json.JSONDecodeError:
                    detail = (result.stderr or result.stdout or "Browser observation failed").strip()
                status = "failed"
            return {
                "status": status,
                "mailbox_address": "",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "detail": detail,
                "coverage": {"folders": [], "complete": False},
                "messages": [],
            }
        try:
            envelope = json.loads(result.stdout)
            observation = json.loads(envelope["result"])
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise MailboxCapabilityError(
                "163.com returned an unsupported or ambiguous browser observation") from error
        actual = str(observation.get("mailbox_address", "")).lower()
        if actual and actual != mailbox_address.lower():
            return {
                "status": "wrong_mailbox",
                "mailbox_address": actual,
                "observed_at": observation.get("observed_at"),
                "detail": (
                    f"Browser is logged into {actual}; intended Mailbox is "
                    f"{mailbox_address.lower()}"
                ),
                "coverage": observation.get("coverage", {"folders": [], "complete": False}),
                "messages": [],
            }
        return observation

    def submit(self, request: dict, attachments=None) -> dict:
        """Carry out one confirmed immediate send and report observed evidence.

        The compose interface is opened and filled only with the exact confirmed
        snapshot.  ``sent`` is returned solely when the Sent folder confirms the
        message; an unconfirmed submission stays ``unknown``.  Authentication
        interruptions are handed to the operator rather than bypassed.
        """
        if not isinstance(request, dict):
            raise MailboxCapabilityError("A confirmed execution request is required")
        files = [str(Path(path)) for path in (attachments or [])]
        collector = Path(__file__).with_name("netease_163_sender.js").read_text(encoding="utf-8")
        # ensure_ascii keeps the injected literals ASCII-safe for the command
        # line; JavaScript decodes the escapes natively.
        collector = collector.replace("__SEND_REQUEST__", json.dumps(request))
        collector = collector.replace("__ATTACHMENT_FILES__", json.dumps(files))
        try:
            result = self._run_cli("--json", "run-code", collector)
        except subprocess.TimeoutExpired:
            return self._send_result("unknown", "Confirmed 163.com submission timed out")
        if result.returncode != 0:
            combined = result.stdout + result.stderr
            if "is not open" in combined:
                try:
                    self._open_browser()
                except subprocess.TimeoutExpired:
                    return self._send_result(
                        "unknown", "Opening the headed 163.com browser timed out")
                return self._send_result(
                    "authentication_required",
                    "The headed 163.com browser is open. Complete login, verification, or "
                    "CAPTCHA as the operator, then run execution again")
            try:
                detail = json.loads(result.stdout).get("error", "Browser submission failed")
            except json.JSONDecodeError:
                detail = (result.stderr or result.stdout or "Browser submission failed").strip()
            return self._send_result("unknown", detail)
        try:
            envelope = json.loads(result.stdout)
            evidence = json.loads(envelope["result"])
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            snippet = (result.stdout or result.stderr or "").strip()[:400]
            raise MailboxCapabilityError(
                f"163.com returned an unsupported or ambiguous send result: "
                f"{snippet or 'no output'}") from error
        if not isinstance(evidence, dict) or evidence.get("outcome") not in {
                "sent", "failed", "unknown", "authentication_required"}:
            raise MailboxCapabilityError(
                "163.com returned an unsupported or ambiguous send outcome")
        evidence.setdefault("reference", "")
        evidence.setdefault("detail", "")
        return evidence

    @staticmethod
    def _send_result(outcome: str, detail: str) -> dict:
        return {
            "outcome": outcome,
            "reference": "",
            "detail": detail,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _command(self, *arguments: str) -> list[str]:
        prefix = ["npx.cmd"]
        node = shutil.which("node")
        if node:
            entrypoint = self._cached_cli_entrypoint()
            if entrypoint:
                # Invoke the package entrypoint directly so cmd.exe's 8191
                # character limit does not constrain readable collector source.
                return [node, str(entrypoint), f"-s={self.session}", *arguments]
            npx_script = Path(node).parent / "node_modules" / "npm" / "bin" / "npx-cli.js"
            if npx_script.exists():
                prefix = [node, str(npx_script)]
        return [*prefix, "--yes", "--package", "@playwright/cli", "playwright-cli",
                f"-s={self.session}", *arguments]

    @staticmethod
    def _cached_cli_entrypoint() -> Path | None:
        roots = []
        configured = os.environ.get("NPM_CONFIG_CACHE")
        local = os.environ.get("LOCALAPPDATA")
        if configured:
            roots.append(Path(configured))
        if local:
            roots.append(Path(local) / "npm-cache")
        roots.append(Path.home() / ".npm")
        candidates = []
        for root in roots:
            candidates.extend(root.glob(
                "_npx/*/node_modules/@playwright/cli/playwright-cli.js"))
        return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None

    def _run_cli(self, *arguments: str):
        return self._runner(
            self._command(*arguments), capture_output=True, text=True,
            encoding="utf-8", timeout=300)

    def _open_browser(self) -> None:
        result = self._run_cli(
            "open", "https://mail.163.com", "--headed",
            "--persistent", "--profile", str(self.profile))
        if result.returncode != 0:
            raise MailboxCapabilityError(
                "Cannot open the headed 163.com browser; verify Node.js/npm and Playwright CLI")

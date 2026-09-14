"""Public interface for persistent local outreach operations."""

from .core import SmartMail
from .errors import SmartMailError
from ._operations.planning import PLAN_DEFAULTS

__all__ = ["SmartMail", "SmartMailError", "PLAN_DEFAULTS"]

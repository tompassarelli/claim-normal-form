"""
System configuration — single source of truth for constants, permissions,
hooks, and defaults.  No mutable state lives here; everything is either
a plain value or a factory function (for hooks dict).

Import this module directly; do not instantiate it.
"""

from typing import Any, Callable, Dict, List, Set

# ---------------------------------------------------------------------------
# Ticket lifecycle
# ---------------------------------------------------------------------------

STATUSES: Set[str] = {"open", "in_progress", "resolved", "closed", "archived", "on_hold"}

# Statuses where work can still happen (not yet closed).
ACTIVE_STATUSES: Set[str] = {"open", "in_progress", "resolved", "on_hold"}

# Once a ticket reaches a terminal status it cannot be transitioned further
# without an explicit reopen action.
TERMINAL_STATUSES: Set[str] = {"closed", "archived"}

# Valid transitions: maps current status -> set of allowed next statuses.
STATUS_TRANSITIONS: Dict[str, Set[str]] = {
    "open":        {"in_progress", "closed"},
    "in_progress": {"open", "resolved", "closed", "on_hold"},
    "resolved":    {"closed", "open"},
    "closed":      {"open", "archived"},
    "on_hold":     {"in_progress", "closed"},
    "archived":    {"open"},
}

# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------

PRIORITIES: List[str] = ["low", "medium", "high", "urgent"]

PRIORITY_WEIGHTS: Dict[str, int] = {
    "low":    1,
    "medium": 2,
    "high":   3,
    "urgent": 5,
}

# ---------------------------------------------------------------------------
# Users & roles
# ---------------------------------------------------------------------------

ROLES: Set[str] = {"admin", "agent", "viewer", "team_lead"}

# All discrete actions in the system.
SYSTEM_ACTIONS: List[str] = [
    "create",
    "view",
    "update",
    "assign",
    "close",
    "comment",
    "tag",
    "search",
    "report",
    "export",
    "import",
    "manage_team",
    "manage_sla",
    "manage_users",
    "bulk_update",
]

# Role → frozenset of allowed actions.
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "admin": set(SYSTEM_ACTIONS),           # full access
    "team_lead": {
        "create", "view", "update", "assign", "close",
        "comment", "tag", "search", "report", "export",
        "manage_team", "bulk_update",
    },
    "agent": {
        "create", "view", "update", "assign", "close",
        "comment", "tag", "search",
    },
    "viewer": {
        "view", "search", "report",
    },
}

def can(role: str, action: str) -> bool:
    """Return True if *role* is permitted to perform *action*."""
    return action in ROLE_PERMISSIONS.get(role, set())


# ---------------------------------------------------------------------------
# Lifecycle hooks
#
# Each key maps to {"pre": [...], "post": [...]}.  Handlers have the
# signature (context: dict) -> None and are called in list order.
# An empty list means no hooks registered for that slot.
# ---------------------------------------------------------------------------

def _empty_hooks() -> Dict[str, List[Callable[[Dict[str, Any]], None]]]:
    return {"pre": [], "post": []}

HOOKS: Dict[str, Dict[str, List[Callable[[Dict[str, Any]], None]]]] = {
    "create":     _empty_hooks(),
    "update":     _empty_hooks(),
    "transition": _empty_hooks(),
    "assign":     _empty_hooks(),
    "comment":    _empty_hooks(),
    "close":      _empty_hooks(),
    "tag":        _empty_hooks(),
    "delete":     _empty_hooks(),
}

# ---------------------------------------------------------------------------
# Ticket sources
# ---------------------------------------------------------------------------

SOURCES: Set[str] = {"web", "email", "api", "phone", "chat"}

# ---------------------------------------------------------------------------
# Default SLA (response / resolution in minutes, keyed by priority)
# ---------------------------------------------------------------------------

DEFAULT_SLA: Dict[str, Dict[str, int]] = {
    "low":    {"response": 480,  "resolution": 2880},   # 8 h / 48 h
    "medium": {"response": 240,  "resolution": 1440},   # 4 h / 24 h
    "high":   {"response": 60,   "resolution": 480},    # 1 h / 8 h
    "urgent": {"response": 15,   "resolution": 120},    # 15 min / 2 h
}

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

MAX_TAGS_PER_TICKET: int = 10
MAX_COMMENT_LENGTH: int = 5000
SEARCH_RESULT_LIMIT: int = 50

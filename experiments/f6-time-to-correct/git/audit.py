"""Audit module for ClaimDesk.

Append-only audit trail for all ticket lifecycle events. Hook functions
are registered into config.HOOKS by calling register_audit_hooks(), which
config.py does at import time.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AuditEntry:
    timestamp: str
    action: str
    ticket_id: str
    user_id: str
    details: Dict[str, Any] = field(default_factory=dict)


_audit_log: List[AuditEntry] = []


def log_action(action: str, ticket_id: str, user_id: str, **details) -> AuditEntry:
    """Append a new entry to the audit trail and return it."""
    entry = AuditEntry(
        timestamp=str(int(time.time())),
        action=action,
        ticket_id=ticket_id,
        user_id=user_id,
        details=details,
    )
    _audit_log.append(entry)
    return entry


def get_audit_trail(ticket_id: Optional[str] = None) -> List[AuditEntry]:
    """Return all audit entries, optionally filtered to a single ticket."""
    if ticket_id is None:
        return list(_audit_log)
    return [e for e in _audit_log if e.ticket_id == ticket_id]


def reset_audit() -> None:
    """Clear the audit log (intended for test teardown)."""
    _audit_log.clear()


# ---------------------------------------------------------------------------
# Hook implementations — called by config.HOOKS registrations
# ---------------------------------------------------------------------------

def _on_post_create(ticket, user_id: str = "", **_kwargs) -> None:
    log_action("create", ticket_id=ticket.id, user_id=user_id)


def _on_post_transition(ticket, user_id: str = "", old_status: str = "",
                        new_status: str = "", **_kwargs) -> None:
    log_action(
        "transition",
        ticket_id=ticket.id,
        user_id=user_id,
        old_status=old_status,
        new_status=new_status,
    )


def _on_post_assign(ticket, user_id: str = "", assigned_by: str = "",
                    **_kwargs) -> None:
    log_action(
        "assign",
        ticket_id=ticket.id,
        user_id=assigned_by or user_id,
        assignee=user_id,
    )


def _on_post_close(ticket, user_id: str = "", **_kwargs) -> None:
    log_action("close", ticket_id=ticket.id, user_id=user_id)


def register_audit_hooks() -> None:
    """Wire audit callbacks into config.HOOKS.

    Safe to call multiple times — checks for duplicates before appending.
    """
    from config import HOOKS

    def _add(hook_name: str, fn) -> None:
        if fn not in HOOKS[hook_name]:
            HOOKS[hook_name].append(fn)

    _add("post_create", _on_post_create)
    _add("post_transition", _on_post_transition)
    _add("post_assign", _on_post_assign)
    _add("post_close", _on_post_close)

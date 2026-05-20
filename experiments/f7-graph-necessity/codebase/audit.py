"""
Audit trail for the helpdesk/CRM application.

Every significant state change (ticket create/update/transition/assign/close,
comment add, permission denial) is recorded as an AuditEntry in the store.

Event hook registration
-----------------------
Call register_audit_hooks() once at startup.  It wires listeners into the
events module so that ticket.* events are automatically logged without
callers needing to touch this module directly.  The explicit log_* helpers
remain available for cases where the event system is bypassed.
"""

import time
import uuid
from typing import Any, List

import events
from models import AuditEntry, Comment, Ticket


# ---------------------------------------------------------------------------
# Internal store (imported lazily in helpers to avoid circular imports)
# ---------------------------------------------------------------------------

def _store():
    import store  # noqa: PLC0415
    return store


# ---------------------------------------------------------------------------
# Core entry-point
# ---------------------------------------------------------------------------

def log_action(
    action: str,
    entity_type: str,
    entity_id: str,
    user_id: str = "",
    **details: Any,
) -> AuditEntry:
    """Create and persist a single AuditEntry.

    Returns the created entry.  This is the lowest-level helper; prefer
    the typed log_* wrappers for structured logging.
    """
    entry = AuditEntry(
        id=str(uuid.uuid4()),
        timestamp=str(time.time()),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        details=dict(details),
    )
    _store().add_audit(entry)
    return entry


# ---------------------------------------------------------------------------
# Typed helpers
# ---------------------------------------------------------------------------

def log_ticket_create(ticket: Ticket, user_id: str) -> AuditEntry:
    """Record that *ticket* was created by *user_id*."""
    return log_action(
        "ticket.created",
        "ticket",
        ticket.id,
        user_id=user_id,
        title=ticket.title,
        priority=ticket.priority,
        source=ticket.source,
        status=ticket.status,
        contact_email=ticket.contact_email,
    )


def log_ticket_update(
    ticket: Ticket,
    user_id: str,
    changed_fields: dict,
) -> AuditEntry:
    """Record a field-level update to *ticket*.

    *changed_fields* should be a mapping of field_name -> {"old": v, "new": v}.
    """
    return log_action(
        "ticket.updated",
        "ticket",
        ticket.id,
        user_id=user_id,
        changed_fields=changed_fields,
    )


def log_ticket_transition(
    ticket: Ticket,
    user_id: str,
    old_status: str,
    new_status: str,
) -> AuditEntry:
    """Record a status transition on *ticket*."""
    return log_action(
        "ticket.transitioned",
        "ticket",
        ticket.id,
        user_id=user_id,
        old_status=old_status,
        new_status=new_status,
    )


def log_ticket_assign(
    ticket: Ticket,
    user_id: str,
    assignee_id: str,
) -> AuditEntry:
    """Record that *ticket* was assigned to *assignee_id* by *user_id*."""
    return log_action(
        "ticket.assigned",
        "ticket",
        ticket.id,
        user_id=user_id,
        assignee_id=assignee_id,
        previous_assignee=ticket.assignee,
    )


def log_ticket_close(ticket: Ticket, user_id: str) -> AuditEntry:
    """Record that *ticket* was closed by *user_id*."""
    return log_action(
        "ticket.closed",
        "ticket",
        ticket.id,
        user_id=user_id,
        final_status=ticket.status,
    )


def log_comment_add(comment: Comment, user_id: str) -> AuditEntry:
    """Record that *comment* was added by *user_id*."""
    return log_action(
        "comment.added",
        "comment",
        comment.id,
        user_id=user_id,
        ticket_id=comment.ticket_id,
        is_internal=comment.is_internal,
        preview=comment.preview(120),
    )


def log_permission_denied(
    user_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
) -> AuditEntry:
    """Record a failed permission check.

    These entries are intentionally written even for unknown/invalid users
    so that intrusion patterns are visible in the audit trail.
    """
    return log_action(
        "permission.denied",
        entity_type,
        entity_id,
        user_id=user_id,
        attempted_action=action,
    )


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_ticket_audit(ticket_id: str) -> List[AuditEntry]:
    """Return all audit entries touching *ticket_id*, oldest first."""
    all_entries = _store().list_audit()
    return [
        e for e in all_entries
        if e.entity_id == ticket_id and e.entity_type == "ticket"
        or e.details.get("ticket_id") == ticket_id
    ]


def get_user_audit(user_id: str) -> List[AuditEntry]:
    """Return all audit entries authored by *user_id*, oldest first."""
    all_entries = _store().list_audit()
    return [e for e in all_entries if e.user_id == user_id]


def get_recent_actions(limit: int = 50) -> List[AuditEntry]:
    """Return up to *limit* most-recent audit entries, newest first."""
    all_entries = _store().list_audit()
    # Entries are appended in insertion order; reverse for recency.
    return list(reversed(all_entries))[:limit]


def reset_audit() -> None:
    """Remove all audit entries.  Intended for test teardown only."""
    _store().clear_audit()


# ---------------------------------------------------------------------------
# Automatic event hooks
# ---------------------------------------------------------------------------

def _on_ticket_created(ticket: Ticket, user_id: str = "", **_: Any) -> None:
    log_ticket_create(ticket, user_id)


def _on_ticket_updated(
    ticket: Ticket,
    user_id: str = "",
    changed_fields: dict = None,
    **_: Any,
) -> None:
    log_ticket_update(ticket, user_id, changed_fields or {})


def _on_ticket_transitioned(
    ticket: Ticket,
    user_id: str = "",
    old_status: str = "",
    new_status: str = "",
    **_: Any,
) -> None:
    log_ticket_transition(ticket, user_id, old_status, new_status)


def _on_ticket_assigned(
    ticket: Ticket,
    user_id: str = "",
    assignee_id: str = "",
    **_: Any,
) -> None:
    log_ticket_assign(ticket, user_id, assignee_id)


def _on_ticket_closed(ticket: Ticket, user_id: str = "", **_: Any) -> None:
    log_ticket_close(ticket, user_id)


def _on_comment_added(comment: Comment, user_id: str = "", **_: Any) -> None:
    log_comment_add(comment, user_id)


def register_audit_hooks() -> None:
    """Register audit listeners for all ticket lifecycle events.

    Safe to call multiple times — duplicate registration is idempotent
    because events.register_listener appends; callers should ensure this
    is only called once at startup (e.g. from an application factory).
    """
    events.register_listener("ticket.created",     _on_ticket_created)
    events.register_listener("ticket.updated",     _on_ticket_updated)
    events.register_listener("ticket.transitioned", _on_ticket_transitioned)
    events.register_listener("ticket.assigned",    _on_ticket_assigned)
    events.register_listener("ticket.closed",      _on_ticket_closed)
    events.register_listener("ticket.commented",   _on_comment_added)

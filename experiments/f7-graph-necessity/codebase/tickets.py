"""
High-level ticket operations for the helpdesk/CRM application.

This module is the primary entry point for all ticket mutations.
It orchestrates: input validation, store reads/writes, audit logging,
and event emission.  Business rules about *which* transitions are valid
live in workflow.py; *what* to record lives in audit.py; *who* is
allowed lives in permissions.py.

Quick reference
---------------
create_ticket()      — validate + persist + emit ticket.created
update_ticket()      — validate + diff + persist + emit ticket.updated
get_ticket()         — thin delegate to store
list_tickets()       — filtered list from store
delete_ticket()      — soft-delete + emit ticket.deleted
get_ticket_history() — audit trail for a single ticket
bulk_update()        — transactional batch of update_ticket calls
count_by_status()    — aggregate counts
count_by_priority()  — aggregate counts
get_overdue_tickets()— tickets that have breached their SLA resolution window
get_recent_tickets() — newest-first slice
search_tickets()     — substring match on title + description
"""

import time
import uuid
from dataclasses import fields as dataclass_fields
from typing import Any, Dict, List, Optional

import config
import events
import store as _store
from models import AuditEntry, Ticket


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return str(time.time())


def _new_id() -> str:
    return str(uuid.uuid4())


def _diff_fields(old: Ticket, new: Ticket) -> Dict[str, Dict[str, Any]]:
    """Return a mapping of field_name -> {"old": v, "new": v} for changed fields."""
    changed: Dict[str, Dict[str, Any]] = {}
    for f in dataclass_fields(old):
        old_val = getattr(old, f.name)
        new_val = getattr(new, f.name)
        if old_val != new_val:
            changed[f.name] = {"old": old_val, "new": new_val}
    return changed


def _sla_resolution_seconds(ticket: Ticket) -> Optional[float]:
    """Return the SLA resolution deadline in seconds-since-epoch, or None."""
    sla = config.DEFAULT_SLA.get(ticket.priority)
    if sla is None:
        return None
    try:
        created = float(ticket.created_at)
    except (ValueError, TypeError):
        return None
    return created + sla["resolution"] * 60


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_ticket(
    title: str,
    description: str,
    priority: str = "medium",
    source: str = "web",
    contact_email: str = "",
    user_id: str = "",
) -> Ticket:
    """Validate, persist, and return a new Ticket.

    Fires the ``ticket.created`` event after a successful write.

    Raises
    ------
    ValueError
        If *priority* is not in config.PRIORITIES, *source* is not in
        config.SOURCES, or *title* is empty.
    """
    title = title.strip()
    if not title:
        raise ValueError("title must not be empty")
    if priority not in config.PRIORITIES:
        raise ValueError(
            f"Invalid priority '{priority}'. Valid values: {sorted(config.PRIORITIES)}"
        )
    if source not in config.SOURCES:
        raise ValueError(
            f"Invalid source '{source}'. Valid values: {sorted(config.SOURCES)}"
        )

    now = _now()
    ticket = Ticket(
        id=_new_id(),
        title=title,
        description=description,
        status="open",
        priority=priority,
        source=source,
        contact_email=contact_email,
        created_at=now,
        updated_at=now,
    )
    _store.add_ticket(ticket)
    events.emit("ticket.created", ticket=ticket, user_id=user_id)
    return ticket


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_ticket(ticket_id: str) -> Ticket:
    """Return the Ticket for *ticket_id*.

    Raises KeyError if the ticket does not exist.
    """
    return _store.get_ticket(ticket_id)


def list_tickets(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    team: Optional[str] = None,
    tag: Optional[str] = None,
    source: Optional[str] = None,
) -> List[Ticket]:
    """Return all tickets matching the supplied filter criteria.

    All filters are optional and ANDed together.  Passing no filters
    returns every non-deleted ticket in the store.
    """
    tickets = _store.list_tickets()
    if status is not None:
        tickets = [t for t in tickets if t.status == status]
    if priority is not None:
        tickets = [t for t in tickets if t.priority == priority]
    if assignee is not None:
        tickets = [t for t in tickets if t.assignee == assignee]
    if team is not None:
        tickets = [t for t in tickets if t.team == team]
    if tag is not None:
        tickets = [t for t in tickets if tag in t.tags]
    if source is not None:
        tickets = [t for t in tickets if t.source == source]
    return tickets


def get_ticket_history(ticket_id: str) -> List[AuditEntry]:
    """Return the ordered audit trail for *ticket_id*.

    Delegates to audit.get_ticket_audit() so the store is the single
    source of truth; importing audit here is safe because audit.py does
    not import tickets.py.
    """
    from audit import get_ticket_audit  # local import to avoid circular ref at load
    return get_ticket_audit(ticket_id)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

_IMMUTABLE_FIELDS = frozenset({"id", "created_at"})

def update_ticket(ticket_id: str, user_id: str = "", **fields: Any) -> Ticket:
    """Update allowed fields on an existing ticket and persist.

    Fires ``ticket.updated`` (and ``ticket.transitioned`` when the status
    changes) after a successful write.

    Raises
    ------
    KeyError
        If *ticket_id* does not exist.
    ValueError
        If any supplied field value is invalid or the field is immutable.
    """
    ticket = _store.get_ticket(ticket_id)
    old_status = ticket.status

    for key, value in fields.items():
        if key in _IMMUTABLE_FIELDS:
            raise ValueError(f"Field '{key}' is immutable and cannot be updated")
        if key == "status":
            if value not in config.STATUSES:
                raise ValueError(
                    f"Invalid status '{value}'. Valid: {sorted(config.STATUSES)}"
                )
            allowed = config.STATUS_TRANSITIONS.get(ticket.status, set())
            if value != ticket.status and value not in allowed:
                raise ValueError(
                    f"Cannot transition from '{ticket.status}' to '{value}'. "
                    f"Allowed: {sorted(allowed)}"
                )
        if key == "priority" and value not in config.PRIORITIES:
            raise ValueError(
                f"Invalid priority '{value}'. Valid: {sorted(config.PRIORITIES)}"
            )
        if key == "source" and value not in config.SOURCES:
            raise ValueError(
                f"Invalid source '{value}'. Valid: {sorted(config.SOURCES)}"
            )
        if key == "tags":
            if not isinstance(value, list):
                raise ValueError("tags must be a list of strings")
            if len(value) > config.MAX_TAGS_PER_TICKET:
                raise ValueError(
                    f"Too many tags: max is {config.MAX_TAGS_PER_TICKET}"
                )

    # Apply updates.
    snapshot_before = Ticket(**{f.name: getattr(ticket, f.name) for f in dataclass_fields(ticket)})
    for key, value in fields.items():
        setattr(ticket, key, value)
    ticket.updated_at = _now()

    changed = _diff_fields(snapshot_before, ticket)
    _store.update_ticket(ticket)

    # Emit events.
    if changed:
        events.emit("ticket.updated", ticket=ticket, user_id=user_id, changed_fields=changed)
    if "status" in changed:
        new_status = ticket.status
        events.emit(
            "ticket.transitioned",
            ticket=ticket,
            user_id=user_id,
            old_status=old_status,
            new_status=new_status,
        )
        if new_status == "closed":
            events.emit("ticket.closed", ticket=ticket, user_id=user_id)
    if "assignee" in changed and ticket.assignee is not None:
        events.emit(
            "ticket.assigned",
            ticket=ticket,
            user_id=user_id,
            assignee_id=ticket.assignee,
        )

    return ticket


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_ticket(ticket_id: str, user_id: str = "") -> None:
    """Soft-delete *ticket_id* by setting status to 'closed' and tagging it.

    A soft delete is preferred so that audit history remains intact and
    the ticket can be inspected after the fact.  The ticket is tagged with
    ``__deleted__`` and transitioned to *closed*; it will be excluded from
    list_tickets() results because store.list_tickets() filters deleted ones.

    Fires ``ticket.deleted`` after the store write.

    Raises
    ------
    KeyError
        If *ticket_id* does not exist.
    """
    ticket = _store.get_ticket(ticket_id)
    old_status = ticket.status
    ticket.status = "closed"
    if "__deleted__" not in ticket.tags:
        ticket.tags = ticket.tags + ["__deleted__"]
    ticket.updated_at = _now()
    _store.update_ticket(ticket)
    events.emit(
        "ticket.deleted",
        ticket=ticket,
        user_id=user_id,
        previous_status=old_status,
    )


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------

def bulk_update(
    ticket_ids: List[str],
    user_id: str = "",
    **fields: Any,
) -> List[Dict[str, Any]]:
    """Apply the same field updates to every ticket in *ticket_ids*.

    Returns a list of result dicts — one per input id — each with keys:
      ``id``      — the ticket id
      ``ok``      — True on success, False on failure
      ``ticket``  — the updated Ticket (present when ok=True)
      ``error``   — error message string (present when ok=False)

    Individual failures do not abort the remaining updates.
    """
    results: List[Dict[str, Any]] = []
    for ticket_id in ticket_ids:
        try:
            ticket = update_ticket(ticket_id, user_id=user_id, **fields)
            results.append({"id": ticket_id, "ok": True, "ticket": ticket})
        except Exception as exc:
            results.append({"id": ticket_id, "ok": False, "error": str(exc)})
    return results


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------

def count_by_status() -> Dict[str, int]:
    """Return a mapping of status -> ticket count for all non-deleted tickets."""
    counts: Dict[str, int] = {s: 0 for s in config.STATUSES}
    for ticket in _store.list_tickets():
        if "__deleted__" not in ticket.tags:
            counts[ticket.status] = counts.get(ticket.status, 0) + 1
    return counts


def count_by_priority() -> Dict[str, int]:
    """Return a mapping of priority -> ticket count for all non-deleted tickets."""
    counts: Dict[str, int] = {p: 0 for p in config.PRIORITIES}
    for ticket in _store.list_tickets():
        if "__deleted__" not in ticket.tags:
            counts[ticket.priority] = counts.get(ticket.priority, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Convenience queries
# ---------------------------------------------------------------------------

def get_overdue_tickets() -> List[Ticket]:
    """Return tickets that have breached their SLA resolution window.

    A ticket is overdue when:
      - It is not in a terminal status (i.e. not yet closed), AND
      - The current time exceeds created_at + SLA resolution minutes.
    """
    now = float(_now())
    overdue: List[Ticket] = []
    for ticket in _store.list_tickets():
        if ticket.status in config.TERMINAL_STATUSES:
            continue
        if "__deleted__" in ticket.tags:
            continue
        deadline = _sla_resolution_seconds(ticket)
        if deadline is not None and now > deadline:
            overdue.append(ticket)
    return overdue


def get_recent_tickets(limit: int = 20) -> List[Ticket]:
    """Return up to *limit* tickets ordered by creation date, newest first."""
    tickets = [t for t in _store.list_tickets() if "__deleted__" not in t.tags]
    tickets.sort(
        key=lambda t: float(t.created_at) if t.created_at else 0.0,
        reverse=True,
    )
    return tickets[:limit]


def search_tickets(query: str) -> List[Ticket]:
    """Return tickets whose title or description contains *query* (case-insensitive).

    Results are capped at config.SEARCH_RESULT_LIMIT and sorted by
    creation date (newest first) to give the most relevant recent items.
    Deleted tickets are excluded.
    """
    if not query:
        return []
    needle = query.lower()
    matches = [
        t for t in _store.list_tickets()
        if "__deleted__" not in t.tags
        and (needle in t.title.lower() or needle in t.description.lower())
    ]
    matches.sort(
        key=lambda t: float(t.created_at) if t.created_at else 0.0,
        reverse=True,
    )
    return matches[: config.SEARCH_RESULT_LIMIT]

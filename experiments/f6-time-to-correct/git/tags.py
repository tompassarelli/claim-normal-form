"""Tags module for ClaimDesk.

Provides per-ticket tagging via the Ticket.tags field.
"""
from core import get_ticket, update_ticket
from typing import List


def add_tag(ticket_id: str, tag: str) -> List[str]:
    """Add a tag to a ticket. Returns the updated tag list.

    Normalises the tag to lowercase-stripped form. No-ops if the tag
    is already present.
    """
    tag = tag.strip().lower()
    if not tag:
        raise ValueError("tag must be a non-empty string")
    t = get_ticket(ticket_id)
    if t is None:
        raise KeyError(f"Ticket {ticket_id!r} not found")
    if tag not in t.tags:
        update_ticket(ticket_id, tags=t.tags + [tag])
    return get_ticket(ticket_id).tags


def get_tags(ticket_id: str) -> List[str]:
    """Return all tags on a ticket."""
    t = get_ticket(ticket_id)
    if t is None:
        raise KeyError(f"Ticket {ticket_id!r} not found")
    return list(t.tags)


def find_by_tag(tag: str) -> List[str]:
    """Return ticket IDs that carry the given tag."""
    from core import list_tickets
    tag = tag.strip().lower()
    return [t.id for t in list_tickets() if tag in t.tags]

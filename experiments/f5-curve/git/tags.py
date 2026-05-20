"""ClaimDesk tag operations.

Manages per-ticket tags using the ticket's existing tags field.
"""
from typing import List

from core import get_ticket, update_ticket


def add_tag(ticket_id: str, tag: str):
    """Add a tag to a ticket. No-op if the tag already exists."""
    t = get_ticket(ticket_id)
    if t is None:
        raise KeyError(f"Ticket {ticket_id} not found")
    if tag not in t.tags:
        t.tags.append(tag)
        update_ticket(ticket_id, tags=t.tags)


def remove_tag(ticket_id: str, tag: str):
    """Remove a tag from a ticket. No-op if the tag is not present."""
    t = get_ticket(ticket_id)
    if t is None:
        raise KeyError(f"Ticket {ticket_id} not found")
    if tag in t.tags:
        t.tags.remove(tag)
        update_ticket(ticket_id, tags=t.tags)


def get_tags(ticket_id: str) -> List[str]:
    """Return all tags on a ticket."""
    t = get_ticket(ticket_id)
    if t is None:
        raise KeyError(f"Ticket {ticket_id} not found")
    return list(t.tags)


def find_by_tag(tag: str) -> List[str]:
    """Return all ticket IDs that carry the given tag."""
    from core import list_tickets
    return [t.id for t in list_tickets() if tag in t.tags]


def reset_tags():
    """Clear tags on every ticket. Useful for testing."""
    from core import list_tickets
    for t in list_tickets():
        t.tags = []

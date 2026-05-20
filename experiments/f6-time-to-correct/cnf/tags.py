"""Tags module for ClaimDesk.

Per-ticket tagging. Tags are stored directly on the Ticket dataclass's
`tags: List[str]` field so they survive alongside all other ticket data.
"""

from typing import List

from core import get_ticket, list_tickets, update_ticket


def add_tag(ticket_id: str, tag: str) -> List[str]:
    """Add a tag to a ticket.

    Silently deduplicates — adding an existing tag is a no-op.
    Returns the updated tag list.
    """
    t = get_ticket(ticket_id)
    if t is None:
        raise KeyError(f"Ticket not found: {ticket_id}")
    tag = tag.strip()
    if not tag:
        raise ValueError("Tag must not be empty.")
    if tag not in t.tags:
        update_ticket(ticket_id, tags=t.tags + [tag])
    return get_ticket(ticket_id).tags


def get_tags(ticket_id: str) -> List[str]:
    """Return the list of tags for a ticket."""
    t = get_ticket(ticket_id)
    if t is None:
        raise KeyError(f"Ticket not found: {ticket_id}")
    return list(t.tags)


def find_by_tag(tag: str) -> List[str]:
    """Return ticket IDs that carry the given tag."""
    tag = tag.strip()
    return [t.id for t in list_tickets() if tag in t.tags]

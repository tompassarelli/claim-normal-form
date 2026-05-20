"""ClaimDesk tag operations.

Graph context: Ticket dataclass has tags: List[str] field.
config.SYSTEM_ACTIONS should include "tag" or "add_tag".
"""
from typing import List
from core import get_ticket, update_ticket


def add_tag(ticket_id: str, tag: str):
    t = get_ticket(ticket_id)
    if t is None:
        raise KeyError(f"Ticket {ticket_id} not found")
    if tag not in t.tags:
        t.tags.append(tag)
        update_ticket(ticket_id, tags=t.tags)


def remove_tag(ticket_id: str, tag: str):
    t = get_ticket(ticket_id)
    if t is None:
        raise KeyError(f"Ticket {ticket_id} not found")
    if tag in t.tags:
        t.tags.remove(tag)
        update_ticket(ticket_id, tags=t.tags)


def get_tags(ticket_id: str) -> List[str]:
    t = get_ticket(ticket_id)
    if t is None:
        raise KeyError(f"Ticket {ticket_id} not found")
    return list(t.tags)


def find_by_tag(tag: str) -> List[str]:
    from core import list_tickets
    return [t.id for t in list_tickets() if tag in t.tags]

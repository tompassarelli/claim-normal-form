from core import get_ticket, update_ticket
from typing import Optional

VALID_TRANSITIONS = {
    "open": ["in_progress", "closed"],
    "in_progress": ["resolved", "open"],
    "resolved": ["closed", "open"],
    "closed": ["archived"],
    "archived": [],
}

ACTIVE_STATUSES = ["open", "in_progress", "resolved"]
TERMINAL_STATUSES = ["closed", "archived"]


def is_valid_transition(from_status: str, to_status: str) -> bool:
    return to_status in VALID_TRANSITIONS.get(from_status, [])


def transition_ticket(ticket_id: str, new_status: str):
    t = get_ticket(ticket_id)
    if not is_valid_transition(t.status, new_status):
        raise ValueError(f"Invalid transition: {t.status} -> {new_status}")
    return update_ticket(ticket_id, status=new_status)


def archive_ticket(ticket_id: str):
    return transition_ticket(ticket_id, "archived")


def is_active(ticket) -> bool:
    return ticket.status in ACTIVE_STATUSES


def is_archived(ticket) -> bool:
    return ticket.status == "archived"


def get_available_transitions(ticket) -> list:
    return VALID_TRANSITIONS.get(ticket.status, [])

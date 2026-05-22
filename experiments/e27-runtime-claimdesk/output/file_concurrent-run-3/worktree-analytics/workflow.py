from core import get_ticket, update_ticket

VALID_TRANSITIONS = {
    "open": ["in_progress", "closed"],
    "in_progress": ["resolved", "open", "on_hold"],
    "on_hold": ["in_progress", "open"],
    "resolved": ["closed", "open"],
    "closed": ["archived"],
    "archived": [],
}

ACTIVE_STATUSES = ["open", "in_progress", "resolved", "on_hold"]
TERMINAL_STATUSES = ["closed", "archived"]
ALL_STATUSES = ACTIVE_STATUSES + TERMINAL_STATUSES

def is_valid_transition(from_status, to_status):
    return to_status in VALID_TRANSITIONS.get(from_status, [])

def transition_ticket(ticket_id, new_status):
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")
    if not is_valid_transition(ticket.status, new_status):
        raise ValueError(f"Cannot transition from {ticket.status} to {new_status}")
    return update_ticket(ticket_id, status=new_status)

def archive_ticket(ticket_id):
    return transition_ticket(ticket_id, "archived")

def is_active(ticket):
    return ticket.status in ACTIVE_STATUSES

def is_archived(ticket):
    return ticket.status == "archived"

def get_available_transitions(ticket):
    return VALID_TRANSITIONS.get(ticket.status, [])

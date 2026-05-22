# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES, ACTIVE_STATUSES

events = []

def track_transition(ticket_id, old_status, new_status):
    event = {
        "ticket": ticket_id,
        "from": old_status,
        "to": new_status,
        "is_terminal": new_status in TERMINAL_STATUSES,
    }
    events.append(event)
    return event

def active_ticket_count(statuses):
    return sum(1 for s in statuses if s in ACTIVE_STATUSES)

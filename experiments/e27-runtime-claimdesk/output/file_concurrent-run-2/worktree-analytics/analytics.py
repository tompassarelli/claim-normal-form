
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES, ACTIVE_STATUSES

# suspended is neither active nor terminal: excluded from workload metrics but resumable
SUSPENDED_STATUS = "suspended"

events = []

def track_transition(ticket_id, old_status, new_status):
    event = {
        "ticket": ticket_id,
        "from": old_status,
        "to": new_status,
        "is_terminal": new_status in TERMINAL_STATUSES,
        "is_suspended": new_status == SUSPENDED_STATUS,
    }
    events.append(event)
    return event

def active_ticket_count(statuses):
    # suspended is intentionally excluded: it is not active work
    return sum(1 for s in statuses if s in ACTIVE_STATUSES)

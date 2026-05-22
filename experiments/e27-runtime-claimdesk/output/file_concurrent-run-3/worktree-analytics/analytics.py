
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES, ACTIVE_STATUSES, SUSPENDED_STATUSES

events = []

def track_transition(ticket_id, old_status, new_status):
    event = {
        "ticket": ticket_id,
        "from": old_status,
        "to": new_status,
        "is_terminal": new_status in TERMINAL_STATUSES,
        # suspended = paused, not closed; excluded from active workload but resumable
        "is_suspended": new_status in SUSPENDED_STATUSES,
    }
    events.append(event)
    return event

def active_ticket_count(statuses):
    # ACTIVE_STATUSES excludes suspended — suspended tickets are paused, not active work
    return sum(1 for s in statuses if s in ACTIVE_STATUSES)

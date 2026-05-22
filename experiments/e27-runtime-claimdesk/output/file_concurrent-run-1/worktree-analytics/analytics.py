
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES, ACTIVE_STATUSES

# "suspended" is intentionally absent from ACTIVE_STATUSES: suspended tickets are
# paused/frozen and must not be counted as active workload. workflow.py is
# authoritative; this constant encodes the assumption so violations are visible.
_SUSPENDED_STATUS = "suspended"

events = []

def track_transition(ticket_id, old_status, new_status):
    event = {
        "ticket": ticket_id,
        "from": old_status,
        "to": new_status,
        "is_terminal": new_status in TERMINAL_STATUSES,
        "is_suspended": new_status == _SUSPENDED_STATUS,
    }
    events.append(event)
    return event

def active_ticket_count(statuses):
    # Explicitly exclude suspended even if ACTIVE_STATUSES changes unexpectedly.
    return sum(1 for s in statuses if s in ACTIVE_STATUSES and s != _SUSPENDED_STATUS)

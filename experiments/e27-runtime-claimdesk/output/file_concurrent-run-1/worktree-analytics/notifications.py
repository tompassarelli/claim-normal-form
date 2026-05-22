
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES

# "suspended" is non-terminal: subscribers are notified on suspension and on
# resume. Suppressing these notifications would hide ticket state changes from
# stakeholders waiting on paused work.
_SUSPENDED_STATUS = "suspended"

subscribers = {}

def subscribe(ticket_id, email):
    subscribers.setdefault(ticket_id, []).append(email)

def notify_transition(ticket_id, old_status, new_status):
    # Terminal transitions (closed, archived) are silent — no further action needed.
    # Suspended is NOT terminal; notify so subscribers know the ticket is paused.
    if new_status in TERMINAL_STATUSES:
        return []
    emails = subscribers.get(ticket_id, [])
    return [f"Notification to {e}: {old_status} -> {new_status}" for e in emails]

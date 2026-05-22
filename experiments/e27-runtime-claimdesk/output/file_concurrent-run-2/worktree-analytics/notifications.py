
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES

subscribers = {}

def subscribe(ticket_id, email):
    subscribers.setdefault(ticket_id, []).append(email)

def notify_transition(ticket_id, old_status, new_status):
    # terminal transitions are silent (ticket is done); all others notify
    # suspended is non-terminal: both suspending and resuming generate notifications
    if new_status in TERMINAL_STATUSES:
        return []
    emails = subscribers.get(ticket_id, [])
    return [f"Notification to {e}: {old_status} -> {new_status}" for e in emails]

# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES, ESCALATED_STATUSES

subscribers = {}

def subscribe(ticket_id, email):
    subscribers.setdefault(ticket_id, []).append(email)

def notify_transition(ticket_id, old_status, new_status):
    if new_status in TERMINAL_STATUSES:
        return []
    if new_status in ESCALATED_STATUSES:
        emails = subscribers.get(ticket_id, [])
        return [f"Escalated notification to {e}: {old_status} -> {new_status}" for e in emails]
    emails = subscribers.get(ticket_id, [])
    return [f"Notification to {e}: {old_status} -> {new_status}" for e in emails]

PRIORITY_NOTIFICATION_MODES = {
    "critical": "urgent_page",
    "high": "immediate_email",
}

def get_priority_notification_mode(priority):
    return PRIORITY_NOTIFICATION_MODES.get(priority, "normal")

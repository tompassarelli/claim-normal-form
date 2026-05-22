
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

def notify_priority(ticket_id, priority, contact_email=None):
    emails = list(subscribers.get(ticket_id, []))
    if contact_email:
        emails = emails + [contact_email]
    if priority == "high":
        return [f"Email notification to {e}: high priority ticket {ticket_id}" for e in emails]
    if priority == "critical":
        return [f"Urgent page to {e}: CRITICAL priority ticket {ticket_id}" for e in emails]
    return []

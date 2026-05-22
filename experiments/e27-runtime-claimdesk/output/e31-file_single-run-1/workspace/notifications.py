
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES

subscribers = {}

def subscribe(ticket_id, email):
    subscribers.setdefault(ticket_id, []).append(email)

def notify_transition(ticket_id, old_status, new_status):
    if new_status in TERMINAL_STATUSES:
        return []
    emails = subscribers.get(ticket_id, [])
    if new_status == "escalated":
        return [f"URGENT Notification to {e}: ticket escalated ({old_status} -> escalated)" for e in emails]
    if old_status == "escalated" and new_status == "in_progress":
        return [f"Notification to {e}: escalation lifted (escalated -> {new_status})" for e in emails]
    return [f"Notification to {e}: {old_status} -> {new_status}" for e in emails]

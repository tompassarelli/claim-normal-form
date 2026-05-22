
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES, ESCALATED_STATUSES

subscribers = {}

def subscribe(ticket_id, email):
    subscribers.setdefault(ticket_id, []).append(email)

def notify_created(ticket_id, priority, contact_email=""):
    """Send creation notifications based on priority.

    high     → immediate email to contact and subscribers
    critical → urgent page to contact and subscribers
    """
    recipients = list(subscribers.get(ticket_id, []))
    if contact_email and contact_email not in recipients:
        recipients.append(contact_email)
    if not recipients:
        return []
    if priority == "critical":
        return [f"URGENT PAGE to {e}: ticket {ticket_id} created at critical priority" for e in recipients]
    if priority == "high":
        return [f"Immediate email to {e}: ticket {ticket_id} created at high priority" for e in recipients]
    return []

def notify_transition(ticket_id, old_status, new_status, priority="normal"):
    if new_status in TERMINAL_STATUSES:
        return []
    emails = subscribers.get(ticket_id, [])
    if new_status in ESCALATED_STATUSES:
        prefix = "URGENT PAGE" if priority == "critical" else "Escalated notification"
        return [f"{prefix} to {e}: {old_status} -> {new_status}" for e in emails]
    return [f"Notification to {e}: {old_status} -> {new_status}" for e in emails]

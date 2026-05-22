
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import (TERMINAL_STATUSES, ESCALATED_STATUSES,
                      EMAIL_NOTIFY_PRIORITIES, PAGE_NOTIFY_PRIORITIES)

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

def notify_priority(ticket_id, priority: str, recipient_emails: list) -> list:
    """Emit notifications appropriate for the given priority level.

    high  → immediate email to all recipients
    critical → urgent page to all recipients (plus email)
    low/normal → no proactive notification
    """
    out = []
    if priority in EMAIL_NOTIFY_PRIORITIES:
        for e in recipient_emails:
            out.append(f"URGENT email to {e}: ticket {ticket_id} priority={priority}")
    if priority in PAGE_NOTIFY_PRIORITIES:
        for e in recipient_emails:
            out.append(f"URGENT PAGE to {e}: ticket {ticket_id} priority={priority}")
    return out


# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES, ACTIVE_STATUSES, ESCALATED_STATUSES, PRIORITY_SLA_HOURS

events = []

def track_transition(ticket_id, old_status, new_status, priority=None):
    event = {
        "ticket": ticket_id,
        "from": old_status,
        "to": new_status,
        "is_terminal": new_status in TERMINAL_STATUSES,
        "is_escalated": new_status in ESCALATED_STATUSES,
        "priority": priority,
        "sla_hours": PRIORITY_SLA_HOURS.get(priority) if priority else None,
    }
    events.append(event)
    return event

def active_ticket_count(statuses):
    work_statuses = ACTIVE_STATUSES | ESCALATED_STATUSES
    return sum(1 for s in statuses if s in work_statuses)

def tickets_by_priority(tickets):
    result = {}
    for t in tickets:
        p = getattr(t, "priority", "normal")
        result.setdefault(p, []).append(t)
    return result

def sla_report(tickets):
    report = {p: {"sla_hours": h, "tickets": []} for p, h in PRIORITY_SLA_HOURS.items()}
    for t in tickets:
        p = getattr(t, "priority", "normal")
        if p not in report:
            p = "normal"
        report[p]["tickets"].append(t.id)
    return report

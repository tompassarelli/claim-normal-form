# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES, ACTIVE_STATUSES, ESCALATED_STATUSES

events = []

def track_transition(ticket_id, old_status, new_status):
    event = {
        "ticket": ticket_id,
        "from": old_status,
        "to": new_status,
        "is_terminal": new_status in TERMINAL_STATUSES,
        "is_escalated": new_status in ESCALATED_STATUSES,
    }
    events.append(event)
    return event

def active_ticket_count(statuses):
    work_statuses = ACTIVE_STATUSES | ESCALATED_STATUSES
    return sum(1 for s in statuses if s in work_statuses)

PRIORITY_SLA_TARGETS = {
    "critical": 1,
    "high": 4,
    "low": 24,
    "normal": 8,
}

def track_priority_assignment(ticket_id, priority):
    event = {
        "ticket": ticket_id,
        "priority": priority,
        "response_target": PRIORITY_SLA_TARGETS.get(priority),
        "is_critical": priority == "critical",
    }
    events.append(event)
    return event

def sla_compliance(priority, elapsed_hours):
    target = PRIORITY_SLA_TARGETS.get(priority)
    if target is None:
        return True
    return elapsed_hours <= target

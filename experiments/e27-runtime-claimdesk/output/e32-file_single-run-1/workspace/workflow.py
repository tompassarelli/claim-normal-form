
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

TERMINAL_STATUSES = {"archived", "resolved", "closed"}
ACTIVE_STATUSES = {"on_hold", "in_progress", "open"}
ESCALATED_STATUSES = {"escalated"}
ALL_STATUSES = {"escalated", "archived", "resolved", "closed", "on_hold", "in_progress", "open"}

VALID_TRANSITIONS = {
    "open": {"in_progress", "closed"},
    "closed": {"archived"},
    "in_progress": {"on_hold", "closed", "resolved", "escalated"},
    "on_hold": {"in_progress", "closed"},
    "resolved": {"archived"},
    "escalated": {"in_progress", "closed"},
}

PRIORITIES = {"low", "normal", "high", "critical"}

# Response target in hours for each priority level
PRIORITY_SLA_HOURS = {
    "low": 24,
    "normal": 8,
    "high": 4,
    "critical": 1,
}

def is_active(status):
    return status in ACTIVE_STATUSES

def is_terminal(status):
    return status in TERMINAL_STATUSES

def is_escalated(status):
    return status in ESCALATED_STATUSES

def is_valid_priority(priority):
    return priority in PRIORITIES

def sla_hours(priority):
    return PRIORITY_SLA_HOURS.get(priority)

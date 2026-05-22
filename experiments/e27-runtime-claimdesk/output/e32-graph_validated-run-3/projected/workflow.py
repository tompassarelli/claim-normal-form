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

def is_active(status):
    return status in ACTIVE_STATUSES

def is_terminal(status):
    return status in TERMINAL_STATUSES

def is_escalated(status):
    return status in ESCALATED_STATUSES

PRIORITY_LEVELS = {
    "critical": {"response_target": 1, "auto_escalate": True, "escalates_to": "escalated", "required_role": "senior", "notification_mode": "urgent_page"},
    "high": {"response_target": 4, "notification_mode": "immediate_email"},
    "low": {"response_target": 24},
    "normal": {"response_target": 8},
}

def get_response_target(priority):
    config = PRIORITY_LEVELS.get(priority, PRIORITY_LEVELS.get("normal", {}))
    return config.get("response_target")

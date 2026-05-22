# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

TERMINAL_STATUSES = {"archived", "resolved", "closed"}
ACTIVE_STATUSES = {"on_hold", "in_progress", "open"}
BLOCKED_STATUSES = {"suspended"}
ALL_STATUSES = {"suspended", "archived", "resolved", "closed", "on_hold", "in_progress", "open"}

VALID_TRANSITIONS = {
    "open": {"in_progress", "closed"},
    "closed": {"archived"},
    "resolved": {"archived"},
    "in_progress": {"on_hold", "closed", "resolved", "suspended"},
    "on_hold": {"in_progress", "closed", "suspended"},
    "suspended": {"in_progress", "closed"},
}

def is_active(status):
    return status in ACTIVE_STATUSES

def is_terminal(status):
    return status in TERMINAL_STATUSES

def is_blocked(status):
    return status in BLOCKED_STATUSES

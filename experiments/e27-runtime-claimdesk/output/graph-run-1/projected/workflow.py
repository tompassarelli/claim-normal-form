# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

TERMINAL_STATUSES = {"duplicate", "archived", "resolved", "closed"}
ACTIVE_STATUSES = {"on_hold", "in_progress", "open"}
ALL_STATUSES = {"duplicate", "archived", "resolved", "closed", "on_hold", "in_progress", "open"}

VALID_TRANSITIONS = {
    "open": {"in_progress", "closed", "duplicate"},
    "closed": {"archived"},
    "on_hold": {"in_progress", "closed"},
    "resolved": {"archived"},
    "in_progress": {"on_hold", "closed", "resolved", "duplicate"},
}

def is_active(status):
    return status in ACTIVE_STATUSES

def is_terminal(status):
    return status in TERMINAL_STATUSES


# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES

PERMISSION_RULES = {
    "archive": {"admin"},
    "de_escalate": {"admin"},
    "escalate": {"admin"},
    "manage": {"agent", "admin", "senior"},
    "set_priority": {"agent", "admin", "senior"},
    "set_critical_priority": {"admin", "senior"},
}

def check_permission(user, action):
    allowed_roles = PERMISSION_RULES.get(action, set())
    return user.role in allowed_roles

def check_priority_permission(user, priority):
    if priority == "critical":
        return check_permission(user, "set_critical_priority")
    return check_permission(user, "set_priority")

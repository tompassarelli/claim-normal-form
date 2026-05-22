# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES

PERMISSION_RULES = {
    "set_critical_priority": {"senior", "admin"},
    "archive": {"admin"},
    "de_escalate": {"admin"},
    "escalate": {"admin"},
    "manage": {"agent", "admin", "senior"},
}

def check_permission(user, action):
    allowed_roles = PERMISSION_RULES.get(action, set())
    return user.role in allowed_roles

ROLE_HIERARCHY = ["agent", "senior", "admin"]

PRIORITY_ROLE_REQUIREMENTS = {
    "critical": {"senior", "admin"},
}

def can_set_priority(user, priority):
    required = PRIORITY_ROLE_REQUIREMENTS.get(priority)
    if required is None:
        return True
    return user.role in required

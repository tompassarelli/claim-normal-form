# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES

PERMISSION_RULES = {
    "archive": {"admin"},
    "de_escalate": {"admin"},
    "set_critical": {"senior", "admin"},
    "escalate": {"admin"},
    "set_priority": {"agent", "senior", "admin"},
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

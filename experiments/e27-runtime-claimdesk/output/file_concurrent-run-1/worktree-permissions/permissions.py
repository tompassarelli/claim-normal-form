
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES

PERMISSION_RULES = {
    "archive": {"admin"},
    "manage": {"agent", "admin"},
    # suspend: pause active work without closing; not terminal, not counted in active workload
    "suspend": {"agent", "admin"},
    # resume: return a suspended ticket to in_progress
    "resume": {"agent", "admin"},
}

def check_permission(user, action):
    allowed_roles = PERMISSION_RULES.get(action, set())
    return user.role in allowed_roles

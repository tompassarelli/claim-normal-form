
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES

PERMISSION_RULES = {
    "archive": {"admin"},
    "manage": {"agent", "admin"},
    "suspend": {"agent", "admin"},
}

def check_permission(user, action):
    allowed_roles = PERMISSION_RULES.get(action, set())
    return user.role in allowed_roles

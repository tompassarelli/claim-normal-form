
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES

# Suspended is neither active nor terminal: paused, resumable, excluded from workload metrics.
SUSPENDED_STATUSES = ["suspended"]

PERMISSION_RULES = {
    "archive": {"admin"},
    "manage": {"agent", "admin"},
    # suspend: management-level action — pausing active work requires admin authority
    "suspend": {"admin"},
    # resume: restoring suspended work to in_progress; agents may self-resume
    "resume": {"agent", "admin"},
}

def check_permission(user, action):
    allowed_roles = PERMISSION_RULES.get(action, set())
    return user.role in allowed_roles

def is_suspended_status(status):
    return status in SUSPENDED_STATUSES

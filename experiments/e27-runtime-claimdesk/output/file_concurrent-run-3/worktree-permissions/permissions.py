
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES

PERMISSION_RULES = {
    "archive": {"admin"},
    "manage": {"agent", "admin"},
    "suspend": {"agent", "admin"},
    "resume": {"agent", "admin"},
}

# suspended is not active (excluded from workload) and not terminal (can be resumed)
SUSPENDED_STATUS = "suspended"

def check_permission(user, action):
    allowed_roles = PERMISSION_RULES.get(action, set())
    return user.role in allowed_roles

def can_suspend(user, ticket):
    return (
        check_permission(user, "suspend")
        and ticket.status not in TERMINAL_STATUSES
        and ticket.status != SUSPENDED_STATUS
    )

def can_resume(user, ticket):
    return check_permission(user, "resume") and ticket.status == SUSPENDED_STATUS

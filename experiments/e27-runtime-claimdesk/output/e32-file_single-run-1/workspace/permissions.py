
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES

PERMISSION_RULES = {
    "archive": {"admin"},
    "de_escalate": {"admin"},
    "escalate": {"admin"},
    "manage": {"agent", "admin", "senior"},
    # critical tickets may only be assigned to senior agents or admins
    "assign_critical": {"admin", "senior"},
}

def check_permission(user, action):
    allowed_roles = PERMISSION_RULES.get(action, set())
    return user.role in allowed_roles

def can_handle_ticket(user, ticket):
    """Return True if the user's role allows handling this ticket's priority."""
    if ticket.priority == "critical":
        return check_permission(user, "assign_critical")
    return check_permission(user, "manage")

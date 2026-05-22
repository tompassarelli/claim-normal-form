
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES

PERMISSION_RULES = {
    "archive": {"admin"},
    "de_escalate": {"admin"},
    "escalate": {"admin"},
    "manage": {"agent", "admin", "senior"},
    # high priority can be set by any agent; critical requires senior/admin
    # because critical auto-escalates and triggers pages
    "set_high_priority": {"agent", "senior", "admin"},
    "set_critical_priority": {"senior", "admin"},
}

def check_permission(user, action):
    allowed_roles = PERMISSION_RULES.get(action, set())
    return user.role in allowed_roles

def check_priority_permission(user, priority: str) -> bool:
    """Return True if user may assign the given priority to a ticket."""
    if priority == "critical":
        return check_permission(user, "set_critical_priority")
    if priority == "high":
        return check_permission(user, "set_high_priority")
    return check_permission(user, "manage")

def can_handle_priority(user, priority: str) -> bool:
    """Return True if user is eligible to be assigned a ticket at this priority."""
    from workflow import requires_senior
    if requires_senior(priority):
        return user.role in {"senior", "admin"}
    return True

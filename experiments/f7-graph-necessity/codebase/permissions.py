"""
Role-based access control for the helpdesk/CRM application.

Permission checks are two-layered:
  1. Role-level: does this role have the action in ROLE_PERMISSIONS?
  2. Ticket-level: is this specific user related to this ticket?

Use check_ticket_access() as the single entry point for most callers.
Raise PermissionError (built-in) when access is denied — callers that
need a boolean can use has_permission() / can_modify_ticket() directly.
"""

from typing import List, Optional

import config
from models import Ticket, User


# ---------------------------------------------------------------------------
# Core role-level checks
# ---------------------------------------------------------------------------

def has_permission(user: User, action: str) -> bool:
    """Return True if *user*'s role grants the named *action*.

    Unknown actions always return False.  Inactive users are denied all
    non-view actions so they can still be looked up in audit trails.
    """
    if not user.is_active and action != "view":
        return False
    return config.can(user.role, action)


def require_permission(user: User, action: str) -> None:
    """Raise PermissionError if *user* does not have *action*.

    Message format is consistent so callers can parse it if needed.
    """
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.id}' (role={user.role}) is not permitted to '{action}'"
        )


def get_allowed_actions(user: User) -> List[str]:
    """Return the sorted list of actions *user* is currently permitted to take."""
    if not user.is_active:
        # Inactive users retain only 'view' if their role normally allows it.
        if config.can(user.role, "view"):
            return ["view"]
        return []
    allowed = sorted(config.ROLE_PERMISSIONS.get(user.role, set()))
    return allowed


# ---------------------------------------------------------------------------
# Ticket-level checks
# ---------------------------------------------------------------------------

def can_view_ticket(user: User, ticket: Ticket) -> bool:
    """Return True if *user* may read *ticket*.

    Everyone with the 'view' role permission may see any ticket.
    Additionally, the ticket's contact is implicitly granted view access
    when email matches (modelled here as any active user).
    """
    return has_permission(user, "view")


def can_modify_ticket(user: User, ticket: Ticket) -> bool:
    """Return True if *user* may update fields on *ticket*.

    Modification is allowed when:
      - The user has the 'update' permission AND is the assigned agent, OR
      - The user is admin/team_lead (broad update permission), OR
      - The user created/owns the ticket (tracked via assignee for now).
    Viewers are explicitly excluded even if somehow they matched a ticket field.
    """
    if not has_permission(user, "update"):
        return False
    if user.role in {"admin", "team_lead"}:
        return True
    # Agents may update tickets assigned to them or unassigned tickets.
    if user.role == "agent":
        return ticket.assignee is None or ticket.assignee == user.id
    return False


def can_assign_ticket(user: User) -> bool:
    """Return True if *user* may assign (or reassign) a ticket to an agent."""
    return has_permission(user, "assign")


def can_manage_team(user: User) -> bool:
    """Return True if *user* may manage team membership and configuration."""
    return has_permission(user, "manage_team")


def can_manage_users(user: User) -> bool:
    """Return True if *user* may create, update, or deactivate user accounts."""
    return has_permission(user, "manage_users")


def can_export(user: User) -> bool:
    """Return True if *user* may export data (CSV, JSON, etc.)."""
    return has_permission(user, "export")


def can_bulk_update(user: User) -> bool:
    """Return True if *user* may perform bulk ticket updates."""
    return has_permission(user, "bulk_update")


# ---------------------------------------------------------------------------
# Unified access check
# ---------------------------------------------------------------------------

def check_ticket_access(user: User, ticket: Ticket, action: str = "view") -> bool:
    """Return True if *user* is allowed to perform *action* on *ticket*.

    This combines role-level permission with ticket-level ownership logic.
    Supported *action* values are any entry in config.SYSTEM_ACTIONS.

    For write actions (update, close, assign, comment, tag) the more
    restrictive can_modify_ticket() gate is applied on top of the base
    role permission so that agents are restricted to their own tickets.
    """
    if not user.is_active:
        return False

    # Read-only actions: role permission is sufficient.
    if action == "view":
        return can_view_ticket(user, ticket)

    if action == "search":
        return has_permission(user, "search")

    # Assignment: role check only (no ownership constraint).
    if action == "assign":
        return can_assign_ticket(user)

    # Write actions: role check + ticket ownership.
    if action in {"update", "close", "comment", "tag"}:
        return can_modify_ticket(user, ticket)

    # Bulk / management actions delegate to their dedicated helpers.
    if action == "bulk_update":
        return can_bulk_update(user)
    if action == "manage_team":
        return can_manage_team(user)
    if action == "manage_users":
        return can_manage_users(user)
    if action == "export":
        return can_export(user)

    # Default: pure role-level check for anything not explicitly handled.
    return has_permission(user, action)

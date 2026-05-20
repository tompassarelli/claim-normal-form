"""
Input validation and business-rule checks for the helpdesk/CRM application.

Every public function returns a list of human-readable error strings.
An empty list means the input is valid.  Functions never raise on
bad input — they collect all errors so callers can surface them all at once.

Internal helpers (_check_ticket_exists, _check_user_exists) return a single
error string or None, following the same "None means OK" convention used
throughout the module.
"""

import re
from typing import List, Optional

from store import get_ticket, get_user, count_comments, get_tag
from config import (
    STATUSES,
    PRIORITIES,
    SOURCES,
    MAX_TAGS_PER_TICKET,
    MAX_COMMENT_LENGTH,
    ROLES,
    SYSTEM_ACTIONS,
)
from workflow import is_valid_transition, is_terminal

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _check_ticket_exists(ticket_id: str) -> Optional[str]:
    """Return an error string if the ticket does not exist, else None."""
    if not ticket_id or not ticket_id.strip():
        return "ticket_id must not be empty"
    if get_ticket(ticket_id) is None:
        return f"Ticket not found: {ticket_id!r}"
    return None


def _check_user_exists(user_id: str) -> Optional[str]:
    """Return an error string if the user does not exist, else None."""
    if not user_id or not user_id.strip():
        return "user_id must not be empty"
    if get_user(user_id) is None:
        return f"User not found: {user_id!r}"
    return None


def _check_email(email: str, field_name: str = "email") -> Optional[str]:
    if not email or not email.strip():
        return f"{field_name} must not be empty"
    if not _EMAIL_RE.match(email.strip()):
        return f"{field_name} is not a valid email address: {email!r}"
    return None


# ---------------------------------------------------------------------------
# Ticket creation
# ---------------------------------------------------------------------------

def validate_ticket_create(
    title: str,
    description: str,
    priority: str,
    source: str,
    contact_email: str,
) -> List[str]:
    """Validate the fields required to create a new ticket."""
    errors: List[str] = []

    if not title or not title.strip():
        errors.append("title must not be empty")
    elif len(title.strip()) > 200:
        errors.append("title must be 200 characters or fewer")

    if not description or not description.strip():
        errors.append("description must not be empty")

    if priority not in PRIORITIES:
        errors.append(
            f"priority {priority!r} is not valid; choose from {sorted(PRIORITIES)}"
        )

    if source not in SOURCES:
        errors.append(
            f"source {source!r} is not valid; choose from {sorted(SOURCES)}"
        )

    email_err = _check_email(contact_email, "contact_email")
    if email_err:
        errors.append(email_err)

    return errors


# ---------------------------------------------------------------------------
# Ticket update
# ---------------------------------------------------------------------------

def validate_ticket_update(ticket_id: str, **fields) -> List[str]:
    """Validate a partial update to an existing ticket.

    Checks that the ticket exists first, then validates any recognized
    fields that were supplied.
    """
    errors: List[str] = []

    err = _check_ticket_exists(ticket_id)
    if err:
        errors.append(err)
        return errors  # nothing more to check if ticket is missing

    ticket = get_ticket(ticket_id)

    if is_terminal(ticket.status):
        # Updates to terminal tickets are blocked to preserve history.
        errors.append(
            f"Ticket {ticket_id!r} is {ticket.status!r} and cannot be modified"
        )
        return errors

    if "title" in fields:
        title = fields["title"]
        if not title or not str(title).strip():
            errors.append("title must not be empty")
        elif len(str(title).strip()) > 200:
            errors.append("title must be 200 characters or fewer")

    if "priority" in fields and fields["priority"] not in PRIORITIES:
        errors.append(
            f"priority {fields['priority']!r} is not valid; "
            f"choose from {sorted(PRIORITIES)}"
        )

    if "status" in fields and fields["status"] not in STATUSES:
        errors.append(
            f"status {fields['status']!r} is not valid; "
            f"choose from {sorted(STATUSES)}"
        )

    if "contact_email" in fields:
        email_err = _check_email(fields["contact_email"], "contact_email")
        if email_err:
            errors.append(email_err)

    return errors


# ---------------------------------------------------------------------------
# Transition
# ---------------------------------------------------------------------------

def validate_transition(ticket_id: str, new_status: str) -> List[str]:
    """Validate that a status transition is allowed for the given ticket."""
    errors: List[str] = []

    err = _check_ticket_exists(ticket_id)
    if err:
        errors.append(err)
        return errors

    if new_status not in STATUSES:
        errors.append(
            f"status {new_status!r} is not valid; choose from {sorted(STATUSES)}"
        )
        return errors

    ticket = get_ticket(ticket_id)
    if not is_valid_transition(ticket.status, new_status):
        errors.append(
            f"Cannot transition ticket {ticket_id!r} from "
            f"{ticket.status!r} to {new_status!r}"
        )

    return errors


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------

def validate_assignment(ticket_id: str, user_id: str) -> List[str]:
    """Validate that *user_id* may be assigned to *ticket_id*."""
    errors: List[str] = []

    ticket_err = _check_ticket_exists(ticket_id)
    if ticket_err:
        errors.append(ticket_err)

    user_err = _check_user_exists(user_id)
    if user_err:
        errors.append(user_err)

    if errors:
        return errors

    ticket = get_ticket(ticket_id)
    user = get_user(user_id)

    if is_terminal(ticket.status):
        errors.append(
            f"Cannot assign ticket {ticket_id!r}: "
            f"it is already {ticket.status!r}"
        )
        return errors

    if not user.is_active:
        errors.append(f"User {user_id!r} is not active and cannot be assigned tickets")

    if user.role not in ROLES or "assign" not in (SYSTEM_ACTIONS.get(user.role) or []):
        # Roles that explicitly cannot receive assignments
        if user.role not in {"agent", "team_lead", "admin"}:
            errors.append(
                f"User {user_id!r} has role {user.role!r} which does not allow assignment"
            )

    # Check workload cap
    from store import count_assigned_tickets  # local import — store is not yet known
    assigned_count = count_assigned_tickets(user_id)
    if assigned_count >= user.max_tickets:
        errors.append(
            f"User {user_id!r} already has {assigned_count} assigned ticket(s) "
            f"(max {user.max_tickets})"
        )

    return errors


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def validate_comment(
    ticket_id: str,
    body: str,
    is_internal: bool,
) -> List[str]:
    """Validate a new comment being added to a ticket."""
    errors: List[str] = []

    err = _check_ticket_exists(ticket_id)
    if err:
        errors.append(err)
        return errors

    ticket = get_ticket(ticket_id)

    if not body or not body.strip():
        errors.append("comment body must not be empty")
    elif len(body) > MAX_COMMENT_LENGTH:
        errors.append(
            f"comment body exceeds maximum length of {MAX_COMMENT_LENGTH} characters "
            f"(got {len(body)})"
        )

    # External comments are not allowed on closed tickets
    if not is_internal and ticket.status == "closed":
        errors.append(
            f"Cannot add an external comment to ticket {ticket_id!r}: "
            "ticket is closed"
        )

    return errors


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def validate_tag(ticket_id: str, tag_name: str) -> List[str]:
    """Validate adding *tag_name* to *ticket_id*."""
    errors: List[str] = []

    err = _check_ticket_exists(ticket_id)
    if err:
        errors.append(err)
        return errors

    if not tag_name or not tag_name.strip():
        errors.append("tag_name must not be empty")
        return errors

    ticket = get_ticket(ticket_id)

    if tag_name in ticket.tags:
        errors.append(f"Ticket {ticket_id!r} already has tag {tag_name!r}")

    if len(ticket.tags) >= MAX_TAGS_PER_TICKET:
        errors.append(
            f"Ticket {ticket_id!r} already has {len(ticket.tags)} tag(s); "
            f"maximum is {MAX_TAGS_PER_TICKET}"
        )

    # Ensure the tag is registered in the system (optional — soft check)
    if get_tag(tag_name) is None:
        errors.append(f"Tag {tag_name!r} does not exist in the system")

    return errors


# ---------------------------------------------------------------------------
# SLA policies
# ---------------------------------------------------------------------------

def validate_sla_policy(
    name: str,
    response_minutes: int,
    resolution_minutes: int,
) -> List[str]:
    """Validate the fields for creating or updating an SLA policy."""
    errors: List[str] = []

    if not name or not str(name).strip():
        errors.append("SLA policy name must not be empty")
    elif len(str(name).strip()) > 100:
        errors.append("SLA policy name must be 100 characters or fewer")

    if not isinstance(response_minutes, int) or response_minutes < 1:
        errors.append(
            f"response_minutes must be a positive integer (got {response_minutes!r})"
        )

    if not isinstance(resolution_minutes, int) or resolution_minutes < 1:
        errors.append(
            f"resolution_minutes must be a positive integer (got {resolution_minutes!r})"
        )

    if (
        isinstance(response_minutes, int)
        and isinstance(resolution_minutes, int)
        and response_minutes > 0
        and resolution_minutes > 0
        and response_minutes >= resolution_minutes
    ):
        errors.append(
            "response_minutes must be less than resolution_minutes "
            f"(got {response_minutes} >= {resolution_minutes})"
        )

    return errors


# ---------------------------------------------------------------------------
# User creation
# ---------------------------------------------------------------------------

def validate_user_create(name: str, email: str, role: str) -> List[str]:
    """Validate the fields required to create a new user."""
    errors: List[str] = []

    if not name or not name.strip():
        errors.append("name must not be empty")
    elif len(name.strip()) > 120:
        errors.append("name must be 120 characters or fewer")

    email_err = _check_email(email, "email")
    if email_err:
        errors.append(email_err)

    if role not in ROLES:
        errors.append(
            f"role {role!r} is not valid; choose from {sorted(ROLES)}"
        )

    return errors

"""
Ticket state machine and lifecycle helpers.

VALID_TRANSITIONS encodes the allowed edges in the status graph:

    open  ──►  in_progress  ──►  resolved  ──►  closed
     ▲              │                │
     └──────────────┘                │
     └───────────────────────────────┘  (reopen from resolved)

Closed is terminal — no outbound edges.
"""

import time
from typing import List, Optional

from store import get_ticket, update_ticket
from config import TERMINAL_STATUSES, ACTIVE_STATUSES
from events import _run_hooks, emit

# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------

VALID_TRANSITIONS = {
    "open":        ["in_progress", "closed"],
    "in_progress": ["resolved", "open", "on_hold"],
    "resolved":    ["closed", "open"],
    "closed":      ["archived"],
    "on_hold":     ["in_progress", "closed"],
    "archived":    ["open"],
}


# ---------------------------------------------------------------------------
# Predicate helpers
# ---------------------------------------------------------------------------

def is_valid_transition(from_status: str, to_status: str) -> bool:
    """Return True if moving from *from_status* to *to_status* is allowed."""
    return to_status in VALID_TRANSITIONS.get(from_status, [])


def is_terminal(status: str) -> bool:
    """Return True if *status* is a terminal (no-exit) state."""
    return status in TERMINAL_STATUSES


def is_active(status: str) -> bool:
    """Return True if *status* counts as an active (non-terminal) state."""
    return status in ACTIVE_STATUSES


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _now_ts() -> float:
    return time.time()


def _parse_ts(value: str) -> float:
    """Parse a unix-timestamp string, returning 0.0 on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def get_ticket_age_minutes(ticket_id: str) -> int:
    """Return minutes elapsed since the ticket was created.

    Returns 0 if the ticket is not found or has no created_at timestamp.
    """
    ticket = get_ticket(ticket_id)
    if ticket is None:
        return 0
    created = _parse_ts(ticket.created_at)
    if created == 0.0:
        return 0
    return int((_now_ts() - created) / 60)


def get_time_in_status_minutes(ticket_id: str) -> int:
    """Return minutes elapsed since the ticket last changed status.

    Falls back to the created_at timestamp when no transition record is
    available, so the result is always a meaningful lower bound.
    """
    ticket = get_ticket(ticket_id)
    if ticket is None:
        return 0
    # updated_at is refreshed on every status change by update_ticket
    reference = _parse_ts(ticket.updated_at) or _parse_ts(ticket.created_at)
    if reference == 0.0:
        return 0
    return int((_now_ts() - reference) / 60)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_available_transitions(ticket_id: str) -> List[str]:
    """Return the list of statuses the ticket may move to from its current state.

    Returns an empty list if the ticket is not found.
    """
    ticket = get_ticket(ticket_id)
    if ticket is None:
        return []
    return list(VALID_TRANSITIONS.get(ticket.status, []))


# ---------------------------------------------------------------------------
# Core transition
# ---------------------------------------------------------------------------

def transition_ticket(ticket_id: str, new_status: str, user_id: str = "") -> None:
    """Move *ticket_id* to *new_status*, firing pre/post transition events.

    Raises ValueError if the ticket does not exist or the transition is not
    allowed from the current status.
    """
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise ValueError(f"Ticket not found: {ticket_id!r}")

    old_status = ticket.status

    if not is_valid_transition(old_status, new_status):
        raise ValueError(
            f"Invalid transition for ticket {ticket_id!r}: "
            f"{old_status!r} -> {new_status!r}"
        )

    # Pre-transition hooks (legacy path)
    _run_hooks(
        "pre_transition",
        ticket_id=ticket_id,
        old_status=old_status,
        new_status=new_status,
        user_id=user_id,
    )

    # Persist the change
    update_ticket(ticket_id, status=new_status, updated_at=str(_now_ts()))

    # Post-transition events
    emit(
        "ticket.transitioned",
        ticket_id=ticket_id,
        old_status=old_status,
        new_status=new_status,
        user_id=user_id,
    )
    _run_hooks(
        "post_transition",
        ticket_id=ticket_id,
        old_status=old_status,
        new_status=new_status,
        user_id=user_id,
    )

    # Emit a dedicated closed event when entering the terminal state
    if new_status == "closed":
        emit("ticket.closed", ticket_id=ticket_id, user_id=user_id)
        _run_hooks("ticket.closed", ticket_id=ticket_id, user_id=user_id)


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def reopen_ticket(ticket_id: str, user_id: str = "") -> None:
    """Transition a resolved or closed ticket back to open.

    Raises ValueError if the ticket is not in a reopenable state.
    """
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise ValueError(f"Ticket not found: {ticket_id!r}")

    if ticket.status not in ("resolved", "closed", "archived"):
        raise ValueError(
            f"Cannot reopen ticket {ticket_id!r}: "
            f"current status is {ticket.status!r} (expected 'resolved', 'closed', or 'archived')"
        )

    transition_ticket(ticket_id, "open", user_id=user_id)


def close_ticket(ticket_id: str, user_id: str = "") -> None:
    """Transition a ticket directly to closed.

    Raises ValueError if the ticket cannot be closed from its current state.
    """
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise ValueError(f"Ticket not found: {ticket_id!r}")

    if not is_valid_transition(ticket.status, "closed"):
        raise ValueError(
            f"Cannot close ticket {ticket_id!r} from status {ticket.status!r}"
        )

    transition_ticket(ticket_id, "closed", user_id=user_id)

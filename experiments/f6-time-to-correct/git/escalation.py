"""Escalation module for ClaimDesk.

Tracks per-ticket escalation thresholds and checks whether a ticket is
overdue for escalation based on elapsed time since last update.
"""

import time
from typing import Optional, Dict

from core import get_ticket
from config import TERMINAL_STATUSES

# Statuses that are explicitly exempt from escalation.
# TERMINAL_STATUSES covers "closed" and "archived"; "on_hold" is an
# operational hold that should also suppress escalation.
_SKIP_STATUSES = set(TERMINAL_STATUSES) | {"on_hold"}

# In-memory store: ticket_id -> threshold in seconds
_rules: Dict[str, int] = {}


def set_escalation_rule(ticket_id: str, escalate_after_minutes: int = 30) -> None:
    """Register (or overwrite) an escalation threshold for a ticket.

    Args:
        ticket_id: The ticket to watch.
        escalate_after_minutes: Minutes of inactivity before escalation is due.
    """
    _rules[ticket_id] = escalate_after_minutes * 60


def check_escalation(ticket_id: str) -> Optional[dict]:
    """Check whether a ticket is due for escalation.

    Compares elapsed time since ticket.updated_at against the registered
    threshold. Returns an info dict when escalation is due, None otherwise.

    Tickets in closed, archived, or on_hold status are never escalated.

    If the audit module is available, a "escalation_due" action is logged
    when this function fires (i.e., when it returns a non-None result).

    Returns:
        dict with keys {ticket_id, status, updated_at, elapsed_seconds,
                        threshold_seconds} when escalation is due,
        None when the ticket is not due or is exempt.
    """
    threshold = _rules.get(ticket_id)
    if threshold is None:
        return None

    ticket = get_ticket(ticket_id)
    if ticket is None:
        return None

    if ticket.status in _SKIP_STATUSES:
        return None

    try:
        updated_at = int(ticket.updated_at)
    except (ValueError, TypeError):
        return None

    elapsed = int(time.time()) - updated_at
    if elapsed < threshold:
        return None

    info = {
        "ticket_id": ticket_id,
        "status": ticket.status,
        "updated_at": ticket.updated_at,
        "elapsed_seconds": elapsed,
        "threshold_seconds": threshold,
    }

    # Log to audit trail if the audit module is available.
    try:
        from audit import log_action  # type: ignore[import]
        log_action(
            action="escalation_due",
            ticket_id=ticket_id,
            details=info,
        )
    except (ImportError, Exception):
        pass

    return info


def reset_escalation() -> None:
    """Clear all registered escalation rules.

    Intended for use in tests or system resets alongside core.reset_state().
    """
    _rules.clear()

"""Escalation module for ClaimDesk.

Auto-escalation rules: tracks per-ticket thresholds and fires an audit
entry when a ticket has gone too long without activity.

Rules:
- set_escalation_rule(ticket_id, escalate_after_minutes=30)
  Records the threshold for that ticket.
- check_escalation(ticket_id)
  Returns an info dict if the ticket is due for escalation, None/False
  otherwise.  When it fires it also writes an audit entry.
  Skipped for tickets in closed, archived, or on_hold status.
- reset_escalation()
  Clears all escalation data (useful for tests).

Elapsed time is computed as:  now - int(ticket.updated_at)
Threshold is:                  escalate_after_minutes * 60  (seconds)
"""

import time
from typing import Dict, Optional

# ticket_id -> escalate_after_minutes (int)
_rules: Dict[str, int] = {}

# Statuses that suppress escalation
_SKIP_STATUSES = {"closed", "archived", "on_hold"}


def set_escalation_rule(ticket_id: str, escalate_after_minutes: int = 30) -> int:
    """Record an escalation threshold for *ticket_id*.

    Returns the threshold in minutes.
    """
    _rules[ticket_id] = escalate_after_minutes
    return escalate_after_minutes


def check_escalation(ticket_id: str) -> Optional[dict]:
    """Check whether *ticket_id* is due for escalation.

    Returns an info dict when the ticket IS due:
        {
            "ticket_id":              str,
            "escalate_after_minutes": int,
            "elapsed_seconds":        float,
            "threshold_seconds":      int,
        }

    Returns None when:
    - no escalation rule is set for the ticket
    - the ticket cannot be found
    - the ticket status is closed, archived, or on_hold
    - not enough time has elapsed yet
    """
    threshold_minutes = _rules.get(ticket_id)
    if threshold_minutes is None:
        return None

    from core import get_ticket
    ticket = get_ticket(ticket_id)
    if ticket is None:
        return None

    if ticket.status in _SKIP_STATUSES:
        return None

    threshold_seconds = threshold_minutes * 60
    elapsed = time.time() - int(ticket.updated_at)

    if elapsed < threshold_seconds:
        return None

    # Ticket IS due — log to audit trail then return info
    from audit import log_action
    log_action("escalation", ticket_id, user_id="system", priority=ticket.priority)

    return {
        "ticket_id": ticket_id,
        "escalate_after_minutes": threshold_minutes,
        "elapsed_seconds": elapsed,
        "threshold_seconds": threshold_seconds,
    }


def reset_escalation() -> None:
    """Clear all escalation rules (useful for tests)."""
    _rules.clear()

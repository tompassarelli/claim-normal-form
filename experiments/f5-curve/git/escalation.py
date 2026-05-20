"""ClaimDesk escalation module.

Tracks per-ticket escalation rules, checks whether tickets are overdue
for escalation, and can auto-escalate by bumping priority and logging
the event.
"""
from typing import Optional, Dict, List
import time

# Internal state ----------------------------------------------------------
# ticket_id -> {"escalate_after_minutes": int, "set_at": int}
_rules: Dict[str, dict] = {}

# ticket_id -> list of {timestamp, message} dicts
_history: Dict[str, List[dict]] = {}

# Statuses that must never be escalated
_SKIP_STATUSES = {"closed", "archived", "on_hold"}

_PRIORITY_LADDER = ["low", "medium", "high", "urgent"]


# Helpers -----------------------------------------------------------------

def _now() -> int:
    return int(time.time())


def _next_priority(current: str) -> Optional[str]:
    """Return the next-higher priority, or None if already at the top."""
    try:
        idx = _PRIORITY_LADDER.index(current)
    except ValueError:
        return None
    if idx >= len(_PRIORITY_LADDER) - 1:
        return None
    return _PRIORITY_LADDER[idx + 1]


# Public API --------------------------------------------------------------

def set_escalation_rule(ticket_id: str,
                        escalate_after_minutes: int = 30) -> None:
    """Register (or replace) an escalation rule for *ticket_id*."""
    _rules[ticket_id] = {
        "escalate_after_minutes": escalate_after_minutes,
        "set_at": _now(),
    }


def check_escalation(ticket_id: str):
    """Return escalation info if the ticket is due, else None/False.

    Returns None when:
    - no rule exists for the ticket
    - the ticket is in a terminal or held status
    - the ticket hasn't been idle long enough
    """
    from core import get_ticket

    rule = _rules.get(ticket_id)
    if rule is None:
        return None

    ticket = get_ticket(ticket_id)
    if ticket is None:
        return None

    if ticket.status in _SKIP_STATUSES:
        return False

    elapsed_seconds = _now() - int(ticket.updated_at)
    threshold_seconds = rule["escalate_after_minutes"] * 60

    if elapsed_seconds < threshold_seconds:
        return False

    return {
        "ticket_id": ticket_id,
        "current_priority": ticket.priority,
        "next_priority": _next_priority(ticket.priority),
        "elapsed_minutes": elapsed_seconds // 60,
        "threshold_minutes": rule["escalate_after_minutes"],
        "status": ticket.status,
    }


def auto_escalate(ticket_id: str) -> Optional[str]:
    """Escalate the ticket if its rule says so.

    Returns a human-readable message on escalation, or None if nothing
    was done.
    """
    from core import update_ticket

    info = check_escalation(ticket_id)
    if not info:
        return None

    new_priority = info["next_priority"]
    if new_priority is None:
        msg = (f"Ticket {ticket_id} has been idle "
               f"{info['elapsed_minutes']}m but is already at "
               f"highest priority ({info['current_priority']})")
        _history.setdefault(ticket_id, []).append({
            "timestamp": _now(),
            "message": msg,
        })
        return msg

    update_ticket(ticket_id, priority=new_priority)

    msg = (f"Ticket {ticket_id} escalated from "
           f"{info['current_priority']} to {new_priority} "
           f"(idle {info['elapsed_minutes']}m, "
           f"threshold {info['threshold_minutes']}m)")

    _history.setdefault(ticket_id, []).append({
        "timestamp": _now(),
        "message": msg,
    })

    # Reset the rule timer so re-escalation uses the new updated_at
    _rules[ticket_id]["set_at"] = _now()

    return msg


def get_escalation_history(ticket_id: str) -> list:
    """Return the list of escalation events for *ticket_id*."""
    return list(_history.get(ticket_id, []))


def reset_escalation() -> None:
    """Clear all escalation rules and history (useful in tests)."""
    _rules.clear()
    _history.clear()


# Hook callback -----------------------------------------------------------

def _default_escalation_hook(ticket, **_kwargs):
    """post_create hook: give every new ticket a default escalation rule."""
    set_escalation_rule(ticket.id)

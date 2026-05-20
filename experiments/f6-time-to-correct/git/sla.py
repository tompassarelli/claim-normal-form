"""SLA module for ClaimDesk — response-time breach tracking.

Usage:
    set_sla(ticket_id, response_minutes=60)  — start the clock
    check_breach(ticket_id) -> bool          — True if deadline has passed
    get_overdue_tickets() -> list            — active tickets past deadline
    reset_sla()                              — clear all SLA records
"""

import time
from typing import Dict, List, Optional

import core
from config import TERMINAL_STATUSES

# Maps ticket_id -> deadline (Unix timestamp float)
_deadlines: Dict[str, float] = {}


def set_sla(ticket_id: str, response_minutes: int = 60) -> None:
    """Record a deadline of now + response_minutes for ticket_id."""
    _deadlines[ticket_id] = time.time() + response_minutes * 60


def check_breach(ticket_id: str) -> bool:
    """Return True if the SLA deadline for ticket_id has been reached or passed.

    Returns False if no SLA has been set for the ticket, or if the ticket
    is in on_hold status (SLA is considered paused while on hold).
    Uses >= so that response_minutes=0 breaches immediately.
    """
    deadline = _deadlines.get(ticket_id)
    if deadline is None:
        return False
    ticket = core.get_ticket(ticket_id)
    if ticket is not None and ticket.status == "on_hold":
        return False
    return time.time() >= deadline


def get_overdue_tickets() -> List[object]:
    """Return tickets that are both past their SLA deadline AND in an active status."""
    now = time.time()
    overdue = []
    for ticket_id, deadline in _deadlines.items():
        if now >= deadline:
            ticket = core.get_ticket(ticket_id)
            if ticket is not None and ticket.status not in TERMINAL_STATUSES:
                overdue.append(ticket)
    return overdue


def reset_sla() -> None:
    """Clear all SLA deadline records."""
    _deadlines.clear()

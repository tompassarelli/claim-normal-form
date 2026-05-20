"""SLA module for ClaimDesk.

Tracks response-time deadlines per ticket and detects breaches.

Rules:
- set_sla(ticket_id, response_minutes=60) — records deadline = now + response_minutes * 60
- check_breach(ticket_id) — True if now >= deadline, EXCEPT when status is "on_hold"
  (on_hold pauses SLA; the clock stops while the ticket is paused)
- get_overdue_tickets() — tickets past deadline that are active AND not on_hold
- reset_sla() — clear all SLA data (useful for tests)

Wire into ClaimDesk by importing this module from config.py (see bottom of config.py).
"""

import time
from typing import Dict, List, Optional

from core import list_tickets
from models import Ticket
from config import TERMINAL_STATUSES

# ticket_id -> Unix timestamp deadline
_deadlines: Dict[str, float] = {}

# Statuses where SLA is paused (clock does not advance, breach is suppressed)
PAUSED_STATUSES = {"on_hold"}


def set_sla(ticket_id: str, response_minutes: int = 60) -> float:
    """Record an SLA deadline for *ticket_id*.

    deadline = now + response_minutes * 60 seconds.
    Returns the deadline as a Unix timestamp.
    """
    deadline = time.time() + response_minutes * 60
    _deadlines[ticket_id] = deadline
    return deadline


def check_breach(ticket_id: str) -> bool:
    """Return True if the SLA deadline has been reached or passed.

    Returns False when:
    - no SLA is set for the ticket
    - the ticket status is "on_hold" (SLA is paused)
    - the current time is before the deadline
    """
    deadline = _deadlines.get(ticket_id)
    if deadline is None:
        return False

    from core import get_ticket
    ticket = get_ticket(ticket_id)
    if ticket is not None and ticket.status in PAUSED_STATUSES:
        return False

    return time.time() >= deadline


def get_overdue_tickets() -> List[Ticket]:
    """Return all tickets that are past their SLA deadline and in an active,
    non-paused status.

    Excluded:
    - tickets with no SLA set
    - tickets in a terminal status (closed, archived)
    - tickets in a paused status (on_hold)
    """
    now = time.time()
    overdue = []
    for ticket in list_tickets():
        deadline = _deadlines.get(ticket.id)
        if deadline is None:
            continue
        if ticket.status in TERMINAL_STATUSES:
            continue
        if ticket.status in PAUSED_STATUSES:
            continue
        if now >= deadline:
            overdue.append(ticket)
    return overdue


def get_deadline(ticket_id: str) -> Optional[float]:
    """Return the raw deadline timestamp for *ticket_id*, or None if unset."""
    return _deadlines.get(ticket_id)


def reset_sla() -> None:
    """Clear all SLA data (useful for tests)."""
    _deadlines.clear()

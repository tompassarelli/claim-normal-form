"""SLA tracking for ClaimDesk.

Tracks response-time SLAs per ticket and surfaces breaches.
Wired into the ticket lifecycle via config.HOOKS (see bottom of config.py).
"""
from typing import Dict, Optional
import time

import core

# ticket_id -> {"deadline": int, "response_minutes": int}
_sla_data: Dict[str, Dict] = {}

DEFAULT_RESPONSE_MINUTES = 60


def _now() -> int:
    return int(time.time())


# ── public API ──────────────────────────────────────────────────────


def set_sla(ticket_id: str, response_minutes: int = DEFAULT_RESPONSE_MINUTES):
    """Attach an SLA to a ticket.  Deadline = now + response_minutes."""
    ticket = core.get_ticket(ticket_id)
    if ticket is None:
        raise ValueError(f"Ticket {ticket_id} not found")
    deadline = _now() + response_minutes * 60
    _sla_data[ticket_id] = {
        "deadline": deadline,
        "response_minutes": response_minutes,
    }


def check_breach(ticket_id: str) -> bool:
    """Return True if the ticket's SLA has been breached (past deadline)."""
    entry = _sla_data.get(ticket_id)
    if entry is None:
        return False
    return _now() >= entry["deadline"]


def get_overdue_tickets() -> list:
    """Return active tickets whose SLA is breached.

    Excludes closed and archived tickets — only genuinely actionable
    overdue work appears here.
    """
    from workflow import ACTIVE_STATUSES

    overdue = []
    for ticket_id, entry in _sla_data.items():
        if _now() < entry["deadline"]:
            continue
        ticket = core.get_ticket(ticket_id)
        if ticket is None:
            continue
        if ticket.status in ACTIVE_STATUSES:
            overdue.append(ticket)
    return overdue


def sla_report() -> Dict:
    """Summary of SLA compliance across all tracked tickets."""
    total = len(_sla_data)
    breached = 0
    compliant = 0
    no_ticket = 0

    for ticket_id, entry in _sla_data.items():
        ticket = core.get_ticket(ticket_id)
        if ticket is None:
            no_ticket += 1
            continue
        if _now() > entry["deadline"]:
            breached += 1
        else:
            compliant += 1

    return {
        "total_tracked": total,
        "compliant": compliant,
        "breached": breached,
        "compliance_pct": round(compliant / total * 100, 1) if total else 100.0,
    }


def reset_sla():
    """Clear all SLA tracking data (useful in tests)."""
    _sla_data.clear()


# ── hook callback ───────────────────────────────────────────────────


def _on_post_create(ticket, **kwargs):
    """Auto-set default SLA when a ticket is created."""
    set_sla(ticket.id, DEFAULT_RESPONSE_MINUTES)

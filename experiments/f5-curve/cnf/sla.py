"""ClaimDesk SLA tracking.

Tracks response-time SLAs per ticket and surfaces breaches.

Graph context: config.ACTIVE_STATUSES includes "on_hold".
workflow.TERMINAL_STATUSES = ["closed", "archived"].
on_hold is an active-but-paused state — SLA should not breach
while ticket is on_hold.
"""
from typing import Dict, Optional
import time
import core
from workflow import ACTIVE_STATUSES

_sla_data: Dict[str, Dict] = {}
DEFAULT_RESPONSE_MINUTES = 60

_PAUSED_STATUSES = {"on_hold"}


def _now() -> int:
    return int(time.time())


def set_sla(ticket_id: str, response_minutes: int = DEFAULT_RESPONSE_MINUTES):
    ticket = core.get_ticket(ticket_id)
    if ticket is None:
        raise ValueError(f"Ticket {ticket_id} not found")
    deadline = _now() + response_minutes * 60
    _sla_data[ticket_id] = {
        "deadline": deadline,
        "response_minutes": response_minutes,
    }


def check_breach(ticket_id: str):
    entry = _sla_data.get(ticket_id)
    if entry is None:
        return False
    ticket = core.get_ticket(ticket_id)
    if ticket is None:
        return False
    if ticket.status in _PAUSED_STATUSES:
        return False
    return _now() >= entry["deadline"]


def get_overdue_tickets() -> list:
    overdue = []
    for ticket_id, entry in _sla_data.items():
        if _now() < entry["deadline"]:
            continue
        ticket = core.get_ticket(ticket_id)
        if ticket is None:
            continue
        if ticket.status not in ACTIVE_STATUSES:
            continue
        if ticket.status in _PAUSED_STATUSES:
            continue
        overdue.append(ticket)
    return overdue


def reset_sla():
    _sla_data.clear()

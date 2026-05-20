"""ClaimDesk escalation.

Graph context: on_hold is an active-but-paused status — should NOT
escalate. archived is terminal — should NOT escalate. Audit trail
(audit.log_action) should record escalation events.
"""
from typing import Optional, Dict, List
import time

_rules: Dict[str, dict] = {}
_SKIP_STATUSES = {"closed", "archived", "on_hold"}


def _now() -> int:
    return int(time.time())


def set_escalation_rule(ticket_id: str, escalate_after_minutes: int = 30):
    _rules[ticket_id] = {
        "escalate_after_minutes": escalate_after_minutes,
        "set_at": _now(),
    }


def check_escalation(ticket_id: str):
    from core import get_ticket
    rule = _rules.get(ticket_id)
    if rule is None:
        return None
    ticket = get_ticket(ticket_id)
    if ticket is None:
        return None
    if ticket.status in _SKIP_STATUSES:
        return None
    elapsed = _now() - int(ticket.updated_at)
    threshold = rule["escalate_after_minutes"] * 60
    if elapsed < threshold:
        return False
    from audit import log_action
    log_action("escalation", ticket_id, user_id="system",
               priority=ticket.priority)
    return {
        "ticket_id": ticket_id,
        "current_priority": ticket.priority,
        "elapsed_minutes": elapsed // 60,
    }


def reset_escalation():
    _rules.clear()

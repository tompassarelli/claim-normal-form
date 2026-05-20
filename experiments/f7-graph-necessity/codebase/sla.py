"""
SLA policy attachment, breach detection, and reporting.

Deadlines are stored as floating-point unix timestamps (seconds) on an
in-memory _sla_state dict keyed by ticket id.  The store itself is not
extended — SLA metadata is ephemeral and module-local, consistent with the
overall single-process, test-friendly design of this codebase.

Time is always read via time.time() so tests can monkeypatch it:
    import sla, time
    time.time = lambda: <fixed_value>

Priority multipliers: higher PRIORITY_WEIGHT → tighter SLA.
    apply_priority_multiplier(base, "urgent") < apply_priority_multiplier(base, "low")
"""

import time
from typing import Dict, List, Optional

import store
from config import (
    ACTIVE_STATUSES,
    DEFAULT_SLA,
    PRIORITIES,
    PRIORITY_WEIGHTS,
    TERMINAL_STATUSES,
)
from events import _run_hooks
from models import SLAPolicy, Ticket


# ---------------------------------------------------------------------------
# Module-level SLA state
# ---------------------------------------------------------------------------

# { ticket_id: {"response_deadline": float, "resolution_deadline": float,
#               "policy_id": str | None} }
_sla_state: Dict[str, Dict] = {}


# ---------------------------------------------------------------------------
# Attachment
# ---------------------------------------------------------------------------

def attach_sla(ticket_id: str, policy_id: Optional[str] = None) -> None:
    """Attach an SLA policy to a ticket and compute deadlines.

    If *policy_id* is provided, the named SLAPolicy from the store is used.
    Otherwise, the per-priority entries from config.DEFAULT_SLA are used.

    Raises:
        KeyError — ticket not found, or policy_id not found in store
    """
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(f"Ticket '{ticket_id}' not found.")

    if policy_id is not None:
        policy = store.get_sla_policy(policy_id)
        if policy is None:
            raise KeyError(f"SLA policy '{policy_id}' not found.")
        store.update_ticket(ticket_id, sla_policy=policy_id)
    else:
        policy = None

    response_dl   = calculate_response_deadline(ticket, policy=policy)
    resolution_dl = calculate_resolution_deadline(ticket, policy=policy)

    _sla_state[ticket_id] = {
        "response_deadline":   response_dl,
        "resolution_deadline": resolution_dl,
        "policy_id":           policy_id,
    }


# ---------------------------------------------------------------------------
# Deadline calculation
# ---------------------------------------------------------------------------

def calculate_response_deadline(
    ticket: Ticket,
    policy: Optional[SLAPolicy] = None,
) -> float:
    """Return a unix timestamp for when a first response is due."""
    created = _ticket_created_ts(ticket)

    if policy is not None:
        minutes = policy.effective_response(ticket.priority)
    else:
        sla_entry = DEFAULT_SLA.get(ticket.priority, DEFAULT_SLA["medium"])
        base = sla_entry["response"]
        minutes = apply_priority_multiplier(base, ticket.priority)

    return created + minutes * 60.0


def calculate_resolution_deadline(
    ticket: Ticket,
    policy: Optional[SLAPolicy] = None,
) -> float:
    """Return a unix timestamp for when the ticket must be resolved."""
    created = _ticket_created_ts(ticket)

    if policy is not None:
        minutes = policy.effective_resolution(ticket.priority)
    else:
        sla_entry = DEFAULT_SLA.get(ticket.priority, DEFAULT_SLA["medium"])
        base = sla_entry["resolution"]
        minutes = apply_priority_multiplier(base, ticket.priority)

    return created + minutes * 60.0


def apply_priority_multiplier(base_minutes: int, priority: str) -> int:
    """Scale *base_minutes* inversely to priority weight.

    Higher weight → shorter (tighter) SLA.

    The reference weight for the "neutral" level (medium, weight=2) is used
    as the denominator so medium priority tickets get exactly base_minutes.
    """
    weight = PRIORITY_WEIGHTS.get(priority, PRIORITY_WEIGHTS["medium"])
    reference = PRIORITY_WEIGHTS["medium"]      # 2
    scaled = base_minutes * reference / weight
    return max(1, int(scaled))


# ---------------------------------------------------------------------------
# Status queries
# ---------------------------------------------------------------------------

def get_sla_status(ticket_id: str) -> Dict:
    """Return a dict summarising SLA state for *ticket_id*.

    Keys:
        response_deadline    — float unix timestamp (None if no SLA attached)
        resolution_deadline  — float unix timestamp (None if no SLA attached)
        response_breached    — bool
        resolution_breached  — bool
        time_remaining       — seconds until resolution deadline (negative = overdue)
    """
    state = _sla_state.get(ticket_id)
    if state is None:
        return {
            "response_deadline":   None,
            "resolution_deadline": None,
            "response_breached":   False,
            "resolution_breached": False,
            "time_remaining":      None,
        }

    now = time.time()
    resp_dl = state["response_deadline"]
    res_dl  = state["resolution_deadline"]

    return {
        "response_deadline":   resp_dl,
        "resolution_deadline": res_dl,
        "response_breached":   now > resp_dl,
        "resolution_breached": now > res_dl,
        "time_remaining":      res_dl - now,
    }


def check_breach(ticket_id: str) -> bool:
    """Return True if the ticket has breached either response or resolution SLA."""
    status = get_sla_status(ticket_id)
    return status["response_breached"] or status["resolution_breached"]


# ---------------------------------------------------------------------------
# Bulk queries
# ---------------------------------------------------------------------------

def get_breached_tickets() -> List[Ticket]:
    """Return all ACTIVE tickets that have breached their SLA.

    Terminal tickets are excluded — a closed ticket that was breached is a
    historical fact, not an actionable alert.
    """
    now = time.time()
    breached: List[Ticket] = []

    for ticket_id, state in _sla_state.items():
        ticket = store.get_ticket(ticket_id)
        if ticket is None:
            continue
        if ticket.status in TERMINAL_STATUSES:
            continue
        if ticket.status not in ACTIVE_STATUSES:
            continue
        if now > state["response_deadline"] or now > state["resolution_deadline"]:
            breached.append(ticket)

    return breached


def get_at_risk_tickets(threshold_minutes: int = 30) -> List[Ticket]:
    """Return active tickets whose resolution deadline is within *threshold_minutes*."""
    now = time.time()
    threshold_secs = threshold_minutes * 60.0
    at_risk: List[Ticket] = []

    for ticket_id, state in _sla_state.items():
        ticket = store.get_ticket(ticket_id)
        if ticket is None:
            continue
        if ticket.status in TERMINAL_STATUSES:
            continue
        if ticket.status not in ACTIVE_STATUSES:
            continue
        res_dl = state["resolution_deadline"]
        time_remaining = res_dl - now
        # At-risk: not yet breached but will breach within threshold.
        if 0 < time_remaining <= threshold_secs:
            at_risk.append(ticket)

    return at_risk


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------

def escalate_priority(ticket_id: str) -> Optional[Ticket]:
    """Bump the ticket's priority one level if it is breached and not already urgent.

    Returns the updated Ticket, or None if no escalation was performed
    (ticket not found, not breached, or already at maximum priority).
    """
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        return None

    if not check_breach(ticket_id):
        return None

    if ticket.priority == "urgent":
        return None

    idx = PRIORITIES.index(ticket.priority) if ticket.priority in PRIORITIES else -1
    if idx == -1 or idx + 1 >= len(PRIORITIES):
        return None

    old_priority = ticket.priority
    new_priority = PRIORITIES[idx + 1]

    store.update_ticket(ticket_id, priority=new_priority)
    ticket = store.get_ticket(ticket_id)  # refresh reference

    _run_hooks("update", ticket=ticket, field="priority",
               old_value=old_priority, new_value=new_priority)

    # Re-attach SLA so deadlines reflect the new (tighter) priority.
    policy_id = _sla_state.get(ticket_id, {}).get("policy_id")
    attach_sla(ticket_id, policy_id=policy_id)

    return ticket


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def get_compliance_stats(tickets: Optional[List[Ticket]] = None) -> Dict:
    """Return overall SLA compliance statistics.

    If *tickets* is None, all tickets with attached SLA state are considered.
    """
    if tickets is None:
        ticket_ids = list(_sla_state.keys())
        tickets = [t for tid in ticket_ids if (t := store.get_ticket(tid)) is not None]

    total     = len(tickets)
    breached  = sum(1 for t in tickets if check_breach(t.id))
    compliant = total - breached
    pct       = round(100.0 * compliant / total, 1) if total else 100.0

    return {
        "total":          total,
        "compliant":      compliant,
        "breached":       breached,
        "compliance_pct": pct,
    }


def get_sla_report(team_id: Optional[str] = None) -> Dict:
    """Return an SLA report, optionally scoped to a single team.

    Keys in the returned dict:
        team_id             — the requested scope (None = global)
        compliance          — output of get_compliance_stats()
        breached_tickets    — list of ticket ids that are currently breached
        at_risk_tickets     — list of ticket ids approaching breach (30 min)
        by_priority         — {priority: compliance_stats} breakdown
    """
    if team_id is not None:
        all_tickets = store.list_tickets({"team": team_id})
    else:
        all_tickets = store.list_tickets()

    # Only tickets with SLA state attached are meaningful here.
    sla_tickets = [t for t in all_tickets if t.id in _sla_state]

    breached = [t for t in sla_tickets if check_breach(t.id) and t.status in ACTIVE_STATUSES]

    threshold = 30
    now = time.time()
    threshold_secs = threshold * 60.0
    at_risk = [
        t for t in sla_tickets
        if t.status in ACTIVE_STATUSES
        and 0 < (_sla_state[t.id]["resolution_deadline"] - now) <= threshold_secs
    ]

    by_priority: Dict[str, Dict] = {}
    for priority in PRIORITIES:
        priority_tickets = [t for t in sla_tickets if t.priority == priority]
        by_priority[priority] = get_compliance_stats(priority_tickets)

    return {
        "team_id":         team_id,
        "compliance":      get_compliance_stats(sla_tickets),
        "breached_tickets": [t.id for t in breached],
        "at_risk_tickets":  [t.id for t in at_risk],
        "by_priority":      by_priority,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ticket_created_ts(ticket: Ticket) -> float:
    """Return the ticket's creation time as a float unix timestamp."""
    try:
        return float(ticket.created_at)
    except (ValueError, TypeError):
        return time.time()


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------

def reset_sla() -> None:
    """Clear all SLA state.  Intended for test isolation."""
    _sla_state.clear()

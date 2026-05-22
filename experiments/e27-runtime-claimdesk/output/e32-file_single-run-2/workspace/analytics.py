
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

import time
from workflow import (TERMINAL_STATUSES, ACTIVE_STATUSES, ESCALATED_STATUSES,
                      PRIORITY_SLA_HOURS, priority_sla_hours)

events = []

def track_transition(ticket_id, old_status, new_status, priority: str = "normal"):
    event = {
        "ticket": ticket_id,
        "from": old_status,
        "to": new_status,
        "priority": priority,
        "is_terminal": new_status in TERMINAL_STATUSES,
        "is_escalated": new_status in ESCALATED_STATUSES,
    }
    events.append(event)
    return event

def active_ticket_count(statuses):
    work_statuses = ACTIVE_STATUSES | ESCALATED_STATUSES
    return sum(1 for s in statuses if s in work_statuses)

def sla_report(ticket, now: float | None = None) -> dict:
    """Return SLA status for a single ticket.

    now — Unix timestamp; defaults to the current wall time.
    """
    if now is None:
        now = time.time()
    sla_hours = priority_sla_hours(ticket.priority)
    sla_seconds = sla_hours * 3600
    created = int(ticket.created_at) if ticket.created_at else int(now)
    elapsed = now - created
    return {
        "ticket": ticket.id,
        "priority": ticket.priority,
        "sla_hours": sla_hours,
        "elapsed_seconds": elapsed,
        "breached": elapsed > sla_seconds,
        "remaining_seconds": max(0.0, sla_seconds - elapsed),
    }

def priority_distribution(tickets) -> dict:
    """Return a count of tickets grouped by priority."""
    dist: dict[str, int] = {}
    for t in tickets:
        dist[t.priority] = dist.get(t.priority, 0) + 1
    return dist

def sla_breach_summary(tickets, now: float | None = None) -> dict:
    """Return counts of breached vs. on-track tickets, grouped by priority."""
    summary: dict[str, dict] = {}
    for t in tickets:
        report = sla_report(t, now)
        p = t.priority
        bucket = summary.setdefault(p, {"breached": 0, "on_track": 0})
        if report["breached"]:
            bucket["breached"] += 1
        else:
            bucket["on_track"] += 1
    return summary

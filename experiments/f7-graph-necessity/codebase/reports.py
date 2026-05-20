"""
Reporting and analytics for the helpdesk/CRM application.

All report generators follow the same pattern:

  1. Collect tickets (optionally scoped to a team via team_id).
  2. Crunch the numbers into a plain dict.
  3. Persist a Report record in the store and return it.

The store is the source of truth; reports are always generated fresh from
live data and saved for later retrieval / export.

SLA breach detection uses the DEFAULT_SLA resolution thresholds from config
and the ticket's created_at timestamp.  Tickets without a created_at value
are treated as non-breached (conservative default).
"""

import time
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional

import store
from config import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    PRIORITIES,
    PRIORITY_WEIGHTS,
    DEFAULT_SLA,
    SOURCES,
)
from models import Report, Ticket


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_ts() -> float:
    return time.time()


def _now_str() -> str:
    return f"{_now_ts():.3f}"


def _make_report(name: str, report_type: str, data: Dict, filters: Dict) -> Report:
    r = Report(
        id=str(uuid.uuid4()),
        name=name,
        type=report_type,
        created_at=_now_str(),
        data=data,
        filters=filters,
    )
    store.reports[r.id] = r
    return r


def _get_tickets(team_id: Optional[str] = None) -> List[Ticket]:
    """Return all tickets, optionally restricted to a team's members."""
    if team_id is None:
        return store.list_tickets()

    team = store.get_team(team_id)
    if team is None:
        return []

    member_ids = set(team.members)
    return [
        t for t in store.list_tickets()
        if t.assignee in member_ids or t.team == team_id
    ]


def _active_tickets(tickets: List[Ticket]) -> List[Ticket]:
    return [t for t in tickets if t.status in ACTIVE_STATUSES]


def _parse_ts(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _sla_resolution_minutes(ticket: Ticket) -> int:
    """Return the resolution SLA in minutes for *ticket* based on DEFAULT_SLA."""
    sla = DEFAULT_SLA.get(ticket.priority)
    if sla is None:
        return DEFAULT_SLA["medium"]["resolution"]
    return sla["resolution"]


def _is_breached(ticket: Ticket, now: float) -> bool:
    """Return True if the ticket has exceeded its resolution SLA."""
    created = _parse_ts(ticket.created_at)
    if created == 0.0:
        return False
    elapsed_minutes = (now - created) / 60.0
    return elapsed_minutes > _sla_resolution_minutes(ticket)


def _is_at_risk(ticket: Ticket, now: float, threshold: float = 0.8) -> bool:
    """Return True if the ticket has consumed >= *threshold* of its resolution SLA."""
    created = _parse_ts(ticket.created_at)
    if created == 0.0:
        return False
    elapsed_minutes = (now - created) / 60.0
    limit = _sla_resolution_minutes(ticket)
    return (elapsed_minutes / limit) >= threshold if limit > 0 else False


# ---------------------------------------------------------------------------
# Report generators
# ---------------------------------------------------------------------------

def generate_status_report(team_id: Optional[str] = None) -> Report:
    """Return a report with ticket counts grouped by status.

    All statuses are included; nothing is excluded.
    """
    tickets = _get_tickets(team_id)
    by_status: Dict[str, int] = defaultdict(int)
    for t in tickets:
        by_status[t.status] += 1

    data = {
        "total":     len(tickets),
        "by_status": dict(by_status),
    }
    filters = {"team_id": team_id}
    return _make_report("Status Report", "status", data, filters)


def generate_workload_report(team_id: Optional[str] = None) -> Report:
    """Return a report showing active ticket load per agent.

    Keys in data:
        per_agent   — {user_id: ticket_count}
        average     — mean across agents who have at least one ticket
        max         — highest individual load
        unassigned  — active tickets with no assignee
    """
    tickets = _active_tickets(_get_tickets(team_id))
    per_agent: Dict[str, int] = defaultdict(int)
    unassigned = 0

    for t in tickets:
        if t.assignee:
            per_agent[t.assignee] += 1
        else:
            unassigned += 1

    counts = list(per_agent.values())
    average = sum(counts) / len(counts) if counts else 0.0
    max_load = max(counts, default=0)

    data = {
        "per_agent":  dict(per_agent),
        "average":    round(average, 2),
        "max":        max_load,
        "unassigned": unassigned,
    }
    filters = {"team_id": team_id}
    return _make_report("Workload Report", "workload", data, filters)


def generate_sla_report(team_id: Optional[str] = None) -> Report:
    """Return an SLA compliance report for active tickets.

    Keys in data:
        total_active    — total active tickets checked
        compliant       — tickets within SLA
        breached        — tickets past their resolution deadline
        at_risk         — tickets >= 80 % of their resolution deadline
        compliance_pct  — percentage compliant (0–100)
        breached_ids    — list of ticket ids that are breached
        at_risk_ids     — list of ticket ids that are at risk (not already breached)
    """
    tickets = _active_tickets(_get_tickets(team_id))
    now = _now_ts()

    breached_ids: List[str] = []
    at_risk_ids: List[str] = []

    for t in tickets:
        if _is_breached(t, now):
            breached_ids.append(t.id)
        elif _is_at_risk(t, now):
            at_risk_ids.append(t.id)

    total = len(tickets)
    breached = len(breached_ids)
    compliant = total - breached
    compliance_pct = round((compliant / total * 100) if total else 100.0, 1)

    data = {
        "total_active":   total,
        "compliant":      compliant,
        "breached":       breached,
        "at_risk":        len(at_risk_ids),
        "compliance_pct": compliance_pct,
        "breached_ids":   breached_ids,
        "at_risk_ids":    at_risk_ids,
    }
    filters = {"team_id": team_id}
    return _make_report("SLA Report", "sla", data, filters)


def generate_priority_report(team_id: Optional[str] = None) -> Report:
    """Return a report with active ticket counts grouped by priority."""
    tickets = _active_tickets(_get_tickets(team_id))
    by_priority: Dict[str, int] = {p: 0 for p in PRIORITIES}
    for t in tickets:
        if t.priority in by_priority:
            by_priority[t.priority] += 1
        else:
            by_priority[t.priority] = 1

    # Weighted score — useful for a single "heat" number.
    weighted_score = sum(
        count * PRIORITY_WEIGHTS.get(priority, 1)
        for priority, count in by_priority.items()
    )

    data = {
        "total_active":   len(tickets),
        "by_priority":    by_priority,
        "weighted_score": weighted_score,
    }
    filters = {"team_id": team_id}
    return _make_report("Priority Report", "priority", data, filters)


def generate_trend_report(days: int = 30) -> Report:
    """Return a snapshot of created-vs-closed ticket counts.

    A full time-series would require storing event timestamps; since this
    store is in-memory without a query layer, we provide a current snapshot:

        total_created   — all tickets ever added
        total_closed    — tickets currently in a terminal status
        currently_open  — tickets in ACTIVE_STATUSES
        window_days     — the requested window (recorded for reference)
    """
    all_tickets = store.list_tickets()
    total_created = len(all_tickets)
    total_closed = sum(1 for t in all_tickets if t.status in TERMINAL_STATUSES)
    currently_open = sum(1 for t in all_tickets if t.status in ACTIVE_STATUSES)

    data = {
        "total_created":  total_created,
        "total_closed":   total_closed,
        "currently_open": currently_open,
        "window_days":    days,
    }
    filters = {"days": days}
    return _make_report("Trend Report", "trend", data, filters)


def generate_tag_report() -> Report:
    """Return tag usage counts across all active tickets."""
    tickets = _active_tickets(store.list_tickets())
    tag_counts: Dict[str, int] = defaultdict(int)
    for t in tickets:
        for tag in t.tags:
            tag_counts[tag] += 1

    sorted_tags = sorted(tag_counts.items(), key=lambda kv: kv[1], reverse=True)
    data = {
        "total_active":  len(tickets),
        "tag_counts":    dict(sorted_tags),
        "unique_tags":   len(tag_counts),
    }
    return _make_report("Tag Report", "tags", data, {})


def generate_source_report() -> Report:
    """Return ticket counts grouped by source channel."""
    all_tickets = store.list_tickets()
    by_source: Dict[str, int] = defaultdict(int)
    for t in all_tickets:
        by_source[t.source] += 1

    data = {
        "total":     len(all_tickets),
        "by_source": dict(by_source),
    }
    return _make_report("Source Report", "source", data, {})


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def get_dashboard_data(team_id: Optional[str] = None) -> Dict[str, Any]:
    """Return a combined summary suitable for a dashboard widget.

    Keys:
        active_count      — tickets in ACTIVE_STATUSES
        breached_count    — active tickets past their SLA resolution deadline
        unassigned_count  — active tickets with no assignee
        top_priorities    — [{priority, count}] sorted by PRIORITY_WEIGHTS desc
        team_id           — echoed back for context
    """
    tickets = _active_tickets(_get_tickets(team_id))
    now = _now_ts()

    breached_count = sum(1 for t in tickets if _is_breached(t, now))
    unassigned_count = sum(1 for t in tickets if not t.assignee)

    priority_counts: Dict[str, int] = defaultdict(int)
    for t in tickets:
        priority_counts[t.priority] += 1

    top_priorities = sorted(
        [{"priority": p, "count": c} for p, c in priority_counts.items()],
        key=lambda x: PRIORITY_WEIGHTS.get(x["priority"], 0),
        reverse=True,
    )

    return {
        "active_count":     len(tickets),
        "breached_count":   breached_count,
        "unassigned_count": unassigned_count,
        "top_priorities":   top_priorities,
        "team_id":          team_id,
    }


# ---------------------------------------------------------------------------
# Saved reports
# ---------------------------------------------------------------------------

def get_saved_reports() -> List[Report]:
    """Return all persisted reports, newest first."""
    return sorted(
        store.reports.values(),
        key=lambda r: r.created_at,
        reverse=True,
    )


def export_report(report_id: str, format: str = "json") -> str:
    """Serialise a saved report to a string in the requested format.

    Supported formats: "json".  Raises ValueError for unknown formats or a
    missing report.
    """
    import json

    report = store.reports.get(report_id)
    if report is None:
        raise ValueError(f"Report not found: {report_id!r}")

    if format == "json":
        payload = {
            "id":         report.id,
            "name":       report.name,
            "type":       report.type,
            "created_at": report.created_at,
            "filters":    report.filters,
            "data":       report.data,
        }
        return json.dumps(payload, indent=2)

    raise ValueError(f"Unsupported export format: {format!r}")


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------

def reset_reports() -> None:
    """Remove all saved reports from the store.  Intended for test isolation."""
    store.reports.clear()

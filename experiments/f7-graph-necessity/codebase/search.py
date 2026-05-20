"""
Ticket search and filtering.

Design notes:
- filter_tickets() excludes terminal-status tickets by default.  Pass an
  explicit status= to include or restrict to a particular status.
- search_tickets() searches across all statuses (both active and terminal) so
  agents can look up historical records by keyword.
- Timestamps used in find_stale() and created_after/before filters are unix
  epoch floats stored as strings, matching the store convention.
"""

import time
from typing import Any, Dict, List, Optional

import store
from config import ACTIVE_STATUSES, TERMINAL_STATUSES, SEARCH_RESULT_LIMIT
from models import Ticket


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_ts() -> float:
    return time.time()


def _parse_ts(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _matches_query(ticket: Ticket, query: str) -> bool:
    """Return True if *query* is a substring of the ticket's title or description."""
    q = query.lower()
    return q in ticket.title.lower() or q in ticket.description.lower()


def _apply_common_filters(tickets: List[Ticket], filters: Dict[str, Any]) -> List[Ticket]:
    """Apply the standard filter set to *tickets* in-place and return the result."""
    if "status" in filters and filters["status"] is not None:
        tickets = [t for t in tickets if t.status == filters["status"]]
    if "priority" in filters and filters["priority"] is not None:
        tickets = [t for t in tickets if t.priority == filters["priority"]]
    if "assignee" in filters and filters["assignee"] is not None:
        tickets = [t for t in tickets if t.assignee == filters["assignee"]]
    if "team" in filters and filters["team"] is not None:
        tickets = [t for t in tickets if t.team == filters["team"]]
    if "source" in filters and filters["source"] is not None:
        tickets = [t for t in tickets if t.source == filters["source"]]
    if "tag" in filters and filters["tag"] is not None:
        tickets = [t for t in tickets if filters["tag"] in t.tags]
    return tickets


# ---------------------------------------------------------------------------
# Primary search
# ---------------------------------------------------------------------------

def search_tickets(
    query: str,
    filters: Optional[Dict[str, Any]] = None,
    limit: Optional[int] = None,
) -> List[Ticket]:
    """Return tickets whose title or description contains *query* (case-insensitive).

    Optional *filters* dict supports the same keys as filter_tickets().
    Results are ordered by updated_at descending (most recently active first).
    Searches across all statuses unless status is included in filters.
    """
    effective_limit = limit if limit is not None else SEARCH_RESULT_LIMIT
    query = query.strip()

    candidates = list(store.tickets.values())
    if query:
        candidates = [t for t in candidates if _matches_query(t, query)]

    if filters:
        candidates = _apply_common_filters(candidates, filters)

    candidates.sort(key=lambda t: t.updated_at, reverse=True)
    return candidates[:effective_limit]


# ---------------------------------------------------------------------------
# Structured filtering
# ---------------------------------------------------------------------------

def filter_tickets(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    team: Optional[str] = None,
    tag: Optional[str] = None,
    source: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
) -> List[Ticket]:
    """Return tickets matching the provided criteria.

    By default only ACTIVE tickets are returned.  Pass an explicit *status*
    to include terminal tickets or restrict to a single status.
    """
    result = list(store.tickets.values())

    if status is not None:
        result = [t for t in result if t.status == status]
    else:
        result = [t for t in result if t.status in ACTIVE_STATUSES]

    if priority is not None:
        result = [t for t in result if t.priority == priority]
    if assignee is not None:
        result = [t for t in result if t.assignee == assignee]
    if team is not None:
        result = [t for t in result if t.team == team]
    if tag is not None:
        result = [t for t in result if tag in t.tags]
    if source is not None:
        result = [t for t in result if t.source == source]

    if created_after is not None:
        threshold = _parse_ts(created_after)
        result = [t for t in result if _parse_ts(t.created_at) >= threshold]
    if created_before is not None:
        threshold = _parse_ts(created_before)
        result = [t for t in result if _parse_ts(t.created_at) <= threshold]

    result.sort(key=lambda t: t.created_at, reverse=True)
    return result


# ---------------------------------------------------------------------------
# Similarity and discovery
# ---------------------------------------------------------------------------

def find_similar(ticket_id: str) -> List[Ticket]:
    """Return active tickets that share tags and priority with *ticket_id*.

    The source ticket itself is excluded.  Results are ordered by number of
    matching tags (descending), then by updated_at descending.
    """
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        return []

    source_tags = set(ticket.tags)
    candidates = []

    for t in store.tickets.values():
        if t.id == ticket_id:
            continue
        if t.status not in ACTIVE_STATUSES:
            continue
        if t.priority != ticket.priority:
            continue
        shared = source_tags & set(t.tags)
        if shared:
            candidates.append((len(shared), t))

    candidates.sort(key=lambda pair: (pair[0], pair[1].updated_at), reverse=True)
    return [t for _, t in candidates]


def find_unassigned(team_id: Optional[str] = None) -> List[Ticket]:
    """Return active tickets with no assignee.

    Optionally restrict to a specific *team_id*.
    Sorted by priority weight descending, then created_at ascending (oldest first).
    """
    from config import PRIORITY_WEIGHTS

    result = [
        t for t in store.tickets.values()
        if t.status in ACTIVE_STATUSES and t.assignee is None
    ]
    if team_id is not None:
        result = [t for t in result if t.team == team_id]

    result.sort(
        key=lambda t: (
            -PRIORITY_WEIGHTS.get(t.priority, 0),
            _parse_ts(t.created_at),
        )
    )
    return result


def find_stale(minutes: int = 1440) -> List[Ticket]:
    """Return active tickets not updated in the last *minutes* minutes.

    Defaults to 1440 minutes (24 hours).  Sorted by updated_at ascending
    (most neglected first).
    """
    now = _now_ts()
    cutoff = now - (minutes * 60)

    result = [
        t for t in store.tickets.values()
        if t.status in ACTIVE_STATUSES and _parse_ts(t.updated_at) <= cutoff
    ]
    result.sort(key=lambda t: _parse_ts(t.updated_at))
    return result


def find_by_contact(email: str) -> List[Ticket]:
    """Return all tickets (any status) whose contact_email matches *email*.

    Comparison is case-insensitive.  Sorted by created_at descending.
    """
    email_lower = email.strip().lower()
    result = [
        t for t in store.tickets.values()
        if t.contact_email.lower() == email_lower
    ]
    result.sort(key=lambda t: t.created_at, reverse=True)
    return result


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def count_by_filter(**filters: Any) -> int:
    """Return the number of active tickets matching *filters*.

    Accepts the same keyword arguments as filter_tickets().
    """
    return len(filter_tickets(**filters))


def get_search_facets() -> Dict[str, Any]:
    """Return aggregate counts useful for building faceted search UI.

    Returns a dict with keys: status, priority, team, tag — each mapping
    to a sub-dict of value -> count across ALL tickets in the store.
    """
    status_counts: Dict[str, int] = {}
    priority_counts: Dict[str, int] = {}
    team_counts: Dict[str, int] = {}
    tag_counts: Dict[str, int] = {}

    for ticket in store.tickets.values():
        status_counts[ticket.status] = status_counts.get(ticket.status, 0) + 1
        priority_counts[ticket.priority] = priority_counts.get(ticket.priority, 0) + 1
        if ticket.team is not None:
            team_counts[ticket.team] = team_counts.get(ticket.team, 0) + 1
        for tag in ticket.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    return {
        "status": status_counts,
        "priority": priority_counts,
        "team": team_counts,
        "tag": tag_counts,
    }


# ---------------------------------------------------------------------------
# Advanced search
# ---------------------------------------------------------------------------

def advanced_search(
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    team: Optional[str] = None,
    tags: Optional[List[str]] = None,
    source: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: Optional[int] = None,
) -> List[Ticket]:
    """Full-featured search with per-field matching and configurable sorting.

    *title* and *description* are independent substring filters (both
    case-insensitive).  *tags* is a list; all listed tags must be present
    (AND semantics).

    *sort_by* may be any Ticket field name; unknown fields fall back to
    created_at.  *sort_order* is "asc" or "desc" (default "desc").

    Returns at most *limit* results (defaults to SEARCH_RESULT_LIMIT).
    """
    effective_limit = limit if limit is not None else SEARCH_RESULT_LIMIT
    result = list(store.tickets.values())

    if title is not None:
        needle = title.lower()
        result = [t for t in result if needle in t.title.lower()]
    if description is not None:
        needle = description.lower()
        result = [t for t in result if needle in t.description.lower()]
    if status is not None:
        result = [t for t in result if t.status == status]
    if priority is not None:
        result = [t for t in result if t.priority == priority]
    if assignee is not None:
        result = [t for t in result if t.assignee == assignee]
    if team is not None:
        result = [t for t in result if t.team == team]
    if source is not None:
        result = [t for t in result if t.source == source]
    if tags:
        required = set(tags)
        result = [t for t in result if required.issubset(set(t.tags))]

    # Sorting
    valid_fields = {f.name for f in Ticket.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    field_name = sort_by if sort_by in valid_fields else "created_at"
    reverse = sort_order.lower() != "asc"
    result.sort(key=lambda t: getattr(t, field_name, ""), reverse=reverse)

    return result[:effective_limit]

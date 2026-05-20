"""
In-memory data store with CRUD primitives.

Design choices:
- Each entity type lives in its own dict keyed by id (or name for Tags).
- IDs are auto-incremented integers cast to strings so callers always
  receive strings and never need to guess the type.
- All mutations stamp updated_at on the entity if the field exists.
- reset_all() wipes every collection — useful for test isolation.
- No locking: this store is intentionally single-threaded.  If concurrency
  is ever needed, wrap mutations with threading.Lock at the call sites.
"""

import time
from typing import Any, Dict, List, Optional

from models import (
    AuditEntry,
    Comment,
    Notification,
    Report,
    SLAPolicy,
    Tag,
    Team,
    Ticket,
    User,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    """Return current unix time as a string with millisecond precision."""
    return f"{time.time():.3f}"


class _Counter:
    """Thread-unsafe monotonically increasing ID generator."""

    def __init__(self) -> None:
        self._value = 0

    def next(self) -> str:
        self._value += 1
        return str(self._value)

    def reset(self) -> None:
        self._value = 0


# ---------------------------------------------------------------------------
# Store state — module-level singletons
# ---------------------------------------------------------------------------

tickets:      Dict[str, Ticket]      = {}
users:        Dict[str, User]        = {}
teams:        Dict[str, Team]        = {}
comments:     Dict[str, Comment]     = {}
audit_log:    Dict[str, AuditEntry]  = {}
notifications: Dict[str, Notification] = {}
sla_policies: Dict[str, SLAPolicy]  = {}
tags:         Dict[str, Tag]         = {}   # keyed by tag name (lowercase)
reports:      Dict[str, Report]      = {}

_counters: Dict[str, _Counter] = {
    "ticket":       _Counter(),
    "user":         _Counter(),
    "team":         _Counter(),
    "comment":      _Counter(),
    "audit":        _Counter(),
    "notification": _Counter(),
    "sla_policy":   _Counter(),
    "report":       _Counter(),
}


def reset_all() -> None:
    """Clear every collection and reset all ID counters. Use in tests."""
    tickets.clear()
    users.clear()
    teams.clear()
    comments.clear()
    audit_log.clear()
    notifications.clear()
    sla_policies.clear()
    tags.clear()
    reports.clear()
    for counter in _counters.values():
        counter.reset()


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

def add_ticket(ticket: Ticket) -> Ticket:
    if not ticket.id:
        ticket.id = _counters["ticket"].next()
    now = _now()
    if not ticket.created_at:
        ticket.created_at = now
    ticket.updated_at = now
    tickets[ticket.id] = ticket
    return ticket


def get_ticket(ticket_id: str) -> Optional[Ticket]:
    return tickets.get(ticket_id)


def update_ticket(ticket_id: str, **fields: Any) -> Optional[Ticket]:
    ticket = tickets.get(ticket_id)
    if ticket is None:
        return None
    for key, value in fields.items():
        if hasattr(ticket, key):
            setattr(ticket, key, value)
    ticket.updated_at = _now()
    return ticket


def delete_ticket(ticket_id: str) -> bool:
    if ticket_id in tickets:
        del tickets[ticket_id]
        return True
    return False


def list_tickets(filters: Optional[Dict[str, Any]] = None) -> List[Ticket]:
    """
    Return tickets matching all provided filters.

    Supported filter keys: status, priority, assignee, team, source, tag.
    Unrecognised keys are silently ignored so callers can pass a broad
    context dict without breaking things.
    """
    result = list(tickets.values())
    if not filters:
        return result

    if "status" in filters:
        result = [t for t in result if t.status == filters["status"]]
    if "priority" in filters:
        result = [t for t in result if t.priority == filters["priority"]]
    if "assignee" in filters:
        result = [t for t in result if t.assignee == filters["assignee"]]
    if "team" in filters:
        result = [t for t in result if t.team == filters["team"]]
    if "source" in filters:
        result = [t for t in result if t.source == filters["source"]]
    if "tag" in filters:
        result = [t for t in result if filters["tag"] in t.tags]

    return result


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def add_user(user: User) -> User:
    if not user.id:
        user.id = _counters["user"].next()
    users[user.id] = user
    return user


def get_user(user_id: str) -> Optional[User]:
    return users.get(user_id)


def list_users(
    role: Optional[str] = None,
    team: Optional[str] = None,
    active_only: bool = True,
) -> List[User]:
    result = list(users.values())
    if active_only:
        result = [u for u in result if u.is_active]
    if role is not None:
        result = [u for u in result if u.role == role]
    if team is not None:
        result = [u for u in result if u.team == team]
    return result


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

def add_team(team: Team) -> Team:
    if not team.id:
        team.id = _counters["team"].next()
    teams[team.id] = team
    return team


def get_team(team_id: str) -> Optional[Team]:
    return teams.get(team_id)


def get_team_by_name(name: str) -> Optional[Team]:
    name_lower = name.lower()
    for team in teams.values():
        if team.name.lower() == name_lower:
            return team
    return None


def list_teams() -> List[Team]:
    return list(teams.values())


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def add_comment(comment: Comment) -> Comment:
    if not comment.id:
        comment.id = _counters["comment"].next()
    if not comment.created_at:
        comment.created_at = _now()
    comments[comment.id] = comment

    # Bump the parent ticket's updated_at so it surfaces in activity feeds.
    ticket = tickets.get(comment.ticket_id)
    if ticket is not None:
        ticket.updated_at = _now()

    return comment


def get_comments(ticket_id: str) -> List[Comment]:
    return [c for c in comments.values() if c.ticket_id == ticket_id]


def count_comments(ticket_id: str) -> int:
    return sum(1 for c in comments.values() if c.ticket_id == ticket_id)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def add_audit(entry: AuditEntry) -> AuditEntry:
    if not entry.id:
        entry.id = _counters["audit"].next()
    if not entry.timestamp:
        entry.timestamp = _now()
    audit_log[entry.id] = entry
    return entry


def get_audit_trail(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> List[AuditEntry]:
    result = list(audit_log.values())
    if entity_type is not None:
        result = [e for e in result if e.entity_type == entity_type]
    if entity_id is not None:
        result = [e for e in result if e.entity_id == entity_id]
    # Return in chronological order.
    return sorted(result, key=lambda e: e.timestamp)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def add_notification(notif: Notification) -> Notification:
    if not notif.id:
        notif.id = _counters["notification"].next()
    if not notif.created_at:
        notif.created_at = _now()
    notifications[notif.id] = notif
    return notif


def get_notifications(user_id: str, unread_only: bool = False) -> List[Notification]:
    result = [n for n in notifications.values() if n.recipient_id == user_id]
    if unread_only:
        result = [n for n in result if not n.read]
    return sorted(result, key=lambda n: n.created_at, reverse=True)


def mark_read(notif_id: str) -> bool:
    notif = notifications.get(notif_id)
    if notif is None:
        return False
    notif.read = True
    return True


# ---------------------------------------------------------------------------
# SLA policies
# ---------------------------------------------------------------------------

def add_sla_policy(policy: SLAPolicy) -> SLAPolicy:
    if not policy.id:
        policy.id = _counters["sla_policy"].next()
    sla_policies[policy.id] = policy
    return policy


def get_sla_policy(policy_id: str) -> Optional[SLAPolicy]:
    return sla_policies.get(policy_id)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def add_tag(tag: Tag) -> Tag:
    key = tag.name.lower()
    tags[key] = tag
    return tag


def get_tag(name: str) -> Optional[Tag]:
    return tags.get(name.lower())


def list_tags() -> List[Tag]:
    return list(tags.values())

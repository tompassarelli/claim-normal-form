"""
Domain models for the helpdesk/CRM application.

All models are plain dataclasses — no ORM, no framework dependencies.
Mutable defaults use field(default_factory=...) to avoid shared state.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Core ticket entities
# ---------------------------------------------------------------------------

@dataclass
class Ticket:
    id: str
    title: str
    description: str
    status: str = "open"
    priority: str = "medium"
    assignee: Optional[str] = None          # user id
    contact_email: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: List[str] = field(default_factory=list)
    team: Optional[str] = None              # team id
    sla_policy: Optional[str] = None        # sla_policy id
    source: str = "web"

    def is_open(self) -> bool:
        return self.status in {"open", "in_progress"}

    def is_terminal(self) -> bool:
        return self.status == "closed"

    def age_seconds(self, now: str) -> float:
        """Return seconds since creation given a unix-timestamp string."""
        try:
            return float(now) - float(self.created_at)
        except (ValueError, TypeError):
            return 0.0


# ---------------------------------------------------------------------------
# People & teams
# ---------------------------------------------------------------------------

@dataclass
class User:
    id: str
    name: str
    email: str
    role: str = "agent"
    team: Optional[str] = None              # team id
    is_active: bool = True
    max_tickets: int = 10

    def can_be_assigned(self) -> bool:
        return self.is_active and self.role in {"agent", "team_lead"}


@dataclass
class Team:
    id: str
    name: str
    members: List[str] = field(default_factory=list)    # user ids
    lead: Optional[str] = None                          # user id
    specialties: List[str] = field(default_factory=list)

    def has_member(self, user_id: str) -> bool:
        return user_id in self.members


# ---------------------------------------------------------------------------
# Ticket activity
# ---------------------------------------------------------------------------

@dataclass
class Comment:
    id: str
    ticket_id: str
    author_id: str
    body: str
    created_at: str
    is_internal: bool = False               # internal notes not shown to contacts

    def preview(self, length: int = 80) -> str:
        return self.body[:length] + ("…" if len(self.body) > length else "")


# ---------------------------------------------------------------------------
# Service-level agreements
# ---------------------------------------------------------------------------

@dataclass
class SLAPolicy:
    id: str
    name: str
    response_minutes: int = 60
    resolution_minutes: int = 480
    priority_multipliers: Dict[str, float] = field(default_factory=dict)

    def effective_response(self, priority: str) -> int:
        """Return response time in minutes adjusted for priority."""
        multiplier = self.priority_multipliers.get(priority, 1.0)
        return max(1, int(self.response_minutes * multiplier))

    def effective_resolution(self, priority: str) -> int:
        multiplier = self.priority_multipliers.get(priority, 1.0)
        return max(1, int(self.resolution_minutes * multiplier))


# ---------------------------------------------------------------------------
# Audit & notifications
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    id: str
    timestamp: str
    action: str
    entity_type: str
    entity_id: str
    user_id: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Notification:
    id: str
    recipient_id: str
    ticket_id: str
    message: str
    type: str                               # e.g. "assigned", "comment", "sla_breach"
    created_at: str
    read: bool = False


# ---------------------------------------------------------------------------
# Taxonomy & reporting
# ---------------------------------------------------------------------------

@dataclass
class Tag:
    name: str
    color: str = "gray"
    description: str = ""

    def display(self) -> str:
        return f"[{self.name}]"


@dataclass
class Report:
    id: str
    name: str
    type: str                               # e.g. "volume", "sla", "agent_performance"
    created_at: str
    data: Dict[str, Any] = field(default_factory=dict)
    filters: Dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.data

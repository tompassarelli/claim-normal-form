"""
Team management and routing for the helpdesk/CRM application.

Teams group agents under a shared lead, carry a list of specialties
(e.g. ["billing", "urgent"]), and are the unit of routing: when a ticket
arrives, route_ticket() matches the ticket's tags and priority against each
team's specialties and returns the best-fit team.

All public functions that touch the store go through the store module; no
direct dict access is performed here.
"""

import time
from typing import Dict, List, Optional

import store
from config import ACTIVE_STATUSES, PRIORITY_WEIGHTS
from models import Team, User, Ticket
from events import _run_hooks, emit


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return f"{time.time():.3f}"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_team(
    name: str,
    lead_id: Optional[str] = None,
    specialties: Optional[List[str]] = None,
) -> Team:
    """Create and persist a new team.

    Raises ValueError if *name* is empty or a team with that name already
    exists (names are unique to prevent routing ambiguity).

    If *lead_id* is given the referenced user must exist; the user's team
    field is updated to point at the new team.
    """
    name = name.strip()
    if not name:
        raise ValueError("team name must not be empty")

    existing = store.get_team_by_name(name)
    if existing is not None:
        raise ValueError(f"A team named {name!r} already exists (id={existing.id!r})")

    if lead_id is not None:
        lead_user = store.get_user(lead_id)
        if lead_user is None:
            raise ValueError(f"Lead user not found: {lead_id!r}")

    team = Team(
        id="",
        name=name,
        members=[] if lead_id is None else [lead_id],
        lead=lead_id,
        specialties=list(specialties or []),
    )
    team = store.add_team(team)

    # Keep user.team in sync.
    if lead_id is not None:
        _link_user_to_team(lead_id, team.id)

    emit("team.created", team=team)
    return team


def get_team(team_id: str) -> Optional[Team]:
    """Return the team with *team_id*, or None if it does not exist."""
    return store.get_team(team_id)


def get_team_by_name(name: str) -> Optional[Team]:
    """Return the team whose name matches *name* (case-insensitive), or None."""
    return store.get_team_by_name(name)


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

def add_member(team_id: str, user_id: str) -> None:
    """Add *user_id* to *team_id*.

    Raises ValueError if either entity is not found.
    Idempotent: adding an already-present member is a no-op.
    """
    team = _require_team(team_id)
    user = _require_user(user_id)

    if user_id not in team.members:
        team.members.append(user_id)

    # If the user was on a different team, update that reference.
    _link_user_to_team(user_id, team_id)


def remove_member(team_id: str, user_id: str) -> None:
    """Remove *user_id* from *team_id*.

    Raises ValueError if the team is not found.  Silently ignores attempts
    to remove a user who is not a member.  If the removed user is the team
    lead, the lead field is cleared.
    """
    team = _require_team(team_id)

    if user_id in team.members:
        team.members.remove(user_id)

    if team.lead == user_id:
        team.lead = None

    # Clear the user's team pointer if it pointed here.
    user = store.get_user(user_id)
    if user is not None and user.team == team_id:
        user.team = None


def get_team_members(team_id: str) -> List[User]:
    """Return the User objects for every member of the team.

    Raises ValueError if the team does not exist.
    Members whose user records have been deleted are silently omitted.
    """
    team = _require_team(team_id)
    members: List[User] = []
    for uid in team.members:
        u = store.get_user(uid)
        if u is not None:
            members.append(u)
    return members


# ---------------------------------------------------------------------------
# Ticket queries
# ---------------------------------------------------------------------------

def get_team_tickets(team_id: str) -> List[Ticket]:
    """Return active tickets assigned to any member of *team_id*.

    "Active" means the ticket's status is in ACTIVE_STATUSES.  Tickets
    assigned to the team itself (ticket.team == team_id) but without an
    individual assignee are also included.

    Raises ValueError if the team does not exist.
    """
    team = _require_team(team_id)
    member_ids = set(team.members)

    result: List[Ticket] = []
    for ticket in store.list_tickets():
        if ticket.status not in ACTIVE_STATUSES:
            continue
        # Assigned to a team member, or directly to this team.
        if ticket.assignee in member_ids or ticket.team == team_id:
            result.append(ticket)

    return result


def get_team_stats(team_id: str) -> Dict:
    """Return a summary dict for the team.

    Keys:
        member_count        — total members
        active_tickets      — tickets currently in ACTIVE_STATUSES
        avg_workload        — active tickets / member_count (0 if no members)
        tickets_by_status   — {status: count} across all active tickets
        tickets_by_priority — {priority: count} across all active tickets
    """
    team = _require_team(team_id)
    active = get_team_tickets(team_id)

    by_status: Dict[str, int] = {}
    by_priority: Dict[str, int] = {}
    for t in active:
        by_status[t.status] = by_status.get(t.status, 0) + 1
        by_priority[t.priority] = by_priority.get(t.priority, 0) + 1

    member_count = len(team.members)
    active_count = len(active)
    avg = active_count / member_count if member_count else 0.0

    return {
        "member_count":        member_count,
        "active_tickets":      active_count,
        "avg_workload":        round(avg, 2),
        "tickets_by_status":   by_status,
        "tickets_by_priority": by_priority,
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_ticket(ticket_id: str) -> Optional[Team]:
    """Return the best-fit team for a ticket, or None if no match is found.

    Scoring (per team):
      +2  for each of the ticket's tags that appears in team.specialties
      +1  if the ticket's priority appears in team.specialties (e.g. "urgent")
      tie-break: team with fewer current active tickets (lower workload wins)

    A team must have at least one specialty match to be considered.
    """
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        return None

    all_teams = store.list_teams()
    if not all_teams:
        return None

    ticket_tags = {t.lower() for t in ticket.tags}
    ticket_priority = ticket.priority.lower()

    best_team: Optional[Team] = None
    best_score: int = 0
    best_workload: int = 0

    for team in all_teams:
        spec_set = {s.lower() for s in team.specialties}
        if not spec_set:
            continue

        score = 0
        score += 2 * len(ticket_tags & spec_set)
        if ticket_priority in spec_set:
            score += 1

        if score == 0:
            continue

        workload = len(get_team_tickets(team.id))

        if (
            best_team is None
            or score > best_score
            or (score == best_score and workload < best_workload)
        ):
            best_team = team
            best_score = score
            best_workload = workload

    return best_team


# ---------------------------------------------------------------------------
# User → team lookup
# ---------------------------------------------------------------------------

def get_user_team(user_id: str) -> Optional[Team]:
    """Return the team the user belongs to, or None.

    Performs a two-step lookup: first checks user.team, then falls back to
    scanning team membership lists in case the pointer is stale.
    """
    user = store.get_user(user_id)
    if user is None:
        return None

    if user.team:
        team = store.get_team(user.team)
        if team is not None and user_id in team.members:
            return team

    # Fallback scan (handles stale user.team pointer)
    for team in store.list_teams():
        if user_id in team.members:
            _link_user_to_team(user_id, team.id)  # repair pointer
            return team

    return None


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def list_all_teams() -> List[Team]:
    """Return all teams in insertion order."""
    return store.list_teams()


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------

def reset_teams() -> None:
    """Remove all teams from the store and clear team pointers on users.

    Intended for test isolation only.
    """
    for user in store.list_users(active_only=False):
        user.team = None
    store.teams.clear()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _require_team(team_id: str) -> Team:
    team = store.get_team(team_id)
    if team is None:
        raise ValueError(f"Team not found: {team_id!r}")
    return team


def _require_user(user_id: str) -> User:
    user = store.get_user(user_id)
    if user is None:
        raise ValueError(f"User not found: {user_id!r}")
    return user


def _link_user_to_team(user_id: str, team_id: str) -> None:
    """Set user.team = team_id if the user record exists."""
    user = store.get_user(user_id)
    if user is not None:
        user.team = team_id

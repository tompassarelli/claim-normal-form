"""Teams module for ClaimDesk.

Team assignment and filtered queries. Teams are a lightweight registry
mapping team names to sets of ticket IDs. Active-ticket filtering uses
config.TERMINAL_STATUSES so the definition stays in sync system-wide.
"""

from typing import Dict, List, Set

from config import TERMINAL_STATUSES
from core import get_ticket, list_tickets
from models import Ticket

# _teams: team_name -> set of ticket IDs assigned to that team
_teams: Dict[str, Set[str]] = {}


def create_team(team_name: str) -> str:
    """Register a new team.

    Silently no-ops if the team already exists.
    Returns the team name.
    """
    team_name = team_name.strip()
    if not team_name:
        raise ValueError("Team name must not be empty.")
    if team_name not in _teams:
        _teams[team_name] = set()
    return team_name


def assign_to_team(ticket_id: str, team_name: str) -> str:
    """Assign a ticket to a team.

    The team must already exist (call create_team first).
    The ticket must exist in the core store.
    Returns the team name.
    """
    team_name = team_name.strip()
    if team_name not in _teams:
        raise KeyError(f"Team not found: {team_name!r}. Call create_team first.")
    t = get_ticket(ticket_id)
    if t is None:
        raise KeyError(f"Ticket not found: {ticket_id}")
    _teams[team_name].add(ticket_id)
    return team_name


def get_team_tickets(team_name: str) -> List[Ticket]:
    """Return active Ticket objects assigned to the given team.

    Excludes tickets in any terminal status (config.TERMINAL_STATUSES).
    Excludes tickets that have since been deleted from the core store.
    """
    team_name = team_name.strip()
    if team_name not in _teams:
        raise KeyError(f"Team not found: {team_name!r}")
    result = []
    for tid in _teams[team_name]:
        t = get_ticket(tid)
        if t is not None and t.status not in TERMINAL_STATUSES:
            result.append(t)
    return result


def reset_teams() -> None:
    """Clear all team data. Intended for test teardown."""
    _teams.clear()

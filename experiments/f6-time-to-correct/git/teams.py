"""ClaimDesk teams module.

Provides team creation, ticket assignment to teams, and filtered
queries that exclude terminal-status tickets.
"""

from typing import Dict, List, Optional
import core
import config


# In-memory stores for this module.
_teams: Dict[str, set] = {}          # team_name -> set of ticket_ids
_ticket_team: Dict[str, str] = {}    # ticket_id -> team_name


def create_team(team_name: str) -> str:
    """Create a new team.  Returns the team name.
    Raises ValueError if the team already exists.
    """
    if team_name in _teams:
        raise ValueError(f"Team already exists: {team_name!r}")
    _teams[team_name] = set()
    return team_name


def assign_to_team(ticket_id: str, team_name: str) -> None:
    """Assign a ticket to a team.

    Raises KeyError if the ticket does not exist in core state.
    Raises ValueError if the team does not exist.
    """
    ticket = core.get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(f"No ticket with id {ticket_id!r}")
    if team_name not in _teams:
        raise ValueError(f"Team does not exist: {team_name!r}")

    # Remove from any previous team.
    previous = _ticket_team.get(ticket_id)
    if previous and previous in _teams:
        _teams[previous].discard(ticket_id)

    _teams[team_name].add(ticket_id)
    _ticket_team[ticket_id] = team_name


def get_team_tickets(team_name: str) -> List:
    """Return active Ticket objects assigned to team_name.

    Tickets whose status is in config.TERMINAL_STATUSES are excluded.
    Raises ValueError if the team does not exist.
    """
    if team_name not in _teams:
        raise ValueError(f"Team does not exist: {team_name!r}")

    result = []
    for ticket_id in _teams[team_name]:
        ticket = core.get_ticket(ticket_id)
        if ticket is None:
            continue
        if ticket.status not in config.TERMINAL_STATUSES:
            result.append(ticket)
    return result


def reset_teams() -> None:
    """Clear all team state.  Intended for use in tests and resets."""
    _teams.clear()
    _ticket_team.clear()

"""ClaimDesk teams feature module.

Provides team creation, ticket-to-team assignment, and per-team
ticket queries. Team membership is tracked here (not on the Ticket
dataclass) so the core model stays untouched.
"""
from typing import Dict, List, Set
from models import Ticket
import core
from workflow import ACTIVE_STATUSES

# team_name -> set of ticket_ids
_teams: Dict[str, Set[str]] = {}


def create_team(team_name: str) -> None:
    """Register a new team. Idempotent — re-creating is a no-op."""
    if team_name not in _teams:
        _teams[team_name] = set()


def assign_to_team(ticket_id: str, team_name: str) -> None:
    """Assign a ticket to a team.

    Raises KeyError if the team doesn't exist or the ticket isn't found.
    A ticket may belong to multiple teams (no restriction enforced here).
    """
    if team_name not in _teams:
        raise KeyError(f"Team not found: {team_name}")
    ticket = core.get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(f"Ticket not found: {ticket_id}")
    _teams[team_name].add(ticket_id)


def get_team_tickets(team_name: str) -> List[Ticket]:
    """Return active tickets for *team_name* (excludes closed/archived)."""
    if team_name not in _teams:
        raise KeyError(f"Team not found: {team_name}")
    results: List[Ticket] = []
    for tid in _teams[team_name]:
        ticket = core.get_ticket(tid)
        if ticket is not None and ticket.status in ACTIVE_STATUSES:
            results.append(ticket)
    return results


def team_summary() -> Dict[str, int]:
    """Return {team_name: active_ticket_count} for every team."""
    summary: Dict[str, int] = {}
    for team_name in _teams:
        summary[team_name] = len(get_team_tickets(team_name))
    return summary


def reset_teams() -> None:
    """Clear all team state. Used in tests."""
    _teams.clear()

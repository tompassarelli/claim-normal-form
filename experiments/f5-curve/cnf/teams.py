"""ClaimDesk teams feature.

Graph context: config.ACTIVE_STATUSES = ["open", "in_progress",
"resolved", "on_hold"]. workflow.is_active() checks against these.
Team queries should exclude archived/closed tickets.
"""
from typing import Dict, List, Set
from models import Ticket
import core
from config import ACTIVE_STATUSES

_teams: Dict[str, Set[str]] = {}


def create_team(team_name: str) -> None:
    if team_name not in _teams:
        _teams[team_name] = set()


def assign_to_team(ticket_id: str, team_name: str) -> None:
    if team_name not in _teams:
        raise KeyError(f"Team not found: {team_name}")
    ticket = core.get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(f"Ticket not found: {ticket_id}")
    _teams[team_name].add(ticket_id)


def get_team_tickets(team_name: str) -> List[Ticket]:
    if team_name not in _teams:
        raise KeyError(f"Team not found: {team_name}")
    results: List[Ticket] = []
    for tid in _teams[team_name]:
        ticket = core.get_ticket(tid)
        if ticket is not None and ticket.status in ACTIVE_STATUSES:
            results.append(ticket)
    return results


def reset_teams() -> None:
    _teams.clear()

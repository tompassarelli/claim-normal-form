"""
Ticket assignment and workload management.

Public surface:
    assign_ticket       — attach a user to a ticket
    unassign_ticket     — remove the current assignee
    reassign_ticket     — swap assignee in one call
    auto_assign         — heuristic least-loaded assignment
    get_workload        — active ticket counts for one agent
    get_team_workload   — workload summary for every member of a team
    get_available_agents — agents below their max_tickets cap
    is_overloaded       — True when an agent is at or above their cap
    balance_workload    — produce a list of suggested reassignments
    reset_assignment    — no-op; exists for API consistency with other modules
"""

from typing import Dict, List, Optional

import store
from config import ACTIVE_STATUSES
from events import _run_hooks
from models import Ticket, User


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class AssignmentError(ValueError):
    """Raised when an assignment cannot be completed."""


# ---------------------------------------------------------------------------
# Core assignment operations
# ---------------------------------------------------------------------------

def assign_ticket(
    ticket_id: str,
    user_id: str,
    assigned_by: str = "",
) -> Ticket:
    """Assign *user_id* to *ticket_id*.

    Raises:
        KeyError          — ticket or user not found
        AssignmentError   — user is inactive, ineligible, or over capacity
    """
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(f"Ticket '{ticket_id}' not found.")

    user = store.get_user(user_id)
    if user is None:
        raise KeyError(f"User '{user_id}' not found.")

    if not user.is_active:
        raise AssignmentError(f"User '{user_id}' is not active.")

    if not user.can_be_assigned():
        raise AssignmentError(
            f"User '{user_id}' has role '{user.role}' which cannot be assigned tickets."
        )

    if is_overloaded(user_id):
        raise AssignmentError(
            f"User '{user_id}' is at or over their ticket capacity ({user.max_tickets})."
        )

    old_assignee = ticket.assignee
    store.update_ticket(ticket_id, assignee=user_id)

    _run_hooks("assign", ticket=ticket, old_assignee=old_assignee, new_assignee=user_id,
               assigned_by=assigned_by)

    return ticket


def unassign_ticket(ticket_id: str, assigned_by: str = "") -> Ticket:
    """Remove the current assignee from *ticket_id*.

    Raises:
        KeyError — ticket not found
    """
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(f"Ticket '{ticket_id}' not found.")

    old_assignee = ticket.assignee
    store.update_ticket(ticket_id, assignee=None)

    _run_hooks("assign", ticket=ticket, old_assignee=old_assignee, new_assignee=None,
               assigned_by=assigned_by)

    return ticket


def reassign_ticket(
    ticket_id: str,
    new_user_id: str,
    assigned_by: str = "",
) -> Ticket:
    """Unassign the current holder and assign *new_user_id* in one operation.

    Validation follows the same rules as assign_ticket().
    """
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(f"Ticket '{ticket_id}' not found.")

    user = store.get_user(new_user_id)
    if user is None:
        raise KeyError(f"User '{new_user_id}' not found.")

    if not user.is_active:
        raise AssignmentError(f"User '{new_user_id}' is not active.")

    if not user.can_be_assigned():
        raise AssignmentError(
            f"User '{new_user_id}' has role '{user.role}' which cannot be assigned tickets."
        )

    # Capacity check: if new user already holds this ticket, skip the count
    # (we're not adding a new ticket, just retaining it).
    if ticket.assignee != new_user_id and is_overloaded(new_user_id):
        raise AssignmentError(
            f"User '{new_user_id}' is at or over their ticket capacity ({user.max_tickets})."
        )

    old_assignee = ticket.assignee
    store.update_ticket(ticket_id, assignee=new_user_id)

    _run_hooks("assign", ticket=ticket, old_assignee=old_assignee, new_assignee=new_user_id,
               assigned_by=assigned_by)

    return ticket


# ---------------------------------------------------------------------------
# Automatic assignment
# ---------------------------------------------------------------------------

def auto_assign(ticket_id: str) -> Optional[Ticket]:
    """Assign the ticket to the least-loaded eligible agent.

    Strategy:
    1. Prefer agents on the ticket's team (if the ticket has a team).
    2. Fall back to any available agent across all teams.
    3. Return None if no eligible agent exists.
    """
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        return None

    # Prefer team-scoped agents first.
    candidates = get_available_agents(team_id=ticket.team) if ticket.team else []
    if not candidates:
        candidates = get_available_agents()

    if not candidates:
        return None

    # Pick the agent with the fewest active tickets.
    def _load(user: User) -> int:
        return get_workload(user.id)["total_active"]

    best = min(candidates, key=_load)

    old_assignee = ticket.assignee
    store.update_ticket(ticket_id, assignee=best.id)

    _run_hooks("assign", ticket=ticket, old_assignee=old_assignee, new_assignee=best.id,
               assigned_by="auto")

    return ticket


# ---------------------------------------------------------------------------
# Workload queries
# ---------------------------------------------------------------------------

def get_workload(user_id: str) -> Dict[str, int]:
    """Return a workload summary dict for *user_id*.

    Keys: open_count, in_progress_count, resolved_count, total_active.
    Counts only tickets in ACTIVE_STATUSES assigned to this user.
    """
    assigned = store.list_tickets({"assignee": user_id})
    active = [t for t in assigned if t.status in ACTIVE_STATUSES]

    return {
        "open_count":        sum(1 for t in active if t.status == "open"),
        "in_progress_count": sum(1 for t in active if t.status == "in_progress"),
        "resolved_count":    sum(1 for t in active if t.status == "resolved"),
        "total_active":      len(active),
    }


def get_team_workload(team_id: str) -> List[Dict]:
    """Return a list of {user_id, workload} dicts for every member of *team_id*.

    Members with no tickets are included with zeroed counts.  Sorted by
    total_active descending so the most loaded agent appears first.
    """
    team = store.get_team(team_id)
    if team is None:
        return []

    result = []
    for user_id in team.members:
        result.append({"user_id": user_id, "workload": get_workload(user_id)})

    result.sort(key=lambda r: r["workload"]["total_active"], reverse=True)
    return result


def get_available_agents(team_id: Optional[str] = None) -> List[User]:
    """Return active, assignable agents who have not yet hit their cap.

    If *team_id* is provided, only members of that team are considered.
    """
    users = store.list_users(active_only=True, team=team_id)
    eligible = [u for u in users if u.can_be_assigned()]
    return [u for u in eligible if not is_overloaded(u.id)]


def is_overloaded(user_id: str) -> bool:
    """Return True when the agent is at or above their max_tickets threshold."""
    user = store.get_user(user_id)
    if user is None:
        return False
    workload = get_workload(user_id)
    return workload["total_active"] >= user.max_tickets


# ---------------------------------------------------------------------------
# Workload balancing
# ---------------------------------------------------------------------------

def balance_workload(team_id: str) -> List[Dict]:
    """Suggest reassignments to even out load across team members.

    Returns a list of dicts:
        {"ticket_id": str, "from_user": str, "to_user": str}

    Strategy: repeatedly move the highest-priority open ticket from the
    most overloaded agent to the least loaded available agent until no agent
    is overloaded or no more moves are possible.  This is a greedy heuristic,
    not an optimal solver.

    No actual reassignments are performed — the caller decides whether to
    apply the suggestions.
    """
    team = store.get_team(team_id)
    if team is None:
        return []

    # Build mutable load map: {user_id: [ticket, ...]} for active tickets.
    load_map: Dict[str, List[Ticket]] = {}
    for user_id in team.members:
        user = store.get_user(user_id)
        if user is None or not user.is_active or not user.can_be_assigned():
            continue
        assigned = store.list_tickets({"assignee": user_id})
        load_map[user_id] = [t for t in assigned if t.status in ACTIVE_STATUSES]

    suggestions: List[Dict] = []

    for _ in range(100):  # safety limit
        if not load_map:
            break

        overloaded = {
            uid: tickets
            for uid, tickets in load_map.items()
            if _user_max(uid) is not None
            and len(tickets) >= _user_max(uid)  # type: ignore[operator]
        }
        if not overloaded:
            break

        # Most loaded overloaded agent.
        from_uid = max(overloaded, key=lambda uid: len(load_map[uid]))

        # Least loaded agent with remaining capacity.
        under_capacity = {
            uid: tickets
            for uid, tickets in load_map.items()
            if uid != from_uid
            and _user_max(uid) is not None
            and len(tickets) < _user_max(uid)  # type: ignore[operator]
        }
        if not under_capacity:
            break  # nowhere to move tickets

        to_uid = min(under_capacity, key=lambda uid: len(load_map[uid]))

        # Move the ticket with the highest-weight priority.
        from config import PRIORITY_WEIGHTS
        candidate_tickets = load_map[from_uid]
        ticket_to_move = max(
            candidate_tickets,
            key=lambda t: PRIORITY_WEIGHTS.get(t.priority, 0),
        )

        suggestions.append({
            "ticket_id": ticket_to_move.id,
            "from_user": from_uid,
            "to_user":   to_uid,
        })

        # Update the in-memory simulation.
        load_map[from_uid].remove(ticket_to_move)
        load_map[to_uid].append(ticket_to_move)

    return suggestions


def _user_max(user_id: str) -> Optional[int]:
    user = store.get_user(user_id)
    return user.max_tickets if user else None


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------

def reset_assignment() -> None:
    """No persistent state to reset; present for API consistency."""
    pass

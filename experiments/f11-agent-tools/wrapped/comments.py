from typing import Optional, List, Dict
import time

from core import get_ticket

# graph returned no TERMINAL_STATUSES constant; "closed" is the only terminal
# state visible in core.py (close_ticket sets status="closed").
TERMINAL_STATUSES = {"closed"}


_comments: List[Dict] = []


def _now() -> str:
    return str(int(time.time()))


def add_comment(ticket_id: str, user_id: str, text: str) -> Optional[dict]:
    """Return comment dict, or None if ticket is in a terminal state."""
    ticket = get_ticket(ticket_id)
    if ticket is None or ticket.status in TERMINAL_STATUSES:
        return None
    comment = {
        "ticket_id": ticket_id,
        "user_id": user_id,
        "text": text,
        "timestamp": _now(),
    }
    _comments.append(comment)
    return comment


def get_comments(ticket_id: Optional[str] = None) -> list:
    if ticket_id is None:
        return list(_comments)
    return [c for c in _comments if c["ticket_id"] == ticket_id]


def reset_comments() -> None:
    _comments.clear()
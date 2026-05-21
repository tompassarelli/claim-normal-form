from core import get_ticket
from typing import Optional
import time

_comments: list = []

# Only open tickets accept new comments; closed tickets are read-only.
_COMMENTING_ALLOWED_STATUSES = {"open"}


def add_comment(ticket_id: str, user_id: str, text: str) -> Optional[dict]:
    ticket = get_ticket(ticket_id)
    if ticket is None or ticket.status not in _COMMENTING_ALLOWED_STATUSES:
        return None
    comment = {
        "ticket_id": ticket_id,
        "user_id": user_id,
        "text": text,
        "timestamp": str(int(time.time())),
    }
    _comments.append(comment)
    return comment


def get_comments(ticket_id: Optional[str] = None) -> list:
    if ticket_id is None:
        return list(_comments)
    return [c for c in _comments if c["ticket_id"] == ticket_id]


def reset_comments():
    _comments.clear()
from typing import Optional
import time

from core import get_ticket

_comments: list = []

# Statuses on which new comments are not permitted.
# "closed" is the only terminal status visible in the codebase; the graph
# returned no additional facts from hidden modules, so we use a blocklist
# rather than an allowlist to stay open to unknown intermediate statuses.
_BLOCKED_STATUSES = {"closed"}


def add_comment(ticket_id: str, user_id: str, text: str) -> Optional[dict]:
    ticket = get_ticket(ticket_id)
    if ticket is None or ticket.status in _BLOCKED_STATUSES:
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
"""
Ticket comments and internal notes.

External comments are blocked on tickets in a terminal status; internal
notes (is_internal=True) may be added to any ticket regardless of status
so that agents can document post-close activity.

All mutations fire events via events.emit() and the legacy _run_hooks path.
"""

import time
from typing import List, Optional

import store
from config import MAX_COMMENT_LENGTH, TERMINAL_STATUSES
from events import _run_hooks, emit
from models import Comment


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return f"{time.time():.3f}"


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def add_comment(
    ticket_id: str,
    author_id: str,
    body: str,
    is_internal: bool = False,
) -> Comment:
    """Create and persist a comment on *ticket_id*.

    Raises:
        ValueError: if the ticket does not exist, the body is empty or exceeds
                    MAX_COMMENT_LENGTH, or an external comment is attempted on
                    a ticket in a terminal status.
    """
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise ValueError(f"Ticket not found: {ticket_id!r}")

    body = body.strip()
    if not body:
        raise ValueError("Comment body must not be empty")
    if len(body) > MAX_COMMENT_LENGTH:
        raise ValueError(
            f"Comment body exceeds maximum length of {MAX_COMMENT_LENGTH} characters"
        )

    if not is_internal and ticket.status in TERMINAL_STATUSES:
        raise ValueError(
            f"Cannot add external comment to ticket {ticket_id!r}: "
            f"ticket is in terminal status {ticket.status!r}"
        )

    comment = Comment(
        id="",
        ticket_id=ticket_id,
        author_id=author_id,
        body=body,
        created_at=_now(),
        is_internal=is_internal,
    )

    _run_hooks(
        "pre_comment",
        ticket_id=ticket_id,
        author_id=author_id,
        is_internal=is_internal,
    )

    stored = store.add_comment(comment)

    emit(
        "ticket.commented",
        ticket_id=ticket_id,
        comment_id=stored.id,
        author_id=author_id,
        is_internal=is_internal,
    )
    _run_hooks(
        "post_comment",
        ticket_id=ticket_id,
        comment_id=stored.id,
        author_id=author_id,
        is_internal=is_internal,
    )

    return stored


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

def get_comments(ticket_id: str, include_internal: bool = True) -> List[Comment]:
    """Return all comments for *ticket_id*, sorted oldest-first.

    If *include_internal* is False, internal notes are excluded.
    """
    all_comments = store.get_comments(ticket_id)
    if not include_internal:
        all_comments = [c for c in all_comments if not c.is_internal]
    return sorted(all_comments, key=lambda c: c.created_at)


def get_comment(comment_id: str) -> Optional[Comment]:
    """Return the comment with the given ID, or None if not found."""
    return store.comments.get(comment_id)


def get_recent_comments(ticket_id: str, limit: int = 10) -> List[Comment]:
    """Return up to *limit* most-recent comments for *ticket_id*."""
    all_comments = sorted(
        store.get_comments(ticket_id),
        key=lambda c: c.created_at,
        reverse=True,
    )
    return all_comments[:limit]


def count_comments(ticket_id: str) -> int:
    """Return total number of comments (including internal) on *ticket_id*."""
    return store.count_comments(ticket_id)


def get_user_comments(user_id: str) -> List[Comment]:
    """Return all comments authored by *user_id*, sorted oldest-first."""
    result = [c for c in store.comments.values() if c.author_id == user_id]
    return sorted(result, key=lambda c: c.created_at)


def get_internal_notes(ticket_id: str) -> List[Comment]:
    """Return only internal notes for *ticket_id*, sorted oldest-first."""
    result = [
        c for c in store.get_comments(ticket_id) if c.is_internal
    ]
    return sorted(result, key=lambda c: c.created_at)


def has_comments(ticket_id: str) -> bool:
    """Return True if *ticket_id* has at least one comment."""
    return store.count_comments(ticket_id) > 0


def get_last_comment_time(ticket_id: str) -> Optional[str]:
    """Return the created_at timestamp of the most recent comment, or None."""
    all_comments = store.get_comments(ticket_id)
    if not all_comments:
        return None
    return max(c.created_at for c in all_comments)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def reset_comments() -> None:
    """Remove all comments from the store. Intended for use in tests only."""
    store.comments.clear()
    store._counters["comment"].reset()

"""
Ticket tagging and tag catalogue management.

Tags are stored in the store keyed by lowercase name, giving O(1) lookup.
Each Ticket.tags list holds raw (lowercased) tag names as strings.

Design choices:
- Tag names are always normalised to lowercase before storage or lookup.
- create_tag() is idempotent: calling it on an existing name updates
  color/description rather than raising an error.
- merge_tags() rewrites every ticket that has old_name and ensures the new
  tag exists in the catalogue before doing so.
- delete_tag() removes the tag from the catalogue and from every ticket.
"""

from typing import Dict, List, Optional

import store
from config import MAX_TAGS_PER_TICKET
from events import _run_hooks, emit
from models import Tag


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise(name: str) -> str:
    return name.strip().lower()


# ---------------------------------------------------------------------------
# Ticket-level tagging
# ---------------------------------------------------------------------------

def add_tag_to_ticket(ticket_id: str, tag_name: str) -> List[str]:
    """Attach *tag_name* to *ticket_id*.  Creates the tag if it does not exist.

    Returns the updated tag list on the ticket.

    Raises:
        ValueError: if the ticket is not found or adding the tag would exceed
                    MAX_TAGS_PER_TICKET.
    """
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise ValueError(f"Ticket not found: {ticket_id!r}")

    name = _normalise(tag_name)
    if not name:
        raise ValueError("Tag name must not be empty")

    if name in ticket.tags:
        return list(ticket.tags)

    if len(ticket.tags) >= MAX_TAGS_PER_TICKET:
        raise ValueError(
            f"Ticket {ticket_id!r} already has the maximum of "
            f"{MAX_TAGS_PER_TICKET} tags"
        )

    # Ensure the tag exists in the catalogue.
    if store.get_tag(name) is None:
        store.add_tag(Tag(name=name))

    ticket.tags.append(name)
    store.update_ticket(ticket_id, tags=list(ticket.tags))

    emit("ticket.tagged", ticket_id=ticket_id, tag=name, action="added")
    _run_hooks("post_tag", ticket_id=ticket_id, tag=name, action="added")

    return list(ticket.tags)


def remove_tag_from_ticket(ticket_id: str, tag_name: str) -> List[str]:
    """Remove *tag_name* from *ticket_id*.

    Returns the updated tag list.  Silently succeeds if the ticket did not
    have the tag (idempotent removal).

    Raises:
        ValueError: if the ticket is not found.
    """
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise ValueError(f"Ticket not found: {ticket_id!r}")

    name = _normalise(tag_name)
    if name not in ticket.tags:
        return list(ticket.tags)

    ticket.tags.remove(name)
    store.update_ticket(ticket_id, tags=list(ticket.tags))

    emit("ticket.tagged", ticket_id=ticket_id, tag=name, action="removed")
    _run_hooks("post_tag", ticket_id=ticket_id, tag=name, action="removed")

    return list(ticket.tags)


def get_ticket_tags(ticket_id: str) -> List[str]:
    """Return the tag list for *ticket_id*, or an empty list if not found."""
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        return []
    return list(ticket.tags)


def find_tickets_by_tag(tag_name: str) -> List[str]:
    """Return IDs of all tickets that carry *tag_name*."""
    name = _normalise(tag_name)
    return [t.id for t in store.tickets.values() if name in t.tags]


# ---------------------------------------------------------------------------
# Tag catalogue management
# ---------------------------------------------------------------------------

def create_tag(name: str, color: str = "gray", description: str = "") -> Tag:
    """Create or update a tag in the catalogue.

    If a tag with *name* already exists its color and description are updated
    to the supplied values and the updated Tag is returned.
    """
    name = _normalise(name)
    if not name:
        raise ValueError("Tag name must not be empty")

    existing = store.get_tag(name)
    if existing is not None:
        existing.color = color
        existing.description = description
        return existing

    tag = Tag(name=name, color=color, description=description)
    return store.add_tag(tag)


def get_all_tags() -> List[Tag]:
    """Return all tags in the catalogue, sorted alphabetically by name."""
    return sorted(store.list_tags(), key=lambda t: t.name)


def get_tag_usage() -> Dict[str, int]:
    """Return a dict mapping tag name -> number of tickets that carry it."""
    usage: Dict[str, int] = {}
    for ticket in store.tickets.values():
        for tag in ticket.tags:
            usage[tag] = usage.get(tag, 0) + 1
    return usage


def get_popular_tags(limit: int = 10) -> List[Tag]:
    """Return up to *limit* Tag objects sorted by usage (most used first).

    Tags that appear on tickets but have no catalogue entry are included with
    a synthetic Tag(name=..., color='gray').  Tags with zero usage come last,
    sorted alphabetically.
    """
    usage = get_tag_usage()

    # Build a merged set: catalogue entries + any in-use names not yet catalogued.
    tag_map: Dict[str, Tag] = {t.name: t for t in store.list_tags()}
    for name in usage:
        if name not in tag_map:
            tag_map[name] = Tag(name=name)

    all_tags = list(tag_map.values())
    all_tags.sort(key=lambda t: (-usage.get(t.name, 0), t.name))
    return all_tags[:limit]


def merge_tags(old_name: str, new_name: str) -> int:
    """Rename *old_name* to *new_name* across the entire ticket corpus.

    Creates *new_name* in the catalogue if it does not already exist (copying
    color/description from *old_name* if available).  Removes *old_name* from
    the catalogue after migration.

    Returns the number of tickets whose tag lists were modified.
    """
    old = _normalise(old_name)
    new = _normalise(new_name)
    if not old or not new:
        raise ValueError("Tag names must not be empty")
    if old == new:
        return 0

    old_tag = store.get_tag(old)
    new_tag = store.get_tag(new)
    if new_tag is None:
        color = old_tag.color if old_tag else "gray"
        description = old_tag.description if old_tag else ""
        store.add_tag(Tag(name=new, color=color, description=description))

    count = 0
    for ticket in store.tickets.values():
        if old in ticket.tags:
            ticket.tags.remove(old)
            if new not in ticket.tags:
                ticket.tags.append(new)
            store.update_ticket(ticket.id, tags=list(ticket.tags))
            count += 1

    # Remove old tag from catalogue.
    if old in store.tags:
        del store.tags[old]

    return count


def delete_tag(name: str) -> int:
    """Remove *name* from the catalogue and strip it from every ticket.

    Returns the number of tickets from which the tag was removed.
    """
    name = _normalise(name)
    if not name:
        raise ValueError("Tag name must not be empty")

    count = 0
    for ticket in store.tickets.values():
        if name in ticket.tags:
            ticket.tags.remove(name)
            store.update_ticket(ticket.id, tags=list(ticket.tags))
            count += 1

    if name in store.tags:
        del store.tags[name]

    return count


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def reset_tags() -> None:
    """Clear the tag catalogue and remove all tags from every ticket.

    Intended for use in tests only.
    """
    store.tags.clear()
    for ticket in store.tickets.values():
        ticket.tags.clear()

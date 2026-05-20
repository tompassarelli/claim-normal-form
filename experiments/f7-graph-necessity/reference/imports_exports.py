"""
Data import and export for the helpdesk/CRM application.

Export functions serialise live store data to JSON or CSV strings.
Import functions parse those strings, validate each record, and delegate
to tickets.create_ticket for persistence (so hooks and audit trail fire
normally).

CSV dialect: comma-separated, first row is a header, values are quoted
when they contain commas or newlines.  Multi-value fields (tags) are
stored as pipe-separated strings within a single cell.

Supported formats throughout: "json", "csv".
"""

import csv
import io
import json
import time
import uuid
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import store
from config import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    PRIORITIES,
    SOURCES,
    STATUSES,
)
from models import Ticket


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return f"{time.time():.3f}"


def _serialize_ticket(ticket: Ticket) -> Dict[str, Any]:
    """Return a plain dict for *ticket*, including computed fields.

    Computed fields appended:
        is_active       — bool, True when status in ACTIVE_STATUSES
        age_minutes     — int, minutes since created_at (0 if unknown)
        comment_count   — int, total comments on the ticket
        tag_list        — str, pipe-separated tag names (empty string if none)
        assignee_name   — str, display name of the assignee (or "")
        team_name       — str, display name of the team (or "")
    """
    now = time.time()
    try:
        created = float(ticket.created_at)
        age_minutes = int((now - created) / 60)
    except (TypeError, ValueError):
        age_minutes = 0

    assignee_user = store.get_user(ticket.assignee) if ticket.assignee else None
    team_obj = store.get_team(ticket.team) if ticket.team else None

    return {
        "id":            ticket.id,
        "title":         ticket.title,
        "description":   ticket.description,
        "status":        ticket.status,
        "priority":      ticket.priority,
        "assignee":      ticket.assignee or "",
        "assignee_name": assignee_user.name if assignee_user else "",
        "contact_email": ticket.contact_email,
        "created_at":    ticket.created_at,
        "updated_at":    ticket.updated_at,
        "tags":          ticket.tags,
        "tag_list":      "|".join(ticket.tags),
        "team":          ticket.team or "",
        "team_name":     team_obj.name if team_obj else "",
        "sla_policy":    ticket.sla_policy or "",
        "source":        ticket.source,
        "is_active":     ticket.status in ACTIVE_STATUSES,
        "age_minutes":   age_minutes,
        "comment_count": store.count_comments(ticket.id),
    }


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

_CSV_FIELDS = [
    "id", "title", "description", "status", "priority",
    "assignee", "assignee_name", "contact_email",
    "created_at", "updated_at",
    "tag_list", "team", "team_name", "sla_policy", "source",
    "is_active", "age_minutes", "comment_count",
]


def _parse_csv(csv_string: str) -> List[Dict[str, str]]:
    """Parse a CSV string (with header row) into a list of dicts.

    All values are strings; callers are responsible for type coercion.
    Returns an empty list for empty input.
    """
    csv_string = csv_string.strip()
    if not csv_string:
        return []
    reader = csv.DictReader(io.StringIO(csv_string))
    return [dict(row) for row in reader]


def _parse_json(json_string: str) -> List[Dict[str, Any]]:
    """Parse a JSON string into a list of dicts.

    Accepts both a top-level array and an object with a "tickets" key.
    Returns an empty list for empty input.
    """
    json_string = json_string.strip()
    if not json_string:
        return []
    data = json.loads(json_string)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("tickets", [data])
    raise ValueError(f"JSON root must be an array or object, got {type(data).__name__!r}")


def _to_csv(rows: List[Dict[str, Any]], fieldnames: List[str]) -> str:
    """Serialise a list of dicts to a CSV string."""
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=fieldnames,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_REQUIRED_IMPORT_FIELDS = {"title", "description", "contact_email"}


def validate_import_data(data: str, format: str = "json") -> List[str]:
    """Parse *data* and return a list of human-readable error strings.

    An empty list means the data is valid for import.  Errors reference
    the row index (0-based) to help callers pinpoint problems.
    """
    errors: List[str] = []

    try:
        if format == "json":
            rows = _parse_json(data)
        elif format == "csv":
            rows = _parse_csv(data)
        else:
            return [f"Unsupported format: {format!r}"]
    except Exception as exc:
        return [f"Parse error: {exc}"]

    for i, row in enumerate(rows):
        prefix = f"Row {i}"

        for field in _REQUIRED_IMPORT_FIELDS:
            val = row.get(field, "")
            if not str(val).strip():
                errors.append(f"{prefix}: {field!r} is required and must not be empty")

        if "priority" in row and row["priority"] and row["priority"] not in PRIORITIES:
            errors.append(
                f"{prefix}: priority {row['priority']!r} is not valid; "
                f"choose from {PRIORITIES}"
            )

        if "status" in row and row["status"] and row["status"] not in STATUSES:
            errors.append(
                f"{prefix}: status {row['status']!r} is not valid; "
                f"choose from {sorted(STATUSES)}"
            )

        if "source" in row and row["source"] and row["source"] not in SOURCES:
            errors.append(
                f"{prefix}: source {row['source']!r} is not valid; "
                f"choose from {sorted(SOURCES)}"
            )

    return errors


# ---------------------------------------------------------------------------
# Ticket export
# ---------------------------------------------------------------------------

def export_tickets(
    filters: Optional[Dict[str, Any]] = None,
    format: str = "json",
) -> str:
    """Export filtered tickets as a JSON or CSV string.

    *filters* is passed directly to store.list_tickets.  Each ticket is
    serialised via _serialize_ticket so computed fields are included.

    Raises ValueError for unsupported formats.
    """
    tickets = store.list_tickets(filters)
    rows = [_serialize_ticket(t) for t in tickets]

    if format == "json":
        return json.dumps({"tickets": rows, "count": len(rows)}, indent=2)

    if format == "csv":
        return _to_csv(rows, _CSV_FIELDS)

    raise ValueError(f"Unsupported export format: {format!r}")


def export_ticket(ticket_id: str, format: str = "json") -> str:
    """Export a single ticket with full detail including comments and audit trail.

    Raises ValueError if the ticket does not exist or the format is unsupported.
    """
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise ValueError(f"Ticket not found: {ticket_id!r}")

    base = _serialize_ticket(ticket)

    comments_raw = store.get_comments(ticket_id)
    comments_data = [
        {
            "id":          c.id,
            "author_id":   c.author_id,
            "body":        c.body,
            "created_at":  c.created_at,
            "is_internal": c.is_internal,
        }
        for c in comments_raw
    ]

    audit_raw = store.get_audit_trail(entity_type="ticket", entity_id=ticket_id)
    audit_data = [
        {
            "id":          e.id,
            "timestamp":   e.timestamp,
            "action":      e.action,
            "user_id":     e.user_id,
            "details":     e.details,
        }
        for e in audit_raw
    ]

    if format == "json":
        payload = {**base, "comments": comments_data, "audit_trail": audit_data}
        return json.dumps(payload, indent=2)

    if format == "csv":
        # CSV can only represent flat data; comments and audit are omitted
        # with a note in the comment_count field (already present in base).
        return _to_csv([base], _CSV_FIELDS)

    raise ValueError(f"Unsupported export format: {format!r}")


# ---------------------------------------------------------------------------
# Ticket import
# ---------------------------------------------------------------------------

def import_tickets(
    data: str,
    format: str = "json",
    user_id: str = "",
) -> Dict[str, Any]:
    """Parse *data* and create tickets from each valid record.

    Records with validation errors are skipped.  Terminal-status tickets
    are imported as-is (status is preserved from the source data).

    Returns a dict with keys:
        imported  — number of successfully created tickets
        skipped   — number of records skipped due to errors
        errors    — list of {"row": i, "errors": [...]} dicts
    """
    # Import here to avoid a circular import (tickets imports from store/config,
    # which is fine, but importing at module level would create a dependency cycle
    # if tickets.py ever imports from imports_exports.py).
    try:
        import tickets as tickets_module
        create_ticket = tickets_module.create_ticket
    except ImportError:
        # Fallback: create directly via store when tickets module is unavailable.
        create_ticket = _store_create_ticket

    try:
        if format == "json":
            rows = _parse_json(data)
        elif format == "csv":
            rows = _parse_csv(data)
        else:
            return {"imported": 0, "skipped": 0, "errors": [{"row": -1, "errors": [f"Unsupported format: {format!r}"]}]}
    except Exception as exc:
        return {"imported": 0, "skipped": 0, "errors": [{"row": -1, "errors": [f"Parse error: {exc}"]}]}

    imported = 0
    skipped = 0
    error_list: List[Dict[str, Any]] = []

    for i, row in enumerate(rows):
        row_errors: List[str] = []

        title = str(row.get("title", "")).strip()
        description = str(row.get("description", "")).strip()
        contact_email = str(row.get("contact_email", "")).strip()

        if not title:
            row_errors.append("title is required")
        if not description:
            row_errors.append("description is required")
        if not contact_email:
            row_errors.append("contact_email is required")

        priority = str(row.get("priority", "medium")).strip() or "medium"
        if priority not in PRIORITIES:
            row_errors.append(f"priority {priority!r} is not valid")
            priority = "medium"

        source = str(row.get("source", "web")).strip() or "web"
        if source not in SOURCES:
            row_errors.append(f"source {source!r} is not valid")
            source = "web"

        if row_errors:
            error_list.append({"row": i, "errors": row_errors})
            skipped += 1
            continue

        # Parse optional fields
        tag_list_raw = str(row.get("tag_list", row.get("tags", ""))).strip()
        if isinstance(row.get("tags"), list):
            tags = [str(t).strip() for t in row["tags"] if str(t).strip()]
        else:
            tags = [t.strip() for t in tag_list_raw.split("|") if t.strip()]

        status = str(row.get("status", "open")).strip() or "open"
        if status not in STATUSES:
            status = "open"

        try:
            ticket = create_ticket(
                title=title,
                description=description,
                priority=priority,
                source=source,
                contact_email=contact_email,
                user_id=user_id,
            )
            # Apply tags and non-default status as post-create updates so we
            # don't depend on create_ticket's exact signature.
            updates: Dict[str, Any] = {}
            if tags:
                updates["tags"] = tags
            if status != "open" and status != ticket.status:
                updates["status"] = status
            if updates:
                store.update_ticket(ticket.id, **updates)
            imported += 1
        except Exception as exc:
            error_list.append({"row": i, "errors": [str(exc)]})
            skipped += 1

    return {"imported": imported, "skipped": skipped, "errors": error_list}


# ---------------------------------------------------------------------------
# Team report export
# ---------------------------------------------------------------------------

def export_team_report(team_id: str, format: str = "json") -> str:
    """Export all active tickets assigned to members of *team_id*.

    Raises ValueError if the team does not exist or format is unsupported.
    """
    team = store.get_team(team_id)
    if team is None:
        raise ValueError(f"Team not found: {team_id!r}")

    member_ids = set(team.members)
    tickets = [
        t for t in store.list_tickets()
        if t.status in ACTIVE_STATUSES
        and (t.assignee in member_ids or t.team == team_id)
    ]
    rows = [_serialize_ticket(t) for t in tickets]
    meta = {
        "team_id":   team.id,
        "team_name": team.name,
        "count":     len(rows),
    }

    if format == "json":
        return json.dumps({"meta": meta, "tickets": rows}, indent=2)

    if format == "csv":
        return _to_csv(rows, _CSV_FIELDS)

    raise ValueError(f"Unsupported export format: {format!r}")


# ---------------------------------------------------------------------------
# Audit trail export
# ---------------------------------------------------------------------------

def export_audit_trail(
    ticket_id: Optional[str] = None,
    format: str = "json",
) -> str:
    """Export audit entries to a string.

    If *ticket_id* is given, only entries for that ticket are exported.
    Otherwise all audit entries are exported.

    Raises ValueError for unsupported formats.
    """
    entries = store.get_audit_trail(
        entity_type="ticket" if ticket_id else None,
        entity_id=ticket_id,
    )
    rows = [
        {
            "id":          e.id,
            "timestamp":   e.timestamp,
            "action":      e.action,
            "entity_type": e.entity_type,
            "entity_id":   e.entity_id,
            "user_id":     e.user_id,
            "details":     e.details,
        }
        for e in entries
    ]

    if format == "json":
        return json.dumps({"audit_trail": rows, "count": len(rows)}, indent=2)

    if format == "csv":
        fieldnames = ["id", "timestamp", "action", "entity_type", "entity_id", "user_id"]
        flat_rows = [{k: r[k] for k in fieldnames} for r in rows]
        return _to_csv(flat_rows, fieldnames)

    raise ValueError(f"Unsupported export format: {format!r}")


# ---------------------------------------------------------------------------
# Fallback ticket creator (used when tickets.py is not importable)
# ---------------------------------------------------------------------------

def _store_create_ticket(
    title: str,
    description: str,
    priority: str = "medium",
    source: str = "web",
    contact_email: str = "",
    tags: Optional[List[str]] = None,
    user_id: str = "",
) -> Ticket:
    """Minimal ticket creation that bypasses the tickets module."""
    ticket = Ticket(
        id="",
        title=title,
        description=description,
        status="open",
        priority=priority,
        contact_email=contact_email,
        tags=list(tags or []),
        source=source,
    )
    return store.add_ticket(ticket)


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------

def reset_imports() -> None:
    """No-op: this module has no persistent state to reset.

    Included for API consistency with other modules.
    """
    pass

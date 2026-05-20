"""F4 integration oracle.

Tests that expose coordination failures when multiple agents modify
shared files (config.py, core.py) and write feature modules.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from core import *
from models import Ticket, User
from workflow import *
import config


# ═══════════════════════════════════════════════════════════════
# BASE TESTS — sanity checks
# ═══════════════════════════════════════════════════════════════

def test_base_create():
    reset_state()
    t = create_ticket("Bug", "Broken")
    assert t.status == "open"


def test_base_close():
    reset_state()
    t = create_ticket("Bug", "Broken")
    close_ticket(t.id)
    assert get_ticket(t.id).status == "closed"


def test_workflow_transitions():
    reset_state()
    t = create_ticket("Bug", "Broken")
    transition_ticket(t.id, "in_progress")
    assert get_ticket(t.id).status == "in_progress"
    transition_ticket(t.id, "resolved")
    assert get_ticket(t.id).status == "resolved"


def test_workflow_archive():
    reset_state()
    t = create_ticket("Old bug", "Fixed")
    transition_ticket(t.id, "closed")
    archive_ticket(t.id)
    assert get_ticket(t.id).status == "archived"
    assert is_archived(get_ticket(t.id))


# ═══════════════════════════════════════════════════════════════
# SHARED CONFIG TESTS — do agents agree on system state?
# ═══════════════════════════════════════════════════════════════

def test_config_has_archive_action():
    """config.SYSTEM_ACTIONS must include 'archive'."""
    assert "archive" in config.SYSTEM_ACTIONS, (
        f"SYSTEM_ACTIONS missing 'archive': {config.SYSTEM_ACTIONS}")


def test_config_has_transition_action():
    """config.SYSTEM_ACTIONS must include 'transition'."""
    assert "transition" in config.SYSTEM_ACTIONS, (
        f"SYSTEM_ACTIONS missing 'transition': {config.SYSTEM_ACTIONS}")


def test_config_terminal_has_archived():
    """config.TERMINAL_STATUSES must include 'archived'."""
    assert "archived" in config.TERMINAL_STATUSES, (
        f"TERMINAL_STATUSES missing 'archived': {config.TERMINAL_STATUSES}")


def test_config_all_statuses_complete():
    """config.ALL_STATUSES must include all 5 workflow states."""
    for s in ["open", "in_progress", "resolved", "closed", "archived"]:
        assert s in config.ALL_STATUSES, (
            f"ALL_STATUSES missing '{s}': {config.ALL_STATUSES}")


def test_config_no_duplicates():
    """No duplicates in any config list."""
    assert len(config.SYSTEM_ACTIONS) == len(set(config.SYSTEM_ACTIONS)), (
        f"Duplicates in SYSTEM_ACTIONS: {config.SYSTEM_ACTIONS}")
    assert len(config.ALL_STATUSES) == len(set(config.ALL_STATUSES)), (
        f"Duplicates in ALL_STATUSES: {config.ALL_STATUSES}")


# ═══════════════════════════════════════════════════════════════
# HOOK REGISTRATION TESTS — did agents wire into shared hooks?
# ═══════════════════════════════════════════════════════════════

def test_hooks_registered():
    """At least one hook must be registered in config.HOOKS."""
    total = sum(len(v) for v in config.HOOKS.values())
    assert total > 0, "No hooks registered — agents didn't wire into the hook system"


def test_post_create_has_hooks():
    """post_create should have at least one hook (audit or notification)."""
    assert len(config.HOOKS.get("post_create", [])) > 0, (
        "No post_create hooks — neither audit nor notification wired in")


def test_post_transition_has_hooks():
    """post_transition should have hooks for audit and/or notification."""
    assert len(config.HOOKS.get("post_transition", [])) > 0, (
        "No post_transition hooks — transitions go unrecorded/unnotified")


# ═══════════════════════════════════════════════════════════════
# CROSS-CUTTING TESTS — do features coordinate correctly?
# ═══════════════════════════════════════════════════════════════

def test_create_triggers_audit():
    """Creating a ticket should produce an audit entry."""
    reset_state()
    try:
        from audit import reset_audit, get_audit_trail
        reset_audit()
    except ImportError:
        assert False, "audit module not found"
    t = create_ticket("Bug", "Broken", user_id="U-1")
    trail = get_audit_trail(t.id)
    assert len(trail) >= 1, (
        f"Expected audit entry for create, got {len(trail)}")


def test_transition_triggers_audit():
    """Transitioning a ticket should produce an audit entry."""
    reset_state()
    try:
        from audit import reset_audit, get_audit_trail
        reset_audit()
    except ImportError:
        assert False, "audit module not found"
    t = create_ticket("Bug", "Broken", user_id="U-1")
    transition_ticket(t.id, "in_progress")
    trail = get_audit_trail(t.id)
    has_transition = any(
        e.action == "transition" or
        (hasattr(e, 'details') and e.details.get("new_status") == "in_progress")
        for e in trail
    )
    assert has_transition, (
        f"No transition audit entry found. Trail: {trail}")


def test_archived_no_notification():
    """Archiving a ticket must NOT trigger a notification."""
    reset_state()
    try:
        from notifications import reset_notifications, get_notifications
        reset_notifications()
    except ImportError:
        assert False, "notifications module not found"
    t = create_ticket("Old", "Done")
    transition_ticket(t.id, "closed")
    archive_ticket(t.id)
    notifs = get_notifications(t.id)
    archive_notifs = [n for n in notifs
                      if "archived" in n.get("message", "").lower()
                      or n.get("new_status") == "archived"]
    assert len(archive_notifs) == 0, (
        f"Archived ticket triggered notification: {archive_notifs}")


def test_permission_check_on_create():
    """Permission system should gate ticket creation."""
    reset_state()
    try:
        from permissions import has_permission
    except ImportError:
        assert False, "permissions module not found"
    viewer = register_user("U-1", "Viewer", "v@t.com", "viewer")
    assert not has_permission(viewer, "create"), (
        "Viewer should NOT have create permission")


def test_archive_permission_exists():
    """Archive must be in the permission matrix."""
    reset_state()
    try:
        from permissions import has_permission
    except ImportError:
        assert False, "permissions module not found"
    admin = register_user("U-1", "Admin", "a@t.com", "admin")
    assert has_permission(admin, "archive"), (
        "Admin should have archive permission")


def test_on_hold_in_workflow():
    """on_hold must be a valid status in the workflow."""
    assert "on_hold" in VALID_TRANSITIONS, (
        f"on_hold not in VALID_TRANSITIONS: {list(VALID_TRANSITIONS.keys())}")


def test_on_hold_transition():
    """Should be able to transition to on_hold from in_progress."""
    reset_state()
    t = create_ticket("Bug", "Waiting on customer")
    transition_ticket(t.id, "in_progress")
    transition_ticket(t.id, "on_hold")
    assert get_ticket(t.id).status == "on_hold"


def test_on_hold_in_config():
    """on_hold must appear in config status lists."""
    assert "on_hold" in config.ALL_STATUSES, (
        f"on_hold not in ALL_STATUSES: {config.ALL_STATUSES}")


def test_on_hold_is_active():
    """on_hold tickets are still active (not terminal)."""
    assert "on_hold" not in config.TERMINAL_STATUSES, (
        "on_hold should NOT be terminal")
    reset_state()
    t = create_ticket("Bug", "Waiting")
    update_ticket(t.id, status="on_hold")
    assert is_active(t) or t.status not in TERMINAL_STATUSES, (
        "on_hold ticket should be considered active")


if __name__ == "__main__":
    passed = failed = errors = 0
    results = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                results.append((name, "PASS", ""))
            except AssertionError as e:
                failed += 1
                results.append((name, "FAIL", str(e)))
            except Exception as e:
                errors += 1
                results.append((name, "ERROR", f"{type(e).__name__}: {e}"))
    for name, status, msg in results:
        line = f"  {status}: {name}"
        if msg:
            line += f": {msg}"
        print(line)
    print(f"\n{passed} passed, {failed} failed, {errors} errors out of {passed+failed+errors}")

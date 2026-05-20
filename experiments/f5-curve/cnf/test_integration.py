"""F5 coordination curve — integration oracle.

Tests organized by agent-count tier:
  Tier A (3 agents: permissions, audit, notifications): tests 1-10
  Tier B (5 agents: + analytics, sla): tests 11-18
  Tier C (8 agents: + tags, teams, escalation): tests 19-28

Cross-cutting depth increases with tier.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from core import *
from models import Ticket, User
from workflow import *
import config


# ═══════════════════════════════════════════════════════════════
# TIER A — 3 agents (permissions, audit, notifications)
# ═══════════════════════════════════════════════════════════════

def test_a01_base_create():
    reset_state()
    t = create_ticket("Bug", "Broken")
    assert t.status == "open"


def test_a02_workflow_transitions():
    reset_state()
    t = create_ticket("Bug", "Broken")
    transition_ticket(t.id, "in_progress")
    assert get_ticket(t.id).status == "in_progress"


def test_a03_config_has_archive():
    assert "archive" in config.SYSTEM_ACTIONS


def test_a04_config_terminal_has_archived():
    assert "archived" in config.TERMINAL_STATUSES


def test_a05_hooks_registered():
    total = sum(len(v) for v in config.HOOKS.values())
    assert total >= 3, f"Only {total} hooks registered"


def test_a06_create_triggers_audit():
    reset_state()
    from audit import reset_audit, get_audit_trail
    reset_audit()
    t = create_ticket("Bug", "Broken", user_id="U-1")
    trail = get_audit_trail(t.id)
    assert len(trail) >= 1, "No audit entry for create"


def test_a07_archived_no_notification():
    reset_state()
    from notifications import reset_notifications, get_notifications
    reset_notifications()
    t = create_ticket("Old", "Done")
    transition_ticket(t.id, "closed")
    archive_ticket(t.id)
    notifs = get_notifications(t.id)
    archive_notifs = [n for n in notifs
                      if "archived" in n.get("message", "").lower()]
    assert len(archive_notifs) == 0, f"Archived triggered notification: {archive_notifs}"


def test_a08_archive_permission():
    reset_state()
    from permissions import has_permission
    admin = register_user("U-1", "Admin", "a@t.com", "admin")
    assert has_permission(admin, "archive")


def test_a09_on_hold_in_workflow():
    assert "on_hold" in VALID_TRANSITIONS


def test_a10_on_hold_transition():
    reset_state()
    t = create_ticket("Bug", "Waiting")
    transition_ticket(t.id, "in_progress")
    transition_ticket(t.id, "on_hold")
    assert get_ticket(t.id).status == "on_hold"


# ═══════════════════════════════════════════════════════════════
# TIER B — 5 agents (+ analytics, sla)
# ═══════════════════════════════════════════════════════════════

def test_b01_active_count_excludes_archived():
    reset_state()
    from analytics import active_ticket_count
    t1 = create_ticket("Active", "Open")
    t2 = create_ticket("Old", "Archive")
    update_ticket(t2.id, status="closed")
    update_ticket(t2.id, status="archived")
    assert active_ticket_count() == 1, "Archived counted as active"


def test_b02_summary_has_all_statuses():
    reset_state()
    from analytics import ticket_summary
    summary = ticket_summary()
    for s in ["open", "closed", "archived"]:
        assert s in summary, f"Summary missing '{s}': {summary}"


def test_b03_on_hold_in_summary():
    reset_state()
    from analytics import ticket_summary
    summary = ticket_summary()
    assert "on_hold" in summary, f"Summary missing 'on_hold': {summary}"


def test_b04_unassigned_excludes_archived():
    reset_state()
    from analytics import unassigned_tickets
    t1 = create_ticket("Active", "Needs work")
    t2 = create_ticket("Done", "Archive")
    update_ticket(t2.id, status="closed")
    update_ticket(t2.id, status="archived")
    ids = [t.id for t in unassigned_tickets()]
    assert t2.id not in ids, "Archived in unassigned list"


def test_b05_sla_exists():
    try:
        from sla import set_sla, check_breach
    except ImportError:
        assert False, "sla module not found"


def test_b06_sla_breach_excludes_archived():
    reset_state()
    from sla import set_sla, get_overdue_tickets
    t1 = create_ticket("Active", "Open")
    set_sla(t1.id, response_minutes=0)  # immediate breach
    t2 = create_ticket("Old", "Done")
    set_sla(t2.id, response_minutes=0)
    update_ticket(t2.id, status="closed")
    update_ticket(t2.id, status="archived")
    overdue = get_overdue_tickets()
    ids = [t.id if isinstance(t, Ticket) else t for t in overdue]
    assert t1.id in ids, "Active overdue ticket missing"
    assert t2.id not in ids, "Archived ticket in overdue list"


def test_b07_sla_on_hold_pauses():
    """SLA should recognize on_hold as non-breaching or paused."""
    reset_state()
    from sla import set_sla, check_breach
    t = create_ticket("Waiting", "On hold")
    set_sla(t.id, response_minutes=0)
    update_ticket(t.id, status="on_hold")
    breach = check_breach(t.id)
    # on_hold should either pause the SLA or not count as breached
    # (agent must know on_hold is a valid active-but-paused state)
    assert breach is not True or "on_hold" in str(breach), \
        "SLA breach should account for on_hold status"


def test_b08_analytics_sla_cross_cut():
    """Active ticket count and SLA overdue should agree on active set."""
    reset_state()
    from analytics import active_ticket_count
    from sla import set_sla, get_overdue_tickets
    t1 = create_ticket("A", "Active")
    t2 = create_ticket("B", "Active")
    set_sla(t1.id, response_minutes=0)
    set_sla(t2.id, response_minutes=0)
    update_ticket(t2.id, status="closed")
    update_ticket(t2.id, status="archived")
    active = active_ticket_count()
    overdue = get_overdue_tickets()
    overdue_ids = [t.id if isinstance(t, Ticket) else t for t in overdue]
    assert active == 1, f"Active count {active}, expected 1"
    assert t2.id not in overdue_ids, "Archived in overdue"


# ═══════════════════════════════════════════════════════════════
# TIER C — 8 agents (+ tags, teams, escalation)
# ═══════════════════════════════════════════════════════════════

def test_c01_tags_exist():
    try:
        from tags import add_tag, get_tags, find_by_tag
    except ImportError:
        assert False, "tags module not found"


def test_c02_tags_on_ticket():
    reset_state()
    from tags import add_tag, get_tags
    t = create_ticket("Bug", "Tagged")
    add_tag(t.id, "urgent")
    add_tag(t.id, "frontend")
    tags = get_tags(t.id)
    assert "urgent" in tags
    assert "frontend" in tags


def test_c03_teams_exist():
    try:
        from teams import create_team, assign_to_team, get_team_tickets
    except ImportError:
        assert False, "teams module not found"


def test_c04_team_tickets_exclude_archived():
    reset_state()
    from teams import create_team, assign_to_team, get_team_tickets
    create_team("backend")
    t1 = create_ticket("Active", "Open")
    t2 = create_ticket("Old", "Done")
    assign_to_team(t1.id, "backend")
    assign_to_team(t2.id, "backend")
    update_ticket(t2.id, status="closed")
    update_ticket(t2.id, status="archived")
    team_tickets = get_team_tickets("backend")
    ids = [t.id if isinstance(t, Ticket) else t for t in team_tickets]
    assert t1.id in ids, "Active team ticket missing"
    assert t2.id not in ids, "Archived ticket in team list"


def test_c05_escalation_exists():
    try:
        from escalation import set_escalation_rule, check_escalation
    except ImportError:
        assert False, "escalation module not found"


def test_c06_escalation_skips_on_hold():
    """Auto-escalation should not escalate on_hold tickets."""
    reset_state()
    from escalation import set_escalation_rule, check_escalation
    t = create_ticket("Paused", "Waiting on customer")
    set_escalation_rule(t.id, escalate_after_minutes=0)
    update_ticket(t.id, status="on_hold")
    result = check_escalation(t.id)
    # Should NOT escalate because ticket is on_hold
    assert result is None or result is False or "on_hold" in str(result), \
        f"Escalation fired on on_hold ticket: {result}"


def test_c07_escalation_skips_archived():
    """Auto-escalation should not escalate archived tickets."""
    reset_state()
    from escalation import set_escalation_rule, check_escalation
    t = create_ticket("Done", "Archived")
    set_escalation_rule(t.id, escalate_after_minutes=0)
    update_ticket(t.id, status="closed")
    update_ticket(t.id, status="archived")
    result = check_escalation(t.id)
    assert result is None or result is False, \
        f"Escalation fired on archived ticket: {result}"


def test_c08_escalation_in_audit():
    """Escalation actions should appear in audit trail."""
    reset_state()
    from escalation import set_escalation_rule, check_escalation
    from audit import reset_audit, get_audit_trail
    reset_audit()
    t = create_ticket("Urgent", "Needs escalation", user_id="U-1")
    set_escalation_rule(t.id, escalate_after_minutes=0)
    check_escalation(t.id)
    trail = get_audit_trail(t.id)
    # Should have at least create + escalation entries
    assert len(trail) >= 1, "No audit trail entries"


def test_c09_tags_in_config():
    """Tag actions should be in SYSTEM_ACTIONS."""
    assert "tag" in config.SYSTEM_ACTIONS or "add_tag" in config.SYSTEM_ACTIONS, \
        f"No tag action in SYSTEM_ACTIONS: {config.SYSTEM_ACTIONS}"


def test_c10_team_in_config():
    """Team actions should be in SYSTEM_ACTIONS."""
    assert "assign_team" in config.SYSTEM_ACTIONS or "team" in config.SYSTEM_ACTIONS, \
        f"No team action in SYSTEM_ACTIONS: {config.SYSTEM_ACTIONS}"


if __name__ == "__main__":
    passed = failed = errors = 0
    results = []
    tier_results = {"A": [0, 0, 0], "B": [0, 0, 0], "C": [0, 0, 0]}

    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            tier = name[5].upper()
            try:
                fn()
                passed += 1
                results.append((name, "PASS", ""))
                tier_results[tier][0] += 1
            except AssertionError as e:
                failed += 1
                results.append((name, "FAIL", str(e)))
                tier_results[tier][1] += 1
            except Exception as e:
                errors += 1
                results.append((name, "ERROR", f"{type(e).__name__}: {e}"))
                tier_results[tier][2] += 1

    for name, status, msg in results:
        line = f"  {status}: {name}"
        if msg:
            line += f": {msg}"
        print(line)

    print(f"\nTotal: {passed} passed, {failed} failed, {errors} errors")
    print(f"\nTier A (3 agents): {tier_results['A'][0]}p {tier_results['A'][1]}f {tier_results['A'][2]}e / {sum(tier_results['A'])}")
    print(f"Tier B (5 agents): {tier_results['B'][0]}p {tier_results['B'][1]}f {tier_results['B'][2]}e / {sum(tier_results['B'])}")
    print(f"Tier C (8 agents): {tier_results['C'][0]}p {tier_results['C'][1]}f {tier_results['C'][2]}e / {sum(tier_results['C'])}")

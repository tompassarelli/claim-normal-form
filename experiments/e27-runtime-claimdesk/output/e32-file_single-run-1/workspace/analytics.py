
# Auto-generated from CNF claim graph
# DO NOT EDIT — edit the graph, re-project

from workflow import TERMINAL_STATUSES, ACTIVE_STATUSES, ESCALATED_STATUSES, PRIORITIES, PRIORITY_SLA_HOURS

events = []

def track_transition(ticket_id, old_status, new_status, priority="normal"):
    event = {
        "ticket": ticket_id,
        "from": old_status,
        "to": new_status,
        "priority": priority,
        "is_terminal": new_status in TERMINAL_STATUSES,
        "is_escalated": new_status in ESCALATED_STATUSES,
    }
    events.append(event)
    return event

def active_ticket_count(statuses):
    work_statuses = ACTIVE_STATUSES | ESCALATED_STATUSES
    return sum(1 for s in statuses if s in work_statuses)

def priority_breakdown(tickets):
    """Return count of tickets per priority level."""
    counts = {p: 0 for p in PRIORITIES}
    for t in tickets:
        if t.priority in counts:
            counts[t.priority] += 1
    return counts

def sla_report(tickets, now_ts: int):
    """Return SLA compliance per priority.

    For each ticket still open, checks whether the response target window
    has elapsed since creation.  Returns a dict keyed by priority with
    keys: total, breached, compliant.

    now_ts  — current Unix timestamp (int)
    """
    report = {
        p: {"total": 0, "breached": 0, "compliant": 0}
        for p in PRIORITIES
    }
    for t in tickets:
        p = t.priority
        if p not in report:
            continue
        report[p]["total"] += 1
        created = int(t.created_at) if t.created_at else now_ts
        elapsed_hours = (now_ts - created) / 3600
        target_hours = PRIORITY_SLA_HOURS[p]
        if elapsed_hours > target_hours:
            report[p]["breached"] += 1
        else:
            report[p]["compliant"] += 1
    return report

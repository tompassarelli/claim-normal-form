import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from core import *
from models import Ticket, User, Contact


def test_create_ticket():
    reset_state()
    t = create_ticket("Login broken", "Can't log in")
    assert t.id == "T-1"
    assert t.status == "open"
    assert t.title == "Login broken"


def test_update_ticket():
    reset_state()
    t = create_ticket("Bug", "Something broke")
    t2 = update_ticket(t.id, priority="high")
    assert t2.priority == "high"


def test_assign_ticket():
    reset_state()
    u = register_user("U-1", "Alice", "alice@test.com")
    t = create_ticket("Bug", "Something broke")
    t2 = assign_ticket(t.id, u.id)
    assert t2.assignee == "U-1"


def test_close_ticket():
    reset_state()
    t = create_ticket("Bug", "Something broke")
    t2 = close_ticket(t.id)
    assert t2.status == "closed"


def test_list_tickets():
    reset_state()
    create_ticket("Bug 1", "First")
    create_ticket("Bug 2", "Second")
    close_ticket("T-1")
    assert len(list_tickets()) == 2
    assert len(list_tickets(status="open")) == 1
    assert len(list_tickets(status="closed")) == 1


def test_register_user():
    reset_state()
    u = register_user("U-1", "Alice", "alice@test.com", "admin")
    assert u.role == "admin"
    assert get_user("U-1").name == "Alice"


def test_create_contact():
    reset_state()
    c = create_contact("Bob", "bob@acme.com", "Acme Corp")
    assert c.id == "C-1"
    assert c.company == "Acme Corp"


def test_list_users():
    reset_state()
    register_user("U-1", "Alice", "a@t.com", "admin")
    register_user("U-2", "Bob", "b@t.com", "agent")
    register_user("U-3", "Carol", "c@t.com", "agent")
    assert len(list_users()) == 3
    assert len(list_users(role="agent")) == 2


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
            except Exception as e:
                print(f"FAIL: {name}: {e}")
                failed += 1
    print(f"{passed} passed, {failed} failed")

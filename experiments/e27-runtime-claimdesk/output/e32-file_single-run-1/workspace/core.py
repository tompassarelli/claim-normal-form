from models import Ticket, User, Contact
from workflow import is_valid_priority
from typing import List, Optional, Dict
import time

_tickets: Dict[str, Ticket] = {}
_users: Dict[str, User] = {}
_contacts: Dict[str, Contact] = {}
_next_ticket = [1]
_next_contact = [1]


def _now():
    return str(int(time.time()))


def create_ticket(title: str, description: str, contact_email: str = "",
                  priority: str = "normal") -> Ticket:
    if not is_valid_priority(priority):
        raise ValueError(f"Invalid priority '{priority}'. Must be one of: low, normal, high, critical")
    tid = f"T-{_next_ticket[0]}"
    _next_ticket[0] += 1
    now = _now()
    # Critical tickets start in escalated state and require senior/admin handling
    initial_status = "escalated" if priority == "critical" else "open"
    t = Ticket(id=tid, title=title, description=description,
               contact_email=contact_email, priority=priority,
               status=initial_status, created_at=now, updated_at=now)
    _tickets[tid] = t
    return t


def get_ticket(ticket_id: str) -> Optional[Ticket]:
    return _tickets.get(ticket_id)


def update_ticket(ticket_id: str, **fields) -> Ticket:
    t = _tickets[ticket_id]
    for k, v in fields.items():
        setattr(t, k, v)
    t.updated_at = _now()
    return t


def assign_ticket(ticket_id: str, user_id: str) -> Ticket:
    return update_ticket(ticket_id, assignee=user_id)


def close_ticket(ticket_id: str) -> Ticket:
    return update_ticket(ticket_id, status="closed")


def list_tickets(status: Optional[str] = None) -> List[Ticket]:
    tickets = list(_tickets.values())
    if status:
        tickets = [t for t in tickets if t.status == status]
    return tickets


def register_user(uid: str, name: str, email: str,
                  role: str = "agent") -> User:
    u = User(id=uid, name=name, email=email, role=role)
    _users[uid] = u
    return u


def get_user(user_id: str) -> Optional[User]:
    return _users.get(user_id)


def create_contact(name: str, email: str, company: str = "") -> Contact:
    cid = f"C-{_next_contact[0]}"
    _next_contact[0] += 1
    c = Contact(id=cid, name=name, email=email, company=company)
    _contacts[cid] = c
    return c


def get_contact(contact_id: str) -> Optional[Contact]:
    return _contacts.get(contact_id)


def list_users(role: Optional[str] = None) -> List[User]:
    users = list(_users.values())
    if role:
        users = [u for u in users if u.role == role]
    return users


def reset_state():
    _tickets.clear()
    _users.clear()
    _contacts.clear()
    _next_ticket[0] = 1
    _next_contact[0] = 1

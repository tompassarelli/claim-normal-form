from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Ticket:
    id: str
    title: str
    description: str
    status: str = "open"
    priority: str = "normal"
    assignee: Optional[str] = None
    contact_email: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class User:
    id: str
    name: str
    email: str
    role: str = "agent"


@dataclass
class Contact:
    id: str
    name: str
    email: str
    company: str = ""
    tickets: List[str] = field(default_factory=list)

from models import User
from typing import List

PERMISSION_MATRIX = {
    "admin": [
        "create_ticket", "get_ticket", "update_ticket", "assign_ticket",
        "close_ticket", "list_tickets", "transition_ticket", "archive_ticket",
        "register_user", "get_user", "list_users", "create_contact", "get_contact",
    ],
    "agent": [
        "create_ticket", "get_ticket", "update_ticket", "assign_ticket",
        "close_ticket", "list_tickets", "transition_ticket", "archive_ticket",
        "get_user", "list_users", "create_contact", "get_contact",
    ],
    "viewer": [
        "get_ticket", "list_tickets", "get_user", "list_users", "get_contact",
    ],
}
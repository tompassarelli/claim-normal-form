"""Domain models for an order processing system."""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class OrderStatus(Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    PRICED = "priced"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class Address:
    street: str
    city: str
    region: str
    postal_code: str
    country: str


@dataclass
class Item:
    sku: str
    name: str
    quantity: int
    price: float
    weight: float = 0.5
    cost: float = 0.0


@dataclass
class Discount:
    code: str
    rate: float
    description: str = ""


@dataclass
class Order:
    id: str
    items: List[Item] = field(default_factory=list)
    address: Optional[Address] = None
    discount: Optional[Discount] = None
    shipping_method: str = "standard"
    status: OrderStatus = OrderStatus.PENDING
    notes: str = ""

"""Data models for testing search."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Product:
    """A product in the catalog."""

    id: int
    name: str
    price: float
    created_at: datetime


@dataclass
class Order:
    """A customer order."""

    id: int
    user_id: int
    products: list[int]
    total: float

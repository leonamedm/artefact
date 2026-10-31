"""Domain records returned by repositories and consumed by services."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum


class ProductStatus(StrEnum):
    ACTIVE = "active"
    DISCONTINUED = "discontinued"
    COMING_SOON = "coming_soon"


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Category:
    category_id: int
    name: str
    description: str


@dataclass(frozen=True)
class Promotion:
    promotion_id: int
    product_id: int
    discount_percent: int
    description: str
    is_active: bool


@dataclass(frozen=True)
class Product:
    product_id: int
    name: str
    category_id: int
    category_name: str
    description: str
    price: Decimal
    stock_quantity: int
    status: ProductStatus
    specs: dict[str, str]
    active_promotion: Promotion | None = None

    @property
    def is_sellable(self) -> bool:
        return self.status is ProductStatus.ACTIVE and self.stock_quantity > 0


@dataclass(frozen=True)
class Customer:
    customer_id: int
    name: str
    phone: str
    email: str
    city: str


@dataclass(frozen=True)
class OrderItem:
    product_id: int
    product_name: str
    quantity: int


@dataclass(frozen=True)
class Order:
    order_id: int
    customer_id: int
    order_date: date
    status: OrderStatus
    total: Decimal
    payment_method: str
    tracking_code: str | None
    estimated_delivery: date | None
    notes: str | None
    items: tuple[OrderItem, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PolicySection:
    number: int
    title: str
    topic: str
    customer_facing: bool
    text: str

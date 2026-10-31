"""Typed reading of the original CSVs. Parsing errors fail loudly; values are never "fixed" here."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from emporio_agent.config import SOURCE_CSV


class SourceError(ValueError):
    pass


@dataclass(frozen=True)
class CategoryRow:
    category_id: int
    name: str
    description: str


@dataclass(frozen=True)
class ProductRow:
    product_id: int
    price: Decimal
    name: str
    category_id: int
    description: str
    stock_quantity: int
    status: str
    specs: dict[str, str]
    created_at: date


@dataclass(frozen=True)
class PromotionRow:
    promotion_id: int
    product_id: int
    discount_percent: int
    description: str
    is_active: bool


@dataclass(frozen=True)
class CustomerRow:
    customer_id: int
    name: str
    phone: str
    email: str
    city: str


@dataclass(frozen=True)
class OrderRow:
    order_id: int
    customer_id: int
    order_date: date
    status: str
    total: Decimal
    payment_method: str
    tracking_code: str | None
    estimated_delivery: date | None
    notes: str | None


@dataclass(frozen=True)
class OrderItemRow:
    order_id: int
    quantity: int
    product_id: int


@dataclass(frozen=True)
class SourceData:
    categories: list[CategoryRow]
    products: list[ProductRow]
    promotions: list[PromotionRow]
    customers: list[CustomerRow]
    orders: list[OrderRow]
    order_items: list[OrderItemRow]


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SourceError(f"Missing source file: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


def _int(value: str, where: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise SourceError(f"{where}: expected integer, got {value!r}") from exc


def _decimal(value: str, where: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise SourceError(f"{where}: expected number, got {value!r}") from exc


def _date(value: str, where: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SourceError(f"{where}: expected ISO date, got {value!r}") from exc


def _optional(value: str) -> str | None:
    return value or None


def load_sources(data_dir: Path) -> SourceData:
    def path(key: str) -> Path:
        return data_dir / SOURCE_CSV[key]

    categories = [
        CategoryRow(_int(r["category_id"], "categories.category_id"), r["name"], r["description"])
        for r in _rows(path("categories"))
    ]

    products = []
    for r in _rows(path("products")):
        where = f"products[{r['product_id']}]"
        try:
            specs = json.loads(r["specs"]) if r["specs"] else {}
        except json.JSONDecodeError as exc:
            raise SourceError(f"{where}.specs: invalid JSON") from exc
        products.append(
            ProductRow(
                product_id=_int(r["product_id"], where),
                price=_decimal(r["price_brl"], f"{where}.price_brl"),
                name=r["name"],
                category_id=_int(r["category_id"], f"{where}.category_id"),
                description=r["description"],
                stock_quantity=_int(r["stock_quantity"], f"{where}.stock_quantity"),
                status=r["status"],
                specs={str(k): str(v) for k, v in specs.items()},
                created_at=_date(r["created_at"], f"{where}.created_at"),
            )
        )

    promotions = [
        PromotionRow(
            promotion_id=_int(r["promotion_id"], "promotions.promotion_id"),
            product_id=_int(r["product_id"], "promotions.product_id"),
            discount_percent=_int(r["discount_percent"], "promotions.discount_percent"),
            description=r["description"],
            is_active=_int(r["is_active"], "promotions.is_active") == 1,
        )
        for r in _rows(path("promotions"))
    ]

    customers = [
        CustomerRow(
            customer_id=_int(r["customer_id"], "customers.customer_id"),
            name=r["name"],
            phone=r["phone"],
            email=r["email"],
            city=r["city"],
        )
        for r in _rows(path("customers"))
    ]

    orders = []
    for r in _rows(path("orders")):
        where = f"orders[{r['order_id']}]"
        orders.append(
            OrderRow(
                order_id=_int(r["order_id"], where),
                customer_id=_int(r["customer_id"], f"{where}.customer_id"),
                order_date=_date(r["order_date"], f"{where}.order_date"),
                status=r["status"],
                total=_decimal(r["total_brl"], f"{where}.total_brl"),
                payment_method=r["payment_method"],
                tracking_code=_optional(r["tracking_code"]),
                estimated_delivery=(
                    _date(r["estimated_delivery"], f"{where}.estimated_delivery")
                    if r["estimated_delivery"]
                    else None
                ),
                notes=_optional(r["notes"]),
            )
        )

    order_items = [
        OrderItemRow(
            order_id=_int(r["order_id"], "order_items.order_id"),
            quantity=_int(r["quantity"], "order_items.quantity"),
            product_id=_int(r["product_id"], "order_items.product_id"),
        )
        for r in _rows(path("order_items"))
    ]

    return SourceData(categories, products, promotions, customers, orders, order_items)

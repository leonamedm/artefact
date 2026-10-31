"""Orders and customers. Lookups are always by key; there is no "list customers" query."""

from __future__ import annotations

import sqlite3
from datetime import date

from emporio_agent.domain import Customer, Order, OrderItem, OrderStatus
from emporio_agent.money import from_cents


def _customer(row: sqlite3.Row) -> Customer:
    return Customer(row["customer_id"], row["name"], row["phone"], row["email"], row["city"])


class OrderRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, order_id: int) -> Order | None:
        row = self._conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        return self._order(row) if row else None

    def for_customer(self, customer_id: int) -> list[Order]:
        rows = self._conn.execute(
            "SELECT * FROM orders WHERE customer_id = ? ORDER BY order_date DESC, order_id DESC",
            (customer_id,),
        ).fetchall()
        return [self._order(r) for r in rows]

    def customer(self, customer_id: int) -> Customer | None:
        row = self._conn.execute(
            "SELECT * FROM customers WHERE customer_id = ?", (customer_id,)
        ).fetchone()
        return _customer(row) if row else None

    def customers_matching(self, *, phone_digits: str, email_norm: str) -> list[Customer]:
        rows = self._conn.execute(
            "SELECT * FROM customers WHERE phone_digits = ? AND email_norm = ?",
            (phone_digits, email_norm),
        ).fetchall()
        return [_customer(r) for r in rows]

    def _order(self, row: sqlite3.Row) -> Order:
        items = self._conn.execute(
            "SELECT oi.product_id, p.name, oi.quantity FROM order_items oi "
            "JOIN products p ON p.product_id = oi.product_id "
            "WHERE oi.order_id = ? ORDER BY oi.rowid",
            (row["order_id"],),
        ).fetchall()
        return Order(
            order_id=row["order_id"],
            customer_id=row["customer_id"],
            order_date=date.fromisoformat(row["order_date"]),
            status=OrderStatus(row["status"]),
            total=from_cents(row["total_cents"]),
            payment_method=row["payment_method"],
            tracking_code=row["tracking_code"],
            estimated_delivery=(
                date.fromisoformat(row["estimated_delivery"]) if row["estimated_delivery"] else None
            ),
            notes=row["notes"],
            items=tuple(OrderItem(i["product_id"], i["name"], i["quantity"]) for i in items),
        )

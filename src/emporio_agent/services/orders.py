"""Order lookup with customer identification (LGPD, manual §9).

Order data is only returned when the requester proves who they are: order id + the phone or
e-mail on file, or phone + e-mail together. Failures are indistinguishable ("not found or does
not match") so the tool cannot be used to discover which orders or customers exist.
"""

from __future__ import annotations

from datetime import date

from emporio_agent.domain import Customer, Order, OrderStatus
from emporio_agent.repositories.orders import OrderRepository
from emporio_agent.text import digits, normalize


def phone_key(phone: str) -> str:
    """Digits with the Brazil country code removed: "+55 (67) 99812-3456" -> "67998123456"."""
    value = digits(phone)
    if value.startswith("55") and len(value) in (12, 13):
        value = value[2:]
    return value


class OrderService:
    def __init__(self, repo: OrderRepository) -> None:
        self._repo = repo

    def _matches(self, customer: Customer, email: str | None, phone: str | None) -> bool:
        if email and normalize(email) == normalize(customer.email):
            return True
        return bool(phone) and phone_key(phone) == phone_key(customer.phone)

    def find_order(
        self, order_id: int, *, email: str | None = None, phone: str | None = None
    ) -> tuple[Order, Customer] | None:
        if not (email or phone):
            return None
        order = self._repo.get(order_id)
        if order is None:
            return None
        customer = self._repo.customer(order.customer_id)
        if customer is None or not self._matches(customer, email, phone):
            return None
        return order, customer

    def find_customer_orders(
        self, *, email: str, phone: str
    ) -> tuple[Customer, list[Order]] | None:
        if not (email and phone):
            return None
        matches = self._repo.customers_matching(
            phone_digits=phone_key(phone), email_norm=normalize(email)
        )
        if len(matches) != 1:
            return None
        customer = matches[0]
        return customer, self._repo.for_customer(customer.customer_id)


def tracking_visible(order: Order) -> bool:
    """§5.3: the tracking code exists once the order is dispatched."""
    return order.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED) and bool(
        order.tracking_code
    )


def is_delayed(order: Order, today: date) -> bool:
    return (
        order.status is OrderStatus.SHIPPED
        and order.estimated_delivery is not None
        and order.estimated_delivery < today
    )

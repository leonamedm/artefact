from __future__ import annotations

from emporio_agent.domain import OrderStatus
from emporio_agent.services.orders import is_delayed, phone_key, tracking_visible
from tests.conftest import TODAY

# Order 8 belongs to customer 2: Ana Carolina Ferreira, (67) 99654-7821,
# anacarol.ferreira@coldmail.com


def test_identify_by_order_and_phone(orders):
    found = orders.find_order(8, phone="(67) 99654-7821")
    assert found is not None
    order, customer = found
    assert customer.customer_id == 2
    assert order.status is OrderStatus.SHIPPED


def test_phone_formats_and_email_case_are_normalized(orders):
    assert orders.find_order(8, phone="+55 67 996547821")
    assert orders.find_order(8, email="AnaCarol.Ferreira@ColdMail.com ")


def test_wrong_contact_or_missing_contact_reveals_nothing(orders):
    assert orders.find_order(8, phone="(67) 99812-3456") is None  # another customer's phone
    assert orders.find_order(8) is None
    assert orders.find_order(999, phone="(67) 99654-7821") is None


def test_listing_requires_both_email_and_phone(orders):
    assert orders.find_customer_orders(email="anacarol.ferreira@coldmail.com", phone="") is None
    found = orders.find_customer_orders(
        email="anacarol.ferreira@coldmail.com", phone="(67) 99654-7821"
    )
    assert found is not None
    customer, customer_orders = found
    assert {o.customer_id for o in customer_orders} == {customer.customer_id}


def test_tracking_only_after_dispatch(orders):
    shipped, _ = orders.find_order(8, phone="(67) 99654-7821")
    assert tracking_visible(shipped)
    assert is_delayed(shipped, TODAY)  # ETA 28/02/2026 passed


def test_confirmed_order_has_no_tracking(orders, catalog_conn):
    row = catalog_conn.execute(
        "SELECT c.phone FROM orders o JOIN customers c USING (customer_id) WHERE order_id = 9"
    ).fetchone()
    order, _ = orders.find_order(9, phone=row["phone"])
    assert order.status is OrderStatus.CONFIRMED
    assert not tracking_visible(order)


def test_order_total_is_the_recorded_one(orders, catalog_conn):
    row = catalog_conn.execute(
        "SELECT c.email FROM orders o JOIN customers c USING (customer_id) WHERE order_id = 3"
    ).fetchone()
    order, _ = orders.find_order(3, email=row["email"])
    assert str(order.total) == "3450.00"  # items at current prices would be 3498


def test_phone_key():
    assert phone_key("(67) 99812-3456") == "67998123456"
    assert phone_key("+55 (67) 99812-3456") == "67998123456"

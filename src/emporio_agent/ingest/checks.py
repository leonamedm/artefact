"""Data-quality checks. They report anomalies; they never change the data.

Severity "error" blocks the build (an invariant the services rely on is broken).
"warning"/"info" are logged and handled by explicit rules in the services.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from emporio_agent.domain import OrderStatus, ProductStatus
from emporio_agent.ingest.sources import SourceData

# Manual §5.3: "BR" + 9 alphanumeric characters + "BR".
TRACKING_CODE = re.compile(r"^BR[A-Z0-9]{9}BR$")


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # "error" | "warning" | "info"
    message: str


def run_checks(src: SourceData, reference_date: date) -> list[Finding]:
    findings: list[Finding] = []
    add = findings.append

    def duplicates(name: str, ids: list[int]) -> None:
        for value, count in Counter(ids).items():
            if count > 1:
                add(Finding("DUPLICATE_ID", "error", f"{name}: id {value} appears {count} times"))

    duplicates("categories", [c.category_id for c in src.categories])
    duplicates("products", [p.product_id for p in src.products])
    duplicates("promotions", [p.promotion_id for p in src.promotions])
    duplicates("customers", [c.customer_id for c in src.customers])
    duplicates("orders", [o.order_id for o in src.orders])

    category_ids = {c.category_id for c in src.categories}
    products = {p.product_id: p for p in src.products}
    customer_ids = {c.customer_id for c in src.customers}
    orders = {o.order_id: o for o in src.orders}
    valid_product_status = {s.value for s in ProductStatus}
    valid_order_status = {s.value for s in OrderStatus}

    for p in src.products:
        if p.category_id not in category_ids:
            add(Finding("FK_MISSING", "error", f"product {p.product_id}: unknown category"))
        if p.status not in valid_product_status:
            add(Finding("INVALID_STATUS", "error", f"product {p.product_id}: {p.status!r}"))
        if p.price <= 0:
            add(Finding("INVALID_PRICE", "error", f"product {p.product_id}: price {p.price}"))
        if p.stock_quantity < 0:
            add(Finding("INVALID_STOCK", "error", f"product {p.product_id}: negative stock"))
        if p.status == ProductStatus.DISCONTINUED and p.stock_quantity > 0:
            add(
                Finding(
                    "DISCONTINUED_WITH_STOCK",
                    "warning",
                    f"product {p.product_id} ({p.name}) is discontinued but has stock "
                    f"{p.stock_quantity}; status wins, it is not offered",
                )
            )
        if p.status == ProductStatus.COMING_SOON and p.stock_quantity > 0:
            add(
                Finding(
                    "COMING_SOON_WITH_STOCK",
                    "warning",
                    f"product {p.product_id} ({p.name}) is coming_soon but has stock "
                    f"{p.stock_quantity}; not sellable yet",
                )
            )
        if p.status == ProductStatus.ACTIVE and p.stock_quantity == 0:
            add(
                Finding(
                    "ACTIVE_OUT_OF_STOCK",
                    "info",
                    f"product {p.product_id} ({p.name}) is active with stock 0",
                )
            )

    used_categories = {p.category_id for p in src.products}
    for c in src.categories:
        if c.category_id not in used_categories:
            add(
                Finding(
                    "CATEGORY_WITHOUT_PRODUCTS",
                    "warning",
                    f"category {c.category_id} ({c.name}) has no products",
                )
            )

    for promo in src.promotions:
        if promo.product_id not in products:
            add(Finding("FK_MISSING", "error", f"promotion {promo.promotion_id}: unknown product"))
        if not 0 < promo.discount_percent < 100:
            add(
                Finding(
                    "INVALID_DISCOUNT",
                    "error",
                    f"promotion {promo.promotion_id}: {promo.discount_percent}%",
                )
            )
    active_per_product = Counter(p.product_id for p in src.promotions if p.is_active)
    for product_id, count in active_per_product.items():
        if count > 1:
            # Promotions are not cumulative (manual §6.2) and the data gives no precedence rule.
            add(
                Finding(
                    "MULTIPLE_ACTIVE_PROMOTIONS",
                    "error",
                    f"product {product_id} has {count} active promotions",
                )
            )

    items_by_order: dict[int, list] = {}
    for item in src.order_items:
        if item.order_id not in orders:
            add(Finding("FK_MISSING", "error", f"order_item: unknown order {item.order_id}"))
        if item.product_id not in products:
            add(Finding("FK_MISSING", "error", f"order_item: unknown product {item.product_id}"))
        if item.quantity <= 0:
            add(Finding("INVALID_QUANTITY", "error", f"order {item.order_id}: {item.quantity}"))
        items_by_order.setdefault(item.order_id, []).append(item)

    for o in src.orders:
        ref = f"order {o.order_id}"
        if o.customer_id not in customer_ids:
            add(Finding("FK_MISSING", "error", f"{ref}: unknown customer"))
        if o.status not in valid_order_status:
            add(Finding("INVALID_STATUS", "error", f"{ref}: {o.status!r}"))
        items = items_by_order.get(o.order_id, [])
        if not items:
            add(Finding("ORDER_WITHOUT_ITEMS", "warning", f"{ref} has no items"))
        known = [i for i in items if i.product_id in products]
        current_value = sum((products[i.product_id].price * i.quantity for i in known), Decimal(0))
        if known and current_value != o.total:
            add(
                Finding(
                    "ORDER_TOTAL_MISMATCH",
                    "warning",
                    f"{ref}: recorded total {o.total} vs items at current prices {current_value} "
                    "(prices may have changed since the order); the recorded total is reported",
                )
            )
        for i in known:
            product = products[i.product_id]
            if product.status != ProductStatus.ACTIVE and o.status == OrderStatus.DELIVERED:
                add(
                    Finding(
                        "ORDER_WITH_NON_ACTIVE_PRODUCT",
                        "info",
                        f"{ref} is delivered but contains product {product.product_id} "
                        f"with status {product.status}",
                    )
                )
        shipped = o.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED)
        if shipped and not o.tracking_code:
            add(Finding("TRACKING_MISSING", "warning", f"{ref} is {o.status} without tracking"))
        if not shipped and o.tracking_code:
            add(Finding("TRACKING_ON_UNSHIPPED", "warning", f"{ref} is {o.status} with tracking"))
        if o.tracking_code and not TRACKING_CODE.match(o.tracking_code):
            add(Finding("TRACKING_FORMAT", "warning", f"{ref}: {o.tracking_code!r}"))
        if (
            o.status == OrderStatus.SHIPPED
            and o.estimated_delivery
            and (o.estimated_delivery < reference_date)
        ):
            add(
                Finding(
                    "SHIPPED_PAST_ETA",
                    "warning",
                    f"{ref} still shipped; estimated delivery {o.estimated_delivery} has passed",
                )
            )
        if o.status in (OrderStatus.PENDING, OrderStatus.CONFIRMED):
            add(
                Finding(
                    "ORDER_OPEN",
                    "info",
                    f"{ref} is {o.status} since {o.order_date} "
                    f"({(reference_date - o.order_date).days} days)",
                )
            )

    return findings

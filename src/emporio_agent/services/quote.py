"""Purchase quote for one or more products: totals, PIX, installments and shipping."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from emporio_agent.domain import Product
from emporio_agent.services.catalog import Availability, availability
from emporio_agent.services.payment import (
    InstallmentOption,
    combined_payment_allowed,
    installment_options,
)
from emporio_agent.services.pricing import PriceQuote, quote_price
from emporio_agent.services.shipping import ShippingQuote, quote_shipping


@dataclass(frozen=True)
class QuoteLine:
    product: Product
    quantity: int
    price: PriceQuote
    line_total: Decimal
    line_pix_total: Decimal


@dataclass(frozen=True)
class PurchaseQuote:
    lines: list[QuoteLine]
    unavailable: list[tuple[Product, Availability]]
    insufficient_stock: list[tuple[Product, int]]
    subtotal: Decimal
    pix_total: Decimal
    installments: list[InstallmentOption]
    combined_payment_allowed: bool
    shipping: ShippingQuote | None


def quote_purchase(items: list[tuple[Product, int]], city: str | None = None) -> PurchaseQuote:
    lines: list[QuoteLine] = []
    unavailable: list[tuple[Product, Availability]] = []
    insufficient: list[tuple[Product, int]] = []
    for product, quantity in items:
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        state = availability(product)
        if state is not Availability.AVAILABLE:
            unavailable.append((product, state))
            continue
        if quantity > product.stock_quantity:
            # Report how many are available instead of quoting units the store doesn't have.
            insufficient.append((product, product.stock_quantity))
            continue
        price = quote_price(product)
        lines.append(
            QuoteLine(
                product, quantity, price, price.final_price * quantity, price.pix_price * quantity
            )
        )

    subtotal = sum((line.line_total for line in lines), Decimal("0.00"))
    pix_total = sum((line.line_pix_total for line in lines), Decimal("0.00"))
    has_lines = bool(lines)
    return PurchaseQuote(
        lines=lines,
        unavailable=unavailable,
        insufficient_stock=insufficient,
        subtotal=subtotal,
        pix_total=pix_total,
        installments=installment_options(subtotal) if has_lines else [],
        combined_payment_allowed=combined_payment_allowed(subtotal),
        shipping=(
            quote_shipping(city, subtotal, [line.product for line in lines])
            if city and has_lines
            else None
        ),
    )

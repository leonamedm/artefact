"""Product price with promotion and PIX discount (manual §3 and §6.2)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from emporio_agent.domain import Product, Promotion
from emporio_agent.money import apply_discount

PIX_DISCOUNT_PERCENT = 5


@dataclass(frozen=True)
class PriceQuote:
    list_price: Decimal
    promotion: Promotion | None
    # Price for card, debit or boleto: promotional price when a promotion is active.
    final_price: Decimal
    pix_price: Decimal
    pix_discount_applies: bool


def quote_price(product: Product) -> PriceQuote:
    promotion = product.active_promotion
    if promotion is not None:
        promo_price = apply_discount(product.price, promotion.discount_percent)
        # §6.2: promotions are not cumulative; PIX 5% does not apply to promotional prices.
        return PriceQuote(product.price, promotion, promo_price, promo_price, False)
    return PriceQuote(
        product.price,
        None,
        product.price,
        apply_discount(product.price, PIX_DISCOUNT_PERCENT),
        True,
    )

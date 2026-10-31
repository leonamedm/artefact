"""Shipping fee and delivery estimates (manual §5)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from emporio_agent.domain import Product
from emporio_agent.text import normalize

# The manual does not list the metropolitan-region municipalities. Only the city of Campo Grande
# is treated as metro (convention C5); anything else gets the carrier options without a price.
METRO_CITIES = frozenset({"campo grande"})
FREE_SHIPPING_ABOVE = Decimal("500.00")
METRO_FEE = Decimal("35.00")
METRO_DELIVERY = "1 a 3 dias úteis"

CARRIERS: tuple[tuple[str, str], ...] = (
    ("PAC (Correios)", "5 a 12 dias úteis"),
    ("SEDEX (Correios)", "2 a 5 dias úteis"),
    ("Jadlog (.package)", "3 a 8 dias úteis"),
)

# §5.2: large instruments may need special freight with an individual quote.
_LARGE_ITEM_KEYWORDS = ("bateria acustica", "piano digital", "contrabaixo")


@dataclass(frozen=True)
class ShippingQuote:
    city: str
    metro: bool
    fee: Decimal | None  # None = needs a quote by CEP; never estimated
    delivery_estimate: str | None
    carrier_options: tuple[tuple[str, str], ...] = ()
    large_items: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)


def is_metro(city: str) -> bool:
    # Accepts "Campo Grande", "campo grande - MS", "Campo Grande/MS".
    words = re.sub(r"[^a-z ]", " ", normalize(city)).split()
    if words and words[-1] == "ms":
        words = words[:-1]
    return " ".join(words) in METRO_CITIES


def is_large_item(product: Product) -> bool:
    name = normalize(product.name)
    return any(keyword in name for keyword in _LARGE_ITEM_KEYWORDS)


def quote_shipping(city: str, order_value: Decimal, products: list[Product]) -> ShippingQuote:
    """order_value is the goods total before payment-method discounts (convention C6)."""
    large = tuple(p.name for p in products if is_large_item(p))
    if is_metro(city):
        # "Acima de R$ 500,00" is strict: exactly R$ 500,00 pays the fee (convention C6).
        fee = Decimal("0.00") if order_value > FREE_SHIPPING_ABOVE else METRO_FEE
        return ShippingQuote(
            city=city,
            metro=True,
            fee=fee,
            delivery_estimate=METRO_DELIVERY,
            notes=("Entrega por motoboy próprio; o cliente é contactado por telefone antes.",),
        )
    notes = [
        "Valor calculado pelo CEP de destino, peso e dimensões; a loja informa a cotação.",
        "Todos os envios incluem seguro contra extravio e danos.",
    ]
    if large:
        notes.append(
            "Instrumento de grande porte pode exigir frete especial com cotação individual."
        )
    return ShippingQuote(
        city=city,
        metro=False,
        fee=None,
        delivery_estimate=None,
        carrier_options=CARRIERS,
        large_items=large,
        notes=tuple(notes),
    )

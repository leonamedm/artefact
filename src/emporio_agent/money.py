"""Money helpers. Amounts are Decimal BRL; storage uses integer cents to keep SQL exact."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def round_cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def to_cents(value: Decimal | str) -> int:
    return int(round_cents(Decimal(value)) * 100)


def from_cents(cents: int) -> Decimal:
    return (Decimal(cents) / 100).quantize(CENT)


def apply_discount(price: Decimal, percent: Decimal | int) -> Decimal:
    return round_cents(price * (Decimal(100) - Decimal(percent)) / Decimal(100))


def format_brl(value: Decimal) -> str:
    """Brazilian format: R$ 1.234,56. Given to the model ready-made so it never formats money."""
    integer, _, fraction = f"{round_cents(value):,.2f}".partition(".")
    return f"R$ {integer.replace(',', '.')},{fraction}"

"""Credit-card installments and payment combination rules (manual §3.1)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from emporio_agent.money import round_cents

MAX_INSTALLMENTS = 12
COMBINED_PAYMENT_ABOVE = Decimal("2000.00")


@dataclass(frozen=True)
class InstallmentTier:
    min_count: int
    max_count: int
    min_installment: Decimal


# §3.1. The 2–3x tier reads "no minimum installment (except below R$ 50,00)"; interpreted as
# each installment must be at least R$ 50,00 (convention C4 in docs/data-findings.md).
# The §3 table's "minimum installment R$ 100,00" is the 7–12x tier; §3.1 is more specific.
TIERS: tuple[InstallmentTier, ...] = (
    InstallmentTier(2, 3, Decimal("50.00")),
    InstallmentTier(4, 6, Decimal("80.00")),
    InstallmentTier(7, 12, Decimal("100.00")),
)


@dataclass(frozen=True)
class InstallmentOption:
    count: int
    amount: Decimal


def minimum_installment(count: int) -> Decimal:
    if count == 1:
        return Decimal(0)
    for tier in TIERS:
        if tier.min_count <= count <= tier.max_count:
            return tier.min_installment
    raise ValueError(f"Installments must be between 1 and {MAX_INSTALLMENTS}, got {count}")


def installment_options(total: Decimal) -> list[InstallmentOption]:
    """All interest-free installment counts allowed for this total (1x is always allowed)."""
    if total <= 0:
        raise ValueError("Total must be positive")
    return [
        InstallmentOption(count, round_cents(total / count))
        for count in range(1, MAX_INSTALLMENTS + 1)
        # Compare the exact quotient, not the rounded one, so R$ 99,995 never passes as R$ 100.
        if total / count >= minimum_installment(count)
    ]


def combined_payment_allowed(total: Decimal) -> bool:
    """§3.1: combining payment methods (e.g. PIX + card) only above R$ 2.000,00."""
    return total > COMBINED_PAYMENT_ABOVE

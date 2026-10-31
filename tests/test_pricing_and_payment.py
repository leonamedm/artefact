from __future__ import annotations

from decimal import Decimal

import pytest

from emporio_agent.money import format_brl
from emporio_agent.services.payment import (
    combined_payment_allowed,
    installment_options,
    minimum_installment,
)
from emporio_agent.services.pricing import quote_price

D = Decimal


def test_active_promotion_shows_original_percent_and_promo_price_without_pix(catalog):
    taylor = catalog.get(94)  # Taylor 110e, R$ 5.999, "Desconto Exclusivo" 8% active
    quote = quote_price(taylor)
    assert quote.list_price == D("5999.00")
    assert quote.promotion.discount_percent == 8
    assert quote.final_price == D("5519.08")
    # PIX discount does not stack on a promotional price.
    assert quote.pix_discount_applies is False
    assert quote.pix_price == quote.final_price


def test_no_promotion_gets_five_percent_pix(catalog):
    takamine = catalog.get(95)  # Takamine GD20, R$ 2.199, only an inactive promotion
    quote = quote_price(takamine)
    assert quote.promotion is None
    assert quote.final_price == D("2199.00")
    assert quote.pix_price == D("2089.05")


def test_expired_promotions_are_never_applied(catalog):
    giannini = catalog.get(96)  # two promotions, both inactive
    assert giannini.active_promotion is None
    assert len(catalog.inactive_promotions(96)) == 2
    assert quote_price(giannini).final_price == D("799.90")


@pytest.mark.parametrize(
    ("total", "max_count"),
    [
        ("40.00", 1),  # 2x would be R$ 20 < R$ 50
        ("100.00", 2),  # 2x R$ 50 ok, 3x R$ 33,33 not
        ("240.00", 3),  # 3x R$ 80; 4x R$ 60 < R$ 80
        ("400.00", 5),  # 5x R$ 80; 6x R$ 66,67 < R$ 80; 7x < R$ 100
        ("1000.00", 10),  # 10x R$ 100
        ("1199.00", 11),  # 12x R$ 99,92 < R$ 100
        ("1200.00", 12),
        ("18900.00", 12),  # never more than 12x
    ],
)
def test_installment_tiers(total, max_count):
    options = installment_options(D(total))
    assert options[-1].count == max_count
    assert [o.count for o in options] == list(range(1, max_count + 1))


def test_installment_minimum_uses_exact_value_not_rounded():
    # 1199.99 / 12 = 99.999..., rounds to 100.00 but is below the minimum.
    assert installment_options(D("1199.99"))[-1].count == 11


def test_minimum_installment_bounds():
    assert minimum_installment(1) == 0
    assert minimum_installment(3) == D("50.00")
    assert minimum_installment(6) == D("80.00")
    assert minimum_installment(12) == D("100.00")
    with pytest.raises(ValueError):
        minimum_installment(13)


def test_combined_payment_only_above_two_thousand():
    assert not combined_payment_allowed(D("2000.00"))
    assert combined_payment_allowed(D("2000.01"))


def test_brl_format():
    assert format_brl(D("5519.08")) == "R$ 5.519,08"
    assert format_brl(D("159.9")) == "R$ 159,90"
    assert format_brl(D("18900")) == "R$ 18.900,00"

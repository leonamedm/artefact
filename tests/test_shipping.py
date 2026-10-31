from __future__ import annotations

from decimal import Decimal

import pytest

from emporio_agent.services.shipping import is_metro, quote_shipping

D = Decimal


@pytest.mark.parametrize(
    "city", ["Campo Grande", "campo grande - MS", "Campo Grande/MS", "CAMPO GRANDE"]
)
def test_campo_grande_is_metro(city):
    assert is_metro(city)


@pytest.mark.parametrize("city", ["Dourados", "Três Lagoas", "Grande Campo"])
def test_other_cities_are_not_metro(city):
    assert not is_metro(city)


def test_metro_free_above_500_and_fee_otherwise(catalog):
    product = catalog.get(81)
    assert quote_shipping("Campo Grande", D("500.01"), [product]).fee == D("0.00")
    # "Acima de R$ 500,00" is strict: exactly 500 pays the R$ 35 fee.
    assert quote_shipping("Campo Grande", D("500.00"), [product]).fee == D("35.00")
    assert quote_shipping("Campo Grande", D("159.90"), [product]).fee == D("35.00")


def test_other_city_never_gets_an_invented_price(catalog):
    quote = quote_shipping("Dourados", D("5999.00"), [catalog.get(94)])
    assert quote.fee is None
    assert [name for name, _ in quote.carrier_options] == [
        "PAC (Correios)",
        "SEDEX (Correios)",
        "Jadlog (.package)",
    ]


def test_large_items_flagged_for_special_freight(catalog):
    drum = catalog.get(139)  # Bateria Acústica Yamaha Kit 1 Studio
    quote = quote_shipping("Corumbá", drum.price, [drum])
    assert quote.large_items == (drum.name,)

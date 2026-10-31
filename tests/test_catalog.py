from __future__ import annotations

from decimal import Decimal

import pytest

from emporio_agent.services.catalog import Availability, UnknownCategoryError, availability


def test_violoes_up_to_1000_only_sellable_sorted_by_price(catalog):
    page = catalog.search(category="Violões", max_price=Decimal("1000"), limit=20)
    ids = [p.product_id for p in page.items]
    assert ids, "expected matches"
    assert all(p.category_id == 5 and p.is_sellable for p in page.items)
    assert 96 not in ids  # active but stock 0
    assert 113 not in ids  # discontinued
    prices = [p.price for p in page.items]
    assert prices == sorted(prices)
    assert page.total == len(ids)


def test_price_filter_uses_promotional_price(catalog):
    # Crafter HT-100 lists at R$ 2.399 with an active 18% promotion -> R$ 1.967,18.
    page = catalog.search(
        category="Violões", min_price=Decimal("1900"), max_price=Decimal("2000"), limit=20
    )
    assert 90 in [p.product_id for p in page.items]
    assert 95 not in [p.product_id for p in page.items]  # Takamine GD20, R$ 2.199, no promotion


def test_unavailable_items_only_when_requested(catalog):
    page = catalog.search(category="Violões", include_unavailable=True, limit=20)
    ids = [p.product_id for p in page.items]
    assert 96 in ids and 113 in ids


def test_text_search_is_accent_and_punctuation_insensitive(catalog):
    assert [p.product_id for p in catalog.find_by_name("takamine gd20")] == [95]
    assert [p.product_id for p in catalog.find_by_name("Takamine GD-20")] == [95]
    assert catalog.search(text="violao eletrico aco").total > 0


def test_empty_categories_return_nothing(catalog):
    assert catalog.search(category="Cordas Orquestrais").total == 0


def test_unknown_category_is_rejected(catalog):
    with pytest.raises(UnknownCategoryError):
        catalog.search(category="Amplificadores")


def test_status_wins_over_stock(catalog):
    assert availability(catalog.get(136)) is Availability.DISCONTINUED  # stock 13
    assert availability(catalog.get(130)) is Availability.COMING_SOON  # stock 2
    assert availability(catalog.get(96)) is Availability.OUT_OF_STOCK
    assert availability(catalog.get(95)) is Availability.AVAILABLE


def test_alternatives_are_sellable_same_category(catalog):
    discontinued = catalog.get(136)
    alternatives = catalog.alternatives(discontinued)
    assert alternatives
    assert all(a.category_id == discontinued.category_id and a.is_sellable for a in alternatives)
    assert 136 not in [a.product_id for a in alternatives]


def test_page_size_is_capped(catalog):
    assert len(catalog.search(limit=500).items) <= 20

from __future__ import annotations

from datetime import date

import pytest

from emporio_agent.domain import OrderStatus
from emporio_agent.services.returns import Outcome, ReturnReason, assess_return
from tests.conftest import TODAY

DELIVERED = OrderStatus.DELIVERED


def regret(received, purchase=date(2026, 10, 20), **kw):
    return assess_return(
        ReturnReason.REGRET,
        order_status=kw.pop("status", DELIVERED),
        purchase_date=purchase,
        received_date=received,
        today=TODAY,
        **kw,
    )


def test_regret_within_seven_days_of_receipt():
    result = regret(date(2026, 10, 25))
    assert result.outcome is Outcome.ELIGIBLE
    assert result.deadline == date(2026, 11, 1)
    assert result.days_left == 1


def test_regret_last_day_is_inclusive():
    assert regret(date(2026, 10, 24)).outcome is Outcome.ELIGIBLE


def test_regret_day_eight_is_expired():
    result = regret(date(2026, 10, 23))
    assert result.outcome is Outcome.EXPIRED
    assert result.days_left == -1


def test_regret_requires_received_date_never_assumes_eta():
    assert regret(None).outcome is Outcome.NEEDS_RECEIVED_DATE


def test_regret_only_for_online_purchases():
    assert regret(date(2026, 10, 30), online_purchase=False).outcome is Outcome.NOT_APPLICABLE


def test_not_delivered_or_cancelled_orders():
    assert regret(None, status=OrderStatus.SHIPPED).outcome is Outcome.NEEDS_HUMAN
    assert regret(None, status=OrderStatus.CANCELLED).outcome is Outcome.NOT_APPLICABLE


def test_possibly_non_eligible_item_goes_to_human():
    result = regret(date(2026, 10, 30), possibly_non_eligible=True)
    assert result.outcome is Outcome.NEEDS_HUMAN


def test_defect_exchange_within_thirty_days_of_purchase():
    result = assess_return(
        ReturnReason.DEFECT,
        order_status=DELIVERED,
        purchase_date=date(2026, 10, 5),
        received_date=None,
        today=TODAY,
    )
    assert result.outcome is Outcome.ELIGIBLE
    assert result.deadline == date(2026, 11, 4)


def test_defect_after_thirty_days_within_legal_warranty():
    result = assess_return(
        ReturnReason.DEFECT,
        order_status=DELIVERED,
        purchase_date=date(2026, 9, 1),
        received_date=date(2026, 9, 5),
        today=TODAY,
    )
    assert result.outcome is Outcome.MANUFACTURER_WARRANTY
    assert result.deadline == date(2026, 12, 4)  # 90 days from receipt
    assert "garantia legal" in result.explanation


def test_defect_beyond_legal_warranty_points_to_manufacturer():
    # Real order 1: bought 2025-10-15, estimated delivery 2025-10-25.
    result = assess_return(
        ReturnReason.DEFECT,
        order_status=DELIVERED,
        purchase_date=date(2025, 10, 15),
        received_date=date(2025, 10, 25),
        today=TODAY,
    )
    assert result.outcome is Outcome.MANUFACTURER_WARRANTY
    assert result.days_left < 0
    assert "fabricante" in result.explanation


def test_preference_exchange_seven_days():
    result = assess_return(
        ReturnReason.PREFERENCE,
        order_status=DELIVERED,
        purchase_date=date(2026, 10, 20),
        received_date=date(2026, 10, 28),
        today=TODAY,
    )
    assert result.outcome is Outcome.ELIGIBLE


def test_invalid_received_dates():
    with pytest.raises(ValueError):
        regret(date(2026, 10, 1))  # before the purchase
    with pytest.raises(ValueError):
        regret(date(2026, 11, 5))  # in the future

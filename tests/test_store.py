from __future__ import annotations

from datetime import datetime

from emporio_agent.clock import STORE_TZ
from emporio_agent.services.store import CONTACT, store_status


def at(*args):
    return datetime(*args, tzinfo=STORE_TZ)


def test_saturday_morning_open_until_13():
    status = store_status(at(2026, 10, 31, 10, 0))
    assert status.is_open
    assert status.today_hours[1].hour == 13


def test_saturday_afternoon_next_opening_skips_sunday_and_finados():
    status = store_status(at(2026, 10, 31, 14, 0))
    assert not status.is_open
    # Sunday closed, Monday 02/11 is Finados -> Tuesday 03/11 09:00.
    assert status.next_opening == at(2026, 11, 3, 9, 0)


def test_holiday_is_closed_with_reason():
    status = store_status(at(2026, 11, 2, 11, 0))
    assert not status.is_open
    assert "feriado" in status.closed_reason


def test_weekday_closing_time_is_exclusive():
    assert store_status(at(2026, 11, 3, 17, 59)).is_open
    status = store_status(at(2026, 11, 3, 18, 0))
    assert not status.is_open
    assert status.next_opening == at(2026, 11, 4, 9, 0)


def test_before_opening():
    status = store_status(at(2026, 11, 3, 8, 30))
    assert not status.is_open
    assert status.next_opening == at(2026, 11, 3, 9, 0)


def test_contact_convention():
    assert CONTACT.phone == "(67) 3341-4444"
    assert CONTACT.whatsapp == "(67) 3321-4500"
    assert CONTACT.email == "contato@emporiodamusica.com.br"

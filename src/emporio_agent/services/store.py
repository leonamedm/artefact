"""Store contact details and opening hours (manual §1.2, §2, §7)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache

import holidays

from emporio_agent.clock import STORE_TZ

WEEKDAY_NAMES = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")

# §2. Monday=0 ... Saturday=5; Sunday and holidays closed.
OPENING_HOURS: dict[int, tuple[time, time]] = {
    **{day: (time(9, 0), time(18, 0)) for day in range(5)},
    5: (time(9, 0), time(13, 0)),
}


@dataclass(frozen=True)
class StoreContact:
    name: str
    address: str
    phone: str
    whatsapp: str
    email: str


# The manual is inconsistent (convention C1/C2 in docs/data-findings.md): §1.2 lists
# "(67) 3341-4444" as phone/WhatsApp while §7, the WhatsApp section, says "(67) 3321-4500";
# the e-mail appears with and without an accent. Phone from §1.2, WhatsApp from §7, ASCII e-mail.
CONTACT = StoreContact(
    name="Empório da Música",
    address="Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, CEP 79202-333",
    phone="(67) 3341-4444",
    whatsapp="(67) 3321-4500",
    email="contato@emporiodamusica.com.br",
)


@dataclass(frozen=True)
class StoreStatus:
    now: datetime
    is_open: bool
    today_hours: tuple[time, time] | None
    closed_reason: str | None
    next_opening: datetime | None


@lru_cache(maxsize=8)
def _holidays(year: int) -> holidays.HolidayBase:
    # National + Mato Grosso do Sul holidays. Campo Grande municipal holidays are not covered
    # (open item O3).
    return holidays.Brazil(subdiv="MS", years=year)


def holiday_name(day: date) -> str | None:
    return _holidays(day.year).get(day)


def hours_for(day: date) -> tuple[time, time] | None:
    if holiday_name(day):
        return None
    return OPENING_HOURS.get(day.weekday())


def store_status(now: datetime) -> StoreStatus:
    local = now.astimezone(STORE_TZ)
    today = local.date()
    hours = hours_for(today)
    is_open = hours is not None and hours[0] <= local.time() < hours[1]

    closed_reason = None
    if not is_open:
        if name := holiday_name(today):
            closed_reason = f"feriado ({name})"
        elif today.weekday() == 6:
            closed_reason = "domingo"
        elif hours and local.time() < hours[0]:
            closed_reason = "antes do horário de abertura"
        else:
            closed_reason = "fora do horário de funcionamento"

    next_opening = None
    if not is_open:
        for offset in range(0, 15):
            day = today + timedelta(days=offset)
            day_hours = hours_for(day)
            if day_hours is None:
                continue
            opening = datetime.combine(day, day_hours[0], tzinfo=STORE_TZ)
            if opening > local:
                next_opening = opening
                break

    return StoreStatus(local, is_open, hours, closed_reason, next_opening)

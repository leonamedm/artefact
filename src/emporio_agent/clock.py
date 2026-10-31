"""Injectable clock. Services receive "now" explicitly so date rules are testable."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

STORE_TZ = ZoneInfo("America/Campo_Grande")


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(STORE_TZ)


class FixedClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment if moment.tzinfo else moment.replace(tzinfo=STORE_TZ)

    def now(self) -> datetime:
        return self._moment

"""Immutable daily schedules, independent of Home Assistant.

All public input is validated here, including data read from storage. Device
limits are applied on edits rather than loads, so temporarily missing devices
do not erase or prevent inspection of existing schedules.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

MAX_ROWS = 48
TIME_RE = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z")
ID_RE = re.compile(r"[a-zA-Z0-9_-]{1,64}\Z")


class InvalidSchedule(ValueError):
    """An input or persisted schedule violates the data contract."""


class RevisionConflict(ValueError):
    """Another client saved a newer revision."""


def finite_number(value: Any) -> float:
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise InvalidSchedule("Die Zieltemperatur muss eine endliche Zahl sein.")
    return float(value)


@dataclass(frozen=True)
class TemperatureLimits:
    minimum: float
    maximum: float
    step: float | None = None

    def __post_init__(self) -> None:
        low, high = finite_number(self.minimum), finite_number(self.maximum)
        if low >= high:
            raise InvalidSchedule("Ungültige Temperaturgrenzen des Thermostats.")
        if self.step is not None and finite_number(self.step) <= 0:
            raise InvalidSchedule("Ungültige Temperaturschrittweite.")

    def validate(self, value: float) -> None:
        if not self.minimum <= value <= self.maximum:
            raise InvalidSchedule(
                f"Temperatur muss zwischen {self.minimum} und {self.maximum} liegen."
            )
        # HA temperature steps describe resolution, not an offset from min_temp.
        if self.step is not None:
            units = Decimal(str(value)) / Decimal(str(self.step))
            if units != units.to_integral_value():
                raise InvalidSchedule(f"Temperatur muss in Schritten von {self.step} liegen.")


@dataclass(frozen=True)
class Row:
    id: str
    time: str
    temperature: float
    enabled: bool = True

    @classmethod
    def parse(cls, raw: Any, limits: TemperatureLimits | None = None) -> Row:
        if not isinstance(raw, dict) or set(raw) != {"id", "time", "temperature", "enabled"}:
            raise InvalidSchedule("Eine Schaltzeit braucht id, time, temperature und enabled.")
        if not isinstance(raw["id"], str) or not ID_RE.fullmatch(raw["id"]):
            raise InvalidSchedule("Ungültige Zeilen-ID.")
        if not isinstance(raw["time"], str) or not TIME_RE.fullmatch(raw["time"]):
            raise InvalidSchedule("Uhrzeit muss im Format HH:MM angegeben werden.")
        temperature = finite_number(raw["temperature"])
        if type(raw["enabled"]) is not bool:
            raise InvalidSchedule("Der Aktivierungszustand muss ein Wahrheitswert sein.")
        if limits:
            limits.validate(temperature)
        return cls(raw["id"], raw["time"], temperature, raw["enabled"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "time": self.time,
            "temperature": self.temperature,
            "enabled": self.enabled,
        }


@dataclass(frozen=True)
class Schedule:
    revision: int = 0
    enabled: bool = False
    rows: tuple[Row, ...] = ()

    @classmethod
    def parse(cls, raw: Any, limits: TemperatureLimits | None = None) -> Schedule:
        if not isinstance(raw, dict) or set(raw) != {"revision", "enabled", "rows"}:
            raise InvalidSchedule("Ungültiges Zeitplanformat.")
        if type(raw["revision"]) is not int or raw["revision"] < 0:
            raise InvalidSchedule("Ungültige Revision.")
        if type(raw["enabled"]) is not bool:
            raise InvalidSchedule("enabled muss ein Wahrheitswert sein.")
        if not isinstance(raw["rows"], list) or len(raw["rows"]) > MAX_ROWS:
            raise InvalidSchedule(f"Maximal {MAX_ROWS} Schaltzeiten pro Thermostat.")
        rows = tuple(sorted((Row.parse(r, limits) for r in raw["rows"]), key=lambda r: r.time))
        if len({row.id for row in rows}) != len(rows):
            raise InvalidSchedule("Zeilen-IDs müssen eindeutig sein.")
        if len({row.time for row in rows}) != len(rows):
            raise InvalidSchedule("Pro Uhrzeit ist nur eine Zieltemperatur erlaubt.")
        return cls(raw["revision"], raw["enabled"], rows)

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "enabled": self.enabled,
            "rows": [row.to_dict() for row in self.rows],
        }


@dataclass(frozen=True)
class Occurrence:
    row: Row
    at: datetime


def occurrence_on(row: Row, day: date, timezone: ZoneInfo) -> Occurrence | None:
    """First occurrence on autumn overlap; no occurrence in spring's missing hour."""
    wall = datetime.combine(day, time.fromisoformat(row.time))
    candidate = wall.replace(tzinfo=timezone, fold=0)
    utc = candidate.astimezone(UTC)
    if utc.astimezone(timezone).replace(tzinfo=None) != wall:
        return None
    return Occurrence(row, utc)


def next_occurrence(schedule: Schedule, after: datetime, timezone: ZoneInfo) -> Occurrence | None:
    """Return the next strictly future point; all comparisons happen in UTC."""
    if after.tzinfo is None:
        raise ValueError("An aware datetime is required")
    if not schedule.enabled or not schedule.rows:
        return None
    utc_after = after.astimezone(UTC)
    day = after.astimezone(timezone).date()
    # Today and the following two days cover a skipped spring transition.
    candidates = (
        occurrence_on(row, day + timedelta(days=offset), timezone)
        for offset in range(3)
        for row in schedule.rows
        if row.enabled
    )
    return min(
        (c for c in candidates if c is not None and c.at > utc_after),
        key=lambda c: c.at,
        default=None,
    )

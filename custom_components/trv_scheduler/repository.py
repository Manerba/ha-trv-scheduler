"""Serialized, optimistic-concurrency storage; only publish successful writes."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from .model import InvalidSchedule, RevisionConflict, Schedule, TemperatureLimits


class Storage(Protocol):
    async def async_load(self) -> dict[str, Any] | None: ...

    async def async_save(self, data: dict[str, Any]) -> None: ...


class ScheduleRepository:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage
        self._schedule = Schedule()
        self._lock = asyncio.Lock()
        self._loaded = False

    @property
    def schedule(self) -> Schedule:
        if not self._loaded:
            raise RuntimeError("Repository has not been loaded")
        return self._schedule

    async def async_load(self) -> None:
        async with self._lock:
            raw = await self._storage.async_load()
            self._schedule = Schedule() if raw is None else Schedule.parse(raw)
            self._loaded = True

    async def async_replace(
        self,
        *,
        expected_revision: int,
        enabled: bool,
        rows: list[dict[str, Any]],
        limits: TemperatureLimits | None,
    ) -> Schedule:
        async with self._lock:
            current = self.schedule
            if type(expected_revision) is not int or expected_revision < 0:
                raise InvalidSchedule("Ungültige erwartete Revision.")
            if expected_revision != current.revision:
                raise RevisionConflict("Der Zeitplan wurde inzwischen geändert. Bitte neu laden.")
            candidate = Schedule.parse(
                {"revision": current.revision + 1, "enabled": enabled, "rows": rows}
            )
            previous = {row.id: row for row in current.rows}
            if limits is None:
                # Disabling/deleting must work even while a device is offline.
                needs_limits = candidate.enabled and not current.enabled
                for row in candidate.rows:
                    old = previous.get(row.id)
                    needs_limits |= (
                        old is None
                        or row.time != old.time
                        or row.temperature != old.temperature
                        or (row.enabled and not old.enabled)
                    )
                if needs_limits:
                    raise InvalidSchedule("Thermostat ist momentan nicht erreichbar.")
            else:
                for row in candidate.rows:
                    limits.validate(row.temperature)
            await self._storage.async_save(candidate.to_dict())
            self._schedule = candidate
            return candidate

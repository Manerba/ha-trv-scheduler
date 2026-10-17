"""HA runtime adapter; no scheduling in the browser and no implicit catch-up."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import CONF_CLIMATE, CONF_GATE, CONF_SETTER
from .model import InvalidSchedule, Occurrence, Schedule, TemperatureLimits, next_occurrence
from .repository import ScheduleRepository

_LOGGER = logging.getLogger(__name__)
MAX_LATENESS = timedelta(seconds=60)


class ScheduleManager:
    def __init__(self, hass: HomeAssistant, config: dict, repository: ScheduleRepository) -> None:
        self.hass = hass
        self.config = config
        self.repository = repository
        self._cancel_timer = None
        self._worker: asyncio.Task | None = None
        self._stopped = True
        self._generation = 0
        self.last_result: dict[str, Any] | None = None

    @property
    def entity_id(self) -> str:
        return self.config[CONF_CLIMATE]

    def limits(self) -> TemperatureLimits:
        state = self.hass.states.get(self.entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            raise InvalidSchedule("Thermostat ist momentan nicht erreichbar.")
        return TemperatureLimits(
            state.attributes.get("min_temp"),
            state.attributes.get("max_temp"),
            state.attributes.get("target_temp_step"),
        )

    def validate_lock_request(self, enabled: bool, rows: list) -> None:
        """Do not silently activate lock actions before the gateway adapter exists."""
        candidate = Schedule.parse({"revision": 0, "enabled": enabled, "rows": rows})
        if candidate.enabled and any(row.enabled and row.locked for row in candidate.rows):
            raise InvalidSchedule(
                "Die Gerätesperre ist für dieses Thermostat noch nicht angebunden."
            )

    def snapshot(self) -> dict[str, Any]:
        state = self.hass.states.get(self.entity_id)
        try:
            limits = self.limits()
            bounds = {"min": limits.minimum, "max": limits.maximum, "step": limits.step}
        except InvalidSchedule:
            bounds = None
        point = self._next(dt_util.utcnow())
        return {
            "entity_id": self.entity_id,
            "schedule": self.repository.schedule.to_dict(),
            "limits": bounds,
            "temperature_unit": (
                state.attributes.get("temperature_unit", self.hass.config.units.temperature_unit)
                if state
                else self.hass.config.units.temperature_unit
            ),
            "next_at": point.at.isoformat() if point else None,
            "last_result": self.last_result,
            "lock_supported": False,
        }

    def _next(self, after: datetime) -> Occurrence | None:
        return next_occurrence(
            self.repository.schedule, after, ZoneInfo(self.hass.config.time_zone)
        )

    @callback
    def start(self) -> None:
        self._stopped = False
        self.reschedule()

    @callback
    def reschedule(self) -> None:
        self._generation += 1
        if self._cancel_timer:
            self._cancel_timer()
            self._cancel_timer = None
        if self._stopped or not (point := self._next(dt_util.utcnow())):
            return
        revision = self.repository.schedule.revision
        generation = self._generation

        @callback
        def due(_now):
            # Plan edits/unload can race a callback already queued on HA's loop.
            if (
                self._stopped
                or self._generation != generation
                or self.repository.schedule.revision != revision
            ):
                return
            self._cancel_timer = None
            if self._worker is not None and not self._worker.done():
                self._result(point, "busy")
            else:
                self._worker = self.hass.async_create_task(self._execute(point, revision))
            self.reschedule()

        self._cancel_timer = async_track_point_in_utc_time(self.hass, due, point.at)

    def _result(self, point: Occurrence, status: str) -> None:
        self.last_result = {
            "row_id": point.row.id,
            "scheduled_at": point.at.isoformat(),
            "status": status,
        }

    async def _execute(self, point: Occurrence, revision: int) -> None:
        if self._stopped or self.repository.schedule.revision != revision:
            return
        if dt_util.utcnow() - point.at > MAX_LATENESS:
            self._result(point, "missed")
            return
        gate = self.config.get(CONF_GATE)
        if gate and not self.hass.states.is_state(gate, STATE_ON):
            self._result(point, "blocked")
            return
        try:
            if point.row.locked:
                raise InvalidSchedule("Die Gerätesperre ist noch nicht angebunden.")
            self.limits().validate(point.row.temperature)
            if setter := self.config.get(CONF_SETTER):
                domain, service = setter.split(".", 1)
                data = {"climate_entity": self.entity_id, "temperature": point.row.temperature}
            else:
                domain, service = "climate", "set_temperature"
                data = {"entity_id": self.entity_id, "temperature": point.row.temperature}
            # An existing script can contain its own bounded retries. Avoid overlapping runs.
            await self.hass.services.async_call(domain, service, data, blocking=True)
            self._result(point, "sent")
        except (HomeAssistantError, InvalidSchedule) as err:
            self._result(point, "failed")
            _LOGGER.warning("Zeitsteuerung für %s fehlgeschlagen: %s", self.entity_id, err)

    async def stop(self) -> None:
        self._stopped = True
        if self._cancel_timer:
            self._cancel_timer()
            self._cancel_timer = None
        if self._worker and not self._worker.done():
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

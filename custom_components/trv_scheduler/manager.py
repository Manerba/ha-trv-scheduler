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
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from .const import CONF_CLIMATE, CONF_GATE, CONF_SETTER
from .device_lock import DeviceLock
from .model import InvalidSchedule, Occurrence, Schedule, TemperatureLimits, next_occurrence
from .repository import ScheduleRepository

_LOGGER = logging.getLogger(__name__)
MAX_LATENESS = timedelta(seconds=60)


class ScheduleManager:
    def __init__(
        self,
        hass: HomeAssistant,
        config: dict,
        repository: ScheduleRepository,
        device_lock: DeviceLock | None = None,
    ) -> None:
        self.hass = hass
        self.config = config
        self.repository = repository
        self.device_lock = device_lock
        self._operation_lock = asyncio.Lock()
        self._cancel_gate = None
        self._cancel_retry = None
        self._recovery_task = None
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
        """Do not silently activate actions on a device without a lock adapter."""
        candidate = Schedule.parse({"revision": 0, "enabled": enabled, "rows": rows})
        if (
            not self.device_lock
            and candidate.enabled
            and any(row.enabled and row.locked for row in candidate.rows)
        ):
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
            "lock_supported": self.device_lock is not None,
            "device_lock": self.device_lock.snapshot() if self.device_lock else None,
            "gate_enabled": self._gate_enabled(),
        }

    def _gate_enabled(self):
        gate = self.config.get(CONF_GATE)
        return not gate or self.hass.states.is_state(gate, STATE_ON)

    def _needs_release(self):
        schedule = self.repository.schedule
        return (
            not schedule.enabled
            or not any(r.enabled for r in schedule.rows)
            or not self._gate_enabled()
        )

    async def async_replace(self, **kwargs):
        async with self._operation_lock:
            if self._stopped:
                raise HomeAssistantError("Zeitsteuerung wird gerade beendet.")
            self.validate_lock_request(kwargs["enabled"], kwargs["rows"])
            await self.repository.async_replace(**kwargs)
            self.reschedule()
            # A plan is already saved at this point. Report unlock errors in device_lock,
            # not as a failed save, and retry while the integration remains loaded.
            await self._release_if_needed()

    async def async_refresh_lock(self):
        if self.device_lock:
            async with self._operation_lock:
                await self.device_lock.async_read()

    async def async_unlock(self):
        if not self.device_lock:
            raise InvalidSchedule("Keine Gerätesperre angebunden.")
        async with self._operation_lock:
            await self.device_lock.async_apply(False)

    async def _release_if_needed(self):
        if not self.device_lock or not self.device_lock.owned or not self._needs_release():
            return
        try:
            await self.device_lock.async_apply(False)
        except (HomeAssistantError, OSError):
            if not self._cancel_retry and not self._stopped:

                @callback
                def retry(_now):
                    self._cancel_retry = None
                    self._queue_recovery()

                self._cancel_retry = async_track_point_in_utc_time(
                    self.hass, retry, dt_util.utcnow() + timedelta(minutes=1)
                )

    def _queue_recovery(self):
        if self._stopped or (self._recovery_task and not self._recovery_task.done()):
            return

        async def recover():
            async with self._operation_lock:
                await self._release_if_needed()

        self._recovery_task = self.hass.async_create_task(recover())

    def _next(self, after: datetime) -> Occurrence | None:
        return next_occurrence(
            self.repository.schedule, after, ZoneInfo(self.hass.config.time_zone)
        )

    @callback
    def start(self) -> None:
        self._stopped = False
        if self.device_lock:
            if (gate := self.config.get(CONF_GATE)) and self._cancel_gate is None:

                @callback
                def gate_changed(_event):
                    self._queue_recovery()

                self._cancel_gate = async_track_state_change_event(self.hass, gate, gate_changed)
            if self.device_lock.owned and self._needs_release():
                self._queue_recovery()
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
        async with self._operation_lock:
            await self._execute_locked(point, revision)

    async def _execute_locked(self, point: Occurrence, revision: int) -> None:
        if self._stopped or self.repository.schedule.revision != revision:
            return
        if dt_util.utcnow() - point.at > MAX_LATENESS:
            self._result(point, "missed")
            return
        if not self._gate_enabled():
            self._result(point, "blocked")
            return
        try:
            if point.row.locked and not self.device_lock:
                raise InvalidSchedule("Die Gerätesperre ist noch nicht angebunden.")
            self.limits().validate(point.row.temperature)
            if setter := self.config.get(CONF_SETTER):
                domain, service = setter.split(".", 1)
                data = {"climate_entity": self.entity_id, "temperature": point.row.temperature}
            else:
                domain, service = "climate", "set_temperature"
                data = {"entity_id": self.entity_id, "temperature": point.row.temperature}
            # An existing script can contain its own bounded retries. Avoid overlapping runs.
            async with asyncio.timeout(90):
                await self.hass.services.async_call(domain, service, data, blocking=True)
            # Gate may have changed while waiting for a retry script to finish.
            if not self._gate_enabled():
                await self._release_if_needed()
                self._result(point, "blocked")
                return
            if self.device_lock:
                await self.device_lock.async_apply(point.row.locked)
            self._result(point, "sent")
        except (HomeAssistantError, InvalidSchedule, OSError, TimeoutError) as err:
            self._result(point, "failed")
            _LOGGER.warning("Zeitsteuerung für %s fehlgeschlagen: %s", self.entity_id, err)
            # An unlock row must still release a previous lock if setting temperature fails.
            if self.device_lock and not point.row.locked:
                try:
                    await self.device_lock.async_apply(False)
                except (HomeAssistantError, OSError):
                    pass

    async def stop(self, *, release=False) -> None:
        async with self._operation_lock:
            # Wait for an in-flight action before inspecting ownership; it may lock
            # the device while we wait. Failed release leaves the manager available.
            if release and self.device_lock and self.device_lock.owned:
                await self.device_lock.async_apply(False)
            self._stopped = True
        if self._cancel_timer:
            self._cancel_timer()
            self._cancel_timer = None
        for unsubscribe in (self._cancel_gate, self._cancel_retry):
            if unsubscribe:
                unsubscribe()
        self._cancel_gate = self._cancel_retry = None
        if self._recovery_task and not self._recovery_task.done():
            self._recovery_task.cancel()
            await asyncio.gather(self._recovery_task, return_exceptions=True)
        if self._worker and not self._worker.done():
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

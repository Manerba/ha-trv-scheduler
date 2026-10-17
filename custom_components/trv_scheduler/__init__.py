"""Daily TRV schedules with independent storage and a WebSocket editor API."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from .api import async_register_commands
from .const import CONF_CLIMATE, DOMAIN
from .device_lock import DeviceLock
from .frontend import async_setup_resources
from .gateway import resolve_gateway
from .manager import ScheduleManager
from .model import InvalidSchedule
from .repository import ScheduleRepository
from .storage import VerifiedStore


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    async_register_commands(hass)
    await async_setup_resources(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    climate = entry.data[CONF_CLIMATE]
    if climate in hass.data[DOMAIN]:
        raise ConfigEntryError("Für dieses Thermostat existiert bereits eine Zeitsteuerung.")
    store = VerifiedStore(hass, f"{DOMAIN}.{entry.entry_id}")
    repository = ScheduleRepository(store)
    try:
        await repository.async_load()
    except InvalidSchedule as err:
        raise ConfigEntryError(f"Gespeicherter Zeitplan ist ungültig: {err}") from err
    lock = None
    if gateway := resolve_gateway(hass, climate):
        lock = DeviceLock(gateway, VerifiedStore(hass, f"{DOMAIN}_lock.{entry.entry_id}"))
        await lock.async_load()
    manager = ScheduleManager(hass, entry.data, repository, lock)
    hass.data[DOMAIN][climate] = manager
    manager.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = hass.data[DOMAIN][entry.data[CONF_CLIMATE]]
    await manager.stop(release=True)
    hass.data[DOMAIN].pop(entry.data[CONF_CLIMATE])
    # Retain the Store on unload/removal: schedule deletion must be explicit.
    return True

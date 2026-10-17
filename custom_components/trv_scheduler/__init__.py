"""Daily TRV schedules with independent storage and a WebSocket editor API."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from .api import async_register_commands
from .const import CONF_CLIMATE, DOMAIN
from .manager import ScheduleManager
from .model import InvalidSchedule
from .repository import ScheduleRepository
from .storage import VerifiedStore


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    async_register_commands(hass)
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
    manager = ScheduleManager(hass, entry.data, repository)
    hass.data[DOMAIN][climate] = manager
    manager.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = hass.data[DOMAIN].pop(entry.data[CONF_CLIMATE])
    await manager.stop()
    # Retain the Store on unload/removal: schedule deletion must be explicit.
    return True

"""HA Store adapter that verifies successful persistence before acknowledging edits.

HA 2025.4 Store logs some filesystem errors without raising them. A direct
read-back is therefore required; otherwise the UI could falsely report success.
No private Store method is overridden.
"""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_VERSION


class VerifiedStore:
    def __init__(self, hass: HomeAssistant, key: str) -> None:
        self.hass = hass
        self.store = Store(hass, STORAGE_VERSION, key, atomic_writes=True)

    async def async_load(self):
        return await self.store.async_load()

    async def async_save(self, data):
        if self.hass.state in (CoreState.stopping, CoreState.final_write, CoreState.stopped):
            raise OSError("Home Assistant is stopping")
        await self.store.async_save(data)
        persisted = await self.hass.async_add_executor_job(self._read_disk)
        if persisted.get("version") != STORAGE_VERSION or persisted.get("data") != data:
            raise OSError("Schedule persistence could not be verified")

    def _read_disk(self):
        with Path(self.store.path).open(encoding="utf-8") as stream:
            return json.load(stream)

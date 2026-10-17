"""Confirmed device state and durable ownership for recovery after a restart."""

from __future__ import annotations

from homeassistant.util import dt as dt_util

from .gateway import GatewayError


class DeviceLock:
    def __init__(self, gateway, store) -> None:
        self.gateway = gateway
        self.store = store
        self.owned = False
        self.locked: bool | None = None
        self.checked_at: str | None = None
        self.error: str | None = None
        self.busy = False

    async def async_load(self) -> None:
        data = await self.store.async_load()
        if data is not None:
            if not isinstance(data, dict) or type(data.get("owned")) is not bool:
                raise GatewayError("Gespeicherter Zustand der Gerätesperre ist ungültig.")
            self.owned = data["owned"]

    def snapshot(self):
        return {
            "locked": self.locked,
            "checked_at": self.checked_at,
            "error": self.error,
            "busy": self.busy,
            "owned": self.owned,
        }

    async def _own(self, value: bool):
        await self.store.async_save({"owned": value})
        self.owned = value

    async def async_read(self):
        self.busy = True
        try:
            self.locked = await self.gateway.async_read_lock()
            self.checked_at = dt_util.utcnow().isoformat()
            self.error = None
        except GatewayError as err:
            self.locked = None
            self.error = str(err)
            raise
        finally:
            self.busy = False

    async def async_apply(self, locked: bool):
        self.busy = True
        try:
            # Write ownership before sending: a lost reply must not strand a lock.
            if locked and not self.owned:
                await self._own(True)
            self.locked = None
            actual = await self.gateway.async_set_lock(locked)
            self.locked = actual
            self.checked_at = dt_util.utcnow().isoformat()
            self.error = None
            if not locked:
                await self._own(False)
        except (GatewayError, OSError) as err:
            self.locked = None
            self.error = str(err)
            raise
        finally:
            self.busy = False

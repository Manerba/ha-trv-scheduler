"""Shelly BLU TRV RPC adapter using registered gateway credentials, server-side only."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Mapping
from typing import Any

import httpx
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.httpx_client import get_async_client

from .const import DOMAIN


class GatewayError(HomeAssistantError):
    """A remote command failed or could not be confirmed."""


class ShellyGateway:
    def __init__(self, client, config: Callable[[], Mapping], component: int, lock) -> None:
        self.client = client
        self.config = config
        self.component = component
        self.lock = lock

    async def _rpc(self, method: str, params: dict | None = None) -> Any:
        config = self.config()
        url = httpx.URL(
            scheme="https" if config.get("ssl", False) else "http",
            host=config["host"],
            port=config.get("port", 80),
            path="/rpc",
        )
        auth = (
            httpx.DigestAuth(config.get("username") or "admin", config["password"])
            if config.get("password")
            else None
        )
        try:
            response = await self.client.post(
                url,
                auth=auth,
                timeout=httpx.Timeout(65, connect=10),
                json={
                    "id": 1,
                    "method": "BluTrv.Call",
                    "params": {
                        "id": self.component,
                        "method": method,
                        "params": params or {"id": 0},
                    },
                },
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or "error" in payload or "result" not in payload:
                raise GatewayError("Das Shelly-Gateway hat den Befehl nicht bestätigt.")
            result = payload["result"]
            if isinstance(result, dict) and "error" in result:
                raise GatewayError("Das Thermostat hat den Befehl abgelehnt.")
            return result
        except (httpx.HTTPError, ValueError, KeyError) as err:
            # Do not expose response bodies, URLs with credentials, or auth challenges.
            raise GatewayError(
                "Shelly-Gateway nicht erreichbar oder Anmeldung fehlgeschlagen."
            ) from err

    @staticmethod
    def _locked(config) -> bool:
        if not isinstance(config, dict) or not isinstance(config.get("ui"), dict):
            raise GatewayError("Das Thermostat meldet keinen Sperrzustand.")
        value = config["ui"].get("lock")
        if type(value) is not bool:
            raise GatewayError("Das Thermostat meldet einen ungültigen Sperrzustand.")
        return value

    async def async_read_lock(self) -> bool:
        async with self.lock:
            return self._locked(await self._rpc("Sys.GetConfig"))

    async def async_set_lock(self, locked: bool) -> bool:
        if type(locked) is not bool:
            raise ValueError("locked must be boolean")
        async with self.lock:
            # Patch only the desired setting, preserving brightness, flip, etc.
            await self._rpc("Sys.SetConfig", {"config": {"ui": {"lock": locked}}})
            actual = self._locked(await self._rpc("Sys.GetConfig"))
            if actual != locked:
                raise GatewayError("Die Gerätesperre wurde vom Thermostat nicht übernommen.")
            return actual


def resolve_gateway(hass, entity_id: str) -> ShellyGateway | None:
    entity = er.async_get(hass).async_get(entity_id)
    if entity is None or entity.platform != "shelly" or not entity.device_id:
        return None
    match = re.search(r"-blutrv:(\d+)$", entity.unique_id)
    device = dr.async_get(hass).async_get(entity.device_id)
    if match is None or device is None or device.model != "Shelly BLU TRV":
        return None
    entry = hass.config_entries.async_get_entry(entity.config_entry_id)
    if entry is None or entry.domain != "shelly" or not entry.data.get("host"):
        return None

    # Credentials stay in the existing Shelly entry and are re-read on each call.
    def config():
        current = hass.config_entries.async_get_entry(entry.entry_id)
        if current is None:
            raise GatewayError("Die zugehörige Shelly-Integration wurde entfernt.")
        return current.data

    locks = hass.data.setdefault(f"{DOMAIN}_gateway_locks", {})
    return ShellyGateway(
        get_async_client(hass),
        config,
        int(match[1]),
        locks.setdefault(entry.entry_id, asyncio.Lock()),
    )

"""Authenticated API; existing HA entity permissions apply to every request."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .model import InvalidSchedule, RevisionConflict


def _manager(hass, connection, msg, policy):
    user = connection.user
    if (
        user is None
        or not user.is_active
        or not user.permissions.check_entity(msg["entity_id"], policy)
    ):
        connection.send_error(
            msg["id"], "unauthorized", "Keine Berechtigung für dieses Thermostat."
        )
        return None
    if manager := hass.data.get(DOMAIN, {}).get(msg["entity_id"]):
        return manager
    connection.send_error(msg["id"], "not_found", "Für dieses Thermostat fehlt die Zeitsteuerung.")
    return None


@websocket_api.websocket_command(
    {
        vol.Required("type"): "trv_scheduler/get",
        vol.Required("entity_id"): str,
    }
)
@callback
def ws_get(hass, connection, msg):
    if manager := _manager(hass, connection, msg, POLICY_READ):
        result = manager.snapshot()
        result["can_edit"] = connection.user.permissions.check_entity(
            msg["entity_id"], POLICY_CONTROL
        )
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "trv_scheduler/replace",
        vol.Required("entity_id"): str,
        vol.Required("expected_revision"): int,
        vol.Required("enabled"): bool,
        vol.Required("rows"): list,
    }
)
@websocket_api.async_response
async def ws_replace(hass, connection, msg):
    if not (manager := _manager(hass, connection, msg, POLICY_CONTROL)):
        return
    try:
        manager.validate_lock_request(msg["enabled"], msg["rows"])
        try:
            limits = manager.limits()
        except InvalidSchedule:
            limits = None
        await manager.repository.async_replace(
            expected_revision=msg["expected_revision"],
            enabled=msg["enabled"],
            rows=msg["rows"],
            limits=limits,
        )
    except RevisionConflict as err:
        connection.send_error(msg["id"], "revision_conflict", str(err))
        return
    except InvalidSchedule as err:
        connection.send_error(msg["id"], "invalid_schedule", str(err))
        return
    except (HomeAssistantError, OSError):
        connection.send_error(
            msg["id"], "save_failed", "Der Zeitplan konnte nicht gespeichert werden."
        )
        return
    manager.reschedule()
    connection.send_result(msg["id"], manager.snapshot())


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_get)
    websocket_api.async_register_command(hass, ws_replace)

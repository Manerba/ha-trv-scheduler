from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.exceptions import ConfigEntryError

from custom_components.trv_scheduler import async_setup, async_setup_entry, async_unload_entry
from custom_components.trv_scheduler.config_flow import TRVSchedulerConfigFlow
from custom_components.trv_scheduler.const import DOMAIN
from custom_components.trv_scheduler.model import TemperatureLimits


@pytest.fixture(autouse=True)
def isolate_webserver_and_registries():
    # Full frontend loading and discovery are covered separately and in the live install.
    with (
        patch("custom_components.trv_scheduler.async_setup_resources", new=AsyncMock()),
        patch("custom_components.trv_scheduler.resolve_gateway", return_value=None),
    ):
        yield


def entry():
    return ConfigEntry(
        domain=DOMAIN,
        title="Schlafzimmer",
        version=1,
        minor_version=1,
        data={"climate_entity": "climate.trv2"},
        options={},
        source="user",
        unique_id="climate.trv2",
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )


async def test_setup_unload_reload_preserves_schedule(hass, rows):
    assert await async_setup(hass, {})
    configured = entry()
    assert await async_setup_entry(hass, configured)
    manager = hass.data[DOMAIN]["climate.trv2"]
    assert not manager.repository.schedule.enabled
    assert manager._cancel_timer is None
    await manager.repository.async_replace(
        expected_revision=0, enabled=True, rows=rows, limits=TemperatureLimits(4, 30, 0.5)
    )
    manager.reschedule()
    assert manager._cancel_timer is not None
    assert await async_unload_entry(hass, configured)
    assert manager._cancel_timer is None
    assert "climate.trv2" not in hass.data[DOMAIN]
    assert await async_setup_entry(hass, configured)
    assert hass.data[DOMAIN]["climate.trv2"].repository.schedule == manager.repository.schedule
    assert await async_unload_entry(hass, configured)


async def test_second_entry_cannot_control_same_thermostat(hass):
    await async_setup(hass, {})
    configured = entry()
    await async_setup_entry(hass, configured)
    with pytest.raises(ConfigEntryError, match="bereits"):
        await async_setup_entry(hass, entry())
    await async_unload_entry(hass, configured)


async def test_websocket_commands_register_with_strict_schemas(hass):
    await async_setup(hass, {})
    handler, schema = hass.data["websocket_api"]["trv_scheduler/get"]
    assert callable(handler)
    assert schema({"id": 1, "type": "trv_scheduler/get", "entity_id": "climate.trv2"})


async def test_config_flow_accepts_existing_climate(hass):
    hass.config_entries = ConfigEntries(hass, {})
    hass.states.async_set("climate.trv2", "heat", {"friendly_name": "Schlafzimmer"})
    flow = TRVSchedulerConfigFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.context = {"source": "user"}
    result = await flow.async_step_user({"climate_entity": "climate.trv2"})
    assert result["type"] == "create_entry"
    assert result["title"] == "Schlafzimmer"


async def test_config_flow_rejects_missing_gate(hass):
    hass.config_entries = ConfigEntries(hass, {})
    hass.states.async_set("climate.trv2", "heat")
    flow = TRVSchedulerConfigFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.context = {"source": "user"}
    result = await flow.async_step_user(
        {
            "climate_entity": "climate.trv2",
            "gate_entity": "input_boolean.missing",
        }
    )
    assert result["type"] == "form"
    assert result["errors"] == {"gate_entity": "invalid_entity"}

"""Exercise HA's real resource collection: create, update and persistence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.lovelace import LOVELACE_DATA
from homeassistant.components.lovelace.resources import (
    ResourceStorageCollection,
    ResourceYAMLCollection,
)
from homeassistant.exceptions import HomeAssistantError

from custom_components.trv_scheduler.frontend import CARD_PATH, CARD_URL, async_register_resource


@pytest.fixture
async def resources(hass):
    dashboard = SimpleNamespace(async_load=AsyncMock(side_effect=HomeAssistantError()))
    collection = ResourceStorageCollection(hass, dashboard)
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=collection)
    return collection


async def test_registers_module_without_bootstrap_injection(hass, resources):
    with patch("custom_components.trv_scheduler.frontend.frontend.add_extra_js_url") as extra:
        await async_register_resource(hass)
        extra.assert_not_called()
    assert resources.loaded
    [item] = resources.async_items()
    assert item["url"] == CARD_URL and item["type"] == "module"
    await async_register_resource(hass)
    assert resources.async_items() == [item]


async def test_upgrades_existing_url_in_place_preserving_other_resources(hass, resources):
    await resources.async_load()
    resources.loaded = True
    old = await resources.async_create_item({"url": CARD_PATH + "?v=0.2.0", "res_type": "js"})
    other = await resources.async_create_item({"url": "/local/other.js", "res_type": "module"})
    await async_register_resource(hass)
    items = resources.async_items()
    assert len(items) == 2 and other in items
    assert next(item for item in items if item["id"] == old["id"]) == {
        "id": old["id"],
        "url": CARD_URL,
        "type": "module",
    }


async def test_resource_survives_reload_without_duplicate(hass, resources):
    await async_register_resource(hass)
    original = resources.async_items()
    # Flush HA's delayed collection save without sleeping.
    await resources.store.async_save({"items": original})
    reloaded = ResourceStorageCollection(hass, resources.ll_config)
    hass.data[LOVELACE_DATA].resources = reloaded
    await async_register_resource(hass)
    assert reloaded.async_items() == original


async def test_yaml_configuration_is_not_mutated(hass):
    items = [{"url": "/local/other.js", "type": "module"}]
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=ResourceYAMLCollection(items))
    with patch("custom_components.trv_scheduler.frontend.frontend.add_extra_js_url") as extra:
        await async_register_resource(hass)
        extra.assert_called_once_with(hass, CARD_URL)
    assert items == [{"url": "/local/other.js", "type": "module"}]

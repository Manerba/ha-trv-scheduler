"""Serve the bundled card and register it with the dashboard resource loader."""

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection

from .const import VERSION

CARD_PATH = "/trv_scheduler/trv-scheduler-card.js"
CARD_URL = f"{CARD_PATH}?v={VERSION}"


async def async_register_resource(hass):
    resources = hass.data[LOVELACE_DATA].resources
    if not isinstance(resources, ResourceStorageCollection):
        # YAML resources are user-owned. Preserve the bootstrap fallback there.
        frontend.add_extra_js_url(hass, CARD_URL)
        return
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True
    for item in resources.async_items():
        if item["url"].split("?", 1)[0] == CARD_PATH:
            if item["url"] != CARD_URL or item["type"] != "module":
                await resources.async_update_item(
                    item["id"], {"url": CARD_URL, "res_type": "module"}
                )
            return
    await resources.async_create_item({"url": CARD_URL, "res_type": "module"})


async def async_setup_resources(hass):
    await hass.http.async_register_static_paths(
        [StaticPathConfig("/trv_scheduler", str(Path(__file__).parent / "frontend"), False)]
    )
    # Cached app bootstrap HTML can omit newly added extra_js_url entries.
    # Lovelace fetches this resource list separately when loading a dashboard.
    await async_register_resource(hass)

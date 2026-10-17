"""Serve the bundled card; no separate download or manual resource URL needed."""

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig

CARD_URL = "/trv_scheduler/trv-scheduler-card.js?v=0.2.0"


async def async_setup_resources(hass):
    await hass.http.async_register_static_paths(
        [StaticPathConfig("/trv_scheduler", str(Path(__file__).parent / "frontend"), False)]
    )
    frontend.add_extra_js_url(hass, CARD_URL)

"""Configure one thermostat and its optional existing heating interlock."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import CONF_CLIMATE, CONF_GATE, CONF_SETTER, DOMAIN


class TRVSchedulerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            entity_id = user_input[CONF_CLIMATE]
            await self.async_set_unique_id(entity_id)
            self._abort_if_unique_id_configured()
            climate = self.hass.states.get(entity_id)
            if climate is None or not entity_id.startswith("climate."):
                errors[CONF_CLIMATE] = "invalid_entity"
            for key, domain in ((CONF_GATE, "input_boolean"), (CONF_SETTER, "script")):
                if entity := user_input.get(key):
                    if not entity.startswith(f"{domain}.") or self.hass.states.get(entity) is None:
                        errors[key] = "invalid_entity"
            if not errors:
                return self.async_create_entry(title=climate.name, data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CLIMATE): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="climate")
                    ),
                    vol.Optional(CONF_GATE): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="input_boolean")
                    ),
                    vol.Optional(CONF_SETTER): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="script")
                    ),
                }
            ),
            errors=errors,
        )

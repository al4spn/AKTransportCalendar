"""Config flow for the Auckland Transport Rail Closures integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import CONF_UPDATE_HOURS, DEFAULT_UPDATE_HOURS, DOMAIN


class ATRailClosuresConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow. No credentials needed - just confirm."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title="Auckland Rail Network", data={}
            )
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return ATRailClosuresOptionsFlow()


class ATRailClosuresOptionsFlow(OptionsFlow):
    """Options: how often to re-check the AT website."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_HOURS,
                        default=self.config_entry.options.get(
                            CONF_UPDATE_HOURS, DEFAULT_UPDATE_HOURS
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
                }
            ),
        )

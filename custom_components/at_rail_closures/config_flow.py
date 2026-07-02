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
from homeassistant.helpers import selector

from .const import (
    CONF_API_KEY,
    CONF_LINES,
    CONF_UPDATE_HOURS,
    DEFAULT_UPDATE_HOURS,
    DOMAIN,
)
from .coordinator import async_validate_api_key
from .parser import RAIL_LINES

LINE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=list(RAIL_LINES),
        multiple=True,
        mode=selector.SelectSelectorMode.LIST,
    )
)

USER_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_API_KEY): str,
        vol.Optional(CONF_LINES, default=list(RAIL_LINES)): LINE_SELECTOR,
    }
)


class ATRailClosuresConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow.

    The AT API key is optional: without one the integration scrapes the
    planned closures web page only; with one it also merges in the official
    GTFS-realtime service alerts feed. The line selection controls which
    per-line sensors and calendars are created.
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = (user_input.get(CONF_API_KEY) or "").strip()
            if api_key:
                error = await async_validate_api_key(self.hass, api_key)
                if error:
                    errors["base"] = error
            if not errors:
                options: dict[str, Any] = {
                    CONF_LINES: user_input.get(CONF_LINES, list(RAIL_LINES)),
                }
                if api_key:
                    options[CONF_API_KEY] = api_key
                return self.async_create_entry(
                    title="Auckland Rail Network", data={}, options=options
                )

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return ATRailClosuresOptionsFlow()


class ATRailClosuresOptionsFlow(OptionsFlow):
    """Options: update interval, AT API key, and which lines to track."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = (user_input.get(CONF_API_KEY) or "").strip()
            if api_key:
                error = await async_validate_api_key(self.hass, api_key)
                if error:
                    errors["base"] = error
            if not errors:
                options: dict[str, Any] = {
                    CONF_UPDATE_HOURS: user_input[CONF_UPDATE_HOURS],
                    CONF_LINES: user_input.get(CONF_LINES, []),
                }
                if api_key:
                    options[CONF_API_KEY] = api_key
                return self.async_create_entry(data=options)

        current = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_UPDATE_HOURS,
                    default=current.get(CONF_UPDATE_HOURS, DEFAULT_UPDATE_HOURS),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
                vol.Optional(
                    CONF_API_KEY,
                    description={
                        "suggested_value": current.get(CONF_API_KEY, "")
                    },
                ): str,
                vol.Optional(
                    CONF_LINES,
                    default=current.get(CONF_LINES, list(RAIL_LINES)),
                ): LINE_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )

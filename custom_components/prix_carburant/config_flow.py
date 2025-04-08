"""Config flow to configure the Prix Carburant integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback

from .const import (
    CONF_DISPLAY_ENTITY_PICTURES,
    CONF_FUELS,
    CONF_MAX_KM,
    CONF_STATIONS,
    DEFAULT_MAX_KM,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FUELS,
)


def _build_schema(data: Mapping[str, Any], options: Mapping[str, Any]) -> vol.Schema:
    """Build schema according to config/options."""

    config: dict[str, Any] = dict(data) | dict(options)

    schema = {
        vol.Required(
            CONF_SCAN_INTERVAL,
            default=config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        ): int,
        vol.Required(
            CONF_DISPLAY_ENTITY_PICTURES,
            default=config.get(CONF_DISPLAY_ENTITY_PICTURES, True),
        ): bool,
    }
    if CONF_STATIONS not in config:
        schema.update(
            {
                vol.Required(
                    CONF_MAX_KM, default=config.get(CONF_MAX_KM, DEFAULT_MAX_KM)
                ): int
            }
        )
    for fuel in FUELS:
        fuel_key = f"{CONF_FUELS}_{fuel}"
        schema.update(
            {
                vol.Required(
                    fuel_key,
                    default=config.get(fuel_key, True),
                ): bool
            }
        )
    return vol.Schema(schema)


class PrixCarburantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Prix Carburant."""

    VERSION = 1

    async def async_step_import(self, import_info) -> ConfigFlowResult:
        """Import a config entry from YAML config."""
        entry = await self.async_set_unique_id(DOMAIN)

        if entry:
            self.hass.config_entries.async_update_entry(entry, data=import_info)
            self._abort_if_unique_id_configured()

        return self.async_create_entry(title=DEFAULT_NAME, data=import_info)

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Get configuration from the user."""
        errors: dict[str, str] = {}
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=_build_schema({}, {}), errors=errors
            )

        entry = await self.async_set_unique_id(DOMAIN)

        if entry:
            self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=DEFAULT_NAME,
            data=user_input,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Define the config flow to handle options."""
        return PrixCarburantOptionsFlowHandler(config_entry)


class PrixCarburantOptionsFlowHandler(OptionsFlow):
    """Handle a PrixCarburant options flow."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.hass.config_entries.async_forward_entry_setup()

    async def async_step_init(self, user_input) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.config_entry, options=user_input
            )
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self.config_entry.entry_id)
            )
            return self.async_create_entry(
                title=DEFAULT_NAME,
                data=user_input,
            )

        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(
                self.config_entry.data, self.config_entry.options
            ),
            errors=errors,
        )

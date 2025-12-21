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
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_SSL_CHECK,
    CONF_DISPLAY_ENTITY_PICTURES,
    CONF_FUELS,
    CONF_MANUAL_STATIONS,
    CONF_MAX_KM,
    CONF_STATIONS,
    DEFAULT_MAX_KM,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FUELS,
)
from .tools import PrixCarburantTool


def _build_schema(data: Mapping[str, Any], options: Mapping[str, Any]) -> vol.Schema:
    """Build schema according to config/options."""

    config: dict[str, Any] = dict(data) | dict(options)

    # For initial setup, only show max distance and fuel selection
    schema = {
        vol.Required(CONF_MAX_KM, default=config.get(CONF_MAX_KM, DEFAULT_MAX_KM)): int
    }

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
        return PrixCarburantOptionsFlowHandler()


class PrixCarburantOptionsFlowHandler(OptionsFlow):
    """Handle a PrixCarburant options flow."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self._stations_to_remove: list[str] = []

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        """Manage the options - show main menu."""
        # Check if configured via YAML
        if CONF_STATIONS in self.config_entry.data:
            return self.async_abort(reason="yaml_configuration")

        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "general_options",
                "fuels_select",
                "manage_stations",
                "add_station",
            ],
        )

    async def async_step_general_options(self, user_input=None) -> ConfigFlowResult:
        """Handle general options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Merge with existing options
            new_options = dict(self.config_entry.options)
            new_options.update(user_input)

            self.hass.config_entries.async_update_entry(
                self.config_entry, options=new_options
            )
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self.config_entry.entry_id)
            )
            return self.async_create_entry(title="", data={})

        config = dict(self.config_entry.data) | dict(self.config_entry.options)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): int,
                vol.Required(
                    CONF_API_SSL_CHECK,
                    default=config.get(CONF_API_SSL_CHECK, True),
                ): bool,
                vol.Required(
                    CONF_DISPLAY_ENTITY_PICTURES,
                    default=config.get(CONF_DISPLAY_ENTITY_PICTURES, True),
                ): bool,
                vol.Required(
                    CONF_MAX_KM,
                    default=config.get(CONF_MAX_KM, DEFAULT_MAX_KM),
                ): int,
            }
        )

        return self.async_show_form(
            step_id="general_options",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_fuels_select(self, user_input=None) -> ConfigFlowResult:
        """Handle fuels selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Merge with existing options
            new_options = dict(self.config_entry.options)
            new_options.update(user_input)

            self.hass.config_entries.async_update_entry(
                self.config_entry, options=new_options
            )
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self.config_entry.entry_id)
            )
            return self.async_create_entry(title="", data={})

        config = dict(self.config_entry.data) | dict(self.config_entry.options)

        schema = {}
        for fuel in FUELS:
            fuel_key = f"{CONF_FUELS}_{fuel}"
            schema[
                vol.Required(
                    fuel_key,
                    default=config.get(fuel_key, True),
                )
            ] = bool

        return self.async_show_form(
            step_id="fuels_select",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_manage_stations(self, user_input=None) -> ConfigFlowResult:
        """Handle station management."""
        errors: dict[str, str] = {}

        if user_input is not None:
            stations_to_remove = user_input.get("stations_to_remove", [])

            if stations_to_remove:
                # Get current manual stations
                manual_stations = list(
                    self.config_entry.options.get(CONF_MANUAL_STATIONS, [])
                )

                # Remove selected stations from manual list
                for station_id in stations_to_remove:
                    if int(station_id) in manual_stations:
                        manual_stations.remove(int(station_id))

                # Update options
                new_options = dict(self.config_entry.options)
                new_options[CONF_MANUAL_STATIONS] = manual_stations

                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=new_options
                )
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self.config_entry.entry_id)
                )

            return self.async_create_entry(title="", data={})

        # Get all stations from coordinator
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]["coordinator"]
        stations = coordinator.data

        if not stations:
            return self.async_abort(reason="no_stations")

        # Get manual stations list
        manual_stations = self.config_entry.options.get(CONF_MANUAL_STATIONS, [])

        # Build station list with type indicator
        station_options = {}
        for station_id, station_data in stations.items():
            station_type = "manual" if int(station_id) in manual_stations else "auto"
            station_name = station_data.get("name", f"Station {station_id}")
            station_options[station_id] = f"{station_name} ({station_type})"

        schema = vol.Schema(
            {
                vol.Optional("stations_to_remove", default=[]): vol.All(
                    [vol.In(station_options.keys())],
                ),
            }
        )

        return self.async_show_form(
            step_id="manage_stations",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "stations": "\n".join(
                    [f"- {name}" for name in station_options.values()]
                )
            },
        )

    async def async_step_add_station(self, user_input=None) -> ConfigFlowResult:
        """Handle adding a station manually."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station_id_str = user_input.get("station_id", "").strip()

            # Validate station ID
            try:
                station_id = int(station_id_str)
            except ValueError:
                errors["station_id"] = "invalid_station_id"
            else:
                # Check if already exists in manual stations
                manual_stations = list(
                    self.config_entry.options.get(CONF_MANUAL_STATIONS, [])
                )

                if station_id in manual_stations:
                    errors["station_id"] = "station_already_exists"
                else:
                    # Check if station exists in coordinator (auto-discovered)
                    coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id][
                        "coordinator"
                    ]
                    if str(station_id) in coordinator.data:
                        errors["station_id"] = "station_already_exists"
                    else:
                        # Validate station exists in API
                        is_valid, error_key = await self._validate_station_id(
                            station_id
                        )

                        if not is_valid:
                            errors["station_id"] = error_key
                        else:
                            # Add to manual stations
                            manual_stations.append(station_id)

                            new_options = dict(self.config_entry.options)
                            new_options[CONF_MANUAL_STATIONS] = manual_stations

                            self.hass.config_entries.async_update_entry(
                                self.config_entry, options=new_options
                            )
                            self.hass.async_create_task(
                                self.hass.config_entries.async_reload(
                                    self.config_entry.entry_id
                                )
                            )

                            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required("station_id"): str,
            }
        )

        return self.async_show_form(
            step_id="add_station",
            data_schema=schema,
            errors=errors,
        )

    async def _validate_station_id(self, station_id: int) -> tuple[bool, str]:
        """Validate station ID by checking API."""
        try:
            websession = async_get_clientsession(self.hass)
            tool = await self.hass.async_add_executor_job(
                PrixCarburantTool,
                self.hass.config.time_zone,
                60,
                True,
                websession,
            )

            # Try to fetch station from API
            response = await tool._request_api(
                {
                    "select": "id",
                    "where": f"id={station_id}",
                    "limit": 1,
                }
            )

            if response["total_count"] != 1:
                return False, "station_not_found"

            return True, ""

        except Exception:
            return False, "station_not_found"

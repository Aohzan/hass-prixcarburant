"""Config flow to configure the Prix Carburant integration."""

from collections.abc import Mapping
from typing import Any

from aiohttp import ClientError
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import ATTR_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_SSL_CHECK,
    CONF_DISPLAY_ENTITY_PICTURES,
    CONF_FUELS,
    CONF_MANUAL_STATIONS,
    CONF_MAX_KM,
    DEFAULT_MAX_KM,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FUELS,
)
from .coordinator import (
    PrixCarburantConfigEntry,
    convert_yaml_config,
    get_entry_config,
)
from .tools import (
    PrixCarburantTool,
    PrixCarburantToolCannotConnectError,
    PrixCarburantToolRateLimitError,
    PrixCarburantToolRequestError,
)


def _build_schema(data: Mapping[str, Any], options: Mapping[str, Any]) -> vol.Schema:
    """Build schema according to config/options."""
    config: dict[str, Any] = dict(data) | dict(options)

    # For initial setup, only show max distance and fuel selection
    schema = {
        vol.Required(
            CONF_MAX_KM, default=config.get(CONF_MAX_KM, DEFAULT_MAX_KM)
        ): vol.All(int, vol.Range(min=0))
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
    MINOR_VERSION = 3

    async def async_step_import(self, import_info: dict[str, Any]) -> ConfigFlowResult:
        """Import the YAML configuration once, its stations become manual stations."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        data, options = convert_yaml_config(import_info, {})
        return self.async_create_entry(title=DEFAULT_NAME, data=data, options=options)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
    def async_get_options_flow(
        config_entry: PrixCarburantConfigEntry,
    ) -> PrixCarburantOptionsFlowHandler:
        """Define the config flow to handle options."""
        return PrixCarburantOptionsFlowHandler()


class PrixCarburantOptionsFlowHandler(OptionsFlowWithReload):
    """Handle a PrixCarburant options flow."""

    def _get_manual_stations(self) -> list[int]:
        """Get manual stations list from config entry data/options."""
        return list(get_entry_config(self.config_entry).get(CONF_MANUAL_STATIONS) or [])

    def _get_loaded_stations(self) -> dict:
        """Get the stations of the coordinator, empty if the entry isn't loaded."""
        entry: PrixCarburantConfigEntry = self.config_entry
        if entry.state is not ConfigEntryState.LOADED:
            return {}
        return entry.runtime_data.data or {}

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Manage the options - show main menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "general_options",
                "fuels_select",
                "add_station",
                "delete_stations",
            ],
        )

    async def async_step_general_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle general options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Merge with existing options
            return self.async_create_entry(data=self.config_entry.options | user_input)

        config = get_entry_config(self.config_entry)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
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
                ): vol.All(int, vol.Range(min=0)),
            }
        )

        return self.async_show_form(
            step_id="general_options",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_fuels_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle fuels selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Merge with existing options
            return self.async_create_entry(data=self.config_entry.options | user_input)

        config = get_entry_config(self.config_entry)

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

    async def async_step_add_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
                manual_stations = self._get_manual_stations()

                if station_id in manual_stations:
                    errors["station_id"] = "station_already_exists"
                else:
                    # Check if station exists in coordinator (auto-discovered)
                    if station_id in self._get_loaded_stations():
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

                            return self.async_create_entry(
                                data=self.config_entry.options
                                | {CONF_MANUAL_STATIONS: manual_stations}
                            )

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

    def _remove_station_entities(
        self, entity_reg: er.EntityRegistry, station_id: str
    ) -> None:
        """Remove all entities for a station."""
        entities = er.async_entries_for_config_entry(
            entity_reg, self.config_entry.entry_id
        )
        for entity in entities:
            if entity.unique_id.startswith(f"{DOMAIN}_{station_id}_"):
                entity_reg.async_remove(entity.entity_id)

    def _remove_station_device(
        self, device_reg: dr.DeviceRegistry, station_id: str
    ) -> None:
        """Remove device for a station."""
        for device in dr.async_entries_for_config_entry(
            device_reg, self.config_entry.entry_id
        ):
            for identifier in device.identifiers:
                if identifier[0] == DOMAIN and str(identifier[1]) == station_id:
                    device_reg.async_remove_device(device.id)
                    return

    async def async_step_delete_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle station deletion."""
        errors: dict[str, str] = {}

        if user_input is not None:
            stations_to_remove = user_input.get("stations_to_remove", [])

            if stations_to_remove:
                # Get registries
                entity_reg = er.async_get(self.hass)
                device_reg = dr.async_get(self.hass)

                # Remove entities and devices for each deleted station
                for station_id in stations_to_remove:
                    self._remove_station_entities(entity_reg, station_id)
                    self._remove_station_device(device_reg, station_id)

                manual_stations = self._get_manual_stations()

                # Remove selected stations from manual list
                for station_id in stations_to_remove:
                    station_id_int = int(station_id)
                    if station_id_int in manual_stations:
                        manual_stations.remove(station_id_int)

                return self.async_create_entry(
                    data=self.config_entry.options
                    | {CONF_MANUAL_STATIONS: manual_stations}
                )

            return self.async_create_entry(data=dict(self.config_entry.options))

        manual_stations = self._get_manual_stations()

        # If no manual stations, abort
        if not manual_stations:
            return self.async_abort(reason="no_stations")

        # Get all stations from coordinator
        stations = self._get_loaded_stations()

        # Build station list from manual stations, including those unknown to the API
        # (closed station or wrong ID) so they can still be removed
        station_options = {}
        for station_id_int in manual_stations:
            station_data = stations.get(station_id_int)
            if station_data is None:
                station_name = f"Station {station_id_int} (not found in API)"
            elif station_data.get(ATTR_NAME, "undefined") != "undefined":
                station_name = station_data[ATTR_NAME]
            else:
                station_name = f"Station {station_id_int}"
            # Use string keys for cv.multi_select
            station_options[str(station_id_int)] = station_name

        schema = vol.Schema(
            {
                vol.Optional("stations_to_remove", default=[]): cv.multi_select(
                    station_options
                ),
            }
        )

        return self.async_show_form(
            step_id="delete_stations",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "stations": "\n".join(
                    [f"- {name}" for name in station_options.values()]
                )
            },
        )

    async def _validate_station_id(self, station_id: int) -> tuple[bool, str]:
        """Validate station ID by checking API."""
        try:
            websession = async_get_clientsession(self.hass)
            tool = PrixCarburantTool(
                self.hass.config.time_zone,
                60,
                api_ssl_check=get_entry_config(self.config_entry).get(
                    CONF_API_SSL_CHECK, True
                ),
                session=websession,
            )

            response = await tool.request_api(
                {
                    "select": "id",
                    "where": f"id={station_id}",
                    "limit": 1,
                }
            )
        except ClientError, PrixCarburantToolCannotConnectError:
            return False, "cannot_connect"
        except PrixCarburantToolRateLimitError:
            return False, "rate_limit"
        except PrixCarburantToolRequestError:
            return False, "station_not_found"
        else:
            if response["total_count"] == 1:
                return True, ""
            return False, "station_not_found"

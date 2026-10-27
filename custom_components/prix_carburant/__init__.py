"""Prix Carburant integration."""

import logging

import probatio

from homeassistant.const import ATTR_ENTITY_ID, ATTR_LATITUDE, ATTR_LONGITUDE, ATTR_NAME
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_ADDRESS,
    ATTR_CITY,
    ATTR_DISTANCE,
    ATTR_POSTAL_CODE,
    ATTR_PRICE,
    CONF_STATIONS,
    DOMAIN,
    FUELS,
    PLATFORMS,
)
from .coordinator import (
    PrixCarburantConfigEntry,
    PrixCarburantCoordinator,
    convert_yaml_config,
)
from .tools import PrixCarburantToolCannotConnectError, PrixCarburantToolRequestError

_LOGGER = logging.getLogger(__name__)

# The YAML configuration is a sensor platform, imported as a config entry
CONFIG_SCHEMA = cv.platform_only_config_schema(DOMAIN)

SERVICE_FIND_NEAREST_STATIONS = "find_nearest_stations"
ATTR_FUEL = "fuel"
_FUELS_BY_LOWER_NAME = {fuel.lower(): fuel for fuel in FUELS}


def _fuel_case(value: str) -> str:
    """Return the name of the fuel whatever its case, like the previous versions."""
    return _FUELS_BY_LOWER_NAME.get(value.lower(), value)


SERVICE_FIND_NEAREST_STATIONS_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_ENTITY_ID): cv.entity_id,
        probatio.Required(ATTR_FUEL): probatio.All(
            cv.string, _fuel_case, probatio.In(FUELS)
        ),
        probatio.Required(ATTR_DISTANCE): cv.positive_int,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Prix Carburant services."""

    async def find_nearest_stations(call: ServiceCall) -> ServiceResponse:
        """Search in the range and return the matching items."""
        entries: list[PrixCarburantConfigEntry] = (
            hass.config_entries.async_loaded_entries(DOMAIN)
        )
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="not_loaded"
            )
        entity_id = call.data[ATTR_ENTITY_ID]
        if (state := hass.states.get(entity_id)) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entity_not_found",
                translation_placeholders={"entity_id": entity_id},
            )
        if ATTR_LONGITUDE not in state.attributes or (
            ATTR_LATITUDE not in state.attributes
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_coordinates",
                translation_placeholders={"entity_id": entity_id},
            )
        try:
            stations = await entries[0].runtime_data.tool.find_nearest_station(
                longitude=float(state.attributes[ATTR_LONGITUDE]),
                latitude=float(state.attributes[ATTR_LATITUDE]),
                fuel=call.data[ATTR_FUEL],
                distance=call.data[ATTR_DISTANCE],
            )
        except (
            PrixCarburantToolCannotConnectError,
            PrixCarburantToolRequestError,
        ) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        return {
            "stations": [
                {
                    "name": station_data[ATTR_NAME],
                    "price": station_data.get(ATTR_PRICE),
                    "address": f"{station_data[ATTR_ADDRESS]}, {station_data[ATTR_POSTAL_CODE]} {station_data[ATTR_CITY]}",
                    "latitude": station_data[ATTR_LATITUDE],
                    "longitude": station_data[ATTR_LONGITUDE],
                }
                for station_data in stations.values()
            ],
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_FIND_NEAREST_STATIONS,
        find_nearest_stations,
        schema=SERVICE_FIND_NEAREST_STATIONS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_migrate_entry(
    hass: HomeAssistant, entry: PrixCarburantConfigEntry
) -> bool:
    """Migrate an old config entry."""
    if entry.version > 1:
        # Downgraded from a future version
        return False

    if entry.minor_version < 2:
        # The unique ID of the refresh button wasn't scoped to the entry
        @callback
        def migrate_unique_id(entity_entry: er.RegistryEntry) -> dict | None:
            if entity_entry.unique_id == f"{DOMAIN}_refresh_button":
                return {"new_unique_id": f"{entry.entry_id}_refresh"}
            return None

        await er.async_migrate_entries(hass, entry.entry_id, migrate_unique_id)
        hass.config_entries.async_update_entry(entry, minor_version=2)

    if entry.minor_version < 3:
        # The stations of an entry imported from YAML become manual stations
        if CONF_STATIONS in entry.data:
            data, options = convert_yaml_config(entry.data, entry.options)
            hass.config_entries.async_update_entry(
                entry, data=data, options=options, minor_version=3
            )
        else:
            hass.config_entries.async_update_entry(entry, minor_version=3)

    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: PrixCarburantConfigEntry
) -> bool:
    """Set up from a config entry."""
    coordinator = PrixCarburantCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: PrixCarburantConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

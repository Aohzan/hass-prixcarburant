"""Prix Carburant integration."""

import logging

import probatio

from homeassistant.const import ATTR_ENTITY_ID, ATTR_LATITUDE, ATTR_LONGITUDE, ATTR_NAME
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_ADDRESS,
    ATTR_BRAND,
    ATTR_CITY,
    ATTR_DISTANCE,
    ATTR_POSTAL_CODE,
    ATTR_PRICE,
    ATTR_UPDATED_DATE,
    CONF_STATIONS,
    DOMAIN,
    FUELS,
    PLATFORMS,
    SORT_PRICE,
    SORTS,
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
ATTR_LIMIT = "limit"
ATTR_SORT = "sort"
# Maximum number of records of a request to the API
MAX_LIMIT = 100
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
        probatio.Optional(ATTR_LIMIT, default=10): probatio.All(
            probatio.Coerce(int), probatio.Range(min=1, max=MAX_LIMIT)
        ),
        probatio.Optional(ATTR_SORT, default=SORT_PRICE): probatio.In(SORTS),
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
                limit=call.data[ATTR_LIMIT],
                sort=call.data[ATTR_SORT],
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
                    "station_id": station_id,
                    "name": station_data[ATTR_NAME],
                    "brand": station_data[ATTR_BRAND],
                    "price": station_data.get(ATTR_PRICE),
                    "updated_date": station_data.get(ATTR_UPDATED_DATE),
                    "distance": station_data[ATTR_DISTANCE],
                    "address": f"{station_data[ATTR_ADDRESS]}, {station_data[ATTR_POSTAL_CODE]} {station_data[ATTR_CITY]}",
                    "latitude": station_data[ATTR_LATITUDE],
                    "longitude": station_data[ATTR_LONGITUDE],
                }
                for station_id, station_data in stations.items()
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
        # Entries of the versions before 2026.10

        # The unique ID of the refresh button wasn't scoped to the entry. A
        # failed migration may have kept the migrated button, then a downgrade
        # registered a new button with the old unique ID: it is a duplicate.
        entity_registry = er.async_get(hass)
        refresh_unique_id = f"{entry.entry_id}_refresh"
        for entity_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        ):
            if entity_entry.unique_id != f"{DOMAIN}_refresh_button":
                continue
            if entity_registry.async_get_entity_id(
                entity_entry.domain, DOMAIN, refresh_unique_id
            ):
                entity_registry.async_remove(entity_entry.entity_id)
            else:
                entity_registry.async_update_entity(
                    entity_entry.entity_id, new_unique_id=refresh_unique_id
                )

        # The station devices were registered with an integer identifier, the
        # device registry expects strings
        device_registry = dr.async_get(hass)
        for device in dr.async_entries_for_config_entry(
            device_registry, entry.entry_id
        ):
            identifiers = {
                (domain, str(identifier)) if domain == DOMAIN else (domain, identifier)
                for domain, identifier in device.identifiers
            }
            if identifiers == device.identifiers:
                continue
            # A device of an older version may already have the string
            # identifier: its entities move to this device before its removal
            for duplicate in device_registry.async_get_devices(
                identifiers=identifiers - device.identifiers,
                config_entry_id=entry.entry_id,
            ):
                for entity_entry in er.async_entries_for_device(
                    entity_registry, duplicate.id, include_disabled_entities=True
                ):
                    entity_registry.async_update_entity(
                        entity_entry.entity_id, device_id=device.id
                    )
                device_registry.async_remove_device(duplicate.id)
            device_registry.async_update_device(device.id, new_identifiers=identifiers)

        # The stations of an entry imported from YAML become manual stations
        data, options = entry.data, entry.options
        if CONF_STATIONS in data:
            data, options = convert_yaml_config(data, options)
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, minor_version=2
        )

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
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
    return True

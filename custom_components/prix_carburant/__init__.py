"""Prix Carburant integration."""

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_NAME,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ATTR_ADDRESS,
    ATTR_CITY,
    ATTR_POSTAL_CODE,
    ATTR_PRICE,
    CONF_API_SSL_CHECK,
    CONF_DISPLAY_ENTITY_PICTURES,
    CONF_MAX_KM,
    CONF_STATIONS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .tools import PrixCarburantTool

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    config: dict = entry.data | entry.options

    websession = async_get_clientsession(hass)

    tool = await hass.async_add_executor_job(
        PrixCarburantTool,
        hass.config.time_zone,
        60,
        config.get(CONF_API_SSL_CHECK, True),
        websession,
    )

    display_entity_pictures = config.get(CONF_DISPLAY_ENTITY_PICTURES, True)
    update_interval = int(config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    # yaml configuration
    if CONF_STATIONS in config:
        _LOGGER.info("Init stations data from yaml list")
        await tool.init_stations_from_list(
            stations_ids=config[CONF_STATIONS],
            latitude=hass.config.latitude,
            longitude=hass.config.longitude,
        )
    # ui configuration
    else:
        _LOGGER.info("Init stations list near Home-Assistant location")
        await tool.init_stations_from_location(
            latitude=hass.config.latitude,
            longitude=hass.config.longitude,
            distance=config[CONF_MAX_KM],
        )
        _LOGGER.info("%s stations found", str(len(tool.stations)))

    async def async_update_data():
        """Fetch data from API."""
        _LOGGER.info("Update stations prices")
        await tool.update_stations_prices()
        return tool.stations

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(hours=update_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "tool": tool,
        "coordinator": coordinator,
        "options": {
            CONF_DISPLAY_ENTITY_PICTURES: display_entity_pictures,
        },
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def find_nearest_stations(call: ServiceCall) -> ServiceResponse:
        """Search in the range and return the matching items."""
        fuel = call.data["fuel"]
        distance = call.data["distance"]
        entity_id = call.data["entity_id"]
        entity = hass.states.get(entity_id)
        if not entity:
            raise HomeAssistantError("The entity specified was not found")
        if "longitude" not in entity.attributes and "latitude" not in entity.attributes:
            raise HomeAssistantError(
                f"No coordinate attributes found for the entity {entity_id}"
            )
        stations = await tool.find_nearest_station(
            longitude=float(entity.attributes["longitude"]),
            latitude=float(entity.attributes["latitude"]),
            fuel=fuel,
            distance=distance,
        )
        return {
            "stations": [
                {
                    "name": station_data[ATTR_NAME],
                    "price": station_data.get(ATTR_PRICE),
                    "address": f"{station_data[ATTR_ADDRESS]}, {station_data[ATTR_POSTAL_CODE]} {station_data[ATTR_CITY]}",
                    "latitude": f"{station_data[ATTR_LATITUDE]}",
                    "longitude": f"{station_data[ATTR_LONGITUDE]}",
                }
                for station_data in stations.values()
            ],
        }

    hass.services.async_register(
        DOMAIN,
        "find_nearest_stations",
        find_nearest_stations,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

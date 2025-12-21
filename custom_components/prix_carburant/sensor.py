"""Prix Carburant sensor platform."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA_BASE,
    RestoreSensor,
    SensorDeviceClass,
)
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE, ATTR_NAME, CURRENCY_EURO

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ADDRESS,
    ATTR_BRAND,
    ATTR_CITY,
    ATTR_DAYS_SINCE_LAST_UPDATE,
    ATTR_DISTANCE,
    ATTR_FUEL_TYPE,
    ATTR_FUELS,
    ATTR_POSTAL_CODE,
    ATTR_PRICE,
    ATTR_UPDATED_DATE,
    CONF_DISPLAY_ENTITY_PICTURES,
    CONF_FUELS,
    CONF_STATIONS,
    DOMAIN,
    FUELS,
)
from .tools import PrixCarburantTool, get_entity_picture, normalize_string

_LOGGER = logging.getLogger(__name__)

# Validation of the yaml configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA_BASE.extend(
    {
        vol.Optional(CONF_STATIONS, default=[]): cv.ensure_list,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,  # noqa: ARG001
    discovery_info: DiscoveryInfoType | None = None,  # noqa: ARG001
) -> None:
    """Set up the Prix Carburant sensor."""
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=config,
        )
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the platform from config_entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    config = entry.data
    options = entry.options

    tool: PrixCarburantTool = data["tool"]

    enabled_fuels = {}
    for fuel in FUELS:
        fuel_key = f"{CONF_FUELS}_{fuel}"
        enabled_fuels[fuel] = options.get(fuel_key, config.get(fuel_key, True))

    entities = []
    for station_id, station_data in tool.stations.items():
        entities.extend(
            [
                PrixCarburant(station_id, station_data, f, data)
                for f in FUELS
                if f in station_data[ATTR_FUELS] and enabled_fuels[f] is True
            ]
        )

    async_add_entities(entities, update_before_add=True)


class PrixCarburant(CoordinatorEntity, RestoreSensor):
    """Representation of a Sensor."""

    _attr_icon = "mdi:gas-station"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = CURRENCY_EURO

    def __init__(
        self, station_id: str, station_info: dict, fuel: str, entry_data: dict
    ) -> None:
        """Initialize the sensor."""
        super().__init__(entry_data["coordinator"])
        self.station_id = station_id
        self.station_info = station_info
        self.fuel = fuel

        self._last_update = None
        self._attr_unique_id = "_".join([DOMAIN, str(self.station_id), self.fuel])
        if self.station_info[ATTR_NAME] != "undefined":
            station_name = f"Station {self.station_info[ATTR_NAME]}"
        else:
            station_name = f"Station {self.station_id}"
        self._attr_name = f"{station_name} {self.fuel}"

        if entry_data["options"][CONF_DISPLAY_ENTITY_PICTURES] is True:
            self._attr_entity_picture = get_entity_picture(
                self.station_info[ATTR_BRAND]
            )

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.station_id)},
            manufacturer=station_info.get(ATTR_BRAND, "Station"),
            model=self.station_id,
            name=station_name,
            configuration_url="https://www.prix-carburants.gouv.fr/",
        )
        self._attr_extra_state_attributes = {
            ATTR_NAME: normalize_string(self.station_info[ATTR_NAME]),
            ATTR_BRAND: self.station_info[ATTR_BRAND],
            ATTR_ADDRESS: normalize_string(self.station_info[ATTR_ADDRESS]),
            ATTR_POSTAL_CODE: self.station_info[ATTR_POSTAL_CODE],
            ATTR_CITY: normalize_string(self.station_info[ATTR_CITY]),
            ATTR_LATITUDE: self.station_info[ATTR_LATITUDE],
            ATTR_LONGITUDE: self.station_info[ATTR_LONGITUDE],
            ATTR_DISTANCE: self.station_info[ATTR_DISTANCE],
            ATTR_UPDATED_DATE: None,
            ATTR_DAYS_SINCE_LAST_UPDATE: None,
            ATTR_FUEL_TYPE: self.fuel,
        }

    @property
    def native_value(self) -> float | None:
        """Return the current price."""
        fuel = self.coordinator.data[self.station_id][ATTR_FUELS].get(self.fuel)
        if fuel:
            # Update date in attributes
            self._attr_extra_state_attributes[ATTR_UPDATED_DATE] = fuel[
                ATTR_UPDATED_DATE
            ]
            try:
                delay = datetime.now(tz=UTC) - datetime.strptime(
                    fuel[ATTR_UPDATED_DATE], "%Y-%m-%dT%H:%M:%S%z"
                )
                self._attr_extra_state_attributes[ATTR_DAYS_SINCE_LAST_UPDATE] = (
                    delay.days
                )
            except ValueError as err:
                _LOGGER.warning(
                    "Cannot calculate days for %s since last update: %s",
                    self._attr_name,
                    err,
                )
            return float(fuel[ATTR_PRICE])
        return None

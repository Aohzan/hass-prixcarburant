"""Prix Carburant sensor platform."""

from datetime import UTC, datetime
import logging

import probatio

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA_BASE,
    RestoreSensor,
    SensorStateClass,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE, ATTR_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
    AddEntitiesCallback,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
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
    ATTR_SHORTAGE_SINCE,
    ATTR_UPDATED_DATE,
    CONF_DISPLAY_ENTITY_PICTURES,
    CONF_FUELS,
    CONF_STATIONS,
    DOMAIN,
    FUELS,
)
from .coordinator import PrixCarburantConfigEntry, PrixCarburantCoordinator
from .tools import StationData, get_entity_picture, normalize_string

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

# Validation of the yaml configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA_BASE.extend(
    {
        probatio.Optional(CONF_STATIONS, default=[]): cv.ensure_list,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Import the YAML configuration as a config entry."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        "deprecated_yaml",
        is_fixable=False,
        issue_domain=DOMAIN,
        severity=ir.IssueSeverity.WARNING,
        translation_key="deprecated_yaml",
        learn_more_url="https://github.com/Aohzan/hass-prixcarburant/blob/master/README.fr.md",
    )
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=config,
        )
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrixCarburantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the platform from config_entry."""
    coordinator = entry.runtime_data
    enabled_fuels = {
        fuel: coordinator.config.get(f"{CONF_FUELS}_{fuel}", True) for fuel in FUELS
    }

    async_add_entities(
        PrixCarburantSensor(coordinator, station_id, fuel)
        for station_id, station_data in coordinator.data.items()
        for fuel in FUELS
        if fuel in station_data[ATTR_FUELS] and enabled_fuels[fuel] is True
    )


def _station_name(station_id: int, station_info: StationData) -> str:
    """Return the name of the station device."""
    if station_info[ATTR_NAME] != "undefined":
        station_name = station_info[ATTR_NAME]
    elif station_info[ATTR_BRAND] and station_info[ATTR_CITY]:
        station_name = f"{station_info[ATTR_BRAND]} {station_info[ATTR_CITY]}"
    elif station_info[ATTR_BRAND]:
        station_name = f"{station_info[ATTR_BRAND]} {station_id}"
    else:
        station_name = str(station_id)

    # Add 'Station' prefix if needed
    if not station_name.lower().startswith(("station", "relais")):
        station_name = f"Station {station_name}"
    return station_name


class PrixCarburantSensor(CoordinatorEntity[PrixCarburantCoordinator], RestoreSensor):
    """Price of a fuel in a station."""

    _attr_has_entity_name = True
    _attr_translation_key = "fuel_price"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "€/l"
    _attr_suggested_display_precision = 3

    def __init__(
        self, coordinator: PrixCarburantCoordinator, station_id: int, fuel: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.station_id = station_id
        self.fuel = fuel
        station_info = coordinator.data[station_id]

        self._attr_unique_id = "_".join([DOMAIN, str(station_id), fuel])
        # The friendly name is the station name (device) followed by the fuel
        self._attr_translation_placeholders = {"fuel": fuel}

        if coordinator.config.get(CONF_DISPLAY_ENTITY_PICTURES, True) is True:
            self._attr_entity_picture = get_entity_picture(station_info[ATTR_BRAND])

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(station_id))},
            manufacturer=station_info.get(ATTR_BRAND, "Station"),
            model=str(station_id),
            name=_station_name(station_id, station_info),
            configuration_url=f"https://www.prix-carburants.gouv.fr/station/{station_id}",
        )
        self._attr_extra_state_attributes = {
            "station_id": str(station_id),
            ATTR_NAME: normalize_string(station_info[ATTR_NAME]),
            ATTR_BRAND: station_info[ATTR_BRAND],
            ATTR_ADDRESS: normalize_string(station_info[ATTR_ADDRESS]),
            ATTR_POSTAL_CODE: station_info[ATTR_POSTAL_CODE],
            ATTR_CITY: normalize_string(station_info[ATTR_CITY]),
            ATTR_LATITUDE: station_info[ATTR_LATITUDE],
            ATTR_LONGITUDE: station_info[ATTR_LONGITUDE],
            ATTR_DISTANCE: station_info[ATTR_DISTANCE],
            ATTR_UPDATED_DATE: None,
            ATTR_DAYS_SINCE_LAST_UPDATE: None,
            ATTR_FUEL_TYPE: fuel,
            ATTR_SHORTAGE_SINCE: station_info[ATTR_FUELS][fuel].get(
                ATTR_SHORTAGE_SINCE
            ),
        }
        self._update_from_data()

    async def async_added_to_hass(self) -> None:
        """Restore the last price on startup when there is no current price."""
        await super().async_added_to_hass()
        if (
            self._attr_native_value is None
            and (last_sensor_data := await self.async_get_last_sensor_data())
            is not None
        ):
            self._attr_native_value = last_sensor_data.native_value

    @callback
    def async_entity_id_changed(self, old_entity_id: str) -> None:
        """Keep the entity on an entity ID change, the price is kept."""
        super().async_entity_id_changed(old_entity_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the price and its attributes from the coordinator."""
        self._update_from_data()
        super()._handle_coordinator_update()

    def _update_from_data(self) -> None:
        """Update the price and its attributes, keeping the last price if none."""
        station = self.coordinator.data.get(self.station_id)
        if station is None or not (fuel := station[ATTR_FUELS].get(self.fuel)):
            return

        self._attr_extra_state_attributes |= {
            ATTR_UPDATED_DATE: fuel.get(ATTR_UPDATED_DATE),
            ATTR_SHORTAGE_SINCE: fuel.get(ATTR_SHORTAGE_SINCE),
        }
        if (updated_date := fuel[ATTR_UPDATED_DATE]) is not None:
            try:
                updated_dt = datetime.strptime(updated_date, "%Y-%m-%dT%H:%M:%S%z")
            except ValueError as err:
                _LOGGER.warning(
                    "Cannot calculate days for %s %s since last update: %s",
                    self.station_id,
                    self.fuel,
                    err,
                )
            else:
                today = datetime.now(tz=UTC).date()
                self._attr_extra_state_attributes[ATTR_DAYS_SINCE_LAST_UPDATE] = max(
                    0, (today - updated_dt.date()).days
                )
        if (price := fuel[ATTR_PRICE]) is not None:
            self._attr_native_value = round(float(price), 3)

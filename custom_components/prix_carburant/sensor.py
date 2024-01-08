"""Prix Carburant sensor platform."""
from __future__ import annotations

from datetime import UTC, datetime
import logging

import voluptuous as vol

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE, ATTR_NAME, CURRENCY_EURO
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.config_validation import PLATFORM_SCHEMA_BASE
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ADDRESS,
    ATTR_BRAND,
    ATTR_CITY,
    ATTR_DAYS_SINCE_LAST_UPDATE,
    ATTR_DISTANCE,
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
from .tools import PrixCarburantTool

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
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
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
        for fuel in FUELS:
            if fuel in station_data[ATTR_FUELS] and enabled_fuels[fuel] is True:
                entities.append(PrixCarburant(station_id, station_data, fuel, data))

    async_add_entities(entities, True)


class PrixCarburant(CoordinatorEntity, SensorEntity):
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
            match self.station_info[ATTR_BRAND]:
                case "Aldi":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/commons/2/2c/Aldi_Nord_201x_logo.svg"
                case "Atac":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/fr/c/c3/Logo_Atac_2015.svg"
                case "Auchan":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/commons/a/aa/Auchan-A.svg"
                case "Avia":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/commons/c/c0/AVIA_International_logo.svg"
                case "BP" | "BP Express":
                    self._attr_entity_picture = (
                        "https://upload.wikimedia.org/wikipedia/fr/3/32/B_P.svg"
                    )
                case "Bricomarché":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/commons/d/dc/BRICOMARCHE.png"
                case "Carrefour" | "Carrefour Contact" | "Carrefour Express":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/fr/3/3b/Logo_Carrefour.svg"
                case "Carrefour Market":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/commons/4/4f/Carrefour_market_logo.svg"
                case "Casino" | "Super Casino":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/commons/6/68/Logo_of_Casino_Supermarch%C3%A9s.svg"
                case "CORA":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/commons/c/ce/Cora_logo.svg"
                case "Elf":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/fr/1/17/ELF_logo_1991-2004.svg"
                case "ENI FRANCE" | "ENI":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/fr/b/b8/Eni_SpA_%28logo%29.svg"
                case "Esso" | "Esso Express":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/commons/0/0e/Esso-Logo.svg"
                case "Géant":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/commons/3/31/Hypermarche_Geant_Casino.jpg"
                case "Huit à 8":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/fr/9/98/Logo_8_%C3%80_Huit.svg"
                case "Intermarché" | "Intermarché Contact":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/fr/8/8c/Logo_Groupe_Les_Mousquetaires.svg"
                case "Leclerc":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/commons/e/ed/Logo_E.Leclerc_Sans_le_texte.svg"
                case "Leader Price" | "LEADER-PRICE":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/fr/2/2d/Logo_Leader_Price_-_2017.svg"
                case "Monoprix":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/commons/0/0a/Monoprix_logo.svg"
                case "Roady":
                    self._attr_entity_picture = (
                        "https://upload.wikimedia.org/wikipedia/fr/6/62/Roady.svg"
                    )
                case "Shell":
                    self._attr_entity_picture = (
                        "https://upload.wikimedia.org/wikipedia/fr/e/e8/Shell_logo.svg"
                    )
                case "SPAR" | "SPAR STATION":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/commons/6/69/Spar_logo_without_red_background.png"
                case "Supermarché Match" | "Supermarche Match":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/fr/a/ad/Logo_Supermarch%C3%A9_Match.svg"
                case "Système U" | "Super U" | "Station U":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/fr/1/13/U_commer%C3%A7ants_logo_2018.svg"
                case "Total" | "Total Access":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/fr/f/f7/Logo_TotalEnergies.svg"
                case "Weldom":
                    self._attr_entity_picture = "https://upload.wikimedia.org/wikipedia/commons/4/4b/Logo_weldom.png"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.station_id)},
            manufacturer=station_info.get(ATTR_BRAND, "Station"),
            model=self.station_id,
            name=station_name,
            configuration_url="https://www.prix-carburants.gouv.fr/",
        )
        self._attr_extra_state_attributes = {
            ATTR_NAME: self.station_info[ATTR_NAME],
            ATTR_BRAND: self.station_info[ATTR_BRAND],
            ATTR_ADDRESS: self.station_info[ATTR_ADDRESS],
            ATTR_POSTAL_CODE: self.station_info[ATTR_POSTAL_CODE],
            ATTR_CITY: self.station_info[ATTR_CITY],
            ATTR_LATITUDE: self.station_info[ATTR_LATITUDE],
            ATTR_LONGITUDE: self.station_info[ATTR_LONGITUDE],
            ATTR_DISTANCE: self.station_info[ATTR_DISTANCE],
            ATTR_UPDATED_DATE: None,
            ATTR_DAYS_SINCE_LAST_UPDATE: None,
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
                self._attr_extra_state_attributes[
                    ATTR_DAYS_SINCE_LAST_UPDATE
                ] = delay.days
            except ValueError as err:
                _LOGGER.warning(
                    "Cannot calculate days for %s since last update: %s",
                    self._attr_name,
                    err,
                )
            # return price
            return float(fuel[ATTR_PRICE])
        return None

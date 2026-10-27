"""Data update coordinator of the Prix Carburant integration."""

from collections.abc import Mapping
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_API_SSL_CHECK,
    CONF_DISPLAY_ENTITY_PICTURES,
    CONF_FUELS,
    CONF_MANUAL_STATIONS,
    CONF_MAX_KM,
    CONF_STATIONS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FUELS,
)
from .tools import (
    PrixCarburantTool,
    PrixCarburantToolCannotConnectError,
    PrixCarburantToolRateLimitError,
    PrixCarburantToolRequestError,
    StationData,
)

_LOGGER = logging.getLogger(__name__)

# Seconds before retrying an update failed because of a transient error, instead
# of waiting for the next update hours later with the sensors unavailable
RETRY_AFTER = 15 * 60

type PrixCarburantConfigEntry = ConfigEntry[PrixCarburantCoordinator]


def get_entry_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return the entry data overridden by the options."""
    return {**entry.data, **entry.options}


def convert_yaml_config(
    data: Mapping[str, Any], options: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert a configuration imported from YAML to the data and options of the UI.

    The stations of the YAML configuration become manual stations and the
    discovery is disabled: the entry keeps the same stations and entities.
    """
    station_ids: list[int] = list(options.get(CONF_MANUAL_STATIONS) or [])
    for station_id in data.get(CONF_STATIONS) or []:
        try:
            station_id_int = int(station_id)
        except TypeError, ValueError:
            _LOGGER.warning("Invalid station ID ignored: %s", station_id)
            continue
        if station_id_int not in station_ids:
            station_ids.append(station_id_int)

    kept_keys = (
        CONF_API_SSL_CHECK,
        CONF_DISPLAY_ENTITY_PICTURES,
        *(f"{CONF_FUELS}_{fuel}" for fuel in FUELS),
    )
    new_data = {CONF_MAX_KM: 0} | {key: data[key] for key in kept_keys if key in data}
    new_options = {
        key: value for key, value in options.items() if key != CONF_MAX_KM
    } | {CONF_MANUAL_STATIONS: station_ids}
    return new_data, new_options


class PrixCarburantCoordinator(DataUpdateCoordinator[dict[int, StationData]]):
    """Fetch the fuel prices of the stations."""

    config_entry: PrixCarburantConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PrixCarburantConfigEntry) -> None:
        """Initialize the coordinator."""
        self.config = get_entry_config(entry)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            # An interval of 0, saved by the previous versions, would poll continuously
            update_interval=timedelta(
                hours=max(
                    1, int(self.config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
                )
            ),
        )
        self.tool = PrixCarburantTool(
            hass.config.time_zone,
            60,
            self.config.get(CONF_API_SSL_CHECK, True),
            session=async_get_clientsession(hass),
        )

    async def _async_setup(self) -> None:
        """Load the station names and find the stations."""
        await self.tool.async_initialize()
        latitude = self.hass.config.latitude
        longitude = self.hass.config.longitude
        try:
            # A maximum distance of 0 disables the discovery
            if max_km := self.config[CONF_MAX_KM]:
                _LOGGER.info(
                    "Init stations list near Home-Assistant location (%s km around %s %s)",
                    max_km,
                    latitude,
                    longitude,
                )
                await self.tool.init_stations_from_location(
                    latitude=latitude, longitude=longitude, distance=max_km
                )
                _LOGGER.info("%s stations found", len(self.tool.stations))

            if manual_stations := self.config.get(CONF_MANUAL_STATIONS):
                _LOGGER.info("Adding %s manual stations", len(manual_stations))
                await self.tool.add_manual_stations(
                    manual_station_ids=manual_stations,
                    latitude=latitude,
                    longitude=longitude,
                )
        except (
            PrixCarburantToolCannotConnectError,
            PrixCarburantToolRequestError,
        ) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err

    async def _async_update_data(self) -> dict[int, StationData]:
        """Fetch the prices of the stations."""
        _LOGGER.info("Update stations prices")
        try:
            # A partial update would create no entity for the stations without
            # price at the first update
            await self.tool.update_stations_prices(allow_partial=self.data is not None)
        except PrixCarburantToolRateLimitError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="rate_limit",
                retry_after=RETRY_AFTER if err.retry_after is None else err.retry_after,
            ) from err
        except PrixCarburantToolCannotConnectError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
                retry_after=RETRY_AFTER,
            ) from err
        except PrixCarburantToolRequestError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return self.tool.stations

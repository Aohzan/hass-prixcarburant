"""Data update coordinator of the Prix Carburant integration."""

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
    CONF_MANUAL_STATIONS,
    CONF_MAX_KM,
    CONF_STATIONS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .tools import (
    PrixCarburantTool,
    PrixCarburantToolCannotConnectError,
    PrixCarburantToolRateLimitError,
    PrixCarburantToolRequestError,
)

_LOGGER = logging.getLogger(__name__)

type PrixCarburantConfigEntry = ConfigEntry[PrixCarburantCoordinator]


def get_entry_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return the entry data overridden by the options."""
    return {**entry.data, **entry.options}


class PrixCarburantCoordinator(DataUpdateCoordinator[dict[int, dict[str, Any]]]):
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
            update_interval=timedelta(
                hours=int(self.config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            ),
        )
        self.tool = PrixCarburantTool(
            hass.config.time_zone,
            60,
            self.config.get(CONF_API_SSL_CHECK, True),
            async_get_clientsession(hass),
        )

    async def _async_setup(self) -> None:
        """Load the station names and find the stations."""
        await self.tool.async_initialize()
        latitude = self.hass.config.latitude
        longitude = self.hass.config.longitude
        try:
            # yaml configuration
            if CONF_STATIONS in self.config:
                _LOGGER.info("Init stations data from yaml list")
                await self.tool.init_stations_from_list(
                    stations_ids=self.config[CONF_STATIONS],
                    latitude=latitude,
                    longitude=longitude,
                )
                return

            # ui configuration, a maximum distance of 0 disables the discovery
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

    async def _async_update_data(self) -> dict[int, dict[str, Any]]:
        """Fetch the prices of the stations."""
        _LOGGER.info("Update stations prices")
        try:
            await self.tool.update_stations_prices()
        except PrixCarburantToolRateLimitError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="rate_limit",
                retry_after=err.retry_after,
            ) from err
        except (
            PrixCarburantToolCannotConnectError,
            PrixCarburantToolRequestError,
        ) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return self.tool.stations

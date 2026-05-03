"""Tools for Prix Carburant."""

import json
import logging
from asyncio import timeout
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from socket import gaierror

import requests
from aiohttp import ClientError, ClientSession
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE, ATTR_NAME

from .const import (
    ATTR_ADDRESS,
    ATTR_BRAND,
    ATTR_CITY,
    ATTR_DISTANCE,
    ATTR_FUELS,
    ATTR_POSTAL_CODE,
    ATTR_PRICE,
    ATTR_SHORTAGE_SINCE,
    ATTR_UPDATED_DATE,
    FUELS,
)

_LOGGER = logging.getLogger(__name__)

PRIX_CARBURANT_API_URL = "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/prix-des-carburants-en-france-flux-instantane-v2/records"
STATIONS_NAME_FILE = "stations_name.json"
STATIONS_NAME_URL = "https://raw.githubusercontent.com/Aohzan/hass-prixcarburant/refs/heads/master/custom_components/prix_carburant/stations_name.json"
BRAND_LOGO_BASE_URL = "https://raw.githubusercontent.com/Aohzan/hass-prixcarburant/refs/heads/master/brand_logos/"
HTTP_OK = 200


class PrixCarburantTool:
    """Prix Carburant class with stations information."""

    def __init__(
        self,
        time_zone: str = "Europe/Paris",
        request_timeout: int = 30,
        api_ssl_check: bool = True,  # noqa: FBT001, FBT002
        session: ClientSession | None = None,
    ) -> None:
        """Init tool."""
        self._user_time_zone = time_zone
        self._api_ssl_check = api_ssl_check
        self._local_stations_data: dict[str, dict] = {}
        self._stations_data: dict[str, dict] = {}

        _LOGGER.debug("Loading stations from: %s", STATIONS_NAME_URL)
        response = requests.get(STATIONS_NAME_URL, timeout=request_timeout)
        if (
            response.status_code == HTTP_OK
            and "Bad Gateway" not in response.text
            and "Not Found" not in response.text
        ):
            _LOGGER.debug("Successfully retrieved data from: %s", STATIONS_NAME_URL)
            self._local_stations_data = response.json()
        else:
            _LOGGER.exception(
                "Loading stations data from github failed with error: [ Request error: %s ], instead loading data from local file: %s",
                response.status_code,
                STATIONS_NAME_FILE,
            )
            with (Path(__file__).parent / STATIONS_NAME_FILE).open(
                encoding="UTF-8",
            ) as file:
                self._local_stations_data = json.load(file)

        self._request_timeout = request_timeout
        self._session = session
        self._close_session = False

        if self._session is None:
            self._session = ClientSession()
            self._close_session = True

    @property
    def stations(self) -> dict:
        """Return stations information."""
        return self._stations_data

    async def request_api(
        self,
        params: dict,
    ) -> dict:
        """Make a request to the JSON API."""
        try:
            params.update(
                {
                    "lang": "fr",
                    "timezone": self._user_time_zone,
                }
            )
            async with timeout(self._request_timeout):
                response = await self._session.request(  # type: ignore[union-attr]
                    method="GET",
                    url=PRIX_CARBURANT_API_URL,
                    params=params,
                    ssl=self._api_ssl_check,
                )
                content = await response.json()

                if response.status == HTTP_OK and "results" in content:
                    response.close()
                    return content

                msg = f"API request error {response.status}: {content}"
                raise PrixCarburantToolRequestError(msg)

        except TimeoutError as exception:
            msg = "Timeout occurred while connecting to Prix Carburant API."
            raise PrixCarburantToolCannotConnectError(msg) from exception
        except (ClientError, gaierror) as exception:
            msg = "Error occurred while communicating with the Prix Carburant API."
            raise PrixCarburantToolCannotConnectError(msg) from exception

    async def init_stations_from_list(
        self, stations_ids: list[int], latitude: float, longitude: float
    ) -> None:
        """Get data from station list ID."""
        data = {}
        _LOGGER.debug("Call %s API to retrieve station data", PRIX_CARBURANT_API_URL)

        for station_id in stations_ids:
            _LOGGER.debug(
                "Search station ID %s",
                station_id,
            )
            response = await self.request_api(
                {
                    "select": "id,latitude,longitude,cp,adresse,ville",  # codespell:ignore-words-list=adresse
                    "where": f"id={station_id}",
                    "limit": 1,
                }
            )
            if response["total_count"] != 1:
                _LOGGER.error(
                    "%s stations returned, must be 1", response["total_count"]
                )
                continue
            data.update(
                self._build_station_data(
                    response["results"][0],
                    user_latitude=latitude,
                    user_longitude=longitude,
                )
            )

        self._stations_data = data

    async def init_stations_from_location(
        self,
        latitude: float,
        longitude: float,
        distance: int,
    ) -> None:
        """Get data from near stations."""
        data = {}
        _LOGGER.debug("Call %s API to retrieve station data", PRIX_CARBURANT_API_URL)
        response_count = await self.request_api(
            {
                "select": "id",
                "where": f"distance(geom, geom'POINT({longitude} {latitude})', {distance}km)",
                "limit": 1,
            }
        )
        stations_count = response_count["total_count"]
        _LOGGER.debug("%s stations returned by the API", stations_count)

        for query_offset in range(0, stations_count, 100):
            query_limit = (
                100
                if query_offset < stations_count - 100
                else stations_count - query_offset
            )
            _LOGGER.debug(
                "Query stations from %s to %s/%s",
                query_offset,
                query_limit,
                stations_count,
            )
            async with timeout(self._request_timeout):
                response = await self.request_api(
                    {
                        "select": "id,latitude,longitude,cp,adresse,ville",  # codespell:ignore-words-list=adresse
                        "where": f"distance(geom, geom'POINT({longitude} {latitude})', {distance}km)",
                        "offset": query_offset,
                        "limit": query_limit,
                    }
                )
            for station in response["results"]:
                data.update(
                    self._build_station_data(
                        station, user_longitude=longitude, user_latitude=latitude
                    )
                )

        self._stations_data = data

    async def add_manual_stations(
        self, manual_station_ids: list[int], latitude: float, longitude: float
    ) -> None:
        """Add manual stations to existing stations data without overwriting."""
        _LOGGER.debug("Adding %s manual stations", len(manual_station_ids))

        for station_id in manual_station_ids:
            # Skip if station already exists
            if str(station_id) in self._stations_data:
                _LOGGER.debug("Station %s already exists, skipping", station_id)
                continue

            _LOGGER.debug("Adding manual station ID %s", station_id)
            response = await self.request_api(
                {
                    "select": "id,latitude,longitude,cp,adresse,ville",  # codespell:ignore-words-list=adresse
                    "where": f"id={station_id}",
                    "limit": 1,
                }
            )
            if response["total_count"] != 1:
                _LOGGER.error(
                    "Station %s not found in API (returned %s results)",
                    station_id,
                    response["total_count"],
                )
                continue

            # Add station to existing data
            self._stations_data.update(
                self._build_station_data(
                    response["results"][0],
                    user_latitude=latitude,
                    user_longitude=longitude,
                )
            )

        _LOGGER.info(
            "Manual stations added. Total stations: %s", len(self._stations_data)
        )

    async def update_stations_prices(self) -> None:
        """Update prices of specified stations."""
        _LOGGER.debug("Call %s API to retrieve fuel prices", PRIX_CARBURANT_API_URL)
        query_select = ",".join(
            f"{fuel.lower()}_{suffix}"
            for suffix in ("prix", "maj", "rupture_debut", "rupture_type")
            for fuel in FUELS
        )
        for station_id, station_data in self._stations_data.items():
            _LOGGER.debug(
                "Update fuel prices for station id %s: %s",
                station_id,
                station_data[ATTR_NAME],
            )
            response = await self.request_api(
                {
                    "select": query_select,
                    "where": f"id={station_id}",
                    "limit": 1,
                }
            )
            if response["total_count"] != 1:
                _LOGGER.error(
                    "%s stations returned, must be 1", response["total_count"]
                )
                continue
            new_prices = response["results"][0]
            for fuel in FUELS:
                fuel_key = fuel.lower()
                if (
                    new_prices[f"{fuel_key}_prix"]
                    or new_prices.get(f"{fuel_key}_rupture_type") == "temporaire"
                ):
                    station_data[ATTR_FUELS].update(
                        {
                            fuel: {
                                ATTR_UPDATED_DATE: new_prices.get(f"{fuel_key}_maj"),
                                ATTR_PRICE: new_prices.get(f"{fuel_key}_prix"),
                                ATTR_SHORTAGE_SINCE: new_prices.get(
                                    f"{fuel_key}_rupture_debut"
                                ),
                            }
                        }
                    )

    async def find_nearest_station(
        self, longitude: float, latitude: float, fuel: str, distance: int = 10
    ) -> dict:
        """Return stations near the location where the fuel price is the lowest."""
        data = {}
        _LOGGER.debug(
            "Call %s API to retrieve nearest stations ordered by price",
            PRIX_CARBURANT_API_URL,
        )
        response = await self.request_api(
            {
                "select": "id,latitude,longitude,cp,adresse,ville,"  # codespell:ignore-words-list=adresse
                f"{fuel.lower()}_prix,{fuel.lower()}_maj",
                "where": (
                    f"distance(geom, geom'POINT({longitude} {latitude})', {distance}km)"
                ),
                "order_by": f"{fuel.lower()}_prix",
                "limit": 10,
            }
        )
        stations_count = response["total_count"]
        _LOGGER.debug("%s stations returned by the API", stations_count)

        for station in response["results"]:
            data.update(
                self._build_station_data(
                    station,
                    user_longitude=longitude,
                    user_latitude=latitude,
                    fuel_key=f"{fuel.lower()}_prix",
                )
            )
        return data

    def _build_station_data(
        self,
        station: dict,
        user_longitude: float | None = None,
        user_latitude: float | None = None,
        fuel_key: str | None = None,
    ) -> dict:
        data = {}
        try:
            latitude = float(station["latitude"]) / 100000
            longitude = float(station["longitude"]) / 100000
            distance = (
                _get_distance(longitude, latitude, user_longitude, user_latitude)
                if user_longitude and user_latitude
                else None
            )
            data.update(
                {
                    station["id"]: {
                        ATTR_LATITUDE: latitude,
                        ATTR_LONGITUDE: longitude,
                        ATTR_DISTANCE: distance,
                        ATTR_ADDRESS: station[
                            "ad" + "resse"
                        ],  # split string to avoid codespell french word
                        ATTR_POSTAL_CODE: station["cp"],
                        ATTR_CITY: station["ville"],
                        ATTR_NAME: "undefined",
                        ATTR_BRAND: None,
                        ATTR_FUELS: {},
                    }
                }
            )
            # add fuel price if fuel key specified
            if fuel_key:
                data[station["id"]][ATTR_PRICE] = station[fuel_key]
            # update station data with local data if existing in it
            if local_station_data := self._local_stations_data.get(str(station["id"])):
                for attr_key in (
                    ATTR_NAME,
                    ATTR_BRAND,
                    ATTR_ADDRESS,
                    ATTR_POSTAL_CODE,
                    ATTR_CITY,
                ):
                    if attr_value := local_station_data.get(attr_key):
                        if str(attr_value).isupper() or str(attr_value).islower():
                            data[station["id"]][attr_key] = attr_value.title()
                        else:
                            data[station["id"]][attr_key] = attr_value
        except KeyError, TypeError:
            _LOGGER.exception(
                "Error while getting station %s information",
                station.get("id", "no ID"),
            )
        return data


def _get_distance(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Get distance from 2 locations."""
    earth_radius = 6371

    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    calcul_a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    calcul_c = 2 * atan2(sqrt(calcul_a), sqrt(1 - calcul_a))
    return round(calcul_c * earth_radius, 2)


def get_entity_picture(brand: str) -> str:
    """Get entity picture based on brand."""
    brand_logos = {
        "Aldi": BRAND_LOGO_BASE_URL + "Aldi_Nord.svg",
        "Agip": BRAND_LOGO_BASE_URL + "Agip.svg",
        "Atac": BRAND_LOGO_BASE_URL + "Atac.svg",
        "Auchan": BRAND_LOGO_BASE_URL + "Auchan.svg",
        "Avia": BRAND_LOGO_BASE_URL + "AVIA.svg",
        "BP": BRAND_LOGO_BASE_URL + "BP.svg",
        "BP Express": BRAND_LOGO_BASE_URL + "BP.svg",
        "Bricomarché": BRAND_LOGO_BASE_URL + "Bricomarche.svg",
        "Carrefour": BRAND_LOGO_BASE_URL + "Carrefour.svg",
        "Carrefour Contact": BRAND_LOGO_BASE_URL + "Carrefour.svg",
        "Carrefour Express": BRAND_LOGO_BASE_URL + "Carrefour.svg",
        "Carrefour Market": BRAND_LOGO_BASE_URL + "Carrefour.svg",
        "Costco": BRAND_LOGO_BASE_URL + "Costco.svg",
        "COSTCO": BRAND_LOGO_BASE_URL + "Costco.svg",
        "Dyneff": BRAND_LOGO_BASE_URL + "Dyneff.svg",
        "Elf": BRAND_LOGO_BASE_URL + "ELF.svg",
        "ENI FRANCE": BRAND_LOGO_BASE_URL + "Eni.svg",
        "ENI": BRAND_LOGO_BASE_URL + "Eni.svg",
        "Eni": BRAND_LOGO_BASE_URL + "Eni.svg",
        "Esso": BRAND_LOGO_BASE_URL + "Esso.svg",
        "Esso Express": BRAND_LOGO_BASE_URL + "Esso.svg",
        "Fulli": BRAND_LOGO_BASE_URL + "Fulli.svg",
        "G20": BRAND_LOGO_BASE_URL + "G20.svg",
        "Supermarché G20": BRAND_LOGO_BASE_URL + "G20.svg",
        "Gulf": BRAND_LOGO_BASE_URL + "Gulf.svg",
        "Huit à 8": BRAND_LOGO_BASE_URL + "8_A_Huit.svg",
        "8 à Huit": BRAND_LOGO_BASE_URL + "8_A_Huit.svg",
        "Intermarché": BRAND_LOGO_BASE_URL + "Intermarche.svg",
        "Intermarché Contact": BRAND_LOGO_BASE_URL + "Intermarche.svg",
        "Leclerc": BRAND_LOGO_BASE_URL + "Leclerc.svg",
        "Leader Price": BRAND_LOGO_BASE_URL + "Leader_Price.svg",
        "LEADER-PRICE": BRAND_LOGO_BASE_URL + "Leader_Price.svg",
        "Lidl": BRAND_LOGO_BASE_URL + "Lidl.svg",
        "LIDL": BRAND_LOGO_BASE_URL + "Lidl.svg",
        "Maximarché": BRAND_LOGO_BASE_URL + "Maximarche.png",
        "MIGROS": BRAND_LOGO_BASE_URL + "Migrol.svg",
        "Monoprix": BRAND_LOGO_BASE_URL + "Monoprix.svg",
        "Netto": BRAND_LOGO_BASE_URL + "Netto-FR.svg",
        "Proxy": BRAND_LOGO_BASE_URL + "Proxi.svg",
        "PROXI SUPER": BRAND_LOGO_BASE_URL + "Proxi.svg",
        "Renault": BRAND_LOGO_BASE_URL + "Renault.svg",
        "Roady": BRAND_LOGO_BASE_URL + "Roady-white.svg",
        "ROMPETROL": BRAND_LOGO_BASE_URL + "Rompetrol.svg",
        "Shell": BRAND_LOGO_BASE_URL + "Shell.svg",
        "Simply Market": BRAND_LOGO_BASE_URL + "Auchan.svg",
        "SPAR": BRAND_LOGO_BASE_URL + "Spar.svg",
        "SPAR STATION": BRAND_LOGO_BASE_URL + "Spar.svg",
        "Supermarchés Spar": BRAND_LOGO_BASE_URL + "Spar.svg",
        "Système U": BRAND_LOGO_BASE_URL + "Hyper-U.svg",
        "Super U": BRAND_LOGO_BASE_URL + "Hyper-U.svg",
        "Station U": BRAND_LOGO_BASE_URL + "Hyper-U.svg",
        "Total": BRAND_LOGO_BASE_URL + "TotalEnergies.svg",
        "Total Access": BRAND_LOGO_BASE_URL + "TotalEnergies.svg",
        "Total Contact": BRAND_LOGO_BASE_URL + "TotalEnergies.svg",
        "Elan": BRAND_LOGO_BASE_URL + "ELAN-FR.svg",
        "Weldom": BRAND_LOGO_BASE_URL + "Weldom.svg",
        "Supermarché Match": BRAND_LOGO_BASE_URL + "Match.svg",
        "VITO": BRAND_LOGO_BASE_URL + "Vito.svg",
    }
    return brand_logos.get(brand, "")


def normalize_string(string: str | None) -> str:
    """Normalize a string."""
    if string is None:
        return ""
    if string.isupper() or string.islower():
        return string.title()
    return string


class PrixCarburantToolCannotConnectError(Exception):
    """Exception to indicate an error in connection."""


class PrixCarburantToolRequestError(Exception):
    """Exception to indicate an error with an API request."""

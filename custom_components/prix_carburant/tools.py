"""Tools for Prix Carburant."""

from asyncio import timeout
import json
import logging
import requests
from math import atan2, cos, radians, sin, sqrt
import os
from socket import gaierror

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
    ATTR_UPDATED_DATE,
    FUELS,
)

_LOGGER = logging.getLogger(__name__)

PRIX_CARBURANT_API_URL = "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/prix-des-carburants-en-france-flux-instantane-v2/records"
STATIONS_NAME_FILE = "stations_name.json"
STATIONS_NAME_URL = "https://raw.githubusercontent.com/Aohzan/hass-prixcarburant/refs/heads/master/custom_components/prix_carburant/stations_name.json"


class PrixCarburantTool:
    """Prix Carburant class with stations information."""

    def __init__(
        self,
        time_zone: str = "Europe/Paris",
        request_timeout: int = 30,
        api_ssl_check: bool = True,
        session: ClientSession | None = None,
    ) -> None:
        """Init tool."""
        self._user_time_zone = time_zone
        self._api_ssl_check = api_ssl_check
        self._local_stations_data: dict[str, dict] = {}
        self._stations_data: dict[str, dict] = {}
        
        try: 
            _LOGGER.debug("Loading stations from: %s", STATIONS_NAME_URL)
            response = requests.get(STATIONS_NAME_URL)
            if response.status_code == 200 and "Bad Gateway" not in response.text and "Not Found" not in response.text :
                _LOGGER.debug("Successfully retrieved data from: %s", STATIONS_NAME_URL)
                self._local_stations_data = response.json()
            else:
                raise Exception(f"Request error: {response.status_code}")
        except Exception as ex:
            _LOGGER.error("Loading stations data from github failed with error: [ %s ], instead loading data from local file: %s", ex, STATIONS_NAME_FILE)
            with open(
                os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), STATIONS_NAME_FILE
                ),
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

    async def _request_api(
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

                if response.status == 200 and "results" in content:
                    response.close()
                    return content

                raise PrixCarburantToolRequestError(
                    f"API request error {response.status}: {content}"
                )

        except TimeoutError as exception:
            raise PrixCarburantToolCannotConnectError(
                "Timeout occurred while connecting to Prix Carburant API."
            ) from exception
        except (ClientError, gaierror) as exception:
            raise PrixCarburantToolCannotConnectError(
                "Error occurred while communicating with the Prix Carburant API."
            ) from exception

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
            response = await self._request_api(
                {
                    "select": "id,latitude,longitude,cp,ad"
                    "resse,ville",  # split string to avoid codespell french word
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
        response_count = await self._request_api(
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
                response = await self._request_api(
                    {
                        "select": "id,latitude,longitude,cp,ad"
                        "resse,ville",  # split string to avoid codespell french word
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
            response = await self._request_api(
                {
                    "select": "id,latitude,longitude,cp,ad"
                    "resse,ville",  # split string to avoid codespell french word
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
            [f"{f.lower()}_prix" for f in FUELS] + [f"{f.lower()}_maj" for f in FUELS]
        )
        for station_id, station_data in self._stations_data.items():
            _LOGGER.debug(
                "Update fuel prices for station id %s: %s",
                station_id,
                station_data[ATTR_NAME],
            )
            response = await self._request_api(
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
                if new_prices[f"{fuel_key}_prix"]:
                    station_data[ATTR_FUELS].update(
                        {
                            fuel: {
                                ATTR_UPDATED_DATE: new_prices[f"{fuel_key}_maj"],
                                ATTR_PRICE: new_prices[f"{fuel_key}_prix"],
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
        response = await self._request_api(
            {
                "select": "id,latitude,longitude,cp,ad"
                f"resse,ville,{fuel.lower()}_prix,{fuel.lower()}_maj",  # split string to avoid codespell french word
                "where": f"distance(geom, geom'POINT({longitude} {latitude})', {distance}km)",
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
        except (KeyError, TypeError) as error:
            _LOGGER.error(
                "Error while getting station %s information: %s",
                station.get("id", "no ID"),
                error,
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


def get_entity_picture(brand: str) -> str:  # noqa: C901
    """Get entity picture based on brand."""
    match brand:
        case "Aldi":
            return "https://upload.wikimedia.org/wikipedia/commons/2/2c/Aldi_Nord_201x_logo.svg"
        case "Agip":
            return "https://upload.wikimedia.org/wikipedia/fr/a/ad/Agip.svg"
        case "Atac":
            return "https://upload.wikimedia.org/wikipedia/fr/c/c3/Logo_Atac_2015.svg"
        case "Auchan":
            return "https://upload.wikimedia.org/wikipedia/fr/c/cd/Logo_Auchan_%282015%29.svg"
        case "Avia":
            return "https://upload.wikimedia.org/wikipedia/commons/c/c0/AVIA_International_logo.svg"
        case "BP" | "BP Express":
            return "https://upload.wikimedia.org/wikipedia/fr/3/32/B_P.svg"
        case "Bricomarché":
            return "https://upload.wikimedia.org/wikipedia/commons/4/4e/Bricomarch%C3%A9_logo_2022.svg"
        case (
            "Carrefour" | "Carrefour Contact" | "Carrefour Express" | "Carrefour Market"
        ):
            return "https://upload.wikimedia.org/wikipedia/fr/3/3b/Logo_Carrefour.svg"
        case "Casino" | "Super Casino":
            return "https://upload.wikimedia.org/wikipedia/commons/6/68/Logo_of_Casino_Supermarch%C3%A9s.svg"
        case "Cora" | "CORA":
            return "https://upload.wikimedia.org/wikipedia/commons/c/ce/Cora_logo.svg"
        case "Costco" | "COSTCO":
            return "https://upload.wikimedia.org/wikipedia/commons/5/59/Costco_Wholesale_logo_2010-10-26.svg"
        case "Elf":
            return (
                "https://upload.wikimedia.org/wikipedia/fr/1/17/ELF_logo_1991-2004.svg"
            )
        case "ENI FRANCE" | "ENI":
            return (
                "https://upload.wikimedia.org/wikipedia/fr/b/b8/Eni_SpA_%28logo%29.svg"
            )
        case "Esso" | "Esso Express":
            return "https://upload.wikimedia.org/wikipedia/commons/2/22/Esso_textlogo.svg"
        case "Géant":
            return "https://upload.wikimedia.org/wikipedia/commons/3/31/Hypermarche_Geant_Casino.jpg"
        case "Gulf":
            return "https://upload.wikimedia.org/wikipedia/commons/7/70/Gulf_logo.png"
        case "Huit à 8":
            return (
                "https://upload.wikimedia.org/wikipedia/commons/2/2f/Logo_8_A_Huit.svg"
            )
        case "Intermarché" | "Intermarché Contact":
            return "https://upload.wikimedia.org/wikipedia/commons/9/96/Intermarch%C3%A9_logo_2009_classic.svg"
        case "Leclerc":
            return "https://upload.wikimedia.org/wikipedia/commons/e/ed/Logo_E.Leclerc_Sans_le_texte.svg"
        case "Leader Price" | "LEADER-PRICE":
            return "https://upload.wikimedia.org/wikipedia/fr/2/2d/Logo_Leader_Price_-_2017.svg"
        case "Monoprix":
            return (
                "https://upload.wikimedia.org/wikipedia/commons/0/0a/Monoprix_logo.svg"
            )
        case "Roady":
            return "https://upload.wikimedia.org/wikipedia/fr/6/62/Roady.svg"
        case "Shell":
            return "https://upload.wikimedia.org/wikipedia/fr/e/e8/Shell_logo.svg"
        case "SPAR" | "SPAR STATION" | "Supermarchés Spar":
            return "https://upload.wikimedia.org/wikipedia/commons/archive/7/7c/20230427121841%21Spar-logo.svg"
        case "Système U" | "Super U" | "Station U":
            return "https://upload.wikimedia.org/wikipedia/fr/1/13/U_commer%C3%A7ants_logo_2018.svg"
        case "Total" | "Total Access" | "Elan":
            return (
                "https://upload.wikimedia.org/wikipedia/fr/f/f7/Logo_TotalEnergies.svg"
            )
        case "Weldom":
            return "https://upload.wikimedia.org/wikipedia/commons/9/9d/Weldom_logo_2012.svg"
        case "Supermarché Match":
            return "https://upload.wikimedia.org/wikipedia/fr/a/ad/Logo_Supermarché_Match.svg"
    return ""


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

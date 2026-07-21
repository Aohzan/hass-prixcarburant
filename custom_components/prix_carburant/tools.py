"""Tools for Prix Carburant."""

import asyncio
import bz2
import csv
import io
import json
import logging
from asyncio import sleep, timeout
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
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
    ATTR_SHORTAGE_SINCE,
    ATTR_UPDATED_DATE,
    FUELS,
)

_LOGGER = logging.getLogger(__name__)

PRIX_CARBURANT_API_URL = "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/prix-des-carburants-en-france-flux-instantane-v2/records"
STATIONS_NAME_OSM_URL = (
    "https://www.data.gouv.fr/api/1/datasets/r/fcab3bd4-6c6d-4b73-95d2-cfd5e04ee651"
)
STATIONS_NAME_OSM_FILE = "stations_name_osm.csv"
STATIONS_NAME_FILE = "stations_name.json"
STATIONS_NAME_URL = "https://raw.githubusercontent.com/Aohzan/hass-prixcarburant/refs/heads/master/custom_components/prix_carburant/stations_name.json"
BRAND_LOGO_BASE_URL = "https://raw.githubusercontent.com/Aohzan/hass-prixcarburant/refs/heads/master/brand_logos/"
HTTP_OK = 200
_DELETE_TAG = "DELETE TAG"
_MAX_CONCURRENT_API_REQUESTS = 5


def _parse_stations_csv(content: str) -> dict[str, dict]:
    """Parse a stations CSV string into a {station_id: {name, brand}} dict."""
    result: dict[str, dict] = {}
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        raw_ids = row.get("ref:FR:prix-carburants", "").strip()
        if not raw_ids or raw_ids.startswith(_DELETE_TAG):
            continue

        def _clean(value: str) -> str:
            value = value.strip()
            return "" if value.startswith(_DELETE_TAG) else value

        name = _clean(row.get("name", ""))
        brand = _clean(row.get("brand", ""))
        if not brand:
            brand = _clean(row.get("operator", ""))
        if not brand:
            brand = _clean(row.get("branch", ""))

        if not name and not brand:
            continue
        for raw_station_id in raw_ids.split(";"):
            station_id = raw_station_id.strip()
            if station_id and station_id not in result:
                result[station_id] = {"name": name, "brand": brand}
    return result


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
        self._request_timeout = request_timeout
        self._session = session
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT_API_REQUESTS)

    async def async_initialize(self) -> None:
        """Load stations name data from remote sources, falling back to local files."""
        _LOGGER.debug("Loading OSM stations CSV from: %s", STATIONS_NAME_OSM_URL)
        try:
            async with timeout(self._request_timeout):
                response = await self._session.get(STATIONS_NAME_OSM_URL)  # type: ignore[union-attr]
                response.raise_for_status()
                raw = await response.read()
            csv_content = bz2.decompress(raw).decode("UTF-8")
            osm_stations_data: dict[str, dict] = _parse_stations_csv(csv_content)
            _LOGGER.debug(
                "Successfully retrieved OSM CSV from: %s", STATIONS_NAME_OSM_URL
            )
        except (ClientError, TimeoutError, OSError, ValueError) as err:
            _LOGGER.warning(
                "Failed to load OSM CSV from data.gouv.fr (%s). Using local file: %s",
                err,
                STATIONS_NAME_OSM_FILE,
            )
            with (Path(__file__).parent / STATIONS_NAME_OSM_FILE).open(
                encoding="UTF-8",
            ) as file:
                osm_stations_data = _parse_stations_csv(file.read())

        _LOGGER.debug("Loading custom stations from: %s", STATIONS_NAME_URL)
        try:
            async with timeout(self._request_timeout):
                response = await self._session.get(STATIONS_NAME_URL)  # type: ignore[union-attr]
                response.raise_for_status()
                custom_stations_data: dict[str, dict] = await response.json(
                    content_type=None
                )
            _LOGGER.debug(
                "Successfully retrieved custom data from: %s", STATIONS_NAME_URL
            )
        except (ClientError, TimeoutError, json.JSONDecodeError, ValueError) as err:
            _LOGGER.warning(
                "Failed to load custom stations data from GitHub (%s). Using local file: %s",
                err,
                STATIONS_NAME_FILE,
            )
            with (Path(__file__).parent / STATIONS_NAME_FILE).open(
                encoding="UTF-8",
            ) as file:
                custom_stations_data = json.load(file)

        self._local_stations_data = {**osm_stations_data, **custom_stations_data}

    @property
    def stations(self) -> dict:
        """Return stations information."""
        return self._stations_data

    async def request_api(
        self,
        params: dict,
        retries: int = 3,
        retry_delay: int = 10,
    ) -> dict:
        """Make a request to the JSON API."""
        params.update(
            {
                "lang": "fr",
                "timezone": self._user_time_zone,
            }
        )
        last_exception: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
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

                    _raise_api_request_error(response.status, content)

            except TimeoutError:
                msg = "Timeout occurred while connecting to Prix Carburant API."
                last_exception = PrixCarburantToolCannotConnectError(msg)
            except ClientError, gaierror:
                msg = "Error occurred while communicating with the Prix Carburant API."
                last_exception = PrixCarburantToolCannotConnectError(msg)
            except PrixCarburantToolRequestError:
                raise

            if attempt < retries:
                _LOGGER.warning(
                    "API request failed (attempt %s/%s), retrying in %ss",
                    attempt,
                    retries,
                    retry_delay,
                )
                await sleep(retry_delay)

        if last_exception:
            raise last_exception
        return {}

    async def _fetch_stations_by_ids(
        self, station_ids: list, latitude: float, longitude: float
    ) -> tuple[dict, list[str]]:
        """Fetch station data for the given IDs, returning (data, missing_ids)."""
        if not station_ids:
            return {}, []

        ids_list = ",".join(str(sid) for sid in station_ids)
        query_limit = min(len(station_ids), 100)
        response = await self.request_api(
            {
                "select": "id,latitude,longitude,cp,adresse,ville",  # codespell:ignore-words-list=adresse
                "where": f"id IN ({ids_list})",
                "limit": query_limit,
            }
        )

        api_station_ids = {str(r["id"]) for r in response.get("results", [])}
        missing_ids = [
            str(sid) for sid in station_ids if str(sid) not in api_station_ids
        ]

        data: dict = {}
        for result in response.get("results", []):
            data.update(
                self._build_station_data(
                    result,
                    user_latitude=latitude,
                    user_longitude=longitude,
                )
            )
        return data, missing_ids

    async def init_stations_from_list(
        self, stations_ids: list[int], latitude: float, longitude: float
    ) -> None:
        """Get data from station list ID."""
        _LOGGER.debug("Call %s API to retrieve station data", PRIX_CARBURANT_API_URL)
        if not stations_ids:
            self._stations_data = {}
            return

        data, missing_ids = await self._fetch_stations_by_ids(
            stations_ids, latitude, longitude
        )
        for sid in missing_ids:
            _LOGGER.warning(
                "Station %s not found in the API, it may have closed or its ID has changed",
                sid,
            )
        self._stations_data = data

    async def init_stations_from_location(
        self,
        latitude: float,
        longitude: float,
        distance: int,
    ) -> None:
        """Get data from near stations."""
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

        async def _fetch_page(query_offset: int, query_limit: int) -> dict:
            _LOGGER.debug(
                "Query stations from %s to %s/%s",
                query_offset,
                query_limit,
                stations_count,
            )
            async with self._semaphore:
                response = await self.request_api(
                    {
                        "select": "id,latitude,longitude,cp,adresse,ville",  # codespell:ignore-words-list=adresse
                        "where": f"distance(geom, geom'POINT({longitude} {latitude})', {distance}km)",
                        "offset": query_offset,
                        "limit": query_limit,
                    }
                )
            data: dict = {}
            for station in response["results"]:
                data.update(
                    self._build_station_data(
                        station, user_longitude=longitude, user_latitude=latitude
                    )
                )
            return data

        offsets_limits = [
            (offset, min(100, stations_count - offset))
            for offset in range(0, stations_count, 100)
        ]
        results = await asyncio.gather(
            *[_fetch_page(off, lim) for off, lim in offsets_limits],
        )
        data: dict = {}
        for result in results:
            data.update(result)
        self._stations_data = data

    async def add_manual_stations(
        self, manual_station_ids: list[int], latitude: float, longitude: float
    ) -> None:
        """Add manual stations to existing stations data without overwriting."""
        _LOGGER.debug("Adding %s manual stations", len(manual_station_ids))

        new_ids = [
            sid for sid in manual_station_ids if int(sid) not in self._stations_data
        ]
        if not new_ids:
            _LOGGER.info(
                "Manual stations added. Total stations: %s", len(self._stations_data)
            )
            return

        data, missing_ids = await self._fetch_stations_by_ids(
            new_ids, latitude, longitude
        )
        for sid in missing_ids:
            _LOGGER.error("Station %s not found in API", sid)

        self._stations_data.update(data)

        _LOGGER.info(
            "Manual stations added. Total stations: %s", len(self._stations_data)
        )

    async def update_stations_prices(self) -> None:
        """Update prices of specified stations."""
        _LOGGER.debug("Call %s API to retrieve fuel prices", PRIX_CARBURANT_API_URL)
        query_select = "id," + ",".join(
            f"{fuel.lower()}_{suffix}"
            for suffix in ("prix", "maj", "rupture_debut", "rupture_type")
            for fuel in FUELS
        )
        total_stations = len(self._stations_data)
        if total_stations == 0:
            return

        station_ids = list(self._stations_data.keys())
        ids_list = ",".join(str(sid) for sid in station_ids)
        where_clause = f"id IN ({ids_list})"
        query_limit = min(total_stations, 100)

        try:
            response = await self.request_api(
                {
                    "select": query_select,
                    "where": where_clause,
                    "limit": query_limit,
                }
            )
        except (
            PrixCarburantToolCannotConnectError,
            PrixCarburantToolRequestError,
        ):
            _LOGGER.exception("Failed to update prices from API")
            return

        api_station_ids = {r["id"] for r in response.get("results", [])}
        failed_stations: list[str] = []

        for station_id_ in station_ids:
            if station_id_ not in api_station_ids:
                failed_stations.append(str(station_id_))
                continue
            station_data = self._stations_data[station_id_]
            result = next(r for r in response["results"] if r["id"] == station_id_)
            for fuel in FUELS:
                fuel_key = fuel.lower()
                if (
                    result.get(f"{fuel_key}_prix")
                    or result.get(f"{fuel_key}_rupture_type") == "temporaire"
                ):
                    station_data[ATTR_FUELS].update(
                        {
                            fuel: {
                                ATTR_UPDATED_DATE: result.get(f"{fuel_key}_maj"),
                                ATTR_PRICE: result.get(f"{fuel_key}_prix"),
                                ATTR_SHORTAGE_SINCE: result.get(
                                    f"{fuel_key}_rupture_debut"
                                ),
                            }
                        }
                    )
                else:
                    station_data[ATTR_FUELS].pop(fuel, None)

        if failed_stations:
            _LOGGER.warning(
                "%s/%s station(s) returned no data from the API: %s",
                len(failed_stations),
                total_stations,
                ", ".join(failed_stations),
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
                if user_longitude is not None and user_latitude is not None
                else None
            )
            data.update(
                {
                    station["id"]: {
                        ATTR_LATITUDE: latitude,
                        ATTR_LONGITUDE: longitude,
                        ATTR_DISTANCE: distance,
                        ATTR_ADDRESS: station[
                            "adresse"
                        ],  # codespell:ignore-words-list=adresse
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
                        data[station["id"]][attr_key] = normalize_string(attr_value)
                # allow overriding GPS coordinates (decimal degrees)
                if (override_lat := local_station_data.get("latitude")) is not None:
                    data[station["id"]][ATTR_LATITUDE] = float(override_lat)
                if (override_lon := local_station_data.get("longitude")) is not None:
                    data[station["id"]][ATTR_LONGITUDE] = float(override_lon)
                if (
                    (
                        local_station_data.get("latitude") is not None
                        or local_station_data.get("longitude") is not None
                    )
                    and user_longitude is not None
                    and user_latitude is not None
                ):
                    data[station["id"]][ATTR_DISTANCE] = _get_distance(
                        data[station["id"]][ATTR_LONGITUDE],
                        data[station["id"]][ATTR_LATITUDE],
                        user_longitude,
                        user_latitude,
                    )
        except KeyError, TypeError:
            _LOGGER.exception(
                "Error while getting station %s information",
                station.get("id", "no ID"),
            )
        return data


def _raise_api_request_error(status: int, body: object) -> None:
    """Raise a PrixCarburantToolRequestError with a formatted message."""
    msg = f"API request error {status}: {body}"
    raise PrixCarburantToolRequestError(msg)


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


_BRAND_LOGOS: dict[str, str] = {
    "8 à Huit": BRAND_LOGO_BASE_URL + "8_A_Huit.svg",
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
    "Casino": BRAND_LOGO_BASE_URL + "Casino.svg",
    "COLRUYT": BRAND_LOGO_BASE_URL + "Colruyt.svg",
    "CORA": BRAND_LOGO_BASE_URL + "Cora.svg",
    "COSTCO": BRAND_LOGO_BASE_URL + "Costco.svg",
    "Colruyt": BRAND_LOGO_BASE_URL + "Colruyt.svg",
    "Cora": BRAND_LOGO_BASE_URL + "Cora.svg",
    "Costco": BRAND_LOGO_BASE_URL + "Costco.svg",
    "Dyneff": BRAND_LOGO_BASE_URL + "Dyneff.svg",
    "ENI": BRAND_LOGO_BASE_URL + "Eni.svg",
    "ENI FRANCE": BRAND_LOGO_BASE_URL + "Eni.svg",
    "Elf": BRAND_LOGO_BASE_URL + "ELF.svg",
    "Elan": BRAND_LOGO_BASE_URL + "ELAN-FR.svg",
    "Eni": BRAND_LOGO_BASE_URL + "Eni.svg",
    "Esso": BRAND_LOGO_BASE_URL + "Esso.svg",
    "Esso Express": BRAND_LOGO_BASE_URL + "Esso.svg",
    "Fulli": BRAND_LOGO_BASE_URL + "Fulli.svg",
    "G20": BRAND_LOGO_BASE_URL + "G20.svg",
    "Géant": BRAND_LOGO_BASE_URL + "Geant_Casino.svg",
    "Gulf": BRAND_LOGO_BASE_URL + "Gulf.svg",
    "Huit à 8": BRAND_LOGO_BASE_URL + "8_A_Huit.svg",
    "Intermarché": BRAND_LOGO_BASE_URL + "Intermarche.svg",
    "Intermarché Contact": BRAND_LOGO_BASE_URL + "Intermarche.svg",
    "E.Leclerc": BRAND_LOGO_BASE_URL + "Leclerc.svg",
    "LEADER-PRICE": BRAND_LOGO_BASE_URL + "Leader_Price.svg",
    "LIDL": BRAND_LOGO_BASE_URL + "Lidl.svg",
    "Leclerc": BRAND_LOGO_BASE_URL + "Leclerc.svg",
    "Leader Price": BRAND_LOGO_BASE_URL + "Leader_Price.svg",
    "Lidl": BRAND_LOGO_BASE_URL + "Lidl.svg",
    "MIGROS": BRAND_LOGO_BASE_URL + "Migrol.svg",
    "Maximarché": BRAND_LOGO_BASE_URL + "Maximarche.png",
    "Monoprix": BRAND_LOGO_BASE_URL + "Monoprix.svg",
    "PROXI SUPER": BRAND_LOGO_BASE_URL + "Proxi.svg",
    "Netto": BRAND_LOGO_BASE_URL + "Netto-FR.svg",
    "Proxy": BRAND_LOGO_BASE_URL + "Proxi.svg",
    "Renault": BRAND_LOGO_BASE_URL + "Renault.svg",
    "ROMPETROL": BRAND_LOGO_BASE_URL + "Rompetrol.svg",
    "Roady": BRAND_LOGO_BASE_URL + "Roady-white.svg",
    "SPAR": BRAND_LOGO_BASE_URL + "Spar.svg",
    "SPAR STATION": BRAND_LOGO_BASE_URL + "Spar.svg",
    "Shell": BRAND_LOGO_BASE_URL + "Shell.svg",
    "Simply Market": BRAND_LOGO_BASE_URL + "Auchan.svg",
    "Station U": BRAND_LOGO_BASE_URL + "Hyper-U.svg",
    "Super Casino": BRAND_LOGO_BASE_URL + "Casino.svg",
    "Super U": BRAND_LOGO_BASE_URL + "Hyper-U.svg",
    "Supermarché G20": BRAND_LOGO_BASE_URL + "G20.svg",
    "Supermarché Match": BRAND_LOGO_BASE_URL + "Match.svg",
    "Supermarchés Spar": BRAND_LOGO_BASE_URL + "Spar.svg",
    "Système U": BRAND_LOGO_BASE_URL + "Hyper-U.svg",
    "Total": BRAND_LOGO_BASE_URL + "TotalEnergies.svg",
    "Total Access": BRAND_LOGO_BASE_URL + "TotalEnergies.svg",
    "Total Contact": BRAND_LOGO_BASE_URL + "TotalEnergies.svg",
    "TotalEnergies": BRAND_LOGO_BASE_URL + "TotalEnergies.svg",
    "TotalEnergies Access": BRAND_LOGO_BASE_URL + "TotalEnergies.svg",
    "VITO": BRAND_LOGO_BASE_URL + "Vito.svg",
    "Weldom": BRAND_LOGO_BASE_URL + "Weldom.svg",
}


def get_entity_picture(brand: str) -> str:
    """Get entity picture based on brand."""
    return _BRAND_LOGOS.get(brand, "")


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

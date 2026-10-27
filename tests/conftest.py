"""Fixtures of the Prix Carburant tests."""

import bz2
from collections.abc import Generator
from copy import deepcopy
from http import HTTPStatus
import re
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from syrupy.assertion import SnapshotAssertion
from yarl import URL

from custom_components.prix_carburant.const import CONF_MAX_KM, DEFAULT_NAME, DOMAIN
from custom_components.prix_carburant.tools import (
    PRIX_CARBURANT_API_URL,
    STATIONS_NAME_OSM_URL,
    STATIONS_NAME_URL,
)

ENTRY_DATA = {
    CONF_MAX_KM: 10,
    "fuels_Gazole": True,
    "fuels_E10": True,
    "fuels_E85": True,
    "fuels_SP95": True,
    "fuels_SP98": False,
    "fuels_GPLc": True,
}

# Stations of the API, their coordinates are close to the test location
STATIONS: dict[int, dict[str, Any]] = {
    99900001: {
        "latitude": "3287400",
        "longitude": "-11722700",
        "cp": "92037",
        "adresse": "1 RUE DE LA GARE",
        "ville": "LA JOLLA",
        "gazole_prix": 1.659,
        "gazole_maj": "2026-10-26T08:00:00+02:00",
        "e10_prix": 1.789,
        "e10_maj": "2026-10-25T09:30:00+02:00",
        "sp98_prix": 1.899,
        "sp98_maj": "2026-10-25T09:30:00+02:00",
    },
    99900002: {
        "latitude": "3288000",
        "longitude": "-11723000",
        "cp": "92037",
        "adresse": "Avenue du Port",
        "ville": "La Jolla",
        "gazole_prix": 1.649,
        "gazole_maj": "2026-10-27T07:00:00+02:00",
        "e85_rupture_type": "temporaire",
        "e85_rupture_debut": "2026-10-20T10:00:00+02:00",
    },
    99900003: {
        "latitude": "3286000",
        "longitude": "-11720000",
        "cp": "92122",
        "adresse": "3 boulevard nord",
        "ville": "san diego",
        "gplc_prix": 0.999,
        "gplc_maj": "2026-10-01T12:00:00+02:00",
    },
}
# Station only known when added manually
MANUAL_STATION_ID = 99900101
MANUAL_STATION = {
    "latitude": "3300000",
    "longitude": "-11700000",
    "cp": "92101",
    "adresse": "Route de la mer",
    "ville": "Mission Beach",
    "sp95_prix": 1.799,
    "sp95_maj": "2026-10-26T18:00:00+02:00",
}

OSM_CSV = (
    "ref:FR:prix-carburants,brand,name,operator,branch\n"
    "99900002,Carrefour,,,\n"
    "99900101,,DELETE TAG,Esso,\n"
)
CUSTOM_STATIONS = {"99900001": {"name": "Relais de la Gare", "brand": "Total Access"}}


class FakeApi:
    """Answer the requests to the Prix Carburant API from the stations above."""

    def __init__(self) -> None:
        """Initialize the API with the stations."""
        self.stations = deepcopy(STATIONS)
        self.manual_stations = {MANUAL_STATION_ID: deepcopy(MANUAL_STATION)}
        self.requests: list[dict[str, str]] = []
        self.status = HTTPStatus.OK
        self.headers: dict[str, str] = {}
        self.exc: Exception | None = None
        # Statuses of the next responses, before answering normally
        self.next_statuses: list[HTTPStatus] = []
        # Stations whose requests fail with a server error
        self.failing_ids: set[int] = set()

    async def __call__(
        self, method: str, url: URL, data: Any
    ) -> AiohttpClientMockResponse:
        """Return the records matching the query."""
        params = dict(url.query)
        self.requests.append(params)
        if self.exc is not None:
            raise self.exc
        if self.next_statuses:
            return AiohttpClientMockResponse(
                method,
                url,
                status=self.next_statuses.pop(0),
                json={"error_code": "ServerError", "message": "Error"},
            )
        if self.status != HTTPStatus.OK:
            return AiohttpClientMockResponse(
                method, url, status=self.status, headers=self.headers, json={}
            )

        where = params["where"]
        all_stations = self.stations | self.manual_stations
        if match := re.fullmatch(r"id IN \((.*)\)", where):
            ids = [int(sid) for sid in match[1].split(",")]
            if self.failing_ids.intersection(ids):
                return AiohttpClientMockResponse(
                    method, url, status=HTTPStatus.BAD_GATEWAY, json={}
                )
            records = [
                {"id": sid} | all_stations[sid] for sid in ids if sid in all_stations
            ]
        elif match := re.fullmatch(r"id=(\d+)", where):
            sid = int(match[1])
            records = [{"id": sid} | all_stations[sid]] if sid in all_stations else []
        else:
            records = [{"id": sid} | station for sid, station in self.stations.items()]
            if order_by := params.get("order_by"):
                records = sorted(
                    (record for record in records if record.get(order_by)),
                    key=lambda record: record[order_by],
                )

        total_count = len(records)
        offset = int(params.get("offset", 0))
        records = records[offset : offset + int(params["limit"])]
        return AiohttpClientMockResponse(
            method, url, json={"total_count": total_count, "results": records}
        )


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return the snapshot assertion with the Home Assistant serializer."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable the custom integrations in every test."""


@pytest.fixture(autouse=True)
def no_retry_delay() -> Generator[AsyncMock]:
    """Retry the API requests without waiting."""
    with patch("custom_components.prix_carburant.tools.sleep") as mock_sleep:
        yield mock_sleep


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the config entry of the integration."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="01K8ZQ5V7P2M4R6T8W0Y2A4C6E",
        title=DEFAULT_NAME,
        unique_id=DOMAIN,
        data=ENTRY_DATA,
        version=1,
        minor_version=2,
    )


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> FakeApi:
    """Mock the Prix Carburant API and the station names."""
    api = FakeApi()
    aioclient_mock.get(
        STATIONS_NAME_OSM_URL, content=bz2.compress(OSM_CSV.encode("utf-8"))
    )
    aioclient_mock.get(STATIONS_NAME_URL, json=CUSTOM_STATIONS)
    aioclient_mock.get(PRIX_CARBURANT_API_URL, side_effect=api)
    return api

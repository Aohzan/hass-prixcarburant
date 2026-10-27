"""Tests of the setup and services of the Prix Carburant integration."""

from datetime import timedelta
from http import HTTPStatus

from aiohttp import ClientError
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.prix_carburant.const import (
    CONF_MANUAL_STATIONS,
    CONF_MAX_KM,
    CONF_STATIONS,
    DOMAIN,
)
from custom_components.prix_carburant.tools import (
    PRIX_CARBURANT_API_URL,
    STATIONS_NAME_OSM_URL,
    STATIONS_NAME_URL,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_SCAN_INTERVAL, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.setup import async_setup_component

from .conftest import ENTRY_DATA, MANUAL_STATION_ID, STATIONS, FakeApi

GAZOLE_ENTITY_ID = "sensor.relais_de_la_gare_gazole"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_and_unload(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: FakeApi
) -> None:
    """Test the setup and unload of an entry."""
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert set(mock_config_entry.runtime_data.data) == set(STATIONS)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize("status", [HTTPStatus.BAD_REQUEST, HTTPStatus.BAD_GATEWAY])
async def test_setup_api_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: FakeApi,
    status: HTTPStatus,
) -> None:
    """Test the setup is retried when the API fails."""
    mock_api.status = status
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    # Only the server errors are retried
    assert len(mock_api.requests) == (3 if status >= 500 else 1)


async def test_server_error_retried(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_api: FakeApi,
) -> None:
    """Test a server error with a JSON body is retried during the update."""
    await _setup(hass, mock_config_entry)
    requests = len(mock_api.requests)

    mock_api.next_statuses = [HTTPStatus.SERVICE_UNAVAILABLE]
    mock_api.stations[99900001]["gazole_prix"] = 1.7
    freezer.tick(timedelta(hours=4, minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get(GAZOLE_ENTITY_ID).state == "1.7"
    assert len(mock_api.requests) == requests + 2


async def test_setup_cannot_connect(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: FakeApi
) -> None:
    """Test the API requests are retried before retrying the setup."""
    mock_api.exc = ClientError()
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert len(mock_api.requests) == 3


async def test_scan_interval_zero(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: FakeApi
) -> None:
    """Test an interval of 0 saved by a previous version updates every hour."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_SCAN_INTERVAL: 0}
    )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.runtime_data.update_interval == timedelta(hours=1)


async def test_local_station_names(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the files of the integration are used when the downloads fail."""
    aioclient_mock.get(STATIONS_NAME_OSM_URL, status=HTTPStatus.NOT_FOUND)
    aioclient_mock.get(STATIONS_NAME_URL, exc=ClientError())
    aioclient_mock.get(PRIX_CARBURANT_API_URL, side_effect=FakeApi())
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    # Station 99900001 isn't in the local files
    assert hass.states.get("sensor.station_99900001_gazole") is not None


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (ClientError(), HTTPStatus.OK),
        (None, HTTPStatus.SERVICE_UNAVAILABLE),
        # Rate limit without delay
        (None, HTTPStatus.TOO_MANY_REQUESTS),
    ],
)
async def test_update_failed(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_api: FakeApi,
    exc: Exception | None,
    status: HTTPStatus,
) -> None:
    """Test a transient error is retried after 15 minutes."""
    await _setup(hass, mock_config_entry)
    assert hass.states.get(GAZOLE_ENTITY_ID).state == "1.659"

    mock_api.exc = exc
    mock_api.status = status
    freezer.tick(timedelta(hours=4, minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(GAZOLE_ENTITY_ID).state == STATE_UNAVAILABLE

    mock_api.exc = None
    mock_api.status = HTTPStatus.OK
    freezer.tick(timedelta(minutes=14))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(GAZOLE_ENTITY_ID).state == STATE_UNAVAILABLE

    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(GAZOLE_ENTITY_ID).state == "1.659"


async def test_update_request_error(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_api: FakeApi,
) -> None:
    """Test a request error waits for the next update."""
    await _setup(hass, mock_config_entry)

    mock_api.status = HTTPStatus.BAD_REQUEST
    freezer.tick(timedelta(hours=4, minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(GAZOLE_ENTITY_ID).state == STATE_UNAVAILABLE

    mock_api.status = HTTPStatus.OK
    freezer.tick(timedelta(minutes=16))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(GAZOLE_ENTITY_ID).state == STATE_UNAVAILABLE

    freezer.tick(timedelta(hours=4))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(GAZOLE_ENTITY_ID).state == "1.659"


@pytest.mark.freeze_time("2026-10-27 12:00:00+00:00")
@pytest.mark.parametrize(
    "headers",
    [
        {"Retry-After": "600"},
        # Quota reset 10 minutes after the failed update
        {"X-RateLimit-Reset": "2026-10-27 16:11:00+00:00"},
    ],
)
async def test_rate_limit(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_api: FakeApi,
    headers: dict[str, str],
) -> None:
    """Test the update is retried after the delay requested by the API."""
    await _setup(hass, mock_config_entry)

    mock_api.status = HTTPStatus.TOO_MANY_REQUESTS
    mock_api.headers = headers
    freezer.tick(timedelta(hours=4, minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(GAZOLE_ENTITY_ID).state == STATE_UNAVAILABLE
    # Not retried immediately
    requests = len(mock_api.requests)
    assert requests == 4

    mock_api.status = HTTPStatus.OK
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(GAZOLE_ENTITY_ID).state == "1.659"


async def test_more_than_100_stations(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: FakeApi
) -> None:
    """Test the prices of all the stations are fetched by batches of 100."""
    base = STATIONS[99900001]
    mock_api.stations = {99800000 + index: dict(base) for index in range(250)}
    await _setup(hass, mock_config_entry)

    data = mock_config_entry.runtime_data.data
    assert len(data) == 250
    assert all(
        station["fuels"]["Gazole"]["price"] == 1.659 for station in data.values()
    )
    price_requests = [
        request for request in mock_api.requests if "gazole_prix" in request["select"]
    ]
    assert sorted(int(request["limit"]) for request in price_requests) == [
        50,
        100,
        100,
    ]


async def test_partial_update(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_api: FakeApi,
) -> None:
    """Test the prices fetched are kept when a batch of stations fails."""
    base = STATIONS[99900001]
    mock_api.stations = {99800000 + index: dict(base) for index in range(250)}
    await _setup(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data

    for station in mock_api.stations.values():
        station["gazole_prix"] = 1.7
    # Station of the third batch
    mock_api.failing_ids = {99800210}
    requests = len(mock_api.requests)
    freezer.tick(timedelta(hours=4, minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert coordinator.last_update_success
    prices = {
        station_id: station["fuels"]["Gazole"]["price"]
        for station_id, station in coordinator.data.items()
    }
    assert all(prices[99800000 + index] == 1.7 for index in range(200))
    # The stations of the failed batch keep their last price
    assert all(prices[99800000 + index] == 1.659 for index in range(200, 250))
    assert hass.states.get("sensor.station_99800210_gazole").state == "1.659"
    # Every batch was requested, the failed one retried
    assert len(mock_api.requests) == requests + 2 + 3


async def test_first_update_partial_failure(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: FakeApi
) -> None:
    """Test the setup is retried when a batch fails at the first update."""
    base = STATIONS[99900001]
    mock_api.stations = {99800000 + index: dict(base) for index in range(250)}
    mock_api.failing_ids = {99800210}
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_manual_stations_only(hass: HomeAssistant, mock_api: FakeApi) -> None:
    """Test a maximum distance of 0 only uses the manual stations."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data=ENTRY_DATA | {CONF_MAX_KM: 0},
        options={CONF_MANUAL_STATIONS: [MANUAL_STATION_ID, 9999999]},
        version=1,
        minor_version=2,
    )
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert list(entry.runtime_data.data) == [MANUAL_STATION_ID]
    assert not any(
        request["where"].startswith("distance") for request in mock_api.requests
    )


async def test_migrate_yaml_entry(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_api: FakeApi,
) -> None:
    """Test the stations of an entry imported from YAML become manual stations."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={"platform": DOMAIN, CONF_STATIONS: [99900002, "9999999"]},
        # Options set in the UI before the YAML configuration
        options={CONF_MAX_KM: 15, CONF_MANUAL_STATIONS: [MANUAL_STATION_ID]},
        version=1,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    # Entity customized by the user with the previous version
    customized = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{DOMAIN}_99900002_Gazole",
        config_entry=entry,
        suggested_object_id="my_gazole",
    )
    entity_registry.async_update_entity(customized.entity_id, name="My gazole")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.minor_version == 3
    assert entry.data == {CONF_MAX_KM: 0}
    assert entry.options == {
        CONF_MANUAL_STATIONS: [MANUAL_STATION_ID, 99900002, 9999999]
    }
    assert set(entry.runtime_data.data) == {MANUAL_STATION_ID, 99900002}
    assert not any(
        request["where"].startswith("distance") for request in mock_api.requests
    )
    # The customized entity is kept, without duplicate
    assert entity_registry.async_get(customized.entity_id).name == "My gazole"
    assert hass.states.get("sensor.my_gazole").state == "1.649"
    assert [
        entity_entry.entity_id
        for entity_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        )
        if entity_entry.unique_id == f"{DOMAIN}_99900002_Gazole"
    ] == ["sensor.my_gazole"]


async def test_upgrade_keeps_entity_ids(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_api: FakeApi,
) -> None:
    """Test the entities registered by the previous version are kept."""
    mock_config_entry.add_to_hass(hass)
    # Entity IDs of the previous version, named "<station> <fuel>", or renamed
    previous = {
        f"{DOMAIN}_99900001_Gazole": "relais_de_la_gare_gazole",
        f"{DOMAIN}_99900002_Gazole": "station_carrefour_la_jolla_gazole",
        f"{DOMAIN}_99900003_GPLc": "renamed_by_user",
    }
    for unique_id, object_id in previous.items():
        entity_registry.async_get_or_create(
            "sensor",
            DOMAIN,
            unique_id,
            config_entry=mock_config_entry,
            suggested_object_id=object_id,
        )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    for unique_id, object_id in previous.items():
        assert (
            entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            == f"sensor.{object_id}"
        )
        assert hass.states.get(f"sensor.{object_id}") is not None
    assert not [
        entity_id
        for entity_id in hass.states.async_entity_ids()
        if entity_id.endswith("_2")
    ]


async def test_yaml_import(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
    mock_api: FakeApi,
) -> None:
    """Test the YAML configuration is imported and reported as deprecated."""
    assert await async_setup_component(
        hass,
        "sensor",
        {"sensor": [{"platform": DOMAIN, CONF_STATIONS: [99900001]}]},
    )
    await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].options == {CONF_MANUAL_STATIONS: [99900001]}
    assert issue_registry.async_get_issue(DOMAIN, "deprecated_yaml")
    assert hass.states.get(GAZOLE_ENTITY_ID).state == "1.659"


async def test_migrate_button_unique_id(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_api: FakeApi,
) -> None:
    """Test the unique ID of the refresh button is scoped to the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data=ENTRY_DATA,
        version=1,
        minor_version=1,
    )
    entry.add_to_hass(hass)
    button = entity_registry.async_get_or_create(
        "button",
        DOMAIN,
        f"{DOMAIN}_refresh_button",
        config_entry=entry,
        suggested_object_id="prix_carburant_refresh_prices",
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == 3
    migrated = entity_registry.async_get(button.entity_id)
    assert migrated.unique_id == f"{entry.entry_id}_refresh"
    assert hass.states.get(button.entity_id) is not None


async def test_migrate_from_future_version(
    hass: HomeAssistant, mock_api: FakeApi
) -> None:
    """Test an entry of a future version isn't loaded."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, version=2)
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_find_nearest_stations(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: FakeApi
) -> None:
    """Test the cheapest stations near an entity are returned."""
    await _setup(hass, mock_config_entry)
    hass.states.async_set(
        "person.me", "home", {"latitude": 32.87, "longitude": -117.22}
    )

    response = await hass.services.async_call(
        DOMAIN,
        "find_nearest_stations",
        {ATTR_ENTITY_ID: "person.me", "fuel": "Gazole", "distance": 10},
        blocking=True,
        return_response=True,
    )

    assert response == {
        "stations": [
            {
                # Station without name in the OSM data
                "name": "undefined",
                "price": 1.649,
                "address": "Avenue du Port, 92037 La Jolla",
                "latitude": 32.88,
                "longitude": -117.23,
            },
            {
                "name": "Relais de la Gare",
                "price": 1.659,
                "address": "1 RUE DE LA GARE, 92037 LA JOLLA",
                "latitude": 32.874,
                "longitude": -117.227,
            },
        ]
    }


async def test_find_nearest_stations_errors(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: FakeApi
) -> None:
    """Test the errors of the service."""
    hass.states.async_set(
        "person.me", "home", {"latitude": 32.87, "longitude": -117.22}
    )
    hass.states.async_set("person.nowhere", "home")
    service_data = {"fuel": "Gazole", "distance": 10}

    async def call(entity_id: str) -> None:
        await hass.services.async_call(
            DOMAIN,
            "find_nearest_stations",
            service_data | {ATTR_ENTITY_ID: entity_id},
            blocking=True,
            return_response=True,
        )

    assert await async_setup_component(hass, DOMAIN, {})
    with pytest.raises(ServiceValidationError) as err:
        await call("person.me")
    assert err.value.translation_key == "not_loaded"

    await _setup(hass, mock_config_entry)
    with pytest.raises(ServiceValidationError) as err:
        await call("person.unknown")
    assert err.value.translation_key == "entity_not_found"

    with pytest.raises(ServiceValidationError) as err:
        await call("person.nowhere")
    assert err.value.translation_key == "no_coordinates"

    mock_api.status = HTTPStatus.BAD_REQUEST
    with pytest.raises(HomeAssistantError) as err:
        await call("person.me")
    assert err.value.translation_key == "cannot_connect"

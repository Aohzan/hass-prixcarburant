"""Tests of the config flow of the Prix Carburant integration."""

from http import HTTPStatus
from unittest.mock import patch

from aiohttp import ClientError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.prix_carburant.const import (
    CONF_API_SSL_CHECK,
    CONF_DISPLAY_ENTITY_PICTURES,
    CONF_MANUAL_STATIONS,
    CONF_MAX_KM,
    CONF_STATIONS,
    DEFAULT_NAME,
    DOMAIN,
)
from custom_components.prix_carburant.tools import PrixCarburantTool
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import ENTRY_DATA, MANUAL_STATION_ID, FakeApi

OPTIONS = {
    CONF_SCAN_INTERVAL: 6,
    CONF_API_SSL_CHECK: False,
    CONF_DISPLAY_ENTITY_PICTURES: False,
    CONF_MAX_KM: 10,
}


async def test_user(hass: HomeAssistant, mock_api: FakeApi) -> None:
    """Test the creation of an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA | {CONF_MAX_KM: 0}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == DEFAULT_NAME
    assert result["data"] == ENTRY_DATA | {CONF_MAX_KM: 0}
    assert result["result"].unique_id == DOMAIN


async def test_user_single_instance(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test only one entry can be created."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_import(hass: HomeAssistant, mock_api: FakeApi) -> None:
    """Test the YAML configuration is imported once, as manual stations."""
    data = {
        "platform": DOMAIN,
        CONF_STATIONS: ["99900001", 99900002, "abc", 99900001],
        CONF_DISPLAY_ENTITY_PICTURES: False,
    }
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data=data
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == DEFAULT_NAME
    assert result["data"] == {CONF_MAX_KM: 0, CONF_DISPLAY_ENTITY_PICTURES: False}
    assert result["options"] == {CONF_MANUAL_STATIONS: [99900001, 99900002]}
    assert result["result"].unique_id == DOMAIN

    # The next imports don't change the entry
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data=data | {CONF_STATIONS: [99900003]},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    (entry,) = hass.config_entries.async_entries(DOMAIN)
    assert entry.options == {CONF_MANUAL_STATIONS: [99900001, 99900002]}


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _options_step(hass: HomeAssistant, entry: MockConfigEntry, step: str):
    """Open the options flow on a menu step."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def test_options_general(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: FakeApi
) -> None:
    """Test the general options keep the other options and reload the entry."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_MANUAL_STATIONS: [MANUAL_STATION_ID]}
    )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await _options_step(hass, mock_config_entry, "general_options")
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], OPTIONS
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == OPTIONS | {
        CONF_MANUAL_STATIONS: [MANUAL_STATION_ID]
    }
    # Reloaded with the new options
    assert mock_config_entry.runtime_data.config[CONF_SCAN_INTERVAL] == 6


async def test_options_fuels(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: FakeApi
) -> None:
    """Test the selection of the fuels."""
    await _setup(hass, mock_config_entry)
    assert hass.states.get("sensor.relais_de_la_gare_e10") is not None

    result = await _options_step(hass, mock_config_entry, "fuels_select")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {key: key != "fuels_E10" for key in ENTRY_DATA if key != CONF_MAX_KM},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options["fuels_E10"] is False
    assert hass.states.get("sensor.relais_de_la_gare_e10").state == "unavailable"


async def test_options_add_station(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: FakeApi
) -> None:
    """Test a station is added and the other options are kept."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(mock_config_entry, options=OPTIONS)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await _options_step(hass, mock_config_entry, "add_station")
    assert result["type"] is FlowResultType.FORM
    with patch(
        "custom_components.prix_carburant.config_flow.PrixCarburantTool",
        wraps=PrixCarburantTool,
    ) as tool_class:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"station_id": str(MANUAL_STATION_ID)}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == OPTIONS | {
        CONF_MANUAL_STATIONS: [MANUAL_STATION_ID]
    }
    assert MANUAL_STATION_ID in mock_config_entry.runtime_data.data
    # Validated without SSL check, as set in the options
    assert tool_class.call_args.kwargs["api_ssl_check"] is False


@pytest.mark.parametrize(
    ("station_id", "error"),
    [
        ("abc", "invalid_station_id"),
        ("99900001", "station_already_exists"),
        (str(MANUAL_STATION_ID), "station_already_exists"),
        ("12345", "station_not_found"),
    ],
)
async def test_options_add_station_errors(
    hass: HomeAssistant,
    mock_api: FakeApi,
    station_id: str,
    error: str,
) -> None:
    """Test the errors when adding a station."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=ENTRY_DATA,
        options={CONF_MANUAL_STATIONS: [MANUAL_STATION_ID]},
        minor_version=2,
    )
    await _setup(hass, entry)

    result = await _options_step(hass, entry, "add_station")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"station_id": station_id}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"station_id": error}


@pytest.mark.parametrize(
    ("status", "exc", "error"),
    [
        (HTTPStatus.OK, ClientError(), "cannot_connect"),
        (HTTPStatus.BAD_REQUEST, None, "station_not_found"),
    ],
)
async def test_options_add_station_not_loaded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: FakeApi,
    status: HTTPStatus,
    exc: Exception | None,
    error: str,
) -> None:
    """Test a station can be added when the entry isn't loaded."""
    mock_config_entry.add_to_hass(hass)

    result = await _options_step(hass, mock_config_entry, "add_station")
    mock_api.status = status
    mock_api.exc = exc
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"station_id": "99900001"}
    )
    assert result["errors"] == {"station_id": error}

    mock_api.status = HTTPStatus.OK
    mock_api.exc = None
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"station_id": "99900001"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {CONF_MANUAL_STATIONS: [99900001]}


async def test_options_delete_stations(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    mock_api: FakeApi,
) -> None:
    """Test manual stations are deleted with their entities and device."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=ENTRY_DATA,
        options=OPTIONS | {CONF_MANUAL_STATIONS: [MANUAL_STATION_ID, 9999999]},
        minor_version=2,
    )
    await _setup(hass, entry)
    entity_id = "sensor.station_esso_mission_beach_sp95"
    assert entity_registry.async_get(entity_id) is not None
    assert device_registry.async_get_devices(identifiers={(DOMAIN, MANUAL_STATION_ID)})

    result = await _options_step(hass, entry, "delete_stations")
    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"] == {
        "stations": "- Station 99900101\n- Station 9999999 (not found in API)"
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"stations_to_remove": [str(MANUAL_STATION_ID)]}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == OPTIONS | {CONF_MANUAL_STATIONS: [9999999]}
    assert entity_registry.async_get(entity_id) is None
    assert not device_registry.async_get_devices(
        identifiers={(DOMAIN, MANUAL_STATION_ID)}
    )

    # Nothing selected: the options don't change
    result = await _options_step(hass, entry, "delete_stations")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"stations_to_remove": []}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == OPTIONS | {CONF_MANUAL_STATIONS: [9999999]}


async def test_options_delete_no_station(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test there is nothing to delete without manual stations."""
    mock_config_entry.add_to_hass(hass)

    result = await _options_step(hass, mock_config_entry, "delete_stations")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_stations"

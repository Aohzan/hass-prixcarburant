"""Tests of the entities of the Prix Carburant integration."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from .conftest import FakeApi

GAZOLE_ENTITY_ID = "sensor.relais_de_la_gare_gazole"
E85_ENTITY_ID = "sensor.station_carrefour_la_jolla_e85"
BUTTON_ENTITY_ID = "button.prix_carburant_refresh_prices"


@pytest.mark.freeze_time("2026-10-27 12:00:00+00:00")
@pytest.mark.parametrize("platform", [Platform.BUTTON, Platform.SENSOR])
async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
    mock_api: FakeApi,
    platform: Platform,
) -> None:
    """Test the entities and their states."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("custom_components.prix_carburant.PLATFORMS", [platform])
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_restore_last_price(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: FakeApi,
) -> None:
    """Test a fuel without price keeps the price saved before the restart."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(E85_ENTITY_ID, "0.899"),
                {"native_value": 0.899, "native_unit_of_measurement": "€/l"},
            )
        ],
    )
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(E85_ENTITY_ID)
    assert state.state == "0.899"
    assert state.attributes["shortage_since"] == "2026-10-20T10:00:00+02:00"


async def test_price_update(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_api: FakeApi,
) -> None:
    """Test the prices and attributes follow the updates."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(GAZOLE_ENTITY_ID).state == "1.659"

    mock_api.stations[99900001] |= {
        "gazole_prix": 1.6789,
        "gazole_maj": "2026-10-28T08:00:00+02:00",
    }
    freezer.tick(timedelta(hours=4, minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(GAZOLE_ENTITY_ID)
    assert state.state == "1.679"
    assert state.attributes["updated_date"] == "2026-10-28T08:00:00+02:00"

    # Without price, the last one is kept
    mock_api.stations[99900001] |= {"gazole_prix": None, "gazole_maj": "invalid"}
    freezer.tick(timedelta(hours=4, minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(GAZOLE_ENTITY_ID)
    assert state.state == "1.679"


async def test_refresh_button(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: FakeApi,
) -> None:
    """Test the button refreshes the prices, even after a failed update."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    mock_api.status = 500
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: BUTTON_ENTITY_ID}, blocking=True
    )
    assert hass.states.get(GAZOLE_ENTITY_ID).state == "unavailable"
    assert hass.states.get(BUTTON_ENTITY_ID).state != STATE_UNKNOWN

    mock_api.status = 200
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: BUTTON_ENTITY_ID}, blocking=True
    )
    assert hass.states.get(GAZOLE_ENTITY_ID).state == "1.659"

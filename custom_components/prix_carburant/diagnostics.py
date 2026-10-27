"""Diagnostics support for the Prix Carburant integration."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE
from homeassistant.core import HomeAssistant

from .const import ATTR_ADDRESS, ATTR_DISTANCE
from .coordinator import PrixCarburantConfigEntry

# The stations are around Home Assistant: their position and the distances to
# them would reveal its location
TO_REDACT = {ATTR_ADDRESS, ATTR_DISTANCE, ATTR_LATITUDE, ATTR_LONGITUDE}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PrixCarburantConfigEntry
) -> dict[str, Any]:
    """Return the diagnostics of a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "stations_count": len(coordinator.data),
        "data": async_redact_data(coordinator.data, TO_REDACT),
    }

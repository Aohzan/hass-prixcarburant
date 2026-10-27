"""Diagnostics support for the Prix Carburant integration."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import ATTR_DISTANCE
from .coordinator import PrixCarburantConfigEntry

# The distances to the stations would reveal the location of Home Assistant
TO_REDACT = {ATTR_DISTANCE}


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

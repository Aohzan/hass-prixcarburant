"""Prix Carburant button platform."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the platform from config_entry."""
    async_add_entities(
        [RefreshPrixCarburantButton(hass.data[DOMAIN][entry.entry_id]["coordinator"])],
        update_before_add=True,
    )


class RefreshPrixCarburantButton(ButtonEntity):
    """Representation of a refresh button."""

    def __init__(self, coordinator: DataUpdateCoordinator) -> None:
        """Initialize the button."""
        self.coordinator = coordinator
        self._attr_device_class = ButtonDeviceClass.UPDATE
        self._attr_name = "Prix Carburant - Refresh prices"
        self._attr_icon = "mdi:refresh-circle"
        self._attr_unique_id = f"{DOMAIN}_refresh_button"

    async def async_press(self) -> None:
        """Press the button."""
        _LOGGER.debug("Price refresh asked from button")
        await self.coordinator.async_refresh()

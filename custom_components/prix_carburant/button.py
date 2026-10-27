"""Prix Carburant button platform."""

import logging

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PrixCarburantConfigEntry, PrixCarburantCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrixCarburantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the platform from config_entry."""
    async_add_entities([PrixCarburantRefreshButton(entry.runtime_data)])


class PrixCarburantRefreshButton(
    CoordinatorEntity[PrixCarburantCoordinator], ButtonEntity
):
    """Button refreshing the prices."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh"
    _attr_device_class = ButtonDeviceClass.UPDATE

    def __init__(self, coordinator: PrixCarburantCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_refresh"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            entry_type=DeviceEntryType.SERVICE,
            name=entry.title,
            configuration_url="https://www.prix-carburants.gouv.fr/",
        )

    @property
    def available(self) -> bool:
        """Return True: the prices can be refreshed after a failed update."""
        return True

    async def async_press(self) -> None:
        """Press the button."""
        _LOGGER.debug("Price refresh asked from button")
        await self.coordinator.async_refresh()

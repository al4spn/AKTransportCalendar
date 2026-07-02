"""Base entity for the Auckland Transport Rail Closures integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, CLOSURES_URL, DOMAIN
from .coordinator import ATRailClosuresCoordinator


class ATRailEntity(CoordinatorEntity[ATRailClosuresCoordinator]):
    """Base entity attached to the Auckland Rail Network service device."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: ATRailClosuresCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Auckland Rail Network",
            manufacturer="Auckland Transport",
            model="Planned rail closures",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=CLOSURES_URL,
        )

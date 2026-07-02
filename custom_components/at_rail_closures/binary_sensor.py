"""Binary sensor: is any planned closure active right now."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import ATRailConfigEntry
from .entity import ATRailEntity
from .parser import active_closures


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ATRailConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor."""
    async_add_entities([ClosureActiveBinarySensor(entry.runtime_data)])


class ClosureActiveBinarySensor(ATRailEntity, BinarySensorEntity):
    """On when at least one planned closure is in effect today."""

    _attr_translation_key = "closure_active"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "closure_active")

    def _active(self) -> list:
        return active_closures(
            self.coordinator.data.closures, dt_util.now().date()
        )

    @property
    def is_on(self) -> bool:
        return bool(self._active())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"closures": [c.as_dict() for c in self._active()]}

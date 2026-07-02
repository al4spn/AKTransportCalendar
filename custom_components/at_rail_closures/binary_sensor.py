"""Binary sensors: is a planned closure in effect right now.

One network-wide sensor plus one per enabled line. Time-aware: a closure
"from 9:30pm" only turns the sensor on from 9:30pm.
"""

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
from .parser import Closure, active_closures_at, closures_for_line


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ATRailConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [ClosureActiveBinarySensor(coordinator)]
    entities.extend(
        LineClosureActiveBinarySensor(coordinator, line)
        for line in coordinator.enabled_lines
    )
    async_add_entities(entities)


class ClosureActiveBinarySensor(ATRailEntity, BinarySensorEntity):
    """On when at least one planned closure is in effect right now."""

    _attr_translation_key = "closure_active"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "closure_active")

    def _active(self) -> list[Closure]:
        return active_closures_at(self.coordinator.data.closures, dt_util.now())

    @property
    def is_on(self) -> bool:
        return bool(self._active())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"closures": [c.as_dict() for c in self._active()]}


class LineClosureActiveBinarySensor(ATRailEntity, BinarySensorEntity):
    """On when a closure is in effect right now on a single line."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, line: str) -> None:
        key = line.lower().replace(" ", "_")
        super().__init__(coordinator, f"{key}_closure_active")
        self._line = line
        self._attr_translation_key = "line_closure_active"
        self._attr_translation_placeholders = {"line": line}

    def _active(self) -> list[Closure]:
        return active_closures_at(
            closures_for_line(self.coordinator.data.closures, self._line),
            dt_util.now(),
        )

    @property
    def is_on(self) -> bool:
        return bool(self._active())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "line": self._line,
            "closures": [c.as_dict() for c in self._active()],
        }

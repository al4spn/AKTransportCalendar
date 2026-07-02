"""Sensors for Auckland Transport rail closures."""

from __future__ import annotations

from datetime import datetime, date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    CLOSURES_URL,
    LINE_STATE_CLOSED,
    LINE_STATE_GOOD,
    LINE_STATE_PARTIAL,
    MAX_ATTR_CLOSURES,
    STATE_CLOSURES_ACTIVE,
    STATE_GOOD_SERVICE,
    STATE_REDUCED_SERVICE,
    UPCOMING_WINDOW_DAYS,
)
from .coordinator import ATRailConfigEntry
from .entity import ATRailEntity
from .parser import (
    RAIL_LINES,
    Closure,
    active_closures,
    closures_for_line,
    upcoming_closures,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ATRailConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        NetworkStatusSensor(coordinator),
        NextClosureSensor(coordinator),
    ]
    entities.extend(LineStatusSensor(coordinator, line) for line in RAIL_LINES)
    async_add_entities(entities)


def _today() -> date:
    return dt_util.now().date()


class NetworkStatusSensor(ATRailEntity, SensorEntity):
    """Overall rail network status with closure lists as attributes."""

    _attr_translation_key = "network_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        STATE_GOOD_SERVICE,
        STATE_REDUCED_SERVICE,
        STATE_CLOSURES_ACTIVE,
    ]
    _attr_icon = "mdi:train"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "network_status")

    @property
    def native_value(self) -> str:
        active = active_closures(self.coordinator.data.closures, _today())
        if any(c.closure_type == "full" for c in active):
            return STATE_CLOSURES_ACTIVE
        if active:
            return STATE_REDUCED_SERVICE
        return STATE_GOOD_SERVICE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        closures = self.coordinator.data.closures
        today = _today()
        active = active_closures(closures, today)
        upcoming = upcoming_closures(closures, today, UPCOMING_WINDOW_DAYS)
        attrs: dict[str, Any] = {
            "active_closures": [c.as_dict() for c in active[:MAX_ATTR_CLOSURES]],
            "upcoming_closures": [c.as_dict() for c in upcoming[:MAX_ATTR_CLOSURES]],
            "upcoming_count": len(upcoming),
            "last_checked": self.coordinator.data.fetched_at.isoformat(),
            "source": CLOSURES_URL,
        }
        if upcoming:
            nxt = upcoming[0]
            attrs["next_closure_start"] = nxt.start.isoformat()
            attrs["next_closure_end"] = nxt.end.isoformat()
            attrs["next_closure_title"] = nxt.title
            attrs["next_closure_lines"] = list(nxt.lines)
            attrs["next_closure_in_days"] = (nxt.start - today).days
        return attrs


class NextClosureSensor(ATRailEntity, SensorEntity):
    """Timestamp of the next upcoming closure (shows as 'in 5 days')."""

    _attr_translation_key = "next_closure"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-alert"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "next_closure")

    def _next(self) -> Closure | None:
        upcoming = upcoming_closures(self.coordinator.data.closures, _today())
        return upcoming[0] if upcoming else None

    @property
    def native_value(self) -> datetime | None:
        nxt = self._next()
        if nxt is None:
            return None
        return dt_util.start_of_local_day(nxt.start)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        nxt = self._next()
        if nxt is None:
            return {}
        return {
            "title": nxt.title,
            "lines": list(nxt.lines),
            "start": nxt.start.isoformat(),
            "end": nxt.end.isoformat(),
            "closure_type": nxt.closure_type,
            "description": nxt.description,
            "in_days": (nxt.start - _today()).days,
        }


class LineStatusSensor(ATRailEntity, SensorEntity):
    """Status of a single rail line."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [LINE_STATE_GOOD, LINE_STATE_PARTIAL, LINE_STATE_CLOSED]
    _attr_icon = "mdi:train-variant"

    def __init__(self, coordinator, line: str) -> None:
        key = line.lower().replace(" ", "_")
        super().__init__(coordinator, key)
        self._line = line
        self._attr_translation_key = "line_status"
        self._attr_translation_placeholders = {"line": line}

    def _line_closures(self) -> list[Closure]:
        return closures_for_line(self.coordinator.data.closures, self._line)

    @property
    def native_value(self) -> str:
        active = active_closures(self._line_closures(), _today())
        if any(c.closure_type == "full" for c in active):
            return LINE_STATE_CLOSED
        if active:
            return LINE_STATE_PARTIAL
        return LINE_STATE_GOOD

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        closures = self._line_closures()
        today = _today()
        active = active_closures(closures, today)
        upcoming = upcoming_closures(closures, today, UPCOMING_WINDOW_DAYS)
        attrs: dict[str, Any] = {
            "line": self._line,
            "active_closures": [c.as_dict() for c in active[:MAX_ATTR_CLOSURES]],
            "upcoming_closures": [c.as_dict() for c in upcoming[:MAX_ATTR_CLOSURES]],
        }
        if upcoming:
            attrs["next_closure_start"] = upcoming[0].start.isoformat()
            attrs["next_closure_in_days"] = (upcoming[0].start - today).days
        return attrs

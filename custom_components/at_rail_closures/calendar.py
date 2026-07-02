"""Calendar of planned Auckland rail closures.

Closures covering the same period are merged into a single all-day event,
so "Full closure 9-12 July" shows once even when AT lists it per line.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CLOSURES_URL
from .coordinator import ATRailConfigEntry
from .entity import ATRailEntity
from .parser import Closure, merged_closures


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ATRailConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the calendar."""
    async_add_entities([RailClosuresCalendar(entry.runtime_data)])


def _to_event(closure: Closure) -> CalendarEvent:
    return CalendarEvent(
        summary=closure.title,
        # All-day events use exclusive end dates.
        start=closure.start,
        end=closure.end + timedelta(days=1),
        description=f"{closure.description}\n\nMore info: {CLOSURES_URL}",
        location="Auckland rail network",
    )


class RailClosuresCalendar(ATRailEntity, CalendarEntity):
    """Calendar entity exposing closures as all-day events."""

    _attr_translation_key = "closures"
    _attr_icon = "mdi:calendar-remove"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "calendar")

    def _events(self) -> list[CalendarEvent]:
        return [_to_event(c) for c in merged_closures(self.coordinator.data.closures)]

    @property
    def event(self) -> CalendarEvent | None:
        """The current or next upcoming event."""
        now = dt_util.now()
        for event in self._events():
            if event.end_datetime_local > now:
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return events overlapping the requested window."""
        return [
            event
            for event in self._events()
            if event.start_datetime_local < end_date
            and event.end_datetime_local > start_date
        ]

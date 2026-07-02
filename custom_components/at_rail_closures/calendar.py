"""Calendars of planned Auckland rail closures.

One combined calendar merges closures covering the same period into a single
all-day event ("Full closure 9-12 July" shows once even when AT lists it per
line). In addition, each enabled line gets its own calendar so dashboard
cards can colour-code events per line.
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
from .parser import Closure, closures_for_line, merged_closures


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ATRailConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the calendars."""
    coordinator = entry.runtime_data
    entities: list[CalendarEntity] = [RailClosuresCalendar(coordinator)]
    entities.extend(
        LineClosuresCalendar(coordinator, line)
        for line in coordinator.enabled_lines
    )
    async_add_entities(entities)


def _to_event(closure: Closure, summary: str) -> CalendarEvent:
    return CalendarEvent(
        summary=summary,
        # All-day events use exclusive end dates.
        start=closure.start,
        end=closure.end + timedelta(days=1),
        description=f"{closure.description}\n\nMore info: {CLOSURES_URL}",
        location="Auckland rail network",
    )


class RailClosuresCalendarBase(ATRailEntity, CalendarEntity):
    """Shared event logic for the closure calendars."""

    def _events(self) -> list[CalendarEvent]:
        raise NotImplementedError

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


class RailClosuresCalendar(RailClosuresCalendarBase):
    """Combined calendar: closures across all lines, merged per period."""

    _attr_translation_key = "closures"
    _attr_icon = "mdi:calendar-remove"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "calendar")

    def _events(self) -> list[CalendarEvent]:
        return [
            _to_event(closure, closure.title)
            for closure in merged_closures(self.coordinator.data.closures)
        ]


class LineClosuresCalendar(RailClosuresCalendarBase):
    """Calendar of closures affecting a single line."""

    _attr_translation_key = "line_closures"
    _attr_icon = "mdi:calendar-remove"

    def __init__(self, coordinator, line: str) -> None:
        key = line.lower().replace(" ", "_")
        super().__init__(coordinator, f"calendar_{key}")
        self._line = line
        self._attr_translation_placeholders = {"line": line}

    def _events(self) -> list[CalendarEvent]:
        events = []
        for closure in closures_for_line(
            self.coordinator.data.closures, self._line
        ):
            kind = (
                "Full closure" if closure.closure_type == "full" else "Partial closure"
            )
            events.append(_to_event(closure, kind))
        return events

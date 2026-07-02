"""Calendar of planned Auckland rail closures.

A single calendar where each affected line gets its own event, titled with
the line name ("Southern Line – Full closure"). Events carry exact start and
end times when the source provides them (alerts feed timestamps, or clock
times such as "until 12pm" parsed from the announcement text); otherwise
they are all-day events. Only lines enabled in the integration options
produce events.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CLOSURES_URL
from .coordinator import ATRailConfigEntry
from .entity import ATRailEntity
from .parser import NZ_TZ, Closure


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ATRailConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the calendar."""
    async_add_entities([RailClosuresCalendar(entry.runtime_data)])


def _to_event(closure: Closure, line: str) -> CalendarEvent:
    kind = "Full closure" if closure.closure_type == "full" else "Partial closure"
    summary = f"{line} – {kind}"
    description = f"{closure.description}\n\nMore info: {CLOSURES_URL}"

    if closure.is_all_day:
        return CalendarEvent(
            summary=summary,
            # All-day events use exclusive end dates.
            start=closure.start,
            end=closure.end + timedelta(days=1),
            description=description,
            location="Auckland rail network",
        )

    start = closure.start_dt or datetime.combine(closure.start, time.min, NZ_TZ)
    end = closure.end_dt or datetime.combine(
        closure.end + timedelta(days=1), time.min, NZ_TZ
    )
    return CalendarEvent(
        summary=summary,
        start=start,
        end=end,
        description=description,
        location="Auckland rail network",
    )


class RailClosuresCalendar(ATRailEntity, CalendarEntity):
    """Calendar entity exposing closures as per-line events."""

    _attr_translation_key = "closures"
    _attr_icon = "mdi:calendar-remove"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "calendar")

    def _events(self) -> list[CalendarEvent]:
        enabled = self.coordinator.enabled_lines
        events: list[CalendarEvent] = []
        seen: set[tuple] = set()
        for closure in self.coordinator.data.closures:
            for line in closure.lines:
                if line not in enabled:
                    continue
                key = (line, closure.start, closure.end, closure.closure_type)
                if key in seen:
                    continue
                seen.add(key)
                events.append(_to_event(closure, line))
        events.sort(key=lambda e: (e.start_datetime_local, e.summary))
        return events

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

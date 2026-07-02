"""Mapper for Auckland Transport's GTFS-realtime service alerts feed.

Like ``parser``, this module has no Home Assistant imports so it can be unit
tested standalone. It converts the JSON service alerts response into the same
``Closure`` records the website parser produces, so both sources feed the
same entities.

The feed is GTFS-realtime (https://gtfs.org/documentation/realtime/) served
as JSON. AT has used two envelope shapes over time, both handled here:

* legacy: ``{"status": "OK", "response": {"header": ..., "entity": [...]}}``
* plain GTFS-RT JSON: ``{"header": ..., "entity": [...]}``
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any

from .parser import NZ_TZ, Closure, looks_like_full_closure

# GTFS route_id fragments for Auckland's rail lines. AT route ids have looked
# like "STH-201"; match on the token rather than the exact id.
_ROUTE_TOKENS = {
    "STH": "Southern Line",
    "EAST": "Eastern Line",
    "WEST": "Western Line",
    "ONE": "Onehunga Line",
}
_ROUTE_TYPE_RAIL = 2

# GTFS-RT effect -> our closure type. Effects not listed are ignored
# (NO_EFFECT, ACCESSIBILITY_ISSUE, ...): they are not closures.
_EFFECT_MAP = {
    "NO_SERVICE": "full",
    "REDUCED_SERVICE": "partial",
    "SIGNIFICANT_DELAYS": "partial",
    "DETOUR": "partial",
    "ADDITIONAL_SERVICE": None,
    "MODIFIED_SERVICE": "partial",
    "STOP_MOVED": None,
    "OTHER_EFFECT": "partial",
    "UNKNOWN_EFFECT": "partial",
    "NO_EFFECT": None,
    "ACCESSIBILITY_ISSUE": None,
}


def _entities(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("entity"), list):
        return payload["entity"]
    response = payload.get("response")
    if isinstance(response, dict) and isinstance(response.get("entity"), list):
        return response["entity"]
    # Some deployments return the entity list directly under "response".
    if isinstance(response, list):
        return response
    return []


def _translated(field: Any) -> str:
    """Extract the English (or first) text from a GTFS TranslatedString."""
    if not isinstance(field, dict):
        return ""
    translations = field.get("translation")
    if not isinstance(translations, list) or not translations:
        return ""
    for item in translations:
        if isinstance(item, dict) and item.get("language", "").startswith("en"):
            return str(item.get("text", "")).strip()
    first = translations[0]
    if isinstance(first, dict):
        return str(first.get("text", "")).strip()
    return ""


def _rail_lines(informed_entities: Any) -> tuple[str, ...]:
    lines: list[str] = []
    if not isinstance(informed_entities, list):
        return ()
    for entity in informed_entities:
        if not isinstance(entity, dict):
            continue
        route_id = str(entity.get("route_id") or "").upper()
        if not route_id:
            continue
        for token, line in _ROUTE_TOKENS.items():
            if token in route_id and line not in lines:
                lines.append(line)
    return tuple(lines)


def _to_datetime(timestamp: Any, tz: tzinfo) -> datetime | None:
    try:
        value = int(timestamp)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return datetime.fromtimestamp(value, tz)


def _end_date(end_dt: datetime) -> date:
    """The last calendar day a period covers.

    An end at exactly midnight means "through the end of the previous day"
    (common GTFS convention), so it must not spill into the next date.
    """
    if end_dt.time() == time.min:
        return (end_dt - timedelta(seconds=1)).date()
    return end_dt.date()


def _is_effectively_all_day(start_dt: datetime, end_dt: datetime) -> bool:
    """True when the period covers whole days (midnight to ~midnight)."""
    return start_dt.time() == time.min and (
        end_dt.time() == time.min or end_dt.time() >= time(23, 59)
    )


def parse_service_alerts(
    payload: dict[str, Any], reference: date, tz: tzinfo = NZ_TZ
) -> list[Closure]:
    """Convert a service alerts feed into rail Closure records.

    Alerts that do not affect a rail line, or whose effect is not a service
    reduction, are skipped. An alert with no end time is treated as ongoing
    (its end tracks ``reference`` while the alert stays in the feed).
    """
    closures: list[Closure] = []
    seen: set[tuple] = set()

    for entity in _entities(payload):
        alert = entity.get("alert") if isinstance(entity, dict) else None
        if not isinstance(alert, dict):
            continue

        lines = _rail_lines(alert.get("informed_entity"))
        if not lines:
            continue

        effect = str(alert.get("effect") or "UNKNOWN_EFFECT").upper()
        closure_type = _EFFECT_MAP.get(effect, "partial")
        if closure_type is None:
            continue

        header = _translated(alert.get("header_text"))
        description = _translated(alert.get("description_text"))
        text = " — ".join(part for part in (header, description) if part)
        if not text:
            text = f"Service alert ({effect.replace('_', ' ').title()})"
        # AT sometimes tags full closures with a weaker effect code
        # ("Full Network Closure" alerts carrying REDUCED_SERVICE); trust
        # an explicit full-closure announcement in the text.
        if closure_type == "partial" and looks_like_full_closure(text):
            closure_type = "full"

        periods = alert.get("active_period")
        if not isinstance(periods, list) or not periods:
            periods = [{}]
        for period in periods:
            if not isinstance(period, dict):
                continue
            start_dt = _to_datetime(period.get("start"), tz)
            end_dt = _to_datetime(period.get("end"), tz)

            if start_dt is None and end_dt is None:
                # No period at all: treat as active right now, all day.
                start, end = reference, reference
            elif start_dt is None:
                end = _end_date(end_dt)
                start = min(reference, end)
            elif end_dt is None:
                # Open-ended alert: ongoing while it remains in the feed.
                start = start_dt.date()
                end = max(reference, start)
                end_dt = None
                if start_dt.time() == time.min:
                    start_dt = None
            else:
                start = start_dt.date()
                end = _end_date(end_dt)
                if _is_effectively_all_day(start_dt, end_dt):
                    start_dt = end_dt = None
            if end < start:
                continue

            key = (lines, start, end, closure_type, text)
            if key in seen:
                continue
            seen.add(key)
            closures.append(
                Closure(
                    lines=lines,
                    start=start,
                    end=end,
                    closure_type=closure_type,
                    description=text,
                    source_heading=header,
                    source="alerts",
                    start_dt=start_dt,
                    end_dt=end_dt,
                )
            )

    closures.sort(key=lambda c: (c.start, c.end, c.lines))
    return closures


def combine_sources(
    website: list[Closure], alerts: list[Closure]
) -> list[Closure]:
    """Merge website and alert closures, preferring alert records.

    A website closure is dropped when an alert closure covers the same
    period with the same closure type and touches the same line(s) — the
    alert record carries authoritative timestamps and text.
    """
    combined = list(alerts)
    for closure in website:
        duplicate = any(
            alert.start == closure.start
            and alert.end == closure.end
            and alert.closure_type == closure.closure_type
            and set(alert.lines) & set(closure.lines)
            for alert in alerts
        )
        if not duplicate:
            combined.append(closure)
    combined.sort(key=lambda c: (c.start, c.end, c.lines))
    return combined

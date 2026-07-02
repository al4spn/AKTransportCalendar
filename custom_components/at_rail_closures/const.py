"""Constants for the Auckland Transport Rail Closures integration."""

from __future__ import annotations

DOMAIN = "at_rail_closures"

CLOSURES_URL = (
    "https://at.govt.nz/bus-train-ferry/service-announcements/planned-rail-closures"
)

# at.govt.nz returns 403 to non-browser clients, so we present ourselves as a
# regular desktop browser.
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-NZ,en;q=0.9",
}

CONF_UPDATE_HOURS = "update_hours"
DEFAULT_UPDATE_HOURS = 6

# How far ahead (days) the "upcoming" attribute lists look.
UPCOMING_WINDOW_DAYS = 90
# Cap list attributes so they stay recorder-friendly.
MAX_ATTR_CLOSURES = 15

ATTRIBUTION = "Data from Auckland Transport (at.govt.nz)"

# Network-level status sensor states.
STATE_GOOD_SERVICE = "good_service"
STATE_REDUCED_SERVICE = "reduced_service"
STATE_CLOSURES_ACTIVE = "closures_active"

# Per-line status sensor states.
LINE_STATE_GOOD = "good_service"
LINE_STATE_PARTIAL = "partial_closure"
LINE_STATE_CLOSED = "closed"

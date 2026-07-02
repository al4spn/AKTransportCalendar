"""Diagnostics for the Auckland Transport Rail Closures integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import ATRailConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ATRailConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data.data
    return {
        "fetched_at": data.fetched_at.isoformat(),
        "closure_count": len(data.closures),
        "closures": [closure.as_dict() for closure in data.closures],
    }

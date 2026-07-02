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
        "website_ok": data.website_ok,
        "alerts_ok": data.alerts_ok,
        "api_key_configured": entry.runtime_data.api_key is not None,
        "closure_count": len(data.closures),
        "closures": [closure.as_dict() for closure in data.closures],
    }

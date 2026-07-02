"""The Auckland Transport Rail Closures integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .coordinator import ATRailClosuresCoordinator, ATRailConfigEntry
from .parser import RAIL_LINES

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ATRailConfigEntry) -> bool:
    """Set up Auckland Transport Rail Closures from a config entry."""
    coordinator = ATRailClosuresCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _async_remove_disabled_line_entities(hass, entry, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _async_remove_disabled_line_entities(
    hass: HomeAssistant,
    entry: ATRailConfigEntry,
    coordinator: ATRailClosuresCoordinator,
) -> None:
    """Drop registry entries for lines the user has deselected."""
    registry = er.async_get(hass)
    stale_unique_ids: set[str] = set()
    for line in set(RAIL_LINES) - set(coordinator.enabled_lines):
        key = line.lower().replace(" ", "_")
        stale_unique_ids.add(f"{entry.entry_id}_{key}")
        stale_unique_ids.add(f"{entry.entry_id}_calendar_{key}")
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id in stale_unique_ids:
            registry.async_remove(entity.entity_id)


async def _async_update_listener(hass: HomeAssistant, entry: ATRailConfigEntry) -> None:
    """Reload the entry when options (interval, key, lines) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ATRailConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

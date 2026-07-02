"""Data update coordinator for Auckland Transport rail closures."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CLOSURES_URL,
    CONF_UPDATE_HOURS,
    DEFAULT_UPDATE_HOURS,
    DOMAIN,
    REQUEST_HEADERS,
)
from .parser import Closure, parse_closures

_LOGGER = logging.getLogger(__name__)

ATRailConfigEntry = ConfigEntry["ATRailClosuresCoordinator"]


@dataclass
class RailClosuresData:
    """Parsed closure data plus fetch metadata."""

    closures: list[Closure]
    fetched_at: datetime


class ATRailClosuresCoordinator(DataUpdateCoordinator[RailClosuresData]):
    """Fetch and parse the AT planned rail closures page."""

    config_entry: ATRailConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ATRailConfigEntry) -> None:
        update_hours = entry.options.get(CONF_UPDATE_HOURS, DEFAULT_UPDATE_HOURS)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(hours=update_hours),
        )

    async def _async_update_data(self) -> RailClosuresData:
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(30):
                response = await session.get(CLOSURES_URL, headers=REQUEST_HEADERS)
                if response.status == 403:
                    raise UpdateFailed(
                        "at.govt.nz rejected the request (HTTP 403); the site "
                        "may have tightened its bot protection"
                    )
                response.raise_for_status()
                html = await response.text()
        except TimeoutError as err:
            raise UpdateFailed("Timeout fetching planned rail closures") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error fetching planned rail closures: {err}") from err

        today = dt_util.now().date()
        closures = await self.hass.async_add_executor_job(parse_closures, html, today)
        if not closures:
            _LOGGER.warning(
                "No closures parsed from %s - either there are genuinely no "
                "planned closures, or the page layout has changed",
                CLOSURES_URL,
            )
        return RailClosuresData(closures=closures, fetched_at=dt_util.utcnow())

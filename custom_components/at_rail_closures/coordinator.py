"""Data update coordinator for Auckland Transport rail closures."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .alerts import NZ_TZ, combine_sources, parse_service_alerts
from .const import (
    CLOSURES_URL,
    CONF_API_KEY,
    CONF_LINES,
    CONF_UPDATE_HOURS,
    DEFAULT_UPDATE_HOURS,
    DOMAIN,
    REQUEST_HEADERS,
    SERVICE_ALERTS_URL,
)
from .parser import RAIL_LINES, Closure, parse_closures

_LOGGER = logging.getLogger(__name__)

ATRailConfigEntry = ConfigEntry["ATRailClosuresCoordinator"]


def _api_headers(api_key: str) -> dict[str, str]:
    return {
        "Ocp-Apim-Subscription-Key": api_key,
        "Accept": "application/json",
    }


async def async_validate_api_key(hass: HomeAssistant, api_key: str) -> str | None:
    """Check an AT API key against the service alerts endpoint.

    Returns an error code for the config flow, or None when the key works.
    """
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(15):
            response = await session.get(
                SERVICE_ALERTS_URL, headers=_api_headers(api_key)
            )
    except (TimeoutError, aiohttp.ClientError):
        return "cannot_connect"
    if response.status in (401, 403):
        return "invalid_auth"
    if response.status != 200:
        return "cannot_connect"
    return None


@dataclass
class RailClosuresData:
    """Parsed closure data plus fetch metadata."""

    closures: list[Closure]
    fetched_at: datetime
    website_ok: bool = True
    # None = no API key configured, otherwise success of the last fetch.
    alerts_ok: bool | None = None


class ATRailClosuresCoordinator(DataUpdateCoordinator[RailClosuresData]):
    """Fetch planned closures from the AT website and (optionally) merge in
    the official GTFS-realtime service alerts feed."""

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

    @property
    def api_key(self) -> str | None:
        return self.config_entry.options.get(CONF_API_KEY) or None

    @property
    def enabled_lines(self) -> list[str]:
        """The rail lines the user wants per-line entities for."""
        selected = self.config_entry.options.get(CONF_LINES)
        if selected is None:
            return list(RAIL_LINES)
        return [line for line in RAIL_LINES if line in selected]

    async def _fetch_website(self, session, reference: date) -> list[Closure]:
        async with asyncio.timeout(30):
            response = await session.get(CLOSURES_URL, headers=REQUEST_HEADERS)
            if response.status == 403:
                raise UpdateFailed(
                    "at.govt.nz rejected the request (HTTP 403); the site "
                    "may have tightened its bot protection"
                )
            response.raise_for_status()
            html = await response.text()
        closures = await self.hass.async_add_executor_job(
            parse_closures, html, reference
        )
        if not closures:
            _LOGGER.warning(
                "No closures parsed from %s - either there are genuinely no "
                "planned closures, or the page layout has changed",
                CLOSURES_URL,
            )
        return closures

    async def _fetch_alerts(
        self, session, reference: date, api_key: str
    ) -> list[Closure]:
        async with asyncio.timeout(30):
            response = await session.get(
                SERVICE_ALERTS_URL, headers=_api_headers(api_key)
            )
            if response.status in (401, 403):
                raise UpdateFailed(
                    "AT API rejected the API key (HTTP "
                    f"{response.status}); check it on dev-portal.at.govt.nz"
                )
            response.raise_for_status()
            payload = await response.json(content_type=None)
        return parse_service_alerts(payload, reference)

    async def _async_update_data(self) -> RailClosuresData:
        session = async_get_clientsession(self.hass)
        reference = dt_util.now(NZ_TZ).date()
        api_key = self.api_key

        website_closures: list[Closure] = []
        alert_closures: list[Closure] = []
        website_error: Exception | None = None
        alerts_error: Exception | None = None

        try:
            website_closures = await self._fetch_website(session, reference)
        except (UpdateFailed, TimeoutError, aiohttp.ClientError) as err:
            website_error = err

        if api_key:
            try:
                alert_closures = await self._fetch_alerts(
                    session, reference, api_key
                )
            except (UpdateFailed, TimeoutError, aiohttp.ClientError) as err:
                alerts_error = err

        if website_error and (not api_key or alerts_error):
            raise UpdateFailed(
                f"Website fetch failed ({website_error})"
                + (f"; alerts fetch failed ({alerts_error})" if alerts_error else "")
            ) from website_error
        if website_error:
            _LOGGER.warning(
                "Website fetch failed, continuing with service alerts only: %s",
                website_error,
            )
        if alerts_error:
            _LOGGER.warning(
                "Service alerts fetch failed, continuing with website data "
                "only: %s",
                alerts_error,
            )

        return RailClosuresData(
            closures=combine_sources(website_closures, alert_closures),
            fetched_at=dt_util.utcnow(),
            website_ok=website_error is None,
            alerts_ok=None if not api_key else alerts_error is None,
        )

"""Tests for the GTFS-realtime service alerts mapper."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from at_rail_closures.alerts import combine_sources, parse_service_alerts
from at_rail_closures.parser import NZ_TZ, Closure

FIXTURE = Path(__file__).parent / "fixtures" / "service_alerts.json"
TODAY = date(2026, 7, 2)


@pytest.fixture(name="closures")
def closures_fixture():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return parse_service_alerts(payload, TODAY)


def test_only_rail_service_reductions_kept(closures):
    # 3 rail alerts survive; bus, stop-only and NO_EFFECT alerts are dropped.
    assert len(closures) == 3
    assert all(c.source == "alerts" for c in closures)


def test_full_closure_dates_converted_to_nz_days(closures):
    full = [c for c in closures if c.closure_type == "full"]
    assert len(full) == 1
    assert full[0].start == date(2026, 7, 9)
    assert full[0].end == date(2026, 7, 12)
    assert set(full[0].lines) == {"Southern Line", "Onehunga Line", "Western Line"}
    assert "Buses replace trains" in full[0].description
    # Midnight-to-23:59 periods are normalized to all-day.
    assert full[0].is_all_day


def test_same_day_partial_closure_keeps_exact_times(closures):
    eastern = [c for c in closures if c.lines == ("Eastern Line",)]
    assert len(eastern) == 1
    assert eastern[0].start == eastern[0].end == date(2026, 7, 4)
    assert eastern[0].closure_type == "partial"
    assert eastern[0].start_dt == datetime(2026, 7, 4, 6, 0, tzinfo=NZ_TZ)
    assert eastern[0].end_dt == datetime(2026, 7, 4, 12, 0, tzinfo=NZ_TZ)


def test_open_ended_alert_tracks_reference_date(closures):
    western = [c for c in closures if c.lines == ("Western Line",)]
    assert len(western) == 1
    assert western[0].start == date(2026, 7, 1)
    assert western[0].end == TODAY  # ongoing while the alert stays in feed
    assert western[0].closure_type == "partial"
    assert western[0].start_dt == datetime(2026, 7, 1, 4, 0, tzinfo=NZ_TZ)
    assert western[0].end_dt is None


def test_plain_gtfs_rt_envelope():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert parse_service_alerts(payload["response"], TODAY) == parse_service_alerts(
        payload, TODAY
    )


def test_empty_and_malformed_payloads():
    assert parse_service_alerts({}, TODAY) == []
    assert parse_service_alerts({"response": None}, TODAY) == []
    assert parse_service_alerts({"entity": [{"id": "x"}, {"alert": {}}]}, TODAY) == []


def test_combine_sources_prefers_alert_duplicates(closures):
    website = [
        # Same period/type/line as the alert full closure -> dropped.
        Closure(
            lines=("Southern Line",),
            start=date(2026, 7, 9),
            end=date(2026, 7, 12),
            closure_type="full",
            description="Full closure from Thursday 9 to Sunday 12 July.",
        ),
        # Future closure only the website knows about -> kept.
        Closure(
            lines=("Southern Line",),
            start=date(2026, 8, 15),
            end=date(2026, 8, 16),
            closure_type="full",
            description="Full closure of the entire rail network.",
        ),
    ]
    combined = combine_sources(website, closures)
    assert len(combined) == len(closures) + 1
    website_kept = [c for c in combined if c.source == "website"]
    assert len(website_kept) == 1
    assert website_kept[0].start == date(2026, 8, 15)

"""Tests for the planned rail closures parser."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from at_rail_closures.parser import (
    NZ_TZ,
    RAIL_LINES,
    active_closures,
    closures_for_line,
    parse_closures,
    upcoming_closures,
)

FIXTURE = Path(__file__).parent / "fixtures" / "planned_rail_closures.html"
TODAY = date(2026, 7, 2)


@pytest.fixture(name="closures")
def closures_fixture():
    return parse_closures(FIXTURE.read_text(encoding="utf-8"), TODAY)


def test_parses_expected_number_of_closures(closures):
    # 1 Eastern + 3 Southern + 2 Western + 1 Onehunga + 1 all-lines (Aug)
    # + 1 all-lines (Xmas) + 2 Southern (Jan single days) = 11
    assert len(closures) == 11


def test_active_closure_detected(closures):
    active = active_closures(closures, TODAY)
    assert len(active) == 1
    closure = active[0]
    assert closure.lines == ("Eastern Line",)
    assert closure.start == date(2026, 6, 29)
    assert closure.end == date(2026, 7, 3)
    assert closure.closure_type == "partial"


def test_single_day_partial_closure(closures):
    southern = closures_for_line(closures, "Southern Line")
    partial_4_july = [c for c in southern if c.start == date(2026, 7, 4)]
    assert len(partial_4_july) == 1
    assert partial_4_july[0].end == date(2026, 7, 4)
    assert partial_4_july[0].closure_type == "partial"
    assert "Newmarket" in partial_4_july[0].description


def test_short_range_full_closure(closures):
    onehunga = closures_for_line(closures, "Onehunga Line")
    assert len(onehunga) >= 1
    july = [c for c in onehunga if c.start == date(2026, 7, 9)]
    assert len(july) == 1
    assert july[0].end == date(2026, 7, 12)
    assert july[0].closure_type == "full"


def test_all_lines_heading_applies_to_bullets(closures):
    august = [c for c in closures if c.start == date(2026, 8, 15)]
    assert len(august) == 1
    assert set(august[0].lines) == set(RAIL_LINES)
    assert august[0].end == date(2026, 8, 16)
    assert august[0].closure_type == "full"


def test_cross_year_range_with_explicit_years(closures):
    xmas = [c for c in closures if c.start == date(2026, 12, 26)]
    assert len(xmas) == 1
    assert xmas[0].end == date(2027, 1, 11)
    assert set(xmas[0].lines) == set(RAIL_LINES)


def test_year_rollover_inferred_for_january_dates(closures):
    # "17 and 18 January" with no year, parsed on 2 July 2026 -> 2027.
    january = [c for c in closures if c.start == date(2027, 1, 17)]
    assert len(january) == 1
    assert january[0].lines == ("Southern Line",)
    later = [c for c in closures if c.start == date(2027, 1, 18)]
    assert len(later) == 1


def test_upcoming_window(closures):
    upcoming = upcoming_closures(closures, TODAY, window_days=30)
    starts = {c.start for c in upcoming}
    assert date(2026, 7, 4) in starts
    assert date(2026, 7, 9) in starts
    assert date(2026, 8, 15) not in starts  # beyond 30-day window
    # The active Eastern Line closure is not "upcoming".
    assert date(2026, 6, 29) not in starts


def test_multi_closure_sentence_run_is_split_per_sentence():
    # Regression: AT packs several closures into one bullet. The full-closure
    # classification and "until 12pm" clock time must not leak between them.
    html = """
    <main><h3>Southern Line</h3><ul><li>Southern Line: Partial closure until
    12pm between Waitematā and Newmarket on 4 July. Full closure from 9 to
    12 July. Partial closure until 12pm between Waitematā and Newmarket on
    25 July.</li></ul></main>
    """
    closures = parse_closures(html, TODAY)
    assert len(closures) == 3

    first = [c for c in closures if c.start == date(2026, 7, 4)][0]
    assert first.closure_type == "partial"
    assert first.end_dt == datetime(2026, 7, 4, 12, 0, tzinfo=NZ_TZ)

    middle = [c for c in closures if c.start == date(2026, 7, 9)][0]
    assert middle.end == date(2026, 7, 12)
    assert middle.closure_type == "full"
    assert middle.is_all_day  # no "until 12pm" leakage from the sentence before

    last = [c for c in closures if c.start == date(2026, 7, 25)][0]
    assert last.closure_type == "partial"
    assert last.end_dt == datetime(2026, 7, 25, 12, 0, tzinfo=NZ_TZ)


def test_undated_detail_sentence_attaches_to_previous(closures):
    southern = closures_for_line(closures, "Southern Line")
    partial_4_july = [c for c in southern if c.start == date(2026, 7, 4)][0]
    assert "Rail buses replace trains" in partial_4_july.description


def test_recent_past_dates_stay_in_current_year():
    html = """
    <main><h3>Southern Line</h3>
    <ul><li>Partial closure on 13 and 20 June.</li></ul></main>
    """
    closures = parse_closures(html, TODAY)
    assert {c.start for c in closures} == {date(2026, 6, 13), date(2026, 6, 20)}


def test_clock_times_extracted(closures):
    southern = closures_for_line(closures, "Southern Line")
    partial_4_july = [c for c in southern if c.start == date(2026, 7, 4)][0]
    # "Partial closure until 12pm ... on Saturday 4 July"
    assert partial_4_july.start_dt is None
    assert partial_4_july.end_dt == datetime(2026, 7, 4, 12, 0, tzinfo=NZ_TZ)
    assert not partial_4_july.is_all_day


def test_multi_day_closure_without_times_is_all_day(closures):
    onehunga = closures_for_line(closures, "Onehunga Line")
    july = [c for c in onehunga if c.start == date(2026, 7, 9)][0]
    assert july.is_all_day
    assert july.start_dt is None and july.end_dt is None


def test_titles(closures):
    august = [c for c in closures if c.start == date(2026, 8, 15)][0]
    assert august.title == "All lines – Full closure"
    eastern = active_closures(closures, TODAY)[0]
    assert eastern.title == "Eastern Line – Partial closure"


def test_no_closures_in_empty_page():
    assert parse_closures("<html><body><p>Nothing here</p></body></html>", TODAY) == []


def test_intro_text_without_dates_is_ignored(closures):
    # The intro paragraph mentions no dates, the footer has no lines.
    for closure in closures:
        assert closure.start is not None
        assert closure.lines

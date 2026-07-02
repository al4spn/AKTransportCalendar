"""Parser for the Auckland Transport planned rail closures page.

This module is deliberately free of Home Assistant imports so it can be unit
tested standalone. It scrapes semi-structured CMS content, so it works from
heuristics rather than a fixed schema:

* Headings (h2-h4) provide context: a rail line name ("Southern Line"),
  a month/year ("July 2026") used as a year hint, or a closure title with
  its own date range.
* Bullet points and paragraphs beneath a heading provide the individual
  closure periods and their detail text.
* A block yields closures once we can resolve both affected line(s) and at
  least one date (from the block itself, falling back to heading context).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag

NZ_TZ = ZoneInfo("Pacific/Auckland")

RAIL_LINES = ("Southern Line", "Eastern Line", "Western Line", "Onehunga Line")

_LINE_KEYWORDS = {
    "southern": "Southern Line",
    "eastern": "Eastern Line",
    "western": "Western Line",
    "onehunga": "Onehunga Line",
}
_ALL_LINES_RE = re.compile(
    r"all (rail )?lines|entire (rail )?network|whole (rail )?network"
    r"|network[- ]wide|all train (lines|services)",
    re.IGNORECASE,
)

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_RE = (
    r"(January|February|March|April|May|June|July|August|September|October"
    r"|November|December)"
)
_WEEKDAY_RE = r"(?:(?:Mon|Tues?|Wednes|Thurs?|Fri|Satur|Sun)day,?\s+)?"
_SEP_RE = r"(?:to|until|through to|–|—|-)"

# "3 April to 27 April 2026" / "Friday 3 April to Monday 27 April" (cross-month ok)
_RANGE_FULL_RE = re.compile(
    rf"{_WEEKDAY_RE}(\d{{1,2}})\s+{_MONTH_RE}(?:\s+(\d{{4}}))?"
    rf"\s*{_SEP_RE}\s*"
    rf"{_WEEKDAY_RE}(\d{{1,2}})\s+{_MONTH_RE}(?:\s+(\d{{4}}))?",
    re.IGNORECASE,
)
# "9 to 12 July" / "Thursday 9 – Sunday 12 July 2026"
_RANGE_SHORT_RE = re.compile(
    rf"{_WEEKDAY_RE}(\d{{1,2}})\s*{_SEP_RE}\s*{_WEEKDAY_RE}(\d{{1,2}})\s+"
    rf"{_MONTH_RE}(?:\s+(\d{{4}}))?",
    re.IGNORECASE,
)
# "13 and 20 June" / "4, 11 and 25 July 2026" / "Saturday 4 July"
_DAY_LIST_RE = re.compile(
    rf"{_WEEKDAY_RE}(\d{{1,2}}(?:\s*(?:,|and|&)\s*{_WEEKDAY_RE}\d{{1,2}})*)\s+"
    rf"{_MONTH_RE}(?:\s+(\d{{4}}))?",
    re.IGNORECASE,
)
# Heading like "July 2026" used as a year hint for dates below it.
_MONTH_YEAR_HEADING_RE = re.compile(
    rf"^\s*{_MONTH_RE}\s+(\d{{4}})\s*$", re.IGNORECASE
)

# Clock times like "until 12pm", "from 8.30pm", "until 11:59 am".
_UNTIL_TIME_RE = re.compile(
    r"\buntil\s+(\d{1,2})(?:[:.](\d{2}))?\s*([ap])\.?m\b", re.IGNORECASE
)
_FROM_TIME_RE = re.compile(
    r"\bfrom\s+(\d{1,2})(?:[:.](\d{2}))?\s*([ap])\.?m\b", re.IGNORECASE
)

_FULL_RE = re.compile(
    r"full (?:network )?closure|closure of the entire|fully closed"
    r"|all (?:train )?lines (?:are|will be) closed"
    r"|no trains? (?:will run|running)? ?on",
    re.IGNORECASE,
)
_PARTIAL_RE = re.compile(
    r"partial closure|early closure|earlier closure|closes? early|until \d|"
    r"from \d{1,2}([:.]\d{2})?\s*[ap]m|reduced (service|frequency)|"
    r"(?:closure|closed|no trains?) between [A-ZĀĒĪŌŪ]",
    re.IGNORECASE,
)

_CONTENT_TAGS = ("h2", "h3", "h4", "li", "p", "td")
_HEADING_TAGS = ("h2", "h3", "h4")


@dataclass(frozen=True)
class Closure:
    """A single planned closure period affecting one or more lines."""

    lines: tuple[str, ...]
    start: date
    end: date
    closure_type: str  # "full" or "partial"
    description: str
    source_heading: str = ""
    source: str = "website"  # "website" or "alerts"
    # Exact NZ-local start/end when known (alerts feed timestamps, or a
    # clock time parsed from the announcement text). None = all-day.
    start_dt: datetime | None = None
    end_dt: datetime | None = None

    @property
    def title(self) -> str:
        lines = (
            "All lines" if set(self.lines) == set(RAIL_LINES) else " & ".join(self.lines)
        )
        kind = "Full closure" if self.closure_type == "full" else "Partial closure"
        return f"{lines} – {kind}"

    @property
    def is_all_day(self) -> bool:
        return self.start_dt is None and self.end_dt is None

    def is_active(self, today: date) -> bool:
        return self.start <= today <= self.end

    def is_active_at(self, now: datetime) -> bool:
        """Whether the closure is in effect at this moment.

        Time-aware: a "from 9:30pm" night-works closure is only active from
        9:30pm, not all day. Closures without exact times fall back to
        whole-day semantics.
        """
        if not self.is_active(now.date()):
            return False
        if self.start_dt is not None and now < self.start_dt:
            return False
        if self.end_dt is not None and now > self.end_dt:
            return False
        return True

    def is_upcoming(self, today: date) -> bool:
        return self.start > today

    def as_dict(self) -> dict:
        result = {
            "title": self.title,
            "lines": list(self.lines),
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "closure_type": self.closure_type,
            "description": self.description,
            "source": self.source,
        }
        if self.start_dt is not None:
            result["start_time"] = self.start_dt.isoformat()
        if self.end_dt is not None:
            result["end_time"] = self.end_dt.isoformat()
        return result


@dataclass
class _Context:
    """Heading context carried down to the blocks beneath it."""

    lines: tuple[str, ...] = ()
    year_hint: int | None = None
    dates: tuple[tuple[date, date], ...] = ()
    heading: str = ""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _detect_lines(text: str) -> tuple[str, ...]:
    if _ALL_LINES_RE.search(text):
        return RAIL_LINES
    lower = text.lower()
    found = tuple(
        name for key, name in _LINE_KEYWORDS.items() if key in lower
    )
    return found


def _infer_year(month: int, day: int, reference: date, year_hint: int | None) -> int:
    """Pick a year for a date given without one.

    Prefer the section's "Month YYYY" heading hint when it matches sensibly;
    otherwise assume the current year, rolling forward when the date would be
    long past (announcements are about upcoming work).
    """
    if year_hint is not None:
        for candidate_year in (year_hint, year_hint + 1):
            candidate = date(candidate_year, month, day)
            if candidate >= reference - timedelta(days=45):
                return candidate_year
        return year_hint
    candidate = date(reference.year, month, day)
    if candidate < reference - timedelta(days=45):
        return reference.year + 1
    return reference.year


def _make_date(
    day: int, month: int, year: int | None, reference: date, year_hint: int | None
) -> date | None:
    try:
        if year is not None:
            return date(year, month, day)
        return date(_infer_year(month, day, reference, year_hint), month, day)
    except ValueError:
        return None


def _extract_dates(
    text: str, reference: date, year_hint: int | None
) -> list[tuple[date, date]]:
    """Extract (start, end) date ranges from free text.

    Patterns are applied most-specific first and matched spans are blanked
    out so a range is not re-counted by the day-list pattern.
    """
    ranges: list[tuple[date, date]] = []
    working = text

    def blank(match: re.Match) -> str:
        return " " * (match.end() - match.start())

    for match in list(_RANGE_FULL_RE.finditer(working)):
        d1, m1, y1, d2, m2, y2 = match.groups()
        year2 = int(y2) if y2 else None
        year1 = int(y1) if y1 else None
        month1, month2 = _MONTHS[m1.lower()], _MONTHS[m2.lower()]
        end = _make_date(int(d2), month2, year2, reference, year_hint)
        if end is not None and year1 is None:
            # The year of the end date anchors the start date too.
            start = date(
                end.year - 1 if month1 > month2 else end.year, month1, int(d1)
            )
        else:
            start = _make_date(int(d1), month1, year1, reference, year_hint)
        if start and end and start <= end:
            ranges.append((start, end))
            working = working[: match.start()] + blank(match) + working[match.end():]

    for match in list(_RANGE_SHORT_RE.finditer(working)):
        d1, d2, month_name, year_str = match.groups()
        month = _MONTHS[month_name.lower()]
        year = int(year_str) if year_str else None
        end = _make_date(int(d2), month, year, reference, year_hint)
        start = date(end.year, month, int(d1)) if end else None
        if start and end and start <= end:
            ranges.append((start, end))
            working = working[: match.start()] + blank(match) + working[match.end():]

    for match in _DAY_LIST_RE.finditer(working):
        day_list, month_name, year_str = match.groups()
        month = _MONTHS[month_name.lower()]
        year = int(year_str) if year_str else None
        for day_str in re.findall(r"\d{1,2}", day_list):
            day = _make_date(int(day_str), month, year, reference, year_hint)
            if day:
                ranges.append((day, day))

    return ranges


def looks_like_full_closure(text: str) -> bool:
    """Whether free text announces a full (rather than partial) closure."""
    return _FULL_RE.search(text) is not None


def _closure_type(text: str) -> str:
    if looks_like_full_closure(text):
        return "full"
    return "partial" if _PARTIAL_RE.search(text) else "full"


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_into_segments(
    text: str, reference: date, year_hint: int | None
) -> list[tuple[str, list[tuple[date, date]]]]:
    """Split a block into sentence-level segments, each with its own dates.

    AT often packs several closures into one bullet ("Partial closure until
    12pm ... on 4 July. Full closure from 9 to 12 July."), so classification
    and clock times must not leak between sentences. Undated sentences are
    attached to the preceding dated sentence (they carry detail like "Rail
    buses replace trains"); undated leading sentences prefix the first
    segment.
    """
    segments: list[list] = []
    leading: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        dates = _extract_dates(sentence, reference, year_hint)
        if dates:
            if leading and not segments:
                sentence = " ".join([*leading, sentence])
            leading = []
            segments.append([sentence, dates])
        elif segments:
            segments[-1][0] += f" {sentence}"
        else:
            leading.append(sentence)
    return [(seg_text, dates) for seg_text, dates in segments]


def _parse_clock(match: re.Match) -> time:
    hour = int(match.group(1)) % 12
    if match.group(3).lower() == "p":
        hour += 12
    return time(hour, int(match.group(2) or 0))


def _extract_clock_times(text: str) -> tuple[time | None, time | None]:
    """Pull "from 8pm" / "until 12pm" style clock times out of a block."""
    start_match = _FROM_TIME_RE.search(text)
    end_match = _UNTIL_TIME_RE.search(text)
    return (
        _parse_clock(start_match) if start_match else None,
        _parse_clock(end_match) if end_match else None,
    )


def _find_content_root(soup: BeautifulSoup) -> Tag:
    for selector in (
        "main",
        "#main-content",
        "#content",
        "article",
        '[role="main"]',
        ".main-content",
    ):
        node = soup.select_one(selector)
        if node is not None:
            return node
    return soup.body or soup


def parse_closures(html: str, reference: date) -> list[Closure]:
    """Parse the planned rail closures page into Closure records.

    ``reference`` (today's date in NZ) is used to infer missing years.
    """
    soup = BeautifulSoup(html, "html.parser")
    root = _find_content_root(soup)

    closures: list[Closure] = []
    seen: set[tuple] = set()
    context = _Context()

    for element in root.find_all(_CONTENT_TAGS):
        # Skip nested duplicates (e.g. a <p> inside an <li> we already saw).
        if element.find_parent("li") is not None and element.name != "li":
            continue
        text = _clean(element.get_text(" "))
        if not text:
            continue

        if element.name in _HEADING_TAGS:
            month_year = _MONTH_YEAR_HEADING_RE.match(text)
            if month_year:
                # A "July 2026" heading only refines the year hint.
                context = _Context(
                    lines=context.lines,
                    year_hint=int(month_year.group(2)),
                    heading=text,
                )
                continue
            heading_lines = _detect_lines(text)
            heading_dates = _extract_dates(text, reference, context.year_hint)
            context = _Context(
                lines=heading_lines,
                year_hint=context.year_hint,
                dates=tuple(heading_dates),
                heading=text,
            )
            continue

        block_lines = _detect_lines(text) or context.lines
        if not block_lines:
            continue

        segments = _split_into_segments(text, reference, context.year_hint)
        if not segments:
            # No dated sentence in the block: fall back to heading dates.
            if not context.dates:
                continue
            segments = [(text, list(context.dates))]

        for seg_text, seg_dates in segments:
            closure_type = _closure_type(seg_text)
            start_clock, end_clock = _extract_clock_times(seg_text)
            for start, end in seg_dates:
                key = (block_lines, start, end, closure_type, seg_text)
                if key in seen:
                    continue
                seen.add(key)
                closures.append(
                    Closure(
                        lines=block_lines,
                        start=start,
                        end=end,
                        closure_type=closure_type,
                        description=seg_text,
                        source_heading=context.heading,
                        start_dt=(
                            datetime.combine(start, start_clock, NZ_TZ)
                            if start_clock
                            else None
                        ),
                        end_dt=(
                            datetime.combine(end, end_clock, NZ_TZ)
                            if end_clock
                            else None
                        ),
                    )
                )

    closures.sort(key=lambda c: (c.start, c.end, c.lines))
    return closures


def active_closures(closures: list[Closure], today: date) -> list[Closure]:
    return [c for c in closures if c.is_active(today)]


def active_closures_at(closures: list[Closure], now: datetime) -> list[Closure]:
    return [c for c in closures if c.is_active_at(now)]


def upcoming_closures(
    closures: list[Closure], today: date, window_days: int | None = None
) -> list[Closure]:
    horizon = today + timedelta(days=window_days) if window_days else None
    return [
        c
        for c in closures
        if c.is_upcoming(today) and (horizon is None or c.start <= horizon)
    ]


def closures_for_line(closures: list[Closure], line: str) -> list[Closure]:
    return [c for c in closures if line in c.lines]



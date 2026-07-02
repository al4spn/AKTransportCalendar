# Auckland Transport Rail Closures for Home Assistant

A custom integration that tracks Auckland rail network closures and turns
them into Home Assistant entities: an overall network status, a status sensor
per rail line, the next upcoming closure, and a calendar of all planned
closures.

It combines two sources:

1. **AT's [planned rail closures](https://at.govt.nz/bus-train-ferry/service-announcements/planned-rail-closures)
   page** (scraped) — the long-range closure programme, announced months
   ahead. Works with no account or API key.
2. **AT's official GTFS-realtime service alerts feed** (optional, needs a
   free API key from the [AT developer portal](https://dev-portal.at.govt.nz/)) —
   authoritative, structured data with exact timestamps, including *unplanned*
   disruptions (delays, faults) the web page never shows.

When both sources report the same closure, the API record wins. Closures the
API doesn't know about yet (e.g. next month's programme) still come from the
web page, so the calendar keeps its long horizon.

## Entities

All entities belong to one **Auckland Rail Network** device:

| Entity | Type | What it shows |
|---|---|---|
| `sensor.auckland_rail_network_network_status` | enum | `good_service`, `reduced_service` (partial closure today) or `closures_active` (full closure today). Attributes carry the full `active_closures` and `upcoming_closures` lists. |
| `sensor.auckland_rail_network_southern_line` (also `_eastern_line`, `_western_line`, `_onehunga_line`) | enum | `good_service`, `partial_closure` or `closed` for that line, with that line's upcoming closures as attributes. |
| `sensor.auckland_rail_network_next_closure` | timestamp | Start of the next planned closure — renders as "in 5 days" on tile cards. Title, lines, dates and description in attributes. |
| `binary_sensor.auckland_rail_network_closure_active` | problem | On while any planned closure is in effect. Handy for conditional cards and automations. |
| `calendar.auckland_rail_network_closures` | calendar | Every planned closure as an event per affected line, titled with the line name (e.g. "Southern Line – Full closure"). Events carry exact start/end times when the source provides them (API timestamps, or "until 12pm" style text); otherwise they are all-day events. |

Which lines get status sensors and calendar events is selectable
(checkboxes) in the setup dialog and later from the integration's
**Configure** button. The website is re-checked every 6 hours by default
(configurable, 1–24 hours).

## Installation

### HACS (recommended)

1. HACS → three-dot menu → **Custom repositories**.
2. Add `al4spn/AKTransportCalendar` with category **Integration**.
3. Search for "Auckland Transport Rail Closures" in HACS and download it.
4. Restart Home Assistant.
5. Settings → Devices & Services → **Add Integration** → "Auckland Transport
   Rail Closures".
6. Optionally paste an AT API key (see below) — or add one later via the
   integration's **Configure** button.

### Getting an AT API key (optional but recommended)

1. Register (free) at the [AT developer portal](https://dev-portal.at.govt.nz/).
2. Subscribe to a product that includes the **Realtime API** (service alerts).
3. Copy your subscription key into the integration's config or options flow.
   The key is validated against the API when you save it.

### Manual

Copy `custom_components/at_rail_closures` into your `config/custom_components`
directory, restart, then add the integration as above.

## Dashboard

### Network status overview (markdown card)

A single card with a headline status and the list of upcoming closures:

```yaml
type: markdown
title: Auckland Rail Network
content: |
  {% set s = 'sensor.auckland_rail_network_network_status' %}
  {% set status = states(s) %}
  {% if status == 'good_service' %}
  ## 🟢 Good service
  No planned closures today.
  {% elif status == 'reduced_service' %}
  ## 🟠 Reduced service
  {% for c in state_attr(s, 'active_closures') %}
  **{{ c.title }}** — {{ c.description }}
  {% endfor %}
  {% else %}
  ## 🔴 Closures in place
  {% for c in state_attr(s, 'active_closures') %}
  **{{ c.title }}** — {{ c.description }}
  {% endfor %}
  {% endif %}

  {% set upcoming = state_attr(s, 'upcoming_closures') or [] %}
  {% if upcoming %}
  ### Upcoming closures
  {% for c in upcoming %}
  - **{{ as_datetime(c.start).strftime('%a %-d %b') }}
    {%- if c.end != c.start %} – {{ as_datetime(c.end).strftime('%a %-d %b') }}{% endif %}**:
    {{ c.title }}
  {% endfor %}
  {% else %}
  *No upcoming closures announced.*
  {% endif %}

  ---
  *[Details on at.govt.nz]({{ state_attr(s, 'source') }})*
```

### Per-line tiles

```yaml
type: grid
columns: 2
square: false
cards:
  - type: tile
    entity: sensor.auckland_rail_network_southern_line
    name: Southern
    color: red
  - type: tile
    entity: sensor.auckland_rail_network_eastern_line
    name: Eastern
    color: yellow
  - type: tile
    entity: sensor.auckland_rail_network_western_line
    name: Western
    color: green
  - type: tile
    entity: sensor.auckland_rail_network_onehunga_line
    name: Onehunga
    color: blue
```

(Colours match AT's line colours; tiles show the translated state such as
"Good service" or "Closed".)

### Closures calendar

Works with the built-in calendar card, or custom cards such as Calendar Card
Pro / Atomic Calendar Revive:

```yaml
type: calendar
entities:
  - calendar.auckland_rail_network_closures
initial_view: listMonth
```

```yaml
type: custom:calendar-card-pro
title: Planned rail closures
entities:
  - entity: calendar.auckland_rail_network_closures
    color: '#e4002b'
days_to_show: 60
show_countdown: true
```

### Alert banner only when something is wrong

```yaml
type: conditional
conditions:
  - condition: state
    entity: binary_sensor.auckland_rail_network_closure_active
    state: "on"
card:
  type: markdown
  content: >-
    ⚠️ **Rail closure in effect** —
    {{ state_attr('binary_sensor.auckland_rail_network_closure_active',
       'closures') | map(attribute='title') | join(', ') }}
```

## Automation ideas

Get a phone notification the evening before a closure starts:

```yaml
triggers:
  - trigger: calendar
    entity_id: calendar.auckland_rail_network_closures
    event: start
    offset: "-08:00:00"   # all-day events start at midnight → fires 4pm the day before
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Rail closure from tomorrow
      message: >-
        {{ trigger.calendar_event.summary }}:
        {{ trigger.calendar_event.description }}
mode: queued
```

## How the data sources work (and their limits)

### Service alerts API (with an API key)

The [GTFS-realtime service alerts feed](https://dev-portal.at.govt.nz/realtime-api)
is polled with your subscription key. Alerts affecting rail routes
(Southern/Eastern/Western/Onehunga) with a service-reducing effect
(`NO_SERVICE`, `REDUCED_SERVICE`, `SIGNIFICANT_DELAYS`, …) become closure
records with exact active periods. `NO_SERVICE` maps to a full closure,
everything else to a partial one. Open-ended alerts are treated as ongoing
while they remain in the feed. Alerts feeds are operational, so they may not
carry the multi-month forward programme — that's why the page scraper stays.

The `network status` sensor exposes `website_ok` and `alerts_feed`
attributes so you can see the health of each source at a glance.

### Website scraper

Auckland Transport does not publish a machine-readable feed of the
*long-range* closure programme, so that part is parsed from the announcement
web page itself:

- Requests are sent with normal browser headers (the site returns
  HTTP 403 to non-browser clients).
- The parser walks the page's headings and bullet points, extracting rail
  line names, NZ-style dates ("Saturday 4 July", "9 to 12 July",
  "26 December 2026 to 11 January 2027") and whether each closure is full or
  partial. Missing years are inferred from the current date and any
  "July 2026"-style section headings.
- If AT restructures the page, parsing may degrade. The integration logs a
  warning when a fetch succeeds but no closures are found, and keeps the last
  good data while fetches fail. Please open an issue with a copy of the page
  if that happens.

## Development

```bash
pip install beautifulsoup4 pytest
pytest tests/
```

The parser (`custom_components/at_rail_closures/parser.py`) has no Home
Assistant dependencies and is covered by tests against a fixture of the AT
page in `tests/fixtures/`.

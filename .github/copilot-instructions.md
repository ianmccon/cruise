# Copilot Instructions — Matrix Home Dashboard

Trust these instructions. Only search the codebase if information here is incomplete or appears incorrect.

## What This Repository Is

A Raspberry Pi kiosk dashboard (Flask/Jinja2) that displays on a fullscreen Chromium browser. Sections: calendar events, date/clock, bin collection schedule, cruise countdown + itinerary with live port temps, weather (PirateWeather API, 3 locations), news ticker, Todoist tasks. All sections refresh via AJAX fragment endpoints — no SPA framework, just plain JS fetching HTML partials and replacing `innerHTML`.

## Repository Layout

```
app.py                         # Entire Flask backend (~680 lines, single file)
templates/index.html           # Main page; includes fragments on first load; JS refreshes via AJAX
templates/fragments/           # HTML partials for each section (current-weather, forecast-weather,
                               #   events, news, bins, todoist)
static/dashboard.js            # Client-side JS: news/events rendering
static/style-matrix2025*.css   # Stylesheets (three themes)
config_matrix.json             # Runtime config — GITIGNORED; copy from .sample, never commit
config_matrix.json.sample      # Config template
bin_schedule.json              # Bin type definitions (name, color, icon path)
requirements.txt               # Flask, gunicorn, icalendar, requests, feedparser, pytest
run.sh                         # Production entry: activates venv, starts gunicorn
gunicorn_conf.py               # bind=0.0.0.0:8000, workers=2
tests/                         # pytest suite (test_app, test_bins_and_buses, test_events_fragment, test_utils)
AGENTS.md                      # Coding conventions — read before making changes
```

No GitHub Actions, no CI pipelines, no linter config, no pre-commit hooks.

## Environment

Python 3.11. Venv at `venv/`. **Always activate before any command:**

```bash
source /home/pi/matrix/venv/bin/activate
```

Install deps once (or after `requirements.txt` changes):

```bash
pip install -r requirements.txt
```

`config_matrix.json` is required at import time. The file exists in production. Do not create or modify it.

## Running Tests — Validated Command

```bash
PYTHONPATH=/home/pi/matrix /home/pi/matrix/venv/bin/python -m pytest tests/ -q
```

- **`PYTHONPATH` is required** — tests import `app` as a top-level module.
- 47 test functions (~75 cases with parametrize). All should pass.
- Some tests (`test_events_fragment_renders`, `test_bin_collection_index_renders`, `test_bins_fragment_*`) make real HTTP calls to ICS calendar feeds — expect up to 10 s latency per test; do not incorrectly mock these.
- Do **not** use `python run_tests.py` — uses the unittest runner which misses pytest-style tests.

## Deploying Changes

```bash
sudo systemctl restart matrix.service kiosk.service
```

Template (HTML/Jinja2) changes are picked up on the next request without restarting `matrix.service`. Restart `kiosk.service` to force Chromium reload. Run the dev server with `./run.sh`.

## Code Conventions (enforced — see AGENTS.md)

- **Tests**: pytest-style only — plain functions, `@pytest.fixture`, plain `assert`. Never `unittest.TestCase`.
- **Time**: always `now_local()` → `datetime.now(APP_TIMEZONE)`. Never `datetime.utcnow()`.
- `APP_TIMEZONE` = `ZoneInfo` from config key `TIMEZONE` (default `Europe/London`).
- Secrets/API keys → `config_matrix.json` only. Never hardcoded.
- `ICON_TO_CODE`, `WEATHER_MAP`, `CRUISE_ITINERARY` are module-level constants.
- Weather fragment templates always render their outer container div even when data is `None` (div is empty, not absent) so JS `document.querySelector()` always finds the element.
- CSS specificity: use `td.classname` selectors to override the generic `.itinerary-table td { color: #fff }` rule.

## Architecture Notes

- **`app.py`**: all Flask routes, helpers, constants in one file. Config loaded at import via `config_matrix.json`.
- **Fragment pattern**: `fetchAndUpdate(url, cssSelector)` in JS fetches HTML partial and replaces `innerHTML` of matching element.
- **Weather**: `get_pirate_weather_data(location_key)` → `(current_dict, forecast_list, hourly_summary, daily_summary, location_name)`. Keys: `home`, `east_med`, `dubrovnik`. Units: `uk2` (°C, m/s wind).
- **Bins**: `get_this_week_bins()` always returns `{'bins': [...], 'collection_day': str}` — safe default on ICS failure.
- **`as_local_datetime()`**: normalises `date` or `datetime` (naive or aware) to timezone-aware local datetime.
- **`/cruise-temps`**: returns JSON `{date: "N°"}` — fetches PirateWeather `currently` for 7 port coordinates in parallel via `ThreadPoolExecutor`.

## Flask Routes

| Route | Returns |
|---|---|
| `/` | Full page |
| `/events-fragment` | Calendar events partial |
| `/current-weather-fragment?location=home\|east_med\|dubrovnik` | Current conditions partial |
| `/forecast-weather-fragment?location=…` | 7-day forecast partial |
| `/news-fragment` | News ticker partial |
| `/bins-fragment` | Bin collection partial |
| `/todoist-fragment` | Todoist tasks partial |
| `/cruise-temps` | JSON port temperatures |

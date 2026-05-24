
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone, timedelta
import json
import math
import requests
import os


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Load config
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path) as f:
            return json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"config.json not found at {config_path}. Application cannot start.")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"config.json is not valid JSON: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to load config.json: {e}")

CONFIG = load_config()

# All times are local (Europe/London for flights, ship local for cruise ports)
CRUISE_START = datetime.strptime(CONFIG.get("CRUISE_START", "2026-05-28"), "%Y-%m-%d")
CAR_ROUTE = CONFIG.get("CAR_ROUTE", [])
AIR_ROUTE = CONFIG.get("AIR_ROUTE", [])
HOME_COORDS = tuple(CONFIG.get("HOME_COORDS", [55.876778687666395, -3.155061085364159]))
GLA_COORDS = tuple(CONFIG.get("GLA_COORDS", [55.86471714081724, -4.432244046978144]))
DBV_COORDS = tuple(CONFIG.get("DBV_COORDS", [42.6507, 18.0944]))


def _interpolate_route(coords: list, fraction: float) -> tuple:
    """Return (lat, lon) at the given fraction (0–1) along a list of waypoints."""
    fraction = max(0.0, min(1.0, fraction))
    if fraction == 0:
        return coords[0]
    if fraction == 1:
        return coords[-1]
    seg_lens = [
        math.sqrt((coords[i+1][0]-coords[i][0])**2 + (coords[i+1][1]-coords[i][1])**2)
        for i in range(len(coords)-1)
    ]
    total = sum(seg_lens)
    target = fraction * total
    cumulative = 0.0
    for i, seg_len in enumerate(seg_lens):
        if cumulative + seg_len >= target:
            t = (target - cumulative) / seg_len
            lat = coords[i][0] + t * (coords[i+1][0] - coords[i][0])
            lon = coords[i][1] + t * (coords[i+1][1] - coords[i][1])
            return lat, lon
        cumulative += seg_len
    return coords[-1]

ITINERARY = CONFIG.get("ITINERARY", [])
FLIGHTS = CONFIG.get("FLIGHTS", [])
CONTACTS = CONFIG.get("CONTACTS", [])
EXCURSIONS = CONFIG.get("EXCURSIONS", [])


SEA_LEGS = CONFIG.get("SEA_LEGS", [])


def _sea_position(now: datetime):
    """Return (lat, lon) interpolated along the cruise sea route, or (None, None)."""
    for leg in SEA_LEGS:
        from_e = ITINERARY[leg["from_idx"]]
        to_e   = ITINERARY[leg["to_idx"]]
        fh, fm = from_e["dep"].split(":")
        leg_start = (CRUISE_START + timedelta(days=leg["from_idx"])).replace(hour=int(fh), minute=int(fm))
        ah, am = to_e["arr"].split(":")
        leg_end = (CRUISE_START + timedelta(days=leg["to_idx"])).replace(hour=int(ah), minute=int(am))
        if leg_start <= now <= leg_end:
            frac = (now - leg_start).total_seconds() / (leg_end - leg_start).total_seconds()
            return _interpolate_route(leg["route"], frac)
    return None, None


def _hhmm_to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def get_current_status(now: datetime):
    """Return the current location status and next event for the dashboard."""
    cruise_end = datetime(2026, 6, 4, 8, 0)   # Day 8 departure = disembark

    # Before outbound flight
    outbound = datetime(2026, 5, 28, 6, 0)
    leave_home = datetime(2026, 5, 28, 3, 0)
    arrive_airport_out = datetime(2026, 5, 28, 4, 0)

    if now < leave_home:
        days_to_go = (outbound - now).days
        return {
            "status": "pre_trip",
            "headline": "Holiday countdown",
            "sub": f"{days_to_go} day{'s' if days_to_go != 1 else ''} to go!",
            "location": "Loanhead, Scotland",
            "lat": 55.876778687666395,
            "lon": -3.155061085364159,
            "next_event": "Outbound flight GLA → DBV",
            "next_event_dt": outbound.isoformat(),
            "phase": "pre",
        }

    if leave_home <= now < arrive_airport_out:
        frac = (now - leave_home).total_seconds() / (arrive_airport_out - leave_home).total_seconds()
        lat, lon = _interpolate_route(CAR_ROUTE, frac)
        return {
            "status": "travelling",
            "headline": "On the way to the airport 🚗",
            "sub": "Heading to Glasgow Airport",
            "location": "En route to Glasgow Airport",
            "lat": lat,
            "lon": lon,
            "next_event": "Arrive Glasgow Airport at 04:00",
            "next_event_dt": arrive_airport_out.isoformat(),
            "phase": "pre",
        }

    if arrive_airport_out <= now < outbound:
        return {
            "status": "at_airport",
            "headline": "At Glasgow Airport ✈️",
            "sub": "Outbound flight GLA → DBV departs 06:00",
            "location": "Glasgow Airport, Scotland",
            "lat": 55.86471714081724,
            "lon": -4.432244046978144,
            "next_event": "Outbound flight GLA → DBV at 06:00",
            "next_event_dt": outbound.isoformat(),
            "phase": "pre",
        }

    # Outbound flight: 28 May 06:00 → 10:15
    outbound_land = datetime(2026, 5, 28, 10, 15)
    if outbound <= now < outbound_land:
        frac = (now - outbound).total_seconds() / (outbound_land - outbound).total_seconds()
        lat, lon = _interpolate_route(AIR_ROUTE, frac)
        return {
            "status": "flying_out",
            "headline": "Currently in the air ✈️",
            "location": "Airborne",
            "lat": lat, "lon": lon,
            "next_event": "Land at Dubrovnik 10:15",
            "next_event_dt": outbound_land.isoformat(),
            "phase": "flight",
        }

    # Travelling from Dubrovnik Airport to cruise port: 10:15 → 14:00
    cruise_board = datetime(2026, 5, 28, 14, 0)
    if outbound_land <= now < cruise_board:
        frac = (now - outbound_land).total_seconds() / (cruise_board - outbound_land).total_seconds()
        dbv_airport = (42.5614, 18.2682)
        dbv_port    = (42.6507, 18.0944)
        lat, lon = _interpolate_route([dbv_airport, dbv_port], frac)
        return {
            "status": "travelling",
            "headline": "Travelling to cruise ship 🚗",
            "sub": "Heading to Dubrovnik Port",
            "location": "En route to Dubrovnik Port",
            "lat": lat, "lon": lon,
            "next_event": "Board ship at Dubrovnik Port 14:00",
            "next_event_dt": cruise_board.isoformat(),
            "phase": "pre",
        }

    # On the cruise
    if now < cruise_end:
        day_number = (now.date() - CRUISE_START.date()).days + 1
        day_number = max(1, min(day_number, 8))
        entry = ITINERARY[day_number - 1]

        if entry["at_sea"]:
            sea_lat, sea_lon = _sea_position(now)
            return {
                "status": "at_sea",
                "headline": f"Day {day_number} — At sea 🌊",
                "location": "Mediterranean Sea",
                "lat": sea_lat or 37.5, "lon": sea_lon or 15.5,
                "next_event": f"Next: Arrive at {ITINERARY[day_number]['port']}",
                "next_event_dt": None,
                "phase": "sea",
            }

        now_min = now.hour * 60 + now.minute
        arr_min = _hhmm_to_minutes(entry["arr"])
        dep_min = _hhmm_to_minutes(entry["dep"])

        if now_min < arr_min:
            sea_lat, sea_lon = _sea_position(now)
            return {
                "status": "approaching",
                "headline": f"Day {day_number} — Approaching {entry['port']} 🦭",
                "sub": f"Arriving {entry['arr']} local time",
                "location": f"Approaching {entry['port']}, {entry['country']}",
                "lat": sea_lat or entry["lat"], "lon": sea_lon or entry["lon"],
                "next_event": f"Arrive {entry['port']} at {entry['arr']}",
                "next_event_dt": None,
                "phase": "sea",
            }
        elif now_min < dep_min:
            excursion = entry.get("excursion")
            return {
                "status": "in_port",
                "headline": f"Day {day_number} — In port: {entry['port']}, {entry['country']} ⚓",
                "location": f"{entry['port']}, {entry['country']}",
                "lat": entry["lat"], "lon": entry["lon"],
                "next_event": f"Depart {entry['port']} at {entry['dep']}",
                "next_event_dt": None,
                "phase": "port",
            }
        else:
            # Departed, heading to next
            if day_number < 8:
                next_e = ITINERARY[day_number]
                # Skip at-sea entries to find the next actual port
                next_port = next((e for e in ITINERARY[day_number:] if not e["at_sea"]), next_e)
                sea_lat, sea_lon = _sea_position(now)
                fallback_lat = (entry["lat"] + (next_port["lat"] or entry["lat"])) / 2
                fallback_lon = (entry["lon"] + (next_port["lon"] or entry["lon"])) / 2
                return {
                    "status": "at_sea",
                    "headline": f"Day {day_number} — Departed {entry['port']} 🌊",
                    "location": "Mediterranean Sea",
                    "lat": sea_lat or fallback_lat,
                    "lon": sea_lon or fallback_lon,
                    "next_event": f"Next: Arrive at {next_port['port']}",
                    "next_event_dt": None,
                    "phase": "sea",
                }

    # Return flight window: 4 June 11:15 → 13:40
    return_dep = datetime(2026, 6, 4, 11, 15)
    return_land = datetime(2026, 6, 4, 13, 40)

    if cruise_end <= now < return_dep:
        frac = (now - cruise_end).total_seconds() / (return_dep - cruise_end).total_seconds()
        dbv_port    = (42.6507, 18.0944)
        dbv_airport = (42.5614, 18.2682)
        lat, lon = _interpolate_route([dbv_port, dbv_airport], frac)
        return {
            "status": "travelling",
            "headline": "Travelling to Dubrovnik Airport 🚗",
            "sub": "Return flight TOM1459 departs 11:15",
            "location": "En route to Dubrovnik Airport",
            "lat": lat, "lon": lon,
            "next_event": "Return flight DBV → GLA at 11:15",
            "next_event_dt": return_dep.isoformat(),
            "phase": "pre",
        }

    if return_dep <= now < return_land:
        frac = (now - return_dep).total_seconds() / (return_land - return_dep).total_seconds()
        lat, lon = _interpolate_route(list(reversed(AIR_ROUTE)), frac)
        return {
            "status": "flying_home",
            "headline": "Currently in the air ✈️",
            "location": "Airborne",
            "lat": lat, "lon": lon,
            "next_event": "Land at Glasgow 13:40",
            "next_event_dt": return_land.isoformat(),
            "phase": "flight",
        }

    leave_airport_home = datetime(2026, 6, 4, 14, 45)
    arrive_home = datetime(2026, 6, 4, 15, 45)

    if return_land <= now < leave_airport_home:
        return {
            "status": "at_airport",
            "headline": "Landed at Glasgow Airport 🏠",
            "sub": "Heading home soon",
            "location": "Glasgow Airport, Scotland",
            "lat": 55.86471714081724,
            "lon": -4.432244046978144,
            "next_event": "Depart airport for home at 14:45",
            "next_event_dt": leave_airport_home.isoformat(),
            "phase": "pre",
        }

    if leave_airport_home <= now < arrive_home:
        frac = (now - leave_airport_home).total_seconds() / (arrive_home - leave_airport_home).total_seconds()
        lat, lon = _interpolate_route(list(reversed(CAR_ROUTE)), frac)
        return {
            "status": "travelling",
            "headline": "On the way home 🚗",
            "sub": "Heading back to Loanhead",
            "location": "En route to Loanhead",
            "lat": lat,
            "lon": lon,
            "next_event": "Home",
            "next_event_dt": arrive_home.isoformat(),
            "phase": "pre",
        }

    return {
        "status": "home",
        "headline": "Back home 🏠",
        "sub": "What a trip!",
        "location": "Loanhead, Scotland",
        "lat": 55.876778687666395,
        "lon": -3.155061085364159,
        "next_event": None,
        "next_event_dt": None,
        "phase": "pre",
    }


def next_refresh_seconds(now: datetime) -> int:
    """Calculate seconds until the next significant event so JS can auto-refresh."""
    events = [
        datetime(2026, 5, 28,  6,  0),   # outbound flight
        datetime(2026, 5, 28, 10, 15),   # land Dubrovnik
    ]
    # Add all port arrivals and departures
    for i, entry in enumerate(ITINERARY):
        date = CRUISE_START + timedelta(days=i)
        if entry["arr"]:
            h, m = entry["arr"].split(":")
            events.append(date.replace(hour=int(h), minute=int(m)))
        if entry["dep"]:
            h, m = entry["dep"].split(":")
            events.append(date.replace(hour=int(h), minute=int(m)))
    events += [
        datetime(2026, 6, 4,  8,  0),   # disembark
        datetime(2026, 6, 4, 11, 15),   # return flight
        datetime(2026, 6, 4, 13, 40),   # land Glasgow
    ]
    future = [e for e in events if e > now]
    if future:
        secs = int((min(future) - now).total_seconds())
        return max(secs, 60)
    return 3600


# WMO weather code → emoji
WEATHER_ICONS = {
    0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
    45: "🌫️", 48: "🌫️",
    51: "🌦️", 53: "🌦️", 55: "🌧️",
    61: "🌧️", 63: "🌧️", 65: "🌧️",
    71: "🌨️", 73: "🌨️", 75: "❄️",
    80: "🌦️", 81: "🌧️", 82: "⛈️",
    95: "⛈️", 96: "⛈️", 99: "⛈️",
}




# Simple in-memory cache for weather data
_weather_cache = {}

def get_max_temp_for_day(lat: float, lon: float, date: datetime) -> int | None:
    """Fetch max temp for a given day at lat/lon using Open-Meteo API (no API key needed), with in-memory cache."""
    cache_key = (round(lat, 4), round(lon, 4), date.strftime("%Y-%m-%d"))
    if cache_key in _weather_cache:
        return _weather_cache[cache_key]
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": cache_key[0],
                "longitude": cache_key[1],
                "daily": "temperature_2m_max",
                "temperature_unit": "celsius",
                "timezone": "auto",
                "start_date": cache_key[2],
                "end_date": cache_key[2],
            },
            timeout=5,
        )
        r.raise_for_status()
        data = r.json()
        temps = data.get("daily", {}).get("temperature_2m_max", [])
        if temps:
            temp = round(temps[0])
            _weather_cache[cache_key] = temp
            return temp
    except Exception:
        pass
    _weather_cache[cache_key] = None
    return None



@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    now = datetime.now()
    status = get_current_status(now)
    refresh_secs = next_refresh_seconds(now)
    current_day = (now.date() - CRUISE_START.date()).days + 1
    # Build a list of max temps for each itinerary entry (None for at-sea days)
    itinerary_temps = []
    for i, entry in enumerate(ITINERARY):
        if not entry["at_sea"] and entry["lat"] and entry["lon"]:
            day_date = CRUISE_START + timedelta(days=entry["day"] - 1)
            temp = get_max_temp_for_day(entry["lat"], entry["lon"], day_date)
            itinerary_temps.append(temp)
        else:
            itinerary_temps.append(None)
    weather = None
    if status.get("lat") and status.get("lon"):
        try:
            weather = get_weather(status["lat"], status["lon"])
        except Exception:
            weather = None
    return templates.TemplateResponse(request, "index.html", {
        "now": now,
        "status": status,
        "itinerary": ITINERARY,
        "itinerary_temps": itinerary_temps,
        "flights": FLIGHTS,
        "contacts": CONTACTS,
        "excursions": EXCURSIONS,
        "cruise_start": CRUISE_START,
        "refresh_secs": refresh_secs,
        "itinerary_json": json.dumps(ITINERARY),
        "timedelta": timedelta,
        "current_day": current_day,
        "weather": weather,
    })


@app.get("/status")
async def status_api():
    now = datetime.now()
    status = get_current_status(now)
    return {**status, "refresh_secs": next_refresh_seconds(now), "now": now.isoformat()}

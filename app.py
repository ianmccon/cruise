from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone, timedelta
import json

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# All times are local (Europe/London for flights, ship local for cruise ports)
# Cruise departs Dubrovnik Day 1 = 28 May 2026 (same day as outbound flight lands)

CRUISE_START = datetime(2026, 5, 28)

ITINERARY = [
    {"day": 1, "port": "Dubrovnik", "country": "Croatia",  "arr": "14:00", "dep": "21:00", "at_sea": False,
     "lat": 42.6507, "lon": 18.0944},
    {"day": 2, "port": "At sea",    "country": "",          "arr": None,    "dep": None,    "at_sea": True,
     "lat": None,   "lon": None},
    {"day": 3, "port": "Valetta",   "country": "Malta",     "arr": "09:00", "dep": "18:00", "at_sea": False,
     "lat": 35.8997, "lon": 14.5147},
    {"day": 4, "port": "Messina",   "country": "Sicily",    "arr": "08:00", "dep": "17:00", "at_sea": False,
     "lat": 38.1938, "lon": 15.5540},
    {"day": 5, "port": "Argostoli", "country": "Kefalonia", "arr": "12:00", "dep": "20:00", "at_sea": False,
     "lat": 38.1753, "lon": 20.4892,
     "excursion": "Melissani Lake & Drogarati Cave"},
    {"day": 6, "port": "Corfu Town","country": "Corfu",     "arr": "08:00", "dep": "17:00", "at_sea": False,
     "lat": 39.6243, "lon": 19.9217},
    {"day": 7, "port": "Kotor",     "country": "Montenegro","arr": "08:00", "dep": "17:00", "at_sea": False,
     "lat": 42.4247, "lon": 18.7712,
     "excursion": "Semi-submarine & Kotor Bay walking tour"},
    {"day": 8, "port": "Dubrovnik", "country": "Croatia",   "arr": "04:00", "dep": "08:00", "at_sea": False,
     "lat": 42.6507, "lon": 18.0944},
]

FLIGHTS = [
    {
        "date": "28 May 2026",
        "from_code": "GLA", "from_time": "06:00",
        "flight": "TOM1458",
        "to_code": "DBV",   "to_time": "10:15",
        "direction": "outbound",
    },
    {
        "date": "4 June 2026",
        "from_code": "DBV", "from_time": "11:15",
        "flight": "TOM1459",
        "to_code": "GLA",   "to_time": "13:40",
        "direction": "return",
    },
]

CONTACTS = [
    {"name": "Marella Cruises",    "phone": "0203 636 1931"},
    {"name": "Marella Explorer 2", "phone": "01224 345 151"},
    {"name": "Dad",                "phone": "07921 864281"},
    {"name": "Mam",                "phone": "07597 192699"},
]

EXCURSIONS = [
    {"day": 5, "port": "Argostoli, Kefalonia", "description": "Melissani Lake & Drogarati Cave"},
    {"day": 7, "port": "Kotor, Montenegro",    "description": "Semi-submarine & Kotor Bay walking tour"},
]


def _hhmm_to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def get_current_status(now: datetime):
    """Return the current location status and next event for the dashboard."""
    cruise_end = datetime(2026, 6, 4, 8, 0)   # Day 8 departure = disembark

    # Before outbound flight
    outbound = datetime(2026, 5, 28, 6, 0)
    flight_day = datetime(2026, 5, 28, 0, 0)
    if now < outbound:
        days_to_go = (outbound - now).days
        next_event_dt = outbound
        at_airport = now >= flight_day
        return {
            "status": "pre_trip",
            "headline": "Holiday countdown",
            "sub": f"{days_to_go} day{'s' if days_to_go != 1 else ''} to go!",
            "location": "Glasgow Airport" if at_airport else "Glasgow, Scotland",
            "lat": 55.869829854 if at_airport else 55.8617,
            "lon": -4.426498294 if at_airport else -4.2583,
            "next_event": "Outbound flight GLA → DBV",
            "next_event_dt": outbound.isoformat(),
            "phase": "pre",
        }

    # Outbound flight: 28 May 06:00 → 10:15
    outbound_land = datetime(2026, 5, 28, 10, 15)
    if outbound <= now < outbound_land:
        return {
            "status": "flying_out",
            "headline": "Currently in the air ✈️",
            "location": "Airborne",
            "lat": 44.0, "lon": 12.0,
            "next_event": "Land at Dubrovnik 10:15",
            "next_event_dt": outbound_land.isoformat(),
            "phase": "flight",
        }

    # On the cruise
    if now < cruise_end:
        day_number = (now.date() - CRUISE_START.date()).days + 1
        day_number = max(1, min(day_number, 8))
        entry = ITINERARY[day_number - 1]

        if entry["at_sea"]:
            return {
                "status": "at_sea",
                "headline": f"Day {day_number} — At sea 🌊",
                "location": "Mediterranean Sea",
                "lat": 37.5, "lon": 15.5,
                "next_event": f"Day {day_number+1}: Arrive {ITINERARY[day_number]['port']} at {ITINERARY[day_number]['arr']}",
                "next_event_dt": None,
                "phase": "sea",
            }

        now_min = now.hour * 60 + now.minute
        arr_min = _hhmm_to_minutes(entry["arr"])
        dep_min = _hhmm_to_minutes(entry["dep"])

        if now_min < arr_min:
            return {
                "status": "approaching",
                "headline": f"Day {day_number} — Approaching {entry['port']} 🧭",
                "sub": f"Arriving {entry['arr']} local time",
                "location": f"Approaching {entry['port']}, {entry['country']}",
                "lat": entry["lat"], "lon": entry["lon"],
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
                return {
                    "status": "at_sea",
                    "headline": f"Day {day_number} — Departed {entry['port']} 🌊",
                    "location": "Mediterranean Sea",
                    "lat": (entry["lat"] + (next_e["lat"] or entry["lat"])) / 2,
                    "lon": (entry["lon"] + (next_e["lon"] or entry["lon"])) / 2,
                    "next_event": f"Arrive {next_e['port']} at {next_e['arr']}",
                    "next_event_dt": None,
                    "phase": "sea",
                }

    # Return flight window: 4 June 11:15 → 13:40
    return_dep = datetime(2026, 6, 4, 11, 15)
    return_land = datetime(2026, 6, 4, 13, 40)

    if cruise_end <= now < return_dep:
        return {
            "status": "disembarked",
            "headline": "Disembarked — Dubrovnik airport 🏖️",
            "sub": "Return flight TOM1459 departs 11:15",
            "location": "Dubrovnik, Croatia",
            "lat": 42.6507, "lon": 18.0944,
            "next_event": "Return flight DBV → GLA at 11:15",
            "next_event_dt": return_dep.isoformat(),
            "phase": "port",
        }

    if return_dep <= now < return_land:
        return {
            "status": "flying_home",
            "headline": "Currently in the air ✈️",
            "location": "Airborne",
            "lat": 47.0, "lon": 10.0,
            "next_event": "Land at Glasgow 13:40",
            "next_event_dt": return_land.isoformat(),
            "phase": "flight",
        }

    return {
        "status": "home",
        "headline": "Back home �",
        "sub": "What a trip!",
        "location": "Glasgow, Scotland",
        "lat": 55.8617, "lon": -4.2583,
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


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    now = datetime.now()
    status = get_current_status(now)
    refresh_secs = next_refresh_seconds(now)
    current_day = (now.date() - CRUISE_START.date()).days + 1
    return templates.TemplateResponse(request, "index.html", {
        "now": now,
        "status": status,
        "itinerary": ITINERARY,
        "flights": FLIGHTS,
        "contacts": CONTACTS,
        "excursions": EXCURSIONS,
        "cruise_start": CRUISE_START,
        "refresh_secs": refresh_secs,
        "itinerary_json": json.dumps(ITINERARY),
        "timedelta": timedelta,
        "current_day": current_day,
    })


@app.get("/status")
async def status_api():
    now = datetime.now()
    status = get_current_status(now)
    return {**status, "refresh_secs": next_refresh_seconds(now), "now": now.isoformat()}

"""Tools used by the specialist agents."""

from __future__ import annotations

import random
import string
from collections import defaultdict
from datetime import datetime, timezone

import requests
from langchain_core.tools import tool

from backend.config import settings


def weather_forecast(city: str, lat: float | None = None, lon: float | None = None) -> dict:
    """5-day forecast from OpenWeatherMap, summarised per day. Pass lat/lon when
    known: OWM's own geocoder can pick a same-named town in another country."""
    if not settings.openweather_api_key:
        return {"error": "Weather not configured (OPENWEATHERMAP_API_KEY missing)."}
    key = settings.openweather_api_key
    def call(url: str, **params):
        r = requests.get(url, params={**params, "appid": key}, timeout=10)
        if r.status_code == 401:
            raise PermissionError("OpenWeatherMap rejected the API key (new keys can take 1-2 hours to activate).")
        r.raise_for_status()
        return r.json()

    try:
        if lat is not None and lon is not None:
            place = {"lat": lat, "lon": lon, "name": city.split(",")[0].strip(), "country": ""}
        else:
            geo = call("https://api.openweathermap.org/geo/1.0/direct", q=city, limit=1)
            if not isinstance(geo, list) or not geo:
                return {"error": f"Could not find location '{city}'."}
            place = geo[0]
        data = call("https://api.openweathermap.org/data/2.5/forecast",
                    lat=place["lat"], lon=place["lon"], units="metric")
        if not place.get("country"):
            place["country"] = data.get("city", {}).get("country", "")
    except PermissionError as exc:
        return {"error": str(exc)}
    except (requests.RequestException, ValueError, KeyError) as exc:
        return {"error": f"Weather lookup failed: {type(exc).__name__}"}

    days: dict[str, dict] = defaultdict(lambda: {"temps": [], "conditions": defaultdict(int), "rain_mm": 0.0})
    for e in data.get("list", []):
        d = days[e["dt_txt"][:10]]
        d["temps"].append(e["main"]["temp"])
        d["conditions"][e["weather"][0]["main"]] += 1
        d["rain_mm"] += e.get("rain", {}).get("3h", 0.0)
    daily = [
        {
            "date": date,
            "min_c": round(min(d["temps"]), 1),
            "max_c": round(max(d["temps"]), 1),
            "condition": max(d["conditions"], key=d["conditions"].get),
            "rain_mm": round(d["rain_mm"], 1),
        }
        for date, d in sorted(days.items())
    ]
    return {
        "location": f"{place.get('name')}, {place.get('country')}",
        "daily": daily,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


@tool
def mock_book_item(item_type: str, name: str, date: str, est_price: float = 0.0, currency: str = "USD") -> str:
    """Simulate booking a hotel, activity or transport item. NOT a real booking.
    item_type: 'hotel' | 'activity' | 'transport'. date: YYYY-MM-DD.
    """
    code = "TG-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    price = f"~{est_price:.0f} {currency}" if est_price else "price TBD"
    return f"[SIMULATED] {item_type.title()} '{name}' on {date}: confirmation {code}, est. {price}."

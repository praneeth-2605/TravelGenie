"""
TravelGenie agent tools:
1. get_weather_forecast   -> OpenWeatherMap
2. search_destination_info -> Tavily
3. mock_book_item          -> fake booking confirmation
"""

import os
import random
import string
from datetime import datetime

import requests
from langchain_core.tools import tool
from langchain_tavily import TavilySearch


@tool
def get_weather_forecast(city: str) -> str:
    """Get current weather and short outlook for a city (OpenWeatherMap).
    Use this to ground packing suggestions and weather advisories.
    """
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if not api_key:
        return "Weather tool not configured: missing OPENWEATHERMAP_API_KEY."
    try:
        geo = requests.get(
            "https://api.openweathermap.org/geo/1.0/direct",
            params={"q": city, "limit": 1, "appid": api_key}, timeout=10,
        ).json()
        if not geo:
            return f"Could not find location data for '{city}'."
        lat, lon = geo[0]["lat"], geo[0]["lon"]

        data = requests.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
            timeout=10,
        ).json()
        entries = data.get("list", [])[:8]
        if not entries:
            return f"No forecast data for {city}."
        temps = [e["main"]["temp"] for e in entries]
        conditions = {e["weather"][0]["main"] for e in entries}
        avg = round(sum(temps) / len(temps), 1)
        return (
            f"Weather for {city}: avg {avg}°C (range {round(min(temps),1)}-{round(max(temps),1)}°C), "
            f"conditions: {', '.join(conditions)}. Fetched {datetime.utcnow():%Y-%m-%d %H:%M UTC}."
        )
    except requests.RequestException as exc:
        return f"Weather lookup failed for {city}: {exc}"


def build_search_tool():
    if not os.getenv("TAVILY_API_KEY"):
        return None
    return TavilySearch(
        max_results=5,
        name="search_destination_info",
        description="Search the web for current destination info: attractions, "
                     "neighborhoods, events, safety, seasonal tips.",
    )


@tool
def mock_book_item(item_type: str, name: str, date: str, budget_per_night_or_ticket: float = 0.0) -> str:
    """Simulate booking a hotel/activity/transport item. NOT a real booking API.
    item_type: 'hotel' | 'activity' | 'transport'. date: YYYY-MM-DD.
    """
    code = "TG-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    price = f"~${budget_per_night_or_ticket:.0f}" if budget_per_night_or_ticket else "price TBD"
    return f"[MOCK BOOKING] {item_type.title()} '{name}' on {date} — confirmation {code}, est. {price}."


def get_all_tools():
    tools = [get_weather_forecast, mock_book_item]
    s = build_search_tool()
    if s:
        tools.append(s)
    return tools
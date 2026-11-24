"""Geography skills: coordinates for names, straight-line distance, and places."""

from __future__ import annotations

import math

from backend import places
from backend.skills import register

Point = tuple[float, float]  # (lat, lon)


@register("geocode", "Find coordinates for a place name (city, station, airport, area).", "OpenStreetMap Nominatim")
def geocode(name: str, context: str | None = None) -> Point | None:
    """Coordinates for `name`, trying 'name, context' first (e.g. 'Madgaon station, Goa')."""
    for query in ([f"{name}, {context}"] if context else []) + [name]:
        hit = places.geocode(query)
        if hit:
            return hit["lat"], hit["lon"]
    return None


def haversine_km(a: Point, b: Point) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


@register("find_places", "Real stays (by price tier), sights and restaurants for a destination.", "Wikivoyage")
def find_places(destination: str) -> dict:
    return places.get_places(destination)

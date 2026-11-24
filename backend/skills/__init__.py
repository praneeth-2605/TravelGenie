"""TravelGenie skills: small, reusable, deterministic capabilities the agents use.

Agents decide *what* to do (often with an LLM); skills *do* one concrete job
against real data, with caching and graceful fallbacks:

    geocode          place name → coordinates           (OpenStreetMap Nominatim)
    route_legs       real road distance + travel time    (OSRM routing on OpenStreetMap)
    find_places      stays, sights, restaurants          (Wikivoyage listings)
    find_photos      real photos for places              (Wikidata / Wikipedia / Wikimedia Commons)
    weather          5-day forecast                      (OpenWeatherMap)
    build_schedule   timestamped day-by-day itinerary    (pure code over the skills above)

The registry below documents every skill (name, purpose, source) so the
pipeline is easy to inspect, test and extend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    source: str
    run: Callable


REGISTRY: dict[str, Skill] = {}


def register(name: str, description: str, source: str):
    def wrap(fn: Callable) -> Callable:
        REGISTRY[name] = Skill(name, description, source, fn)
        return fn
    return wrap


def catalog() -> list[dict]:
    """Human-readable list of skills (used by docs and the health endpoint)."""
    return [{"name": s.name, "description": s.description, "source": s.source} for s in REGISTRY.values()]


# Import the modules so their skills register themselves.
from backend.skills import geo, photos, routing, schedule  # noqa: E402

__all__ = ["REGISTRY", "Skill", "catalog", "register", "geo", "photos", "routing", "schedule"]

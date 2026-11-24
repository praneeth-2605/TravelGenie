"""Routing skill: real road distances and travel times between stops.

Uses OSRM (open-source routing on OpenStreetMap data) with all of a day's
stops in ONE request; each consecutive pair becomes a leg. Short legs are
walked; longer ones use a local vehicle (auto-rickshaw / cab in India) with a
traffic and pickup allowance. If routing is unavailable, falls back to a clearly
labelled estimate from straight-line distance.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import asdict, dataclass

import requests

from backend import db
from backend.skills import register
from backend.skills.geo import Point, haversine_km

log = logging.getLogger(__name__)

OSRM = "https://router.project-osrm.org/route/v1/driving/"
UA = {"User-Agent": "TravelGenie/1.0 (open-source travel planner)"}
WALK_KM_PER_H = 4.5
MAX_WALK_KM = 1.2
TRAFFIC = 1.35          # city traffic vs. OSRM's free-flow times
PICKUP_MIN = 5          # waiting for / finding a ride
_lock = threading.Lock()
_last = 0.0


@dataclass
class Leg:
    distance_km: float
    minutes: int
    mode: str            # "walk" | "auto / cab" | "taxi / transit"
    source: str          # "osrm" | "estimate"

    def to_dict(self) -> dict:
        return asdict(self)


def _osrm(points: list[Point]) -> list[tuple[float, float]] | None:
    """[(km, minutes)] driving per consecutive pair, or None if unavailable."""
    coords = ";".join(f"{lon:.5f},{lat:.5f}" for lat, lon in points)
    key = f"osrm:{coords}"
    try:
        cached = db.cache_get(key, 30 * 86400)
    except Exception:
        cached = None
    if cached:
        return [tuple(x) for x in cached]
    global _last
    with _lock:  # be polite to the public demo server
        wait = 0.35 - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.time()
        try:
            r = requests.get(OSRM + coords, params={"overview": "false", "steps": "false"}, headers=UA, timeout=15)
            data = r.json()
        except (requests.RequestException, ValueError) as exc:
            log.warning("routing unavailable: %s", exc)
            return None
    if data.get("code") != "Ok":
        return None
    legs = [(leg["distance"] / 1000, leg["duration"] / 60) for leg in data["routes"][0]["legs"]]
    try:
        db.cache_set(key, legs)
    except Exception:
        pass
    return legs


def _vehicle(india: bool) -> str:
    return "auto / cab" if india else "taxi / transit"


@register("route_legs", "Real road distance and travel time for each leg of a route, with a walk-or-ride choice.",
          "OSRM routing on OpenStreetMap")
def route_legs(points: list[Point], india: bool = True) -> list[Leg]:
    """One Leg per consecutive pair of points."""
    if len(points) < 2:
        return []
    road = _osrm(points)
    legs: list[Leg] = []
    for i in range(len(points) - 1):
        straight = haversine_km(points[i], points[i + 1])
        if road:
            km, drive_min = road[i]
            source = "osrm"
        else:
            km, drive_min = straight * 1.3, straight * 1.3 / 25 * 60   # ~25 km/h in towns
            source = "estimate"
        if straight <= MAX_WALK_KM:
            walk_km = min(km, straight * 1.4) if km else straight * 1.3
            legs.append(Leg(round(walk_km, 1), max(3, math.ceil(walk_km / WALK_KM_PER_H * 60)), "walk", source))
        else:
            legs.append(Leg(round(km, 1), math.ceil(drive_min * TRAFFIC) + PICKUP_MIN, _vehicle(india), source))
    return legs

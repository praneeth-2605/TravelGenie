"""Scheduling skill: turns the planner's ordered stops into a timestamped day plan.

The LLM decides WHAT to do and in which order (using only real, listed places);
this code decides WHEN, using real road distances and travel times:

    07:30  Arrive at Madgaon Railway Station (MAO)
    07:40  Auto / cab to Panjim Inn · 33.4 km · 52 min
    08:32  Check in / drop your bags at Panjim Inn
    09:02  Walk to Fontainhas · 0.6 km · 8 min
    09:10  Fontainhas (Latin Quarter) · 1 h 30 min
    ...
    21:15  Back at Panjim Inn

No LLM call, so re-planning after choosing another hotel is instant and free.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from backend.skills import register
from backend.skills.geo import Point, geocode
from backend.skills.routing import route_legs

DEFAULT_MINUTES = {"sight": 90, "activity": 120, "meal": 60, "free": 60}
DAY_START = {"relaxed": 9 * 60 + 30, "moderate": 8 * 60 + 30, "packed": 7 * 60 + 30}
DEPARTURE_BUFFER = {"flight": 120, "train": 30, "bus": 30, "ferry": 45, "car": 0}
CHECK_IN_MIN = 30
COLLECT_BAGS_MIN = 15
LUNCH_FROM, LUNCH_AT = 12 * 60, 12 * 60 + 30          # a meal after sights waits until ~12:30
DINNER_WINDOW, DINNER_FROM, DINNER_AT = (15 * 60 + 30, 0), 19 * 60, 19 * 60 + 30


def _hhmm(minutes: int) -> str:
    minutes = max(0, int(minutes))
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def _parse(t: str | None) -> int | None:
    try:
        h, m = (t or "").strip()[:5].split(":")
        return int(h) * 60 + int(m)
    except ValueError:
        return None


_TIME = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", re.I)


def opening_minute(hours: str | None) -> int | None:
    """Opening time from listing hours such as '9AM-5PM', '7-8PM', '10:30am–6pm' (None if unclear)."""
    if not hours:
        return None
    found = _TIME.findall(hours)
    if not found:
        return None
    h, m, ap = found[0]
    if not ap:  # "7-8PM": the first time takes the meridiem written after it
        ap = next((x[2] for x in found[1:] if x[2]), "")
    h, m = int(h), int(m or 0)
    if h >= 24 or m > 59:
        return None
    ap = ap.lower().replace(".", "")
    if ap == "pm" and h < 12:
        h += 12
    elif ap == "am" and h == 12:
        h = 0
    return h * 60 + m


def _pt(p: dict | None) -> Point | None:
    if p and p.get("lat") is not None and p.get("lon") is not None:
        return float(p["lat"]), float(p["lon"])
    return None


def _public(p: dict) -> dict:
    keys = ("id", "name", "kind", "area", "lat", "lon", "price", "hours", "url", "description", "photo")
    return {k: p.get(k) for k in keys if p.get(k) not in (None, "")}


@register("build_schedule", "Timestamped day-by-day itinerary with real travel legs between every stop.",
          "TravelGenie scheduler (code) + OSRM routing")
def build_schedule(days: list[dict], places: dict[str, dict], destination: str, *,
                   getting_there: dict | None = None, hotel: dict | None = None, hotel_area: str | None = None,
                   start_date: str | None = None, pace: str = "moderate", india: bool = True) -> list[dict]:
    """Return [{day, date, title, steps: [{time, end, kind, title, detail, place, distance_km, minutes, mode}]}]."""
    gt = getting_there or {}
    # Where the traveller sleeps: the chosen hotel, or (until they choose) the recommended area.
    hotel_name = hotel["name"] if hotel else (f"your hotel in {hotel_area}" if hotel_area else "your hotel")
    hotel_pt = _pt(hotel) or (geocode(hotel_area, destination) if hotel_area else None) or geocode(destination)
    hub = gt.get("arrive_at")
    hub_pt = geocode(hub, destination) if hub else None
    depart_hub = gt.get("depart_from_destination") or hub
    depart_pt = geocode(depart_hub, destination) if depart_hub and depart_hub != hub else hub_pt
    mode = (gt.get("mode") or "").lower()
    start = date.fromisoformat(start_date) if start_date else None

    out = []
    for i, d in enumerate(days):
        first, last = i == 0, i == len(days) - 1
        # 1. The ordered list of "moments" for the day, each with an optional location.
        moments: list[dict] = []
        if first and hub:
            moments.append({"kind": "arrive", "title": f"Arrive at {hub}", "pt": hub_pt, "minutes": 10,
                            "detail": f"By {mode}" + (f" · {gt.get('detail')}" if gt.get("detail") else "")
                                      + " · times are typical, check your ticket"})
            moments.append({"kind": "hotel", "title": f"Check in or drop your bags at {hotel_name}",
                            "pt": hotel_pt, "minutes": CHECK_IN_MIN,
                            "detail": "Standard check-in is usually 12:00–14:00; most places hold luggage earlier.",
                            "place": hotel})
        else:
            moments.append({"kind": "start", "title": f"Start from {hotel_name}", "pt": hotel_pt, "minutes": 0,
                            "place": hotel})
        for s in d.get("stops") or []:
            place = places.get(s.get("place_id") or "")
            kind = s.get("kind") if s.get("kind") in DEFAULT_MINUTES else "sight"
            moments.append({
                "kind": kind,
                "title": place["name"] if place else s.get("title", ""),
                "pt": _pt(place),
                "minutes": int(s.get("duration_min") or DEFAULT_MINUTES[kind]),
                "detail": s.get("note") or "",
                "place": place,
                "cite": s.get("cite"),
                "unverified": bool(s.get("unverified")),
            })
        if last and depart_hub:
            moments.append({"kind": "hotel", "title": f"Check out and collect bags at {hotel_name}", "pt": hotel_pt,
                            "minutes": COLLECT_BAGS_MIN, "place": hotel})
            buffer = DEPARTURE_BUFFER.get(mode, 30)
            moments.append({"kind": "depart", "title": f"Depart from {depart_hub}", "pt": depart_pt, "minutes": 0,
                            "detail": (f"By {mode} · " if mode else "")
                                      + (f"Be there about {buffer} min before departure · " if buffer else "")
                                      + "check your ticket for the exact time"})
        else:
            moments.append({"kind": "end", "title": f"Back at {hotel_name}", "pt": hotel_pt, "minutes": 0,
                            "place": hotel})

        # 2. Lay the day out with real travel legs; fix meal times that don't work and re-lay
        #    (a sunset cruise shouldn't wait for a 16:00 "dinner", and a busy day needs a lunch).
        clock0 = _parse(gt.get("arrive_time")) if first and hub else None
        clock0 = clock0 if clock0 is not None else DAY_START.get(pace, DAY_START["moderate"])
        for _ in range(4):
            steps, starts = _walk(moments, _route(moments, india), clock0)
            if not _fix_meals(moments, starts, d.get("area") or hotel_area or destination):
                break

        out.append({
            "day": d.get("day", i + 1),
            "date": (start + timedelta(days=i)).isoformat() if start else None,
            "title": d.get("title", f"Day {i + 1}"),
            "area": d.get("area"),
            "steps": steps,
        })
    return out


STOP_KINDS = ("sight", "activity", "meal", "free")


def _route(moments: list[dict], india: bool) -> dict:
    """Real travel legs between consecutive known locations (one routing call per day)."""
    located = [k for k, m in enumerate(moments) if m["pt"]]
    legs = route_legs([moments[k]["pt"] for k in located], india=india) if len(located) > 1 else []
    return {located[j + 1]: legs[j] for j in range(len(legs))}


def _walk(moments: list[dict], leg_before: dict, clock: int) -> tuple[list[dict], list[int]]:
    """Assign clock times. Returns the steps and the start minute of every moment."""
    steps, starts = [], []
    seen_activity = False
    for k, m in enumerate(moments):
        leg = leg_before.get(k)
        travel = leg.minutes if leg and leg.distance_km >= 0.05 else 0
        # Keep meals at realistic times: wait (with free time nearby) instead of a 10:30 "lunch".
        if m["kind"] == "meal" and seen_activity:
            later = any(x["kind"] in ("sight", "activity") for x in moments[k + 1:])
            arrive = clock + travel
            if arrive < LUNCH_FROM:
                target = LUNCH_AT
            elif DINNER_WINDOW[0] <= arrive < DINNER_FROM and not later:
                target = DINNER_AT
            else:
                target = None
            if target and target - arrive >= 20:
                steps.append({"time": _hhmm(clock), "end": _hhmm(target - travel), "kind": "free",
                              "title": "Free time: explore nearby, shop or rest", "minutes": target - arrive})
                clock = target - travel
        if m["kind"] in ("sight", "activity"):
            seen_activity = True
            opens = opening_minute((m.get("place") or {}).get("hours"))
            arrive = clock + travel
            if opens is not None and 0 < opens - arrive <= 150:
                wait = opens - arrive
                if wait >= 15:
                    steps.append({"time": _hhmm(clock), "end": _hhmm(clock + wait), "kind": "free",
                                  "title": "Free time: explore nearby, shop or rest", "minutes": wait,
                                  "detail": f"{m['title']} opens at {_hhmm(opens)}"})
                clock += wait
        if travel:
            dest = m["title"]
            for prefix in ("Check in or drop your bags at ", "Check out and collect bags at ", "Back at ", "Depart from "):
                dest = dest.replace(prefix, "")
            how = "Walk" if leg.mode == "walk" else leg.mode.capitalize()
            steps.append({"time": _hhmm(clock), "end": _hhmm(clock + travel), "kind": "travel",
                          "title": f"{how} to {dest}", "distance_km": leg.distance_km, "minutes": travel,
                          "mode": leg.mode, "estimated": leg.source != "osrm"})
            clock += travel
        starts.append(clock)
        title = m["title"]
        generic = re.match(r"(breakfast|brunch|lunch|dinner|snack|coffee|meal) near (.+)", title, re.I)
        if m["kind"] == "meal" and generic:   # name a generic meal by when it actually happens
            title = f"{'Breakfast' if clock < 10 * 60 + 30 else 'Lunch' if clock < 16 * 60 else 'Snack' if clock < 18 * 60 else 'Dinner'} near {generic.group(2)}"
        step = {"time": _hhmm(clock), "end": _hhmm(clock + m["minutes"]) if m["minutes"] else None,
                "kind": m["kind"], "title": title, "detail": m.get("detail") or None,
                "minutes": m["minutes"] or None}
        if m.get("place"):
            step["place"] = _public(m["place"])
        if m.get("cite"):
            step["cite"] = m["cite"]
        if m.get("unverified"):
            step["unverified"] = True
        steps.append(step)
        clock += m["minutes"]
    return steps, starts


def _fix_meals(moments: list[dict], starts: list[int], area: str) -> bool:
    """One correction to the day's meals (moved, dropped or added). True if anything changed."""
    stops = [k for k, m in enumerate(moments) if m["kind"] in STOP_KINDS]
    # a) "Dinner" in the afternoon while sights are still to come: eat after them instead.
    for k in stops:
        if moments[k]["kind"] == "meal" and DINNER_WINDOW[0] <= starts[k] < DINNER_FROM:
            j = k + 1
            while j < len(moments) and moments[j]["kind"] in ("sight", "activity", "free"):
                j += 1
            if any(moments[x]["kind"] in ("sight", "activity") for x in range(k + 1, j)):
                moments.insert(j - 1, moments.pop(k))
                return True
    # b) An evening-only show or market before it opens: move it after the day's other sights.
    for k in stops:
        m = moments[k]
        opens = opening_minute((m.get("place") or {}).get("hours"))
        if m["kind"] in ("sight", "activity") and opens and opens >= 16 * 60 and starts[k] < opens - 150:
            later = [x for x in range(k + 1, len(moments)) if moments[x]["kind"] in ("sight", "activity")]
            if later:
                moments.insert(later[-1], moments.pop(k))
                return True
    # c) Two dinners back to back: keep the first.
    for a, b in zip(stops, stops[1:]):
        if b == a + 1 and moments[a]["kind"] == moments[b]["kind"] == "meal" and starts[b] >= 17 * 60:
            del moments[b]
            return True
    # d) A generic meal less than 3 hours after another meal is one meal too many.
    meals = [k for k in stops if moments[k]["kind"] == "meal"]
    for a, b in zip(meals, meals[1:]):
        if starts[b] - starts[a] < 180 and not moments[b].get("place"):
            del moments[b]
            return True
    # e) A busy day with no lunch: add one (any local place) before the afternoon's first stop.
    if not any(moments[k]["kind"] == "meal" and 11 * 60 + 30 <= starts[k] <= 15 * 60 for k in stops):
        after = [k for k in stops if moments[k]["kind"] in ("sight", "activity") and 12 * 60 + 15 <= starts[k] < 15 * 60]
        if after:
            moments.insert(after[0], {"kind": "meal", "title": f"Lunch near {area}", "pt": None, "minutes": 60,
                                      "detail": "Any busy local place nearby; a set meal or thali is quick and good value."
                                      })
            return True
    return False

"""The structured trip plan: schema, enrichment, scheduling and Markdown rendering.

Pipeline for one plan:

    Planner (LLM) ──► TripPlan JSON:  ordered stops per day (real place ids only),
                                       3 options (budget / luxury / yours) with a stay
                                       *area + type* and 3–5 real stay candidates
         │
    enrich()  ──► validates every place id against the real candidate lists,
                  fetches real photos (find_photos skill),
                  builds a timestamped schedule per option (build_schedule skill:
                  real road distances, arrival hub → hotel → stops → hotel)
         │
    plan dict ──► cards, timeline, map, stays chooser, PDF / calendar / Markdown

Choosing a hotel later only re-runs build_schedule (code, no LLM).
"""

from __future__ import annotations

import re

from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.skills.photos import area_photo, find_photos
from backend.skills.schedule import build_schedule

Tier = Literal["budget", "luxury", "yours"]
TIERS = ("budget", "luxury", "yours")
TIER_LABEL = {"budget": "Budget", "luxury": "Luxury", "yours": "Your budget"}
STAY_TIER = {"budget": ("budget",), "luxury": ("luxury",), "yours": ("mid", "budget", "luxury")}


# ====================================================================== schema
class PlanStop(BaseModel):
    kind: Literal["sight", "meal", "activity", "free"] = "sight"
    place_id: str | None = Field(None, description="id of a SIGHT or EAT candidate; null only for generic free time")
    title: str = Field("", description="Short label; for listed places the real name is used automatically")
    duration_min: int | None = Field(None, description="Realistic time spent here, minutes")
    note: str = Field("", description="One practical tip: what to see/order, best time, tickets")
    cost: float | None = Field(None, description="Per-person entry or meal cost in the plan currency")
    cite: list[int] | None = None

    @field_validator("note", "title", mode="before")
    @classmethod
    def _none_str(cls, v):
        return v or ""

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, v):
        v = str(v or "sight").lower()
        if v in ("sight", "meal", "activity", "free"):
            return v
        if any(w in v for w in ("eat", "food", "lunch", "dinner", "breakfast", "meal", "cafe", "restaurant")):
            return "meal"
        if any(w in v for w in ("free", "rest", "relax", "leisure")):
            return "free"
        return "activity" if v in ("do", "experience", "tour", "cruise") else "sight"


class PlanDay(BaseModel):
    day: int
    title: str
    area: str | None = None
    stops: list[PlanStop]


class Breakdown(BaseModel):
    travel: float = Field(0, description="Getting there and back (flight/train/bus), whole party")
    stay: float = 0
    food: float = 0
    transport: float = Field(0, description="Local transport at the destination")
    activities: float = 0
    other: float = 0


class GettingThere(BaseModel):
    mode: str = Field(description="flight, train, bus, car or ferry")
    detail: str = Field(description="e.g. '3AC sleeper on the Goa Express, Hyderabad → Madgaon'")
    duration: str | None = None
    cost: float | None = Field(None, description="Round trip for the whole party")
    arrive_at: str | None = Field(None, description="Arrival station / airport / bus stand at the destination")
    depart_from_destination: str | None = Field(None, description="Where the return journey leaves from")
    arrive_time: str | None = Field(None, description="Typical arrival time HH:MM on day 1")


class StayAdvice(BaseModel):
    area: str = Field(description="Recommended neighbourhood to stay in")
    kind: str = Field(description="e.g. 'hostel dorm', 'guesthouse', '3-star hotel', 'beach resort'")
    nightly_min: float | None = None
    nightly_max: float | None = None
    why: str = ""
    candidate_ids: list[str] = Field(default_factory=list, description="3-5 STAY candidate ids that fit")

    @field_validator("candidate_ids", mode="before")
    @classmethod
    def _none_list(cls, v):
        return v or []


class PlanOption(BaseModel):
    tier: Tier
    title: str = Field(description="Short catchy name, e.g. 'Backpacker beach life'")
    total: float = Field(description="Total trip cost for the whole party, plan currency")
    breakdown: Breakdown
    getting_there: GettingThere | None = None
    stay: StayAdvice
    highlights: list[str] = Field(default_factory=list)
    fits_budget: bool | None = None
    note: str | None = None

    @field_validator("highlights", mode="before")
    @classmethod
    def _none_list(cls, v):
        return v or []


class TripPlan(BaseModel):
    summary: str = Field(description="2-3 sentence overview of the trip")
    answer: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    currency: str
    days: list[PlanDay]
    options: list[PlanOption]
    packing: list[str] = Field(default_factory=list)
    weather_note: str | None = None
    tips: list[str] = Field(default_factory=list)

    @field_validator("assumptions", "packing", "tips", mode="before")
    @classmethod
    def _none_list(cls, v):
        return v or []

    @model_validator(mode="after")
    def _three_options(self):
        tiers = sorted(o.tier for o in self.options)
        if tiers != ["budget", "luxury", "yours"]:
            raise ValueError(f"options must be exactly budget, luxury and yours; got {tiers}")
        return self


class BookingStep(BaseModel):
    item: str = Field(description="What to book, e.g. 'Train tickets Hyderabad → Madgaon'")
    when: str = Field(description="When to book, e.g. '60 days ahead (IRCTC opens bookings then)'")
    where: str = Field(description="Where/how to book")
    cost: float | None = None


class OptionDetails(BaseModel):
    """What the concierge adds when an option is chosen (the schedule itself is computed)."""
    overview: str = Field(description="3-4 sentences on what this option is like to live")
    booking_checklist: list[BookingStep] = Field(default_factory=list)
    money_tips: list[str] = Field(default_factory=list)
    good_to_know: list[str] = Field(default_factory=list)

    @field_validator("booking_checklist", "money_tips", "good_to_know", mode="before")
    @classmethod
    def _none_list(cls, v):
        return v or []


# ====================================================================== enrichment
_PUBLIC_KEYS = ("id", "name", "kind", "tier", "area", "lat", "lon", "price", "hours", "url", "description", "photo")


def public(p: dict) -> dict:
    return {k: p.get(k) for k in _PUBLIC_KEYS if p.get(k) not in (None, "")}


def _meal_label(stop: PlanStop) -> str:
    t = (stop.title or "").lower()
    for word in ("breakfast", "lunch", "dinner", "snack", "coffee"):
        if word in t:
            return word.capitalize()
    return "Meal"


def enrich(plan: TripPlan, trip: dict, *, stays: list[dict], sights: list[dict], eats: list[dict],
           sources: list[dict], center: dict | None, weather: dict | None, transport: dict | None,
           web_results: list[dict] | None, pace: str = "moderate") -> dict:
    """Validate place ids against real data, add photos, and build a schedule per option."""
    sight_ids = {p["id"]: p for p in [*sights]}
    eat_ids = {p["id"]: p for p in eats}
    stay_ids = {p["id"]: p for p in stays}
    destination = trip.get("destination") or ""
    india = (trip.get("currency") or "").upper() == "INR" or (trip.get("country") or "").lower() == "india"
    data = plan.model_dump()
    # Planner bookkeeping ("all place IDs are valid") is not something a traveller needs to read.
    data["assumptions"] = [x for x in data.get("assumptions") or []
                           if not re.search(r"\b(place[ _]?ids?|ids?|candidate|listed)\b", x, re.I)]
    used: dict[str, dict] = {}

    # 1. Every named stop must be a real listed place; anything else is made generic or flagged.
    #    A sight is visited once per trip (the planner sometimes repeats one on another day).
    visited: set[str] = set()
    for d in data["days"]:
        area = d.get("area") or destination
        d["stops"] = [s for s in d["stops"] if s["kind"] == "meal" or not s.get("place_id")
                      or not (s["place_id"] in visited or visited.add(s["place_id"]))]
        for s in d["stops"]:
            pool = eat_ids if s["kind"] == "meal" else sight_ids
            place = pool.get(s.get("place_id") or "") or sight_ids.get(s.get("place_id") or "") or eat_ids.get(s.get("place_id") or "")
            if place:
                s["title"] = place["name"]
                used[place["id"]] = place
            else:
                s["place_id"] = None
                if s["kind"] == "meal":
                    s["title"] = f"{_meal_label(PlanStop(**s))} near {area}"
                elif s["kind"] in ("sight", "activity"):
                    s["unverified"] = True   # shown with a "not verified" badge in the app

    # 2. Stay candidates per option: only real listings, topped up from the right price tier.
    for o in data["options"]:
        ids = [i for i in o["stay"]["candidate_ids"] if i in stay_ids]
        for p in stays:                     # give the traveller a real choice: up to 6 per option
            if len(ids) >= 6:
                break
            if p.get("tier") in STAY_TIER[o["tier"]] and p["id"] not in ids:
                ids.append(p["id"])
        o["stay"]["candidate_ids"] = ids[:6]
        for i in o["stay"]["candidate_ids"]:
            used[i] = stay_ids[i]

    # 3. Real photos for every place we show (cached), in parallel with nothing else to wait on.
    find_photos(list(used.values()), limit=60)
    for o in data["options"]:   # stays without their own photo get a labelled photo of their area
        for i in o["stay"]["candidate_ids"]:
            p = used[i]
            if not p.get("photo"):
                near = (float(p["lat"]), float(p["lon"])) if p.get("lat") is not None and p.get("lon") is not None else None
                p["photo"] = area_photo(p.get("area") or o["stay"].get("area") or destination, destination, near=near)
    places = {pid: public(p) for pid, p in used.items()}
    data["places"] = places

    # 4. A timestamped schedule per option (each arrives differently and sleeps in a different area).
    order = {t: n for n, t in enumerate(TIERS)}
    data["options"].sort(key=lambda o: order.get(o["tier"], 9))
    travelers = max(int(trip.get("travelers") or 1), 1)
    n_days = max(len(data["days"]), 1)
    for o in data["options"]:
        o["label"] = TIER_LABEL[o["tier"]]
        o["per_person"] = round(o["total"] / travelers, 2) if o.get("total") else None
        o["per_day"] = round(o["total"] / n_days, 2) if o.get("total") else None
        o["stay"]["candidates"] = [places[i] for i in o["stay"]["candidate_ids"] if i in places]

    data.update({
        "trip": {k: v for k, v in trip.items() if v not in (None, [], "")},
        "travelers": travelers,
        "sources": sources,
        "map_center": center,
        "weather": weather,
        "transport": transport,
        "web_results": web_results or [],
        "hotels": {t: None for t in TIERS},     # the stay the traveller picked, per option
        "pace": pace,
        "india": india,
    })
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = dict(zip(TIERS, pool.map(lambda t: schedule_for(data, t), TIERS)))
    data["schedules"] = results
    data["markers"] = build_markers(data)
    return data


def schedule_for(data: dict, tier: str) -> list[dict]:
    """(Re)build one option's timestamped schedule; no LLM call."""
    option = next(o for o in data["options"] if o["tier"] == tier)
    hotel_id = (data.get("hotels") or {}).get(tier)
    hotel = data["places"].get(hotel_id) if hotel_id else None
    return build_schedule(
        data["days"], data["places"], data["trip"].get("destination", ""),
        getting_there=option.get("getting_there"), hotel=hotel, hotel_area=option["stay"].get("area"),
        start_date=data["trip"].get("start_date"), pace=data.get("pace") or "moderate", india=data.get("india", True),
    )


def build_markers(data: dict) -> list[dict]:
    markers: dict[str, dict] = {}
    for d in data["days"]:
        for s in d["stops"]:
            p = data["places"].get(s.get("place_id") or "")
            if p and p.get("lat") is not None:
                m = markers.setdefault(p["id"], {**p, "kind": "meal" if s["kind"] == "meal" else "sight", "days": []})
                if d["day"] not in m["days"]:
                    m["days"].append(d["day"])
    for o in data["options"]:
        picked = (data.get("hotels") or {}).get(o["tier"])
        for pid in ([picked] if picked else o["stay"]["candidate_ids"][:3]):
            p = data["places"].get(pid or "")
            if p and p.get("lat") is not None:
                m = markers.setdefault(pid, {**p, "kind": "stay", "tiers": []})
                m.setdefault("tiers", []).append(o["tier"])
    return list(markers.values())


def active_tier(plan: dict) -> str:
    return plan.get("selected_tier") or "yours"


# ====================================================================== formatting
def indian_number(value: float) -> str:
    """Indian digit grouping: 150000 → 1,50,000 and 12500000 → 1,25,00,000."""
    n = int(round(abs(value)))
    s = str(n)
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ("-" if value < 0 else "") + ",".join([*groups, tail])


def money(value, currency: str) -> str:
    if value is None:
        return "—"
    if (currency or "").upper() == "INR":
        return f"₹{indian_number(value)}"
    return f"{currency} {value:,.0f}"


def stay_label(o: dict, cur: str) -> str:
    s = o["stay"]
    price = ""
    if s.get("nightly_min") or s.get("nightly_max"):
        price = f", {money(s.get('nightly_min'), cur)}–{money(s.get('nightly_max'), cur)}/night"
    return f"{s.get('kind', 'stay').capitalize()} in {s.get('area', '')}{price}"


def _picked_name(plan: dict, o: dict) -> str | None:
    hotel = (plan.get("places") or {}).get(((plan.get("hotels") or {}).get(o["tier"])) or "")
    return hotel["name"] if hotel else None


def step_line(s: dict) -> str:
    if s["kind"] == "travel":
        how = "walk" if s.get("mode") == "walk" else s.get("mode", "")
        return f"{s['time']}  {s['title']} ({s.get('distance_km')} km · {s.get('minutes')} min by {how})"
    dur = f" ({s['minutes']} min)" if s.get("minutes") and s["kind"] not in ("start", "end", "depart") else ""
    return f"{s['time']}  {s['title']}{dur}"


def to_markdown(plan: dict) -> str:
    """Readable Markdown version: used for chat history and the .md export."""
    cur = plan.get("currency", "")
    trip = plan.get("trip", {})
    tier = active_tier(plan)
    lines = [f"# {trip.get('destination', 'Trip')}: {len(plan.get('days', []))}-day plan", ""]
    if plan.get("answer"):
        lines += [f"**{plan['answer']}**", ""]
    lines += [plan.get("summary", ""), ""]
    if plan.get("assumptions"):
        lines += ["_Assumptions: " + "; ".join(plan["assumptions"]) + "_", ""]

    lines += ["## Your three options", "", "| Option | Total | Per person | Stay |", "|---|---|---|---|"]
    for o in plan.get("options", []):
        lines.append(f"| {o['label']}: {o['title']} | {money(o['total'], cur)} | {money(o.get('per_person'), cur)} "
                     f"| {_picked_name(plan, o) or stay_label(o, cur)} |")
    lines.append("")
    for o in plan.get("options", []):
        b = o["breakdown"]
        gt = o.get("getting_there") or {}
        lines += [f"### {o['label']}: {o['title']}",
                  f"**Total {money(o['total'], cur)}** · travel {money(b.get('travel'), cur)} · "
                  f"stay {money(b['stay'], cur)} · food {money(b['food'], cur)} · "
                  f"local transport {money(b['transport'], cur)} · activities {money(b['activities'], cur)} · "
                  f"other {money(b['other'], cur)}"]
        if gt:
            lines.append(f"- Getting there: **{gt['mode'].title()}**: {gt['detail']}"
                         + (f" ({gt['duration']})" if gt.get("duration") else "")
                         + (f", arriving at {gt['arrive_at']}" if gt.get("arrive_at") else "")
                         + (f", {money(gt.get('cost'), cur)} return" if gt.get("cost") else ""))
        picked = plan.get("places", {}).get((plan.get("hotels") or {}).get(o["tier"]) or "")
        lines.append(f"- Stay: **{picked['name'] if picked else stay_label(o, cur)}**"
                     + (f": {o['stay']['why']}" if o["stay"].get("why") else ""))
        lines += [f"- {h}" for h in o.get("highlights", [])]
        lines.append("")

    label = TIER_LABEL.get(tier, tier)
    lines += [f"## Day by day ({label} option)", ""]
    for d in (plan.get("schedules") or {}).get(tier, []):
        when = f" ({d['date']})" if d.get("date") else ""
        lines += [f"### Day {d['day']}{when}: {d['title']}", ""]
        lines += [f"- {step_line(s)}" for s in d["steps"]]
        lines.append("")

    chosen = next((o for o in plan.get("options", []) if o.get("details") and o["tier"] == plan.get("selected_tier")), None)
    if chosen and chosen["details"].get("booking_checklist"):
        lines += ["## Booking checklist", *[f"- [ ] {b['item']}: {b['when']}, via {b['where']}"
                                           + (f" ({money(b.get('cost'), cur)})" if b.get("cost") else "")
                                           for b in chosen["details"]["booking_checklist"]], ""]

    if plan.get("transport") and plan["transport"].get("modes"):
        t = plan["transport"]
        lines += [f"## Getting there from {t.get('origin')}", t.get("summary", ""), ""]
        for m in t["modes"]:
            if not m.get("available"):
                continue
            price = (f"{money(m.get('price_min'), t.get('currency'))}–{money(m.get('price_max'), t.get('currency'))}"
                     if m.get("price_min") is not None else "")
            lines.append(f"- **{m['mode'].title()}**: {m.get('duration') or ''} · {price} per person one way"
                         + (f" · {m['route']}" if m.get("route") else ""))
        lines.append("")

    if plan.get("weather_note"):
        lines += ["## Weather", plan["weather_note"], ""]
    if plan.get("packing"):
        lines += ["## Packing list", *[f"- {p}" for p in plan["packing"]], ""]
    if plan.get("tips"):
        lines += ["## Tips", *[f"- {t}" for t in plan["tips"]], ""]
    lines.append("_Times are planned with real road distances; prices are estimates. Check with providers before booking._")
    return "\n".join(lines)

"""The structured trip plan: schema, enrichment and Markdown rendering.

The Planner agent returns a TripPlan as JSON. One shared day-by-day
sightseeing plan, plus three options that differ in comfort and cost:
Budget, Luxury, and "Your budget" (fitted to the traveller's range).
Every format (cards, timeline, map, PDF, calendar, Markdown) is rendered
from this one object.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Tier = Literal["budget", "luxury", "yours"]
TIER_LABEL = {"budget": "Budget", "luxury": "Luxury", "yours": "Your budget"}


class PlanItem(BaseModel):
    time: str = Field(description="Morning, Afternoon, Evening (or a clock time)")
    title: str
    description: str = ""
    place_id: str | None = Field(None, description="id of a candidate sight (e.g. 'p14') if this visits one")
    cost: float | None = Field(None, description="Per-person cost in the plan currency, if any")
    cite: list[int] | None = Field(None, description="Knowledge source numbers backing this item")


class PlanDay(BaseModel):
    day: int
    title: str
    area: str | None = None
    items: list[PlanItem]


class Breakdown(BaseModel):
    stay: float = 0
    food: float = 0
    transport: float = 0
    activities: float = 0
    other: float = 0


class StayPick(BaseModel):
    place_id: str | None = Field(None, description="id of the chosen candidate stay (e.g. 'p3')")
    name: str
    nightly: float | None = Field(None, description="Price per night for the whole party")
    why: str = ""


class PlanOption(BaseModel):
    tier: Tier
    title: str = Field(description="Short catchy name, e.g. 'Backpacker beach life'")
    total: float = Field(description="Total trip cost for the whole party, plan currency")
    breakdown: Breakdown
    stay: StayPick
    alt_stay_ids: list[str] | None = Field(None, description="1-2 other suitable candidate stay ids")
    highlights: list[str] = Field(default_factory=list, description="How this option differs: dining, transport, extras")
    fits_budget: bool | None = Field(None, description="For 'yours': does it fit the stated range?")
    note: str | None = None

    @field_validator("highlights", mode="before")
    @classmethod
    def _none_list(cls, v):
        return v or []


class TripPlan(BaseModel):
    summary: str = Field(description="2-3 sentence overview of the trip")
    answer: str | None = Field(None, description="Direct answer if the traveller asked a question")
    assumptions: list[str] = Field(default_factory=list)
    currency: str = Field(description="ISO currency code used for every amount")
    days: list[PlanDay]
    options: list[PlanOption] = Field(description="Exactly three: budget, luxury, yours (in that order)")
    packing: list[str] = Field(default_factory=list)
    weather_note: str | None = None
    tips: list[str] = Field(default_factory=list)

    @field_validator("assumptions", "packing", "tips", mode="before")
    @classmethod
    def _none_list(cls, v):
        return v or []


def enrich(plan: TripPlan, trip: dict, stays: list[dict], sights: list[dict],
           sources: list[dict], center: dict | None, weather: dict | None) -> dict:
    """Attach real place data (coords, prices, links) and dates to the plan."""
    by_id = {p["id"]: p for p in [*stays, *sights]}
    data = plan.model_dump()
    travelers = max(int(trip.get("travelers") or 1), 1)

    start = None
    if trip.get("start_date"):
        try:
            start = date.fromisoformat(trip["start_date"])
        except ValueError:
            start = None

    markers: dict[str, dict] = {}
    for d in data["days"]:
        d["date"] = (start + timedelta(days=d["day"] - 1)).isoformat() if start else None
        for item in d["items"]:
            place = by_id.get(item.get("place_id") or "")
            if place:
                item["place"] = _place_public(place)
                if place.get("lat") is not None:
                    markers.setdefault(place["id"], {**_place_public(place), "kind": "sight", "days": []})
                    markers[place["id"]]["days"].append(d["day"])

    order = {"budget": 0, "luxury": 1, "yours": 2}
    data["options"].sort(key=lambda o: order.get(o["tier"], 9))
    for o in data["options"]:
        o["label"] = TIER_LABEL.get(o["tier"], o["tier"].title())
        o["per_person"] = round(o["total"] / travelers, 2) if o.get("total") else None
        days = max(len(data["days"]), 1)
        o["per_day"] = round(o["total"] / days, 2) if o.get("total") else None
        place = by_id.get(o["stay"].get("place_id") or "")
        if place:
            o["stay"]["place"] = _place_public(place)
            if place.get("lat") is not None:
                markers.setdefault(place["id"], {**_place_public(place), "kind": "stay", "tiers": []})
                markers[place["id"]].setdefault("tiers", []).append(o["tier"])
        o["alt_stays"] = [_place_public(by_id[i]) for i in (o.pop("alt_stay_ids", None) or []) if i in by_id]

    data["trip"] = {k: v for k, v in trip.items() if v not in (None, [], "")}
    data["travelers"] = travelers
    data["sources"] = sources
    data["map_center"] = center
    data["markers"] = list(markers.values())
    data["weather"] = weather
    data["stay_candidates"] = [_place_public(s) for s in stays]
    return data


def _place_public(p: dict) -> dict:
    keys = ("id", "name", "kind", "tier", "area", "lat", "lon", "price", "hours", "url", "description")
    return {k: p.get(k) for k in keys if p.get(k) not in (None, "")}


def money(value, currency: str) -> str:
    if value is None:
        return "—"
    return f"{currency} {value:,.0f}"


def to_markdown(plan: dict) -> str:
    """Readable Markdown version: used for chat history and the .md export."""
    cur = plan.get("currency", "")
    trip = plan.get("trip", {})
    lines = [f"# {trip.get('destination', 'Trip')} — {len(plan.get('days', []))}-day plan", ""]
    if plan.get("answer"):
        lines += [f"**{plan['answer']}**", ""]
    lines += [plan.get("summary", ""), ""]
    if plan.get("assumptions"):
        lines += ["_Assumptions: " + "; ".join(plan["assumptions"]) + "_", ""]

    lines += ["## Your three options", "", "| Option | Total | Per person | Stay |", "|---|---|---|---|"]
    for o in plan.get("options", []):
        lines.append(f"| {o['label']}: {o['title']} | {money(o['total'], cur)} | {money(o.get('per_person'), cur)} "
                     f"| {o['stay']['name']} |")
    lines.append("")
    for o in plan.get("options", []):
        b = o["breakdown"]
        lines += [f"### {o['label']} — {o['title']}",
                  f"**Total {money(o['total'], cur)}** · stay {money(b['stay'], cur)} · food {money(b['food'], cur)} · "
                  f"transport {money(b['transport'], cur)} · activities {money(b['activities'], cur)} · "
                  f"other {money(b['other'], cur)}",
                  f"- Stay: **{o['stay']['name']}**" + (f" ({money(o['stay'].get('nightly'), cur)}/night)" if o['stay'].get('nightly') else "")
                  + (f" — {o['stay']['why']}" if o['stay'].get('why') else "")]
        lines += [f"- {h}" for h in o.get("highlights", [])]
        if o.get("note"):
            lines.append(f"- _{o['note']}_")
        lines.append("")

    lines += ["## Day by day", ""]
    for d in plan.get("days", []):
        when = f" ({d['date']})" if d.get("date") else ""
        lines += [f"### Day {d['day']}{when} — {d['title']}", ""]
        for it in d["items"]:
            cite = "".join(f"[{n}]" for n in (it.get("cite") or []))
            cost = f" · {money(it['cost'], cur)}" if it.get("cost") else ""
            lines.append(f"- **{it['time']}:** {it['title']}{cost} {cite}".rstrip())
            if it.get("description"):
                lines.append(f"  {it['description']}")
        lines.append("")

    if plan.get("weather_note"):
        lines += ["## Weather", plan["weather_note"], ""]
    if plan.get("packing"):
        lines += ["## Packing list", *[f"- {p}" for p in plan["packing"]], ""]
    if plan.get("tips"):
        lines += ["## Tips", *[f"- {t}" for t in plan["tips"]], ""]
    if plan.get("sources"):
        lines += ["## Sources", *[f"{s['n']}. {s['title']}" + (f" — {s['section']}" if s.get('section') else "")
                                  + (f" ({s['source']})" if str(s.get('source', '')).startswith('http') else "")
                                  for s in plan["sources"]], ""]
    lines.append("_Prices are estimates; check with the provider before booking._")
    return "\n".join(lines)

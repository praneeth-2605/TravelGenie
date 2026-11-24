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

from pydantic import BaseModel, Field, field_validator, model_validator

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
    getting_there: GettingThere | None = Field(None, description="How this option travels to the destination")
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

    @model_validator(mode="after")
    def _three_options(self):
        tiers = sorted(o.tier for o in self.options)
        if tiers != ["budget", "luxury", "yours"]:
            raise ValueError(f"options must be exactly budget, luxury and yours; got {tiers}")
        return self


class Meal(BaseModel):
    meal: str = Field(description="Breakfast, Lunch, Dinner or Snack")
    place: str = Field(description="Specific restaurant, shack, market or area")
    try_: str | None = Field(None, alias="try", description="What to order")
    cost: float | None = Field(None, description="For the whole party")

    model_config = {"populate_by_name": True}


class DetailDay(BaseModel):
    day: int
    summary: str = Field(description="One line: the feel of the day in this option")
    meals: list[Meal] = Field(default_factory=list)
    getting_around: str | None = Field(None, description="How to move between today's stops, with costs")
    spend: float | None = Field(None, description="Total spend today for the whole party")
    tip: str | None = None

    @field_validator("meals", mode="before")
    @classmethod
    def _none_list(cls, v):
        return v or []


class BookingStep(BaseModel):
    item: str = Field(description="What to book, e.g. 'Train tickets Hyderabad → Madgaon'")
    when: str = Field(description="When to book, e.g. '60 days ahead (IRCTC opens bookings then)'")
    where: str = Field(description="Where/how to book")
    cost: float | None = None


class OptionDetails(BaseModel):
    overview: str = Field(description="3-4 sentences on what this option is like to live")
    days: list[DetailDay]
    booking_checklist: list[BookingStep] = Field(default_factory=list)
    money_tips: list[str] = Field(default_factory=list)
    good_to_know: list[str] = Field(default_factory=list)

    @field_validator("booking_checklist", "money_tips", "good_to_know", mode="before")
    @classmethod
    def _none_list(cls, v):
        return v or []


def enrich(plan: TripPlan, trip: dict, stays: list[dict], sights: list[dict],
           sources: list[dict], center: dict | None, weather: dict | None,
           transport: dict | None = None, web_results: list[dict] | None = None) -> dict:
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
    data["transport"] = transport
    data["web_results"] = web_results or []
    return data


def _place_public(p: dict) -> dict:
    keys = ("id", "name", "kind", "tier", "area", "lat", "lon", "price", "hours", "url", "description")
    return {k: p.get(k) for k in keys if p.get(k) not in (None, "")}


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
        gt = o.get("getting_there") or {}
        lines += [f"### {o['label']} — {o['title']}",
                  f"**Total {money(o['total'], cur)}** · travel {money(b.get('travel'), cur)} · "
                  f"stay {money(b['stay'], cur)} · food {money(b['food'], cur)} · "
                  f"transport {money(b['transport'], cur)} · activities {money(b['activities'], cur)} · "
                  f"other {money(b['other'], cur)}"]
        if gt:
            lines.append(f"- Getting there: **{gt['mode'].title()}**: {gt['detail']}"
                         + (f" ({gt['duration']})" if gt.get("duration") else "")
                         + (f", {money(gt.get('cost'), cur)} return" if gt.get("cost") else ""))
        lines += [f"- Stay: **{o['stay']['name']}**" + (f" ({money(o['stay'].get('nightly'), cur)}/night)" if o['stay'].get('nightly') else "")
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

    chosen = next((o for o in plan.get("options", []) if o.get("details") and o["tier"] == plan.get("selected_tier")), None)
    if chosen:
        det = chosen["details"]
        lines += [f"## Your plan: {chosen['label']} — {chosen['title']}", "", det["overview"], ""]
        for dd in det["days"]:
            lines.append(f"**Day {dd['day']}:** {dd['summary']}" + (f" · spend {money(dd.get('spend'), cur)}" if dd.get("spend") else ""))
            for m in dd.get("meals", []):
                lines.append(f"- {m['meal']}: {m['place']}" + (f" ({m['try']})" if m.get("try") else "")
                             + (f" · {money(m.get('cost'), cur)}" if m.get("cost") else ""))
            if dd.get("getting_around"):
                lines.append(f"- Getting around: {dd['getting_around']}")
            lines.append("")
        if det.get("booking_checklist"):
            lines += ["### Booking checklist", *[f"- [ ] {b['item']}: {b['when']}, via {b['where']}"
                                                + (f" ({money(b.get('cost'), cur)})" if b.get("cost") else "")
                                                for b in det["booking_checklist"]], ""]

    if plan.get("transport") and plan["transport"].get("modes"):
        t = plan["transport"]
        lines += [f"## Getting there from {t.get('origin')}", t.get("summary", ""), ""]
        for m in t["modes"]:
            if not m.get("available"):
                continue
            price = (f"{money(m.get('price_min'), t.get('currency'))}–{money(m.get('price_max'), t.get('currency'))}"
                     if m.get("price_min") is not None else "")
            lines.append(f"- **{m['mode'].title()}**: {m.get('duration') or ''} · {price} per person one way"
                         + (f" · {m['route']}" if m.get("route") else "")
                         + (f" · book via {', '.join(m['book_via'])}" if m.get("book_via") else ""))
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

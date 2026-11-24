"""The multi-agent graph.

                       ┌──► research  ──┐
                       ├──► weather   ──┤
    user ─► supervisor ┼──► stays     ──┼─► compose ─┬─► planner ─► 3 options + day plan
                       ├──► sights    ──┤            └─► writer  ─► cited answer
                       └──► booking   ──┘

The supervisor reads the conversation and the user's saved preferences,
updates the trip brief and picks the specialists this turn needs. They run in
parallel (LangGraph `Send`). New plans and revisions go to the Planner, which
returns a structured TripPlan; questions, bookings and chat go to the Writer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from backend.agents.plan import (OptionDetails, TripPlan, build_markers, enrich, money, schedule_for,
                                 stay_label, step_line)
from backend.agents.specialists import SPECIALISTS, emit
from backend.agents.state import GraphState, RoutingDecision
from backend.llm import ask_json, fast_llm, planner_llm, text_of, writer_llm

log = logging.getLogger(__name__)

# ======================================================================= supervisor
SUPERVISOR_PROMPT = """You are the supervisor of TravelGenie, a team of travel agents.
Today is {today}. Read the conversation and decide how to handle the LAST user message.

Traveller profile (saved preferences, use as defaults): {profile}
Current trip brief (from earlier turns): {trip}
A plan already exists: {has_plan}

Specialists (pick only what this turn needs):
- research: knowledge base + web search (tips, rules, areas, food, what to know)
- weather: live 5-day forecast for the destination
- stays: real hostels/hotels for the destination, by price tier
- sights: real local sights and activities for the destination
- transport: every way to get there from the origin city (flight, train, bus, car, ferry)
- web: web search results / destination guide (what to know, safety, etiquette)
- booking: SIMULATED bookings of hotels/activities/transport

Rules:
- "plan": the user describes a trip (a destination plus length, dates or budget) and no plan exists
  yet, or they want a new destination. Use research + weather + stays + sights + transport + web.
  Even if the message also asks a question, the intent is "plan".
- Questions about getting there (trains, flights, buses, fares) → "question" with transport.
- "revise": change the existing plan (cheaper, more relaxed, swap a day, different budget, more
  days). Call only what the change needs; stays/sights only if the destination changed.
- "question": a specific travel question with no new plan wanted. Usually research only.
- IF A PLAN EXISTS: answering is the default. Use "revise" ONLY when the traveller clearly asks to
  change the plan (change, swap, replace, add, remove, skip, make it cheaper/relaxed, extend, shorten,
  different hotel area, re-plan…). Questions about the plan ("how do I get from the station?", "is the
  fort open on Monday?", "what should I wear?") are "question" and need NO specialists unless they ask
  for new outside facts (then research or transport).
- "book": make simulated bookings. Use booking.
- "chat": greetings / small talk. No specialists.
- Merge new details into the trip brief; keep earlier details unless the user changed them.
  Fill gaps from the profile: currency from home_currency, travelers from default_travelers,
  origin from home_city, budget_min/budget_max from the profile's budget range only if the user
  gave none. "from X" / "flying out of X" sets origin.
- A single budget figure ("under 30000", "30k budget") goes in budget_max.
- Rough dates ("mid-December", "next month") → a concrete start_date guess (15th of that month,
  the next occurrence after today)."""


async def supervisor(state: GraphState) -> dict:
    emit("supervisor", "running", "Reading your request")
    profile = state.get("profile") or {}
    prompt = SUPERVISOR_PROMPT.format(
        today=date.today().isoformat(),
        profile=json.dumps({k: v for k, v in profile.items() if v not in (None, "", []) and k != "user_id"}),
        trip=json.dumps(state.get("trip") or {}),
        has_plan="yes" if state.get("plan") else "no",
    )
    decision = await _route([SystemMessage(prompt), *state["messages"][-8:]], state)
    old_trip = state.get("trip") or {}
    trip = {**old_trip, **(decision.trip.model_dump(exclude_none=True) if decision.trip else {})}
    trip["interests"] = trip.get("interests") or profile.get("interests") or []
    trip["start_date"] = _future_date(trip.get("start_date"))
    trip.setdefault("currency", profile.get("home_currency"))
    if not trip.get("origin") and profile.get("home_city"):
        trip["origin"] = profile["home_city"]
    if not trip.get("travelers") and profile.get("default_travelers"):
        trip["travelers"] = profile["default_travelers"]

    intent = decision.intent
    last = text_of(state["messages"][-1].content) if state.get("messages") else ""
    same_place = not trip.get("destination") or not old_trip.get("destination") or \
        trip["destination"].lower() == old_trip["destination"].lower()
    if state.get("plan") and intent in ("plan", "revise") and same_place and not _CHANGE.search(last):
        log.info("supervisor wanted to %s, but the message asks for no change: answering instead", intent)
        intent = "question"
        trip = {**old_trip, **{k: v for k, v in trip.items() if k == "origin"}}
    agents = list(dict.fromkeys(decision.agents or []))
    if intent == "chat":
        agents = []
    elif intent == "plan":
        agents = list(dict.fromkeys(["research", "weather", "stays", "sights", "transport", "web", *agents]))
    elif intent == "revise" and not state.get("plan"):
        intent = "plan"
        agents = ["research", "weather", "stays", "sights", "transport", "web"]
    elif intent == "question" and not agents and not state.get("plan"):
        agents = ["research"]          # with a plan in hand, the writer can answer from it directly
    # A new destination needs fresh places, weather and transport.
    if trip.get("destination") and old_trip.get("destination") and \
            trip["destination"].lower() != old_trip["destination"].lower() and intent in ("plan", "revise"):
        agents = list(dict.fromkeys([*agents, "stays", "sights", "weather", "research", "transport", "web"]))
    # A new starting city needs a fresh transport comparison.
    if trip.get("origin") and (trip.get("origin") or "").lower() != (old_trip.get("origin") or "").lower() \
            and state.get("plan") and intent in ("plan", "revise", "question"):
        agents = list(dict.fromkeys([*agents, "transport"]))

    reason = decision.reason or f"intent: {intent}"
    emit("supervisor", "done", reason, intent=intent, agents=agents,
         trip={k: v for k, v in trip.items() if v not in (None, [], "")})
    update = {"intent": intent, "agents": agents, "trip": trip, "findings": {}}
    if "research" in agents:
        update["sources"] = []  # keep earlier sources when research isn't re-run
    return update


# Words that mean "change my plan". Without one, a message about an existing plan is answered, not re-planned.
_CHANGE = re.compile(
    r"\b(chang\w*|swap\w*|replac\w*|add\w*|remov\w*|drop\w*|skip\w*|instead|cheaper|costlier|budget|"
    r"relax\w*|faster|slower|shorter|longer|extend\w*|shorten\w*|reduc\w*|increas\w*|updat\w*|modif\w*|"
    r"re-?plan\w*|redo|rework|move|reschedul\w*|switch\w*|includ\w*|exclud\w*|upgrad\w*|downgrad\w*|"
    r"another|different|new plan|more days|fewer days|less (?:walking|travel)|day \d+ (?:to|with))\b", re.I)


def _future_date(value: str | None) -> str | None:
    """Models often pick this year for 'early April' even when it has passed."""
    if not value:
        return None
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return None
    today = date.today()
    while d < today:
        try:
            d = d.replace(year=d.year + 1)
        except ValueError:  # 29 Feb
            d = d.replace(year=d.year + 1, day=28)
    return d.isoformat()


async def _route(messages, state: GraphState) -> RoutingDecision:
    """Tool-call routing, then a JSON-mode retry, then a safe default."""
    try:
        router = fast_llm().with_structured_output(RoutingDecision, method="function_calling")
        return await router.ainvoke(messages)
    except Exception as exc:
        log.warning("structured routing failed, retrying as JSON: %s", str(exc)[:200])
    try:
        schema = json.dumps(RoutingDecision.model_json_schema())
        reply = await fast_llm().ainvoke([
            *messages,
            SystemMessage(f"Respond with ONLY a JSON object matching this schema:\n{schema}"),
        ])
        raw = re.search(r"\{.*\}", text_of(reply.content), re.S)
        return RoutingDecision.model_validate_json(raw.group(0))
    except Exception as exc:
        log.warning("JSON routing failed, using default: %s", str(exc)[:200])
    last = text_of(state["messages"][-1].content) if state.get("messages") else ""
    small_talk = len(last.split()) <= 4 and not state.get("trip")
    return RoutingDecision(intent="chat" if small_talk else "question", trip={},
                           agents=[] if small_talk else ["research"], reason="default routing")


def route(state: GraphState):
    agents = state.get("agents") or []
    if agents:
        return [Send(a, state) for a in agents]
    return "planner" if state.get("intent") in ("plan", "revise") else "writer"


async def compose(state: GraphState) -> dict:
    """Join point after the parallel specialists."""
    return {}


def after_compose(state: GraphState) -> str:
    return "planner" if state.get("intent") in ("plan", "revise") else "writer"


# ======================================================================= planner
PLANNER_PROMPT = """You are TravelGenie's lead trip planner. Build a complete plan as ONE JSON object.

Return exactly this shape (all money in "currency", totals for the WHOLE party):
{{
 "summary": "2-3 sentences",
 "answer": "direct 1-3 line answer if the traveller asked a question, else null",
 "assumptions": ["anything you had to assume (dates, exchange rates, nights, arrival times)"],
 "currency": "{currency}",
 "days": [{{"day": 1, "title": "theme", "area": "neighbourhood",
           "stops": [{{"kind": "sight", "place_id": "p12", "duration_min": 90,
                       "note": "one practical tip: what to see, tickets, best time", "cost": 0, "cite": [1]}},
                     {{"kind": "meal", "place_id": "p40", "title": "Lunch", "duration_min": 60,
                       "note": "what to order", "cost": 0}}]}}],
 "options": [
   {{"tier": "budget", "title": "catchy name", "total": 0,
     "breakdown": {{"travel": 0, "stay": 0, "food": 0, "transport": 0, "activities": 0, "other": 0}},
     "getting_there": {{"mode": "train", "detail": "service/class and route", "duration": "...", "cost": 0,
                       "arrive_at": "exact arrival station/airport/bus stand name", "arrive_time": "HH:MM",
                       "depart_from_destination": "station/airport for the return"}},
     "stay": {{"area": "neighbourhood", "kind": "hostel dorm / guesthouse / 3-star hotel / resort",
              "nightly_min": 0, "nightly_max": 0, "why": "why this area and type suit this option",
              "candidate_ids": ["p3", "p5", "p7"]}},
     "highlights": ["how this option feels: dining, transport, extras"], "fits_budget": null, "note": null}},
   {{"tier": "luxury", ...}},
   {{"tier": "yours", ...}}
 ],
 "packing": ["..."], "weather_note": "...", "tips": ["..."]
}}

Rules for the days (the app turns them into a timestamped schedule with real travel times):
- Exactly {days} days. Each day is an ORDERED list of stops; do NOT write clock times.
- Every "sight"/"activity" stop MUST use a SIGHT candidate id. Every "meal" stop should use an EAT
  candidate id near that day's sights; if none fits, set place_id null and title "Lunch"/"Dinner".
  NEVER invent place names: unlisted places are flagged as unverified to the traveller.
- 3-5 sights or activities per day plus lunch and dinner, in a sensible geographic order (nearby
  places together, no zig-zagging). Pace: {pace}. Interests: {interests}. Dietary: {dietary}.
- Respect hours and the best time of day (sunset cruises/viewpoints in the evening, markets in the
  morning, museums within opening hours). Realistic duration_min for each stop.
- Day 1 starts on arrival, the last day ends with departure: plan fewer stops on those days.
- Cite knowledge sources as numbers in "cite" only when a stop relies on them.

Rules for the options:
- The day plan is shared; options differ in travel mode, stay, food and extras.
- budget: cheapest sensible trip; stay candidates from [budget]. luxury: premium (top stays, flights or
  private transfers, fine dining, special experiences), candidates from [luxury], total clearly highest.
- yours: {yours_rule} Choose the best-value stay type and area; candidates of any tier that fit. Set fits_budget.
- stay: recommend an AREA and TYPE with a nightly price range; list 3-5 real STAY candidate ids that
  match (the traveller picks one). Do not commit to a single hotel.
- getting_there: from the TRANSPORT comparison (budget → cheapest; luxury → fastest/most comfortable;
  yours → best value). Use the real arrival station/airport names given there. travel cost = ROUND TRIP
  for all travellers. If origin is unknown, set getting_there null and travel 0.
- Prefer listed prices; convert with approximate rates (note in assumptions). Nights = {nights}.
  Travellers = {travelers}. Breakdown must add up to total.
{revise_block}
STAY candidates (id [tier] name — area — price):
{stays}

SIGHT candidates (id [kind] name — area — hours/price — note):
{sights}

EAT candidates (id name — area — price — note):
{eats}

TRANSPORT (per person, one way, {currency}):
{transport}

Weather: {weather}

Knowledge sources:
{sources}"""


def _fmt_transport(t: dict | None) -> str:
    if not t or not t.get("modes"):
        return "(origin unknown or no comparison)"
    rows = [f"From {t.get('origin')} (~{t.get('distance_km') or '?'} km):"]
    for m in t["modes"]:
        if m.get("available"):
            rows.append(f"- {m['mode']}{(' ' + m['label']) if m.get('label') else ''}: {m.get('duration') or '?'}, "
                        f"{m.get('price_min')}-{m.get('price_max')}, {m.get('route') or ''}"
                        f"{(' · arrives at ' + m['arrive_at']) if m.get('arrive_at') else ''}"
                        f"{(' ~' + m['arrive_time']) if m.get('arrive_time') else ''}")
    return "\n".join(rows)


def _fmt_stays(stays: list[dict]) -> str:
    rows = [f"{s['id']} [{s['tier']}] {s['name']} — {s.get('area') or ''} — {s.get('price') or 'price n/a'}"
            for s in stays[:20]]
    return "\n".join(rows) or "(none found: recommend an area and type; leave candidate_ids empty)"


def _fmt_eats(eats: list[dict]) -> str:
    rows = [f"{e['id']} {e['name']} — {e.get('area') or ''} — {e.get('price') or ''} — {(e.get('description') or '')[:60]}"
            for e in eats[:16]]
    return "\n".join(rows) or "(none found: use generic meal stops with place_id null)"


def _fmt_sights(sights: list[dict]) -> str:
    rows = [f"{s['id']} [{s['kind']}] {s['name']} — {s.get('area') or ''} — "
            f"{s.get('hours') or ''} {s.get('price') or ''} — {(s.get('description') or '')[:70]}"
            for s in sights[:22]]
    return "\n".join(rows) or "(none found: rely on knowledge sources and well-known landmarks)"


def _fmt_sources(sources: list[dict]) -> str:
    return "\n".join(f"[{s['n']}] {s['title']} — {s.get('section') or ''}: {s['text'][:420]}"
                     for s in sources[:6]) or "(none)"


def _fmt_weather(weather: dict | None, findings: dict) -> str:
    if weather and weather.get("daily"):
        return "; ".join(f"{d['date']} {d['min_c']}-{d['max_c']}°C {d['condition']}" for d in weather["daily"])
    return (findings or {}).get("weather") or "unknown: use seasonal knowledge"


def _compact_plan(plan: dict) -> str:
    cur = plan.get("currency", "")
    lines = ["Current plan:"]
    for o in plan.get("options", []):
        lines.append(f"- {o['tier']}: {money(o['total'], cur)}, {stay_label(o, cur)}")
    for d in plan.get("days", []):
        stops = d.get("stops") or d.get("items") or []
        lines.append(f"- Day {d['day']} {d['title']}: " + "; ".join(f"{s.get('title')} ({s.get('place_id') or '-'})" for s in stops))
    return "\n".join(lines)


def _budget_problem(plan: TripPlan, lo: float | None, hi: float | None, currency: str) -> str | None:
    """Describe how the options break the rules, if they do: Budget must be the cheapest,
    Luxury clearly the most expensive, and "yours" inside the traveller's range."""
    tiers = {o.tier: o for o in plan.options}
    budget, luxury, yours = tiers["budget"], tiers["luxury"], tiers["yours"]
    if luxury.total < max(yours.total, budget.total) * 1.15:
        return (f'The luxury option totals {money(luxury.total, currency)} but must be clearly the most premium and '
                f'expensive of the three (yours is {money(yours.total, currency)}). Upgrade luxury (top stay, flights or '
                f'private transfers, fine dining, special experiences) so it costs well above the others. '
                f'Keep budget and yours as they are. Keep breakdown sums exact.')
    if budget.total > yours.total:
        return (f'The budget option ({money(budget.total, currency)}) must be the cheapest of the three, but "yours" is '
                f'{money(yours.total, currency)}. Make budget cheaper. Keep breakdown sums exact.')
    if not hi:
        return None
    target_lo = (lo or hi * 0.85)
    if yours.total < target_lo * 0.97:
        return (f'The "yours" option totals {money(yours.total, currency)}, below the traveller\'s range of '
                f'{money(lo, currency) if lo else "about " + money(target_lo, currency)} to {money(hi, currency)}. '
                f'Upgrade it (better stay, faster/more comfortable travel, nicer dining, an extra experience) so the '
                f'total lands inside the range, ideally 85-100% of the maximum. Keep breakdown sums exact.')
    if yours.total > hi * 1.03:
        return (f'The "yours" option totals {money(yours.total, currency)}, above the maximum of '
                f'{money(hi, currency)}. Bring it inside the range. Keep breakdown sums exact.')
    return None


async def planner(state: GraphState) -> dict:
    trip = state.get("trip") or {}
    profile = state.get("profile") or {}
    revising = state.get("intent") == "revise" and state.get("plan")
    emit("planner", "running", "Revising your plan" if revising else "Building 3 budget options and your day plan")

    days = min(int(trip.get("days") or 3), 10)
    travelers = int(trip.get("travelers") or 1)
    currency = (trip.get("currency") or profile.get("home_currency") or "USD").upper()
    lo, hi = trip.get("budget_min"), trip.get("budget_max")
    if hi:
        yours = (f"total MUST be between {money(lo, currency)} and {money(hi, currency)}." if lo
                 else f"total MUST be at most {money(hi, currency)} (aim for 85-100% of it).")
    else:
        yours = ("the traveller gave no budget: build a balanced mid-range trip and say so in "
                 "assumptions.")
    system = PLANNER_PROMPT.format(
        currency=currency, days=days, nights=max(days - 1, 1), travelers=travelers,
        pace=profile.get("pace") or "moderate",
        interests=", ".join(trip.get("interests") or []) or "general sightseeing",
        dietary=profile.get("dietary") or "none stated",
        yours_rule=yours,
        revise_block=(f"\nREVISION: change the current plan as the traveller asks; keep what they didn't "
                      f"ask to change.\n{_compact_plan(state['plan'])}\n" if revising else ""),
        stays=_fmt_stays(state.get("stays") or []),
        sights=_fmt_sights(state.get("sights") or []),
        eats=_fmt_eats(state.get("eats") or []),
        weather=_fmt_weather(state.get("weather"), state.get("findings") or {}),
        sources=_fmt_sources(state.get("sources") or []),
        transport=_fmt_transport(state.get("transport")),
    )
    request = HumanMessage(
        f"Trip brief: {json.dumps({k: v for k, v in trip.items() if v not in (None, [], '')})}\n"
        f"Traveller's latest message: {text_of(state['messages'][-1].content)}")

    messages = [SystemMessage(system), request]
    try:
        plan = await ask_json(planner_llm(), messages, TripPlan)
        # The model can't be trusted to respect the range: check it, and give it one correction round.
        problem = _budget_problem(plan, lo, hi, currency)
        if problem:
            log.info("planner budget correction: %s", problem)
            emit("planner", "running", "Checking the three options and adjusting")
            fixed = await ask_json(planner_llm(), [*messages, AIMessage(plan.model_dump_json()),
                                                   HumanMessage(problem + " Return the corrected full JSON only.")], TripPlan)
            if not _budget_problem(fixed, lo, hi, currency):
                plan = fixed
    except RuntimeError as exc:
        emit("planner", "error", "Couldn't build a valid plan; please try again")
        return {"messages": [AIMessage(f"Sorry, I couldn't put a valid plan together this time. {exc}")]}
    yours = next(o for o in plan.options if o.tier == "yours")
    if hi:
        yours.fits_budget = (lo or 0) * 0.97 <= yours.total <= hi * 1.03

    emit("planner", "running", "Adding photos and timing every stop with real travel times")
    data = await asyncio.to_thread(
        enrich, plan, {**trip, "currency": currency},
        stays=state.get("stays") or [], sights=state.get("sights") or [], eats=state.get("eats") or [],
        sources=state.get("sources") or [], center=state.get("map_center"), weather=state.get("weather"),
        transport=state.get("transport"), web_results=state.get("web_results"),
        pace=profile.get("pace") or "moderate")
    # A revision keeps the traveller's chosen option and hotels where they still exist.
    data["selected_tier"] = state.get("selected_tier") if revising else None
    if revising:
        old_hotels = (state["plan"].get("hotels") or {})
        changed = False
        for tier, hid in old_hotels.items():
            option = next((o for o in data["options"] if o["tier"] == tier), None)
            if hid and option and hid in option["stay"]["candidate_ids"]:
                data["hotels"][tier] = hid
                changed = True
        if changed:
            data["schedules"] = {t: await asyncio.to_thread(schedule_for, data, t) for t in data["schedules"]}
            data["markers"] = build_markers(data)
    emit("planner", "done", " · ".join(f"{o['label']} {money(o['total'], currency)}" for o in data["options"]))
    update = {"plan": data, "messages": [AIMessage(_chat_summary(data))]}
    if not revising:
        update["selected_tier"] = None
    return update


def _chat_summary(plan: dict) -> str:
    """Short message for the conversation (the full plan renders as cards)."""
    cur = plan["currency"]
    parts = []
    if plan.get("answer"):
        parts.append(f"**{plan['answer']}**\n")
    parts.append(plan["summary"])
    parts.append("")
    for o in plan["options"]:
        parts.append(f"- **{o['label']}** ({o['title']}): {money(o['total'], cur)} · {stay_label(o, cur)}")
    return "\n".join(parts)


# ======================================================================= option details
DETAILS_PROMPT = """You are TravelGenie's trip concierge. The traveller has CHOSEN the "{label}" option
below; its timestamped day-by-day schedule is already built. Add the practical layer as ONE JSON object:
{{
 "overview": "3-4 sentences: what this option feels like and why it fits",
 "booking_checklist": [{{"item": "...", "when": "how far ahead", "where": "site/app/desk", "cost": 0}}],
 "money_tips": ["..."],
 "good_to_know": ["..."]
}}
Rules: the booking checklist is in the order to book: getting there ({getting_there}), the stay
({stay}), then any tickets/tours from the schedule that need booking ahead. Costs in {currency} for the
WHOLE party ({travelers} people). Be specific and realistic; name only places from the schedule.
Diet: {dietary}.

Chosen option:
{option}

Schedule:
{schedule}"""


async def generate_details(plan: dict, tier: str, profile: dict | None = None) -> dict:
    """The concierge layer for a chosen option: overview, booking checklist, tips."""
    option = next(o for o in plan["options"] if o["tier"] == tier)
    cur = plan.get("currency", "")
    gt = option.get("getting_there") or {}
    hotel = plan.get("places", {}).get((plan.get("hotels") or {}).get(tier) or "")
    schedule = "\n".join(
        f"Day {d['day']} {d['title']}: " + "; ".join(step_line(s) for s in d["steps"] if s["kind"] != "travel")
        for d in (plan.get("schedules") or {}).get(tier, []))
    compact = {k: option.get(k) for k in ("title", "total", "breakdown", "highlights")}
    prompt = DETAILS_PROMPT.format(
        label=option["label"], currency=cur, travelers=plan.get("travelers", 1),
        dietary=(profile or {}).get("dietary") or "no restrictions",
        getting_there=f"{gt.get('mode')}: {gt.get('detail')}" if gt else "not specified",
        stay=hotel["name"] if hotel else stay_label(option, cur),
        option=json.dumps(compact, ensure_ascii=False), schedule=schedule[:4000])
    details = await ask_json(planner_llm(), [HumanMessage(prompt)], OptionDetails)
    return details.model_dump(by_alias=True)


def chosen_block(plan: dict | None, tier: str | None) -> str:
    """Context about the traveller's chosen option and its schedule, for the writer."""
    if not plan or not tier:
        return ""
    o = next((x for x in plan.get("options", []) if x["tier"] == tier), None)
    if not o:
        return ""
    cur = plan.get("currency", "")
    gt = o.get("getting_there") or {}
    hotel = plan.get("places", {}).get((plan.get("hotels") or {}).get(tier) or "")
    lines = [f'The traveller CHOSE the "{o["label"]}" option ({o["title"]}), total {money(o["total"], cur)}.',
             f"Stay: {hotel['name'] + ' (' + (hotel.get('area') or '') + ')' if hotel else stay_label(o, cur) + ' (no hotel picked yet)'}."]
    if gt:
        lines.append(f"Getting there: {gt.get('mode')}: {gt.get('detail')} ({gt.get('duration') or ''}), "
                     f"arriving at {gt.get('arrive_at') or '?'}, {money(gt.get('cost'), cur)} return.")
    lines.append("Breakdown: " + ", ".join(f"{k} {money(v, cur)}" for k, v in o["breakdown"].items()))
    for d in (plan.get("schedules") or {}).get(tier, []):
        lines.append(f"Day {d['day']} {d['title']}: " + " | ".join(step_line(s) for s in d["steps"]))
    return "\n".join(lines)[:6000]


# ======================================================================= writer
WRITER_PROMPT = """You are TravelGenie's travel expert. Answer the traveller using the specialist
findings and the numbered knowledge sources below.

Rules:
- Cite sources inline in exactly this form: [1] or [2][4], right after the sentence that uses them.
  Never invent citations; don't cite general knowledge that isn't in the sources.
- If no source covers a fact that changes over time (visas, entry rules, prices, opening hours),
  start that part with "⚠️ Couldn't verify this against current sources" and tell the traveller
  to confirm with the official source.
- Intent "question": answer directly and concisely. If a plan exists, relate the answer to it;
  if the traveller has chosen an option, answer for THAT option (its budget, stay and transport).
- For transport questions use the transport comparison: give each realistic mode with duration,
  price range, route and where to book.
- Intent "book": confirm the SIMULATED bookings (nothing is really reserved) and how they fit.
- Intent "chat": reply briefly and warmly; invite them to describe a trip (destination, days,
  budget) to get three budget options.
- Clean markdown, no preamble like "Sure!".

Intent: {intent}
Trip brief: {trip}
{plan}
{chosen}
Transport comparison:
{transport}

Specialist findings:
{findings}

Knowledge sources:
{sources}"""


async def writer(state: GraphState) -> dict:
    emit("writer", "running", "Writing your answer")
    plan = state.get("plan")
    system = WRITER_PROMPT.format(
        intent=state.get("intent", "question"),
        trip=json.dumps({k: v for k, v in (state.get("trip") or {}).items() if v not in (None, [], "")}),
        plan=_compact_plan(plan) + "\n" if plan else "",
        chosen=chosen_block(plan, state.get("selected_tier")),
        transport=_fmt_transport(state.get("transport")),
        findings="\n\n".join(f"### {k}\n{v}" for k, v in (state.get("findings") or {}).items()) or "(none)",
        sources="\n\n".join(f"[{s['n']}] {s['title']} — {s.get('section') or ''}\n{s['text']}"
                            for s in state.get("sources") or []) or "(none)",
    )
    reply = await writer_llm().ainvoke([SystemMessage(system), *state["messages"][-8:]])
    emit("writer", "done", "")
    return {"messages": [AIMessage(normalize_citations(text_of(reply.content)))]}


_NATIVE_CITE = re.compile(r"【\s*([^】†]*?)\s*(?:†[^】]*)?】")


def normalize_citations(text: str) -> str:
    """gpt-oss models cite in their native style, 【3†L1-L4】. Convert to [3];
    drop markers that don't point at a numbered source (e.g. 【Budget†L2】)."""
    return _NATIVE_CITE.sub(lambda m: f"[{m.group(1)}]" if m.group(1).isdigit() else "", text)


# ======================================================================= graph
def _isolated(name: str, fn):
    """One failing specialist shouldn't sink the whole answer."""
    async def run(state: GraphState) -> dict:
        try:
            return await fn(state)
        except Exception as exc:
            log.exception("%s agent failed", name)
            emit(name, "error", f"{type(exc).__name__}: {exc}"[:200])
            return {"findings": {name: f"(the {name} agent failed: {exc})"}}
    return run


def build_graph(checkpointer=None):
    g = StateGraph(GraphState)
    g.add_node("supervisor", supervisor)
    for name, fn in SPECIALISTS.items():
        g.add_node(name, _isolated(name, fn))
        g.add_edge(name, "compose")
    g.add_node("compose", compose)
    g.add_node("planner", planner)
    g.add_node("writer", writer)
    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", route, [*SPECIALISTS, "planner", "writer"])
    g.add_conditional_edges("compose", after_compose, ["planner", "writer"])
    g.add_edge("planner", END)
    g.add_edge("writer", END)
    return g.compile(checkpointer=checkpointer)

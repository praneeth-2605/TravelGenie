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

import json
import logging
import re
from datetime import date

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from backend.agents.plan import OptionDetails, TripPlan, enrich, money
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
        profile=json.dumps({k: v for k, v in profile.items() if v not in (None, "", [])}),
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
    agents = list(dict.fromkeys(decision.agents or []))
    if intent == "chat":
        agents = []
    elif intent == "plan":
        agents = list(dict.fromkeys(["research", "weather", "stays", "sights", "transport", "web", *agents]))
    elif intent == "revise" and not state.get("plan"):
        intent = "plan"
        agents = ["research", "weather", "stays", "sights", "transport", "web"]
    elif intent in ("question",) and not agents:
        agents = ["research"]
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
 "assumptions": ["anything you had to assume (dates, exchange rates, nights)"],
 "currency": "{currency}",
 "days": [{{"day": 1, "title": "theme", "area": "neighbourhood",
           "items": [{{"time": "Morning", "title": "what", "description": "1-2 practical sentences",
                       "place_id": "p12 or null", "cost": 0, "cite": [1]}}]}}],
 "options": [
   {{"tier": "budget", "title": "catchy name", "total": 0,
     "breakdown": {{"travel": 0, "stay": 0, "food": 0, "transport": 0, "activities": 0, "other": 0}},
     "getting_there": {{"mode": "train", "detail": "which service/class and route", "duration": "...", "cost": 0}},
     "stay": {{"place_id": "p3 or null", "name": "", "nightly": 0, "why": "why it suits"}},
     "alt_stay_ids": ["p4"], "highlights": ["how this option feels: dining, transport, extras"],
     "fits_budget": null, "note": null}},
   {{"tier": "luxury", ...}},
   {{"tier": "yours", ...}}
 ],
 "packing": ["..."], "weather_note": "...", "tips": ["..."]
}}

Rules:
- days: exactly {days} days. 3-4 items per day (Morning/Afternoon/Evening, optional Night).
  Use the SIGHT candidates (put their id in place_id) and group nearby sights on the same day.
  Pace: {pace}. Interests: {interests}. Dietary: {dietary}.
  Cite knowledge sources as numbers in "cite" when an item relies on them; never invent numbers.
- The day plan is shared; the three options differ in stay, food, transport and extras.
- budget option: the cheapest sensible trip. Stay MUST be a budget-tier candidate (hostel/guesthouse).
- luxury option: premium comfort (best stay, private transfers, fine dining, special experiences).
  Stay MUST be a luxury-tier candidate. Its total must be clearly the highest of the three.
- yours option: {yours_rule} Pick the BEST stay candidate (any tier) that fits what's left after
  food, transport and activities, and say why it is the best match in "why". Set fits_budget.
- getting_there: pick the travel mode that suits each option from the TRANSPORT comparison
  (budget → cheapest e.g. bus/sleeper train; luxury → fastest/most comfortable e.g. flight; yours →
  best value for the budget). "travel" in the breakdown and getting_there.cost = ROUND TRIP for all
  travellers. If origin is unknown, set getting_there null and travel 0, and say so in assumptions.
- Prefer candidates' listed prices; convert to {currency} with approximate rates (note them in
  assumptions). Nights = {nights}. Travellers = {travelers}. Breakdown must add up to total.
- If no candidate fits, set place_id null and name a realistic type (e.g. "Dorm bed in Anjuna").
- Use only facts from the candidates and sources for specific names; keep everything realistic.
{revise_block}
STAY candidates (id [tier] name — area — price — note):
{stays}

SIGHT candidates (id [kind] name — area — hours/price — note):
{sights}

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
            rows.append(f"- {m['mode']}: {m.get('duration') or '?'}, {m.get('price_min')}-{m.get('price_max')}, "
                        f"{m.get('route') or ''}")
    return "\n".join(rows)


def _fmt_stays(stays: list[dict]) -> str:
    rows = [f"{s['id']} [{s['tier']}] {s['name']} — {s.get('area') or ''} — {s.get('price') or 'price n/a'}"
            f" — {(s.get('description') or '')[:70]}" for s in stays[:18]]
    return "\n".join(rows) or "(none found: use realistic estimates and set place_id null)"


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
        lines.append(f"- {o['tier']}: {money(o['total'], cur)}, stay {o['stay']['name']}")
    for d in plan.get("days", []):
        lines.append(f"- Day {d['day']} {d['title']}: " + "; ".join(i["title"] for i in d["items"]))
    return "\n".join(lines)


def _budget_problem(plan: TripPlan, lo: float | None, hi: float | None, currency: str) -> str | None:
    """Describe how the 'yours' option misses the traveller's range, if it does."""
    if not hi:
        return None
    yours = next(o for o in plan.options if o.tier == "yours")
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
            emit("planner", "running", "Adjusting “Your budget” to fit your range")
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

    data = enrich(plan, {**trip, "currency": currency}, state.get("stays") or [], state.get("sights") or [],
                  state.get("sources") or [], state.get("map_center"), state.get("weather"),
                  state.get("transport"), state.get("web_results"))
    # A revision keeps the traveller's chosen option (its details are regenerated on demand).
    data["selected_tier"] = state.get("selected_tier") if revising else None
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
        parts.append(f"- **{o['label']}** ({o['title']}): {money(o['total'], cur)} · stay at {o['stay']['name']}")
    return "\n".join(parts)


# ======================================================================= option details
DETAILS_PROMPT = """You are TravelGenie's trip concierge. The traveller has CHOSEN the "{label}" option
below. Expand it into a detailed, practical plan as ONE JSON object:
{{
 "overview": "3-4 sentences: what this option feels like and why it fits",
 "days": [{{"day": 1, "summary": "one line", "meals": [{{"meal": "Breakfast", "place": "specific place or area",
            "try": "what to order", "cost": 0}}], "getting_around": "how to move between today's stops + cost",
            "spend": 0, "tip": "one practical tip"}}],
 "booking_checklist": [{{"item": "...", "when": "how far ahead", "where": "site/app/desk", "cost": 0}}],
 "money_tips": ["..."],
 "good_to_know": ["..."]
}}
Rules: one entry per day ({days} days) matching the day plan; 2-3 meals per day that suit the
option's comfort level and the traveller's diet ({dietary}); costs in {currency} for the WHOLE party
({travelers} people); "spend" = that day's total (meals + local transport + activities). The booking
checklist starts with getting there ({getting_there}) and the stay ({stay}). Be specific and realistic;
use only well-known or listed places for names, otherwise describe the kind of place and the area.

Chosen option:
{option}

Day plan:
{days_text}"""


async def generate_details(plan: dict, tier: str, profile: dict | None = None) -> dict:
    """Expand one option into a detailed plan (meals, getting around, spend, bookings)."""
    option = next(o for o in plan["options"] if o["tier"] == tier)
    cur = plan.get("currency", "")
    gt = option.get("getting_there") or {}
    days_text = "\n".join(
        f"Day {d['day']} ({d.get('area') or ''}) {d['title']}: " + "; ".join(f"{i['time']} {i['title']}" for i in d["items"])
        for d in plan["days"])
    compact = {k: option.get(k) for k in ("title", "total", "breakdown", "highlights")}
    compact["stay"] = {"name": option["stay"]["name"], "nightly": option["stay"].get("nightly"),
                       "area": (option["stay"].get("place") or {}).get("area")}
    prompt = DETAILS_PROMPT.format(
        label=option["label"], days=len(plan["days"]), currency=cur, travelers=plan.get("travelers", 1),
        dietary=(profile or {}).get("dietary") or "no restrictions",
        getting_there=f"{gt.get('mode')}: {gt.get('detail')}" if gt else "not specified",
        stay=option["stay"]["name"], option=json.dumps(compact, ensure_ascii=False), days_text=days_text)
    details = await ask_json(planner_llm(), [HumanMessage(prompt)], OptionDetails)
    return details.model_dump(by_alias=True)


def chosen_block(plan: dict | None, tier: str | None) -> str:
    """Context about the traveller's chosen option, for the writer."""
    if not plan or not tier:
        return ""
    o = next((x for x in plan.get("options", []) if x["tier"] == tier), None)
    if not o:
        return ""
    cur = plan.get("currency", "")
    gt = o.get("getting_there") or {}
    lines = [f'The traveller CHOSE the "{o["label"]}" option ({o["title"]}), total {money(o["total"], cur)}.',
             f"Stay: {o['stay']['name']} ({money(o['stay'].get('nightly'), cur)}/night). {o['stay'].get('why', '')}"]
    if gt:
        lines.append(f"Getting there: {gt.get('mode')}: {gt.get('detail')} ({gt.get('duration') or ''}), "
                     f"{money(gt.get('cost'), cur)} return.")
    lines.append("Breakdown: " + ", ".join(f"{k} {money(v, cur)}" for k, v in o["breakdown"].items()))
    det = o.get("details")
    if det:
        for d in det["days"]:
            meals = "; ".join(f"{m['meal']} at {m['place']}" for m in d.get("meals", []))
            lines.append(f"Day {d['day']}: {d['summary']} Meals: {meals}. Getting around: {d.get('getting_around') or ''}")
    return "\n".join(lines)


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

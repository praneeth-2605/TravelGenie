"""Specialist agents. Each one runs in parallel and writes into `findings`.

Every agent reports its progress through the LangGraph custom stream so the
UI can show what is happening live ("Research: 6 sources, 1 from the web").
"""

from __future__ import annotations

import asyncio
import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.config import get_stream_writer

from backend.agents.state import GraphState
from backend.agents.tools import mock_book_item, weather_forecast
from backend.llm import main_llm, text_of
from backend.places import geocode, get_places
from backend.rag.pipeline import retrieve


def emit(agent: str, status: str, detail: str = "", **extra) -> None:
    get_stream_writer()({"type": "agent", "agent": agent, "status": status, "detail": detail, **extra})


def _latest_request(state: GraphState) -> str:
    for m in reversed(state.get("messages", [])):
        if m.type == "human":
            return text_of(m.content)
    return ""


def _brief(state: GraphState) -> str:
    trip = {k: v for k, v in (state.get("trip") or {}).items() if v not in (None, [], "")}
    return json.dumps(trip, ensure_ascii=False)


# ------------------------------------------------------------------ research
async def research_agent(state: GraphState) -> dict:
    emit("research", "running", "Searching the knowledge base")
    trip = state.get("trip") or {}
    dest = trip.get("destination")
    request = _latest_request(state)

    jobs = [asyncio.to_thread(retrieve, request, 5, True, dest)]
    if dest and state.get("intent") == "plan":
        interests = ", ".join(trip.get("interests") or [])
        angle = f"top things to do, neighbourhoods and food in {dest} {interests}".strip()
        jobs.append(asyncio.to_thread(retrieve, angle, 5, True, dest, False))
    results = await asyncio.gather(*jobs)

    seen, sources = set(), []
    for r in results:
        for s in r.sources:
            key = (s.source, s.text[:80])
            if key not in seen and len(sources) < 6:
                seen.add(key)
                sources.append(s.to_dict())
    for n, s in enumerate(sources, start=1):
        s["n"] = n
    used_web = any(r.used_web for r in results)
    web_error = next((r.web_error for r in results if r.web_error), None)
    kinds = {s["source_type"] for s in sources}
    detail = (f"{len(sources)} sources" + (" · searched the web" if used_web else "") +
              (f" · {', '.join(sorted(kinds))}" if kinds else "") + (f" · {web_error}" if web_error else ""))
    emit("research", "error" if web_error and not sources else "done", detail, queries=results[0].queries)
    note = f"{len(sources)} sources retrieved."
    if web_error:
        note += f" Live web search was NOT available ({web_error}), so recent facts could not be verified."
    return {"sources": sources, "findings": {"research": note}}


# ------------------------------------------------------------------ weather
async def weather_agent(state: GraphState) -> dict:
    trip = state.get("trip") or {}
    dest = trip.get("destination")
    if not dest:
        emit("weather", "skipped", "No destination yet")
        return {}
    emit("weather", "running", f"Fetching the forecast for {dest}")
    # Geocode with the country so 'Goa' means Goa, India (not Goa in the Philippines).
    query = f"{dest}, {trip['country']}" if trip.get("country") else dest
    geo = await asyncio.to_thread(geocode, query)
    data = await asyncio.to_thread(weather_forecast, dest, geo["lat"] if geo else None, geo["lon"] if geo else None)
    if "error" in data:
        emit("weather", "error", data["error"])
        return {"findings": {"weather": data["error"]}, "weather": None}
    days = data["daily"]
    start = trip.get("start_date")
    if start and days and start > days[-1]["date"]:
        # The trip is beyond the 5-day forecast window: today's weather would mislead.
        emit("weather", "done", f"Trip starts {start}, beyond the 5-day forecast · using seasonal norms")
        return {"findings": {"weather": f"The trip starts {start}, beyond the live forecast window. "
                                        f"Use typical seasonal weather for {dest} at that time of year."},
                "weather": None}
    lines = [f"{d['date']}: {d['min_c']}–{d['max_c']}°C, {d['condition']}, rain {d['rain_mm']}mm" for d in days]
    note = ("Live 5-day forecast for " + data["location"] + " (fetched " + data["fetched_at"] + "):\n"
            + "\n".join(lines) +
            "\nIf the trip is beyond this window, rely on seasonal knowledge instead.")
    emit("weather", "done", f"{data['location']}: {days[0]['min_c']}–{days[0]['max_c']}°C, {days[0]['condition']}")
    return {"findings": {"weather": note}, "weather": data}


# ------------------------------------------------------------------ stays
def _place_query(trip: dict) -> str | None:
    dest = trip.get("destination")
    if not dest:
        return None
    return dest


async def stays_agent(state: GraphState) -> dict:
    trip = state.get("trip") or {}
    dest = _place_query(trip)
    if not dest:
        emit("stays", "skipped", "No destination yet")
        return {}
    emit("stays", "running", f"Finding hostels and hotels in {dest}")
    places = await asyncio.to_thread(get_places, dest)
    stays = places["stays"]
    counts = {t: sum(s["tier"] == t for s in stays) for t in ("budget", "mid", "luxury")}
    if not stays:
        emit("stays", "error", places.get("error") or "No listings found; the planner will use estimates")
    else:
        emit("stays", "done", f"{counts['budget']} budget · {counts['mid']} mid-range · "
                              f"{counts['luxury']} luxury stays (Wikivoyage)")
    return {"stays": stays, "map_center": places.get("center")}


# ------------------------------------------------------------------ sights
async def sights_agent(state: GraphState) -> dict:
    trip = state.get("trip") or {}
    dest = _place_query(trip)
    if not dest:
        emit("sights", "skipped", "No destination yet")
        return {}
    emit("sights", "running", f"Finding local sights in {dest}")
    places = await asyncio.to_thread(get_places, dest)
    sights = places["sights"]
    interests = [i.lower() for i in (trip.get("interests") or [])]
    if interests:
        # Nudge sights matching the traveller's interests to the front.
        def boost(s):
            text = f"{s['name']} {s.get('description', '')}".lower()
            return -sum(any(w in text for w in i.split()) for i in interests)
        sights = sorted(sights, key=boost)
    mapped = sum(1 for s in sights if s.get("lat") is not None)
    if not sights:
        emit("sights", "error", places.get("error") or "No sights found; the planner will use research only")
    else:
        emit("sights", "done", f"{len(sights)} sights and activities · {mapped} on the map")
    return {"sights": sights}  # the stays agent sets map_center (one writer per key per step)


# ------------------------------------------------------------------ booking
BOOKING_PROMPT = """You are the Booking agent. You can only make SIMULATED bookings
with the mock_book_item tool; nothing is really reserved or charged.
Book what the traveller asked for (or 1-2 representative items for a new plan:
one hotel and one key activity). Use plausible names and prices for the
destination and the trip dates (or a sensible upcoming date if none).
After the tool calls, reply with a one-line summary."""


async def booking_agent(state: GraphState) -> dict:
    emit("booking", "running", "Making simulated bookings")
    llm = main_llm().bind_tools([mock_book_item])
    messages = [SystemMessage(BOOKING_PROMPT),
                HumanMessage(f"Trip brief: {_brief(state)}\nRequest: {_latest_request(state)}")]
    confirmations: list[str] = []
    for _ in range(3):
        reply = await llm.ainvoke(messages)
        messages.append(reply)
        if not reply.tool_calls:
            break
        for call in reply.tool_calls:
            result = mock_book_item.invoke(call["args"])
            confirmations.append(result)
            messages.append(ToolMessage(result, tool_call_id=call["id"]))
    emit("booking", "done", f"{len(confirmations)} simulated booking(s)")
    return {"bookings": confirmations,
            "findings": {"booking": "\n".join(confirmations) or "No bookings made."}}


SPECIALISTS = {
    "research": research_agent,
    "weather": weather_agent,
    "stays": stays_agent,
    "sights": sights_agent,
    "booking": booking_agent,
}

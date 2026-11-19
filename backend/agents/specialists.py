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

    jobs = [asyncio.to_thread(retrieve, request, 6, True, dest)]
    if dest and state.get("intent") in ("plan", "revise"):
        interests = ", ".join(trip.get("interests") or [])
        angle = f"top things to do, neighbourhoods and food in {dest} {interests}".strip()
        jobs.append(asyncio.to_thread(retrieve, angle, 5, True, dest, False))
    results = await asyncio.gather(*jobs)

    seen, sources = set(), []
    for r in results:
        for s in r.sources:
            key = (s.source, s.text[:80])
            if key not in seen and len(sources) < 8:
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
    dest = (state.get("trip") or {}).get("destination")
    if not dest:
        emit("weather", "skipped", "No destination yet")
        return {}
    emit("weather", "running", f"Fetching the forecast for {dest}")
    data = await asyncio.to_thread(weather_forecast, dest)
    if "error" in data:
        emit("weather", "error", data["error"])
        return {"findings": {"weather": data["error"]}, "weather": None}
    days = data["daily"]
    lines = [f"{d['date']}: {d['min_c']}–{d['max_c']}°C, {d['condition']}, rain {d['rain_mm']}mm" for d in days]
    note = ("Live 5-day forecast for " + data["location"] + " (fetched " + data["fetched_at"] + "):\n"
            + "\n".join(lines) +
            "\nIf the trip is beyond this window, rely on seasonal knowledge instead.")
    emit("weather", "done", f"{data['location']}: {days[0]['min_c']}–{days[0]['max_c']}°C, {days[0]['condition']}")
    return {"findings": {"weather": note}, "weather": data}


# ------------------------------------------------------------------ budget
BUDGET_PROMPT = """You are the Budget agent of a travel-planning team.
Estimate a realistic cost breakdown for this trip. Use the knowledge excerpts
when they contain prices or budget tips; otherwise use typical costs and say
they are estimates.

Return compact markdown:
- a table with rows: Accommodation, Food, Local transport, Activities, Buffer (10-15%), Total
  (columns: Item | Per day | Trip total), in the traveller's currency
- 2-4 concrete money-saving tips for this destination
- one line verdict: does the stated budget fit? If not, what to change.
Do not write an itinerary."""


async def budget_agent(state: GraphState) -> dict:
    emit("budget", "running", "Estimating costs")
    dest = (state.get("trip") or {}).get("destination")
    ctx = ""
    if dest:
        r = await asyncio.to_thread(retrieve, f"budget costs prices money tips {dest}", 3, False, dest, False)
        ctx = r.context_block()
    msg = await main_llm().ainvoke([
        SystemMessage(BUDGET_PROMPT),
        HumanMessage(f"Trip brief: {_brief(state)}\nRequest: {_latest_request(state)}\n\nKnowledge:\n{ctx}"),
    ])
    emit("budget", "done", "Cost breakdown ready")
    return {"findings": {"budget": text_of(msg.content)}}


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
    "budget": budget_agent,
    "booking": booking_agent,
}

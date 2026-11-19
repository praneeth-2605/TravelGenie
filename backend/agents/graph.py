"""The multi-agent graph.

                     ┌──► research ──┐
    user ─► supervisor ─► weather ───┼─► writer ─► answer
                     ├──► budget ────┤
                     └──► booking ───┘

The supervisor reads the conversation, updates the trip brief and picks which
specialists this turn needs. They run in parallel (LangGraph `Send`), then the
writer merges their findings into one cited answer, streamed token by token.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from backend.agents.specialists import SPECIALISTS, emit
from backend.agents.state import GraphState, RoutingDecision
from backend.llm import fast_llm, text_of, writer_llm

log = logging.getLogger(__name__)

SUPERVISOR_PROMPT = """You are the supervisor of TravelGenie, a team of travel agents.
Today is {today}. Read the conversation and decide how to handle the LAST user message.

Current trip brief (from earlier turns): {trip}

Specialists you can call (pick only what this turn needs):
- research: knowledge base + web search (attractions, food, areas, visas, tips). Needed for almost every travel request.
- weather: live 5-day forecast for the destination.
- budget: cost breakdown and money-saving tips.
- booking: SIMULATED bookings of hotels/activities/transport.

Guidelines:
- New itinerary ("plan"): research + weather + budget. Add booking only if asked.
  If the message describes a trip (a destination plus a length, dates or budget) and no plan
  exists yet, the intent is "plan" even when it also asks a question; the writer answers the
  question inside the plan.
- Revision ("revise"): call only what the change touches (e.g. budget change -> budget, research).
- Specific question: usually research only.
- Greeting / small talk ("chat"): no specialists.
- Merge new details into the trip brief; keep earlier details unless the user changed them.
- If the user gives a rough time ("mid-December", "next month"), set start_date to a concrete
  best guess (e.g. the 15th of that month, in the next occurrence after today)."""

WRITER_PROMPT = """You are TravelGenie's lead planner. Write the final answer for the traveller
using the specialist findings and the numbered knowledge sources below.

Rules:
- Ground facts in the sources and cite them inline in exactly this form: [1] or [2][4]
  (square brackets and the source number only, no 【】 markers), right after the bullet
  or sentence that uses them. Every place, dish, tip or price that appears in a source must be
  cited, including inside the day-by-day plan, not only in the budget. Never invent citations;
  don't cite general knowledge that isn't in the sources.
- Intent "plan": if the traveller also asked a question, answer it first in 1-3 lines. Then a
  day-by-day itinerary with headings exactly like "## Day 1 — <theme>",
  each with **Morning**, **Afternoon**, **Evening** labels on their own line (blank line
  before each label), followed by bullets. Then sections
  "## Budget", "## Packing List" and "## Weather Advisory".
- Intent "revise": revise the existing plan from the conversation instead of starting over;
  output the full updated plan in the same format and briefly note what changed first.
- Intent "question": answer directly and concisely.
- Intent "book": confirm the simulated bookings and how they fit the plan.
- Intent "chat": reply briefly and invite the user to describe a trip.
- If no knowledge source covers a factual point that changes over time (visas, entry rules,
  prices, opening hours, safety), you may give general guidance, but start that part with a clear
  "⚠️ Couldn't verify this against current sources" note and tell the traveller to confirm it
  with the official source. Never present unverified rules or fees as definite.
- Any booking is SIMULATED; say so clearly.
- If key details (dates, length, budget) are missing for a plan, make sensible assumptions,
  state them in one line at the top, and still produce the plan.
- Use clean markdown. No preamble like "Sure!".

Intent: {intent}
Trip brief: {trip}

Specialist findings:
{findings}

Knowledge sources:
{sources}"""


async def supervisor(state: GraphState) -> dict:
    emit("supervisor", "running", "Reading your request")
    prompt = SUPERVISOR_PROMPT.format(today=date.today().isoformat(),
                                      trip=json.dumps(state.get("trip") or {}))
    decision = await _route([SystemMessage(prompt), *state["messages"][-10:]], state)
    # Never lose trip details the router left out this turn.
    trip = {**(state.get("trip") or {}),
            **(decision.trip.model_dump(exclude_none=True) if decision.trip else {})}
    trip["interests"] = trip.get("interests") or []
    agents = list(dict.fromkeys(decision.agents or []))
    if decision.intent == "chat":
        agents = []
    elif not agents:
        agents = ["research"]
    reason = decision.reason or f"intent: {decision.intent}"
    emit("supervisor", "done", reason, intent=decision.intent, agents=agents,
         trip={k: v for k, v in trip.items() if v not in (None, [], "")})
    # Reset per-turn findings and sources.
    return {"intent": decision.intent, "agents": agents, "trip": trip, "findings": {}, "sources": []}


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
    return RoutingDecision(intent="chat" if small_talk else "question",
                           agents=[] if small_talk else ["research"], reason="default routing")


def route(state: GraphState):
    agents = state.get("agents") or []
    return [Send(a, state) for a in agents] if agents else "writer"


def _format_sources(sources: list[dict]) -> str:
    if not sources:
        return "(none)"
    out = []
    for s in sources:
        label = s["title"] + (f" — {s['section']}" if s.get("section") else "")
        out.append(f"[{s['n']}] {label} ({s['source_type']}: {s['source']})\n{s['text']}")
    return "\n\n".join(out)


async def writer(state: GraphState) -> dict:
    emit("writer", "running", "Writing your answer")
    findings = dict(state.get("findings") or {})
    system = WRITER_PROMPT.format(
        intent=state.get("intent", "question"),
        trip=json.dumps({k: v for k, v in (state.get("trip") or {}).items() if v not in (None, [], "")}),
        findings="\n\n".join(f"### {k}\n{v}" for k, v in findings.items()) or "(none)",
        sources=_format_sources(state.get("sources") or []),
    )
    reply = await writer_llm().ainvoke([SystemMessage(system), *state["messages"][-8:]])
    emit("writer", "done", "")
    return {"messages": [AIMessage(normalize_citations(text_of(reply.content)))]}


_NATIVE_CITE = re.compile(r"【\s*([^】†]*?)\s*(?:†[^】]*)?】")


def normalize_citations(text: str) -> str:
    """gpt-oss models cite in their native style, 【3†L1-L4】. Convert to [3];
    drop markers that don't point at a numbered source (e.g. 【Budget†L2】)."""
    return _NATIVE_CITE.sub(lambda m: f"[{m.group(1)}]" if m.group(1).isdigit() else "", text)


def _isolated(name: str, fn):
    """One failing specialist shouldn't sink the whole answer."""
    async def run(state: GraphState) -> dict:
        try:
            return await fn(state)
        except Exception as exc:
            emit(name, "error", f"{type(exc).__name__}: {exc}"[:200])
            return {"findings": {name: f"(the {name} agent failed: {exc})"}}
    return run


def build_graph(checkpointer=None):
    g = StateGraph(GraphState)
    g.add_node("supervisor", supervisor)
    for name, fn in SPECIALISTS.items():
        g.add_node(name, _isolated(name, fn))
        g.add_edge(name, "writer")
    g.add_node("writer", writer)
    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", route, [*SPECIALISTS, "writer"])
    g.add_edge("writer", END)
    return g.compile(checkpointer=checkpointer)

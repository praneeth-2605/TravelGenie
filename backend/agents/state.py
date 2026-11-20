"""Shared graph state and the structured output of the supervisor."""

from __future__ import annotations

import operator
from typing import Annotated, Literal

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

Specialist = Literal["research", "weather", "stays", "sights", "transport", "web", "booking"]


class TripBrief(BaseModel):
    destination: str | None = Field(None, description="City or region, e.g. 'Goa' or 'Kyoto'")
    country: str | None = None
    start_date: str | None = Field(None, description="YYYY-MM-DD if known")
    days: int | None = Field(None, description="Trip length in days")
    travelers: int | None = None
    budget_min: float | None = Field(None, description="Lower end of the traveller's total budget")
    budget_max: float | None = Field(None, description="Upper end of the traveller's total budget "
                                                       "(a single budget figure goes here)")
    currency: str | None = Field(None, description="ISO code such as USD, INR, EUR")
    style: str | None = Field(None, description="backpacker, balanced, luxury, family, ...")
    # Nullable on purpose: models often send null here, and Groq rejects the
    # whole tool call if the schema demands an array.
    interests: list[str] | None = None
    origin: str | None = Field(None, description="City the traveller starts from (e.g. 'Hyderabad')")


class RoutingDecision(BaseModel):
    intent: Literal["plan", "revise", "question", "book", "chat"] = Field(
        description="plan = new trip plan; revise = change the existing plan; "
                    "question = a specific travel question; book = make (simulated) bookings; "
                    "chat = greeting / small talk / off-topic"
    )
    # Required (models skip optional objects), but every field inside is nullable.
    trip: TripBrief = Field(description="The trip brief: always fill destination, days, budget etc. "
                                        "from the whole conversation, merged with what was already known")
    agents: list[Specialist] | None = Field(None, description="Specialists to consult for this turn")
    reason: str | None = Field(None, description="One short sentence explaining the routing")


def merge_dict(old: dict | None, new: dict | None) -> dict:
    """Reducer: merge specialist findings; an explicit {} resets for a new turn."""
    if new == {}:
        return {}
    return {**(old or {}), **(new or {})}


def merge_list(old: list | None, new: list | None) -> list:
    if new == []:
        return []
    return [*(old or []), *(new or [])]


class GraphState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    profile: dict                     # the user's saved preferences
    trip: dict
    intent: str
    agents: list[str]
    findings: Annotated[dict, merge_dict]
    sources: Annotated[list[dict], merge_list]
    bookings: Annotated[list[str], operator.add]
    weather: dict | None
    stays: list[dict]                 # candidate stays (Wikivoyage), by tier
    sights: list[dict]                # candidate sights
    map_center: dict | None
    transport: dict | None            # every way to get there (flight/train/bus/car/ferry)
    web_results: list[dict]           # web search (or Wikivoyage guide) results
    plan: dict | None                 # the latest structured TripPlan (enriched)
    selected_tier: str | None         # the option the traveller chose: budget | luxury | yours

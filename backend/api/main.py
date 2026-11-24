"""TravelGenie API.

Account:   /api/auth/* (signup, login, google, logout, me), /api/account/*, /api/settings
Trips:     GET/PATCH/DELETE /api/trips[/{id}], GET /api/trips/{id}/export?format=pdf|ics|md
Chat:      POST /api/chat – runs the agent team for one trip, streamed as Server-Sent Events
Knowledge: GET/POST /api/documents, DELETE /api/documents/{doc_id}, POST /api/search
Health:    GET /api/health
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend import auth, db, export, history
from backend.agents.graph import build_graph, generate_details
from backend.agents.plan import build_markers, money, schedule_for
from backend.api.routes_account import router as account_router
from backend.config import ROOT, settings
from backend.llm import text_of
from backend.rag import models
from backend.rag.seed import seed_guides
from backend.skills import catalog as skills_catalog
from backend.rag.store import get_store

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("travelgenie")

DIST = ROOT / "frontend" / "dist"


# ------------------------------------------------------------------ startup
# Serverless platforms (Vercel) may not run startup hooks and may handle each
# request on a different event loop, so setup is lazy, thread-safe and done once
# per instance, and each request opens its own chat-history connection.
_ready = False
_ready_lock = threading.Lock()


def _setup() -> None:
    global _ready
    with _ready_lock:
        if _ready:
            return
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        db.init()
        models.warm_up()
        added = seed_guides()
        if settings.database_url:
            from langgraph.checkpoint.postgres import PostgresSaver
            with PostgresSaver.from_conn_string(settings.database_url) as saver:
                saver.setup()  # creates the chat-history tables if needed
        removed = history.purge_orphans()
        if removed:
            log.info("removed %d orphaned conversation(s) from deleted trips/accounts", removed)
        log.info("ready: %s storage, %s search · knowledge base %d chunks (%d new)",
                 "PostgreSQL" if settings.database_url else f"local ({settings.storage_dir})",
                 "Jina API" if models.using_jina() else "local models", get_store().count(), added)
        _ready = True


async def ensure_ready() -> None:
    if not _ready:
        await asyncio.to_thread(_setup)


@asynccontextmanager
async def graph_session():
    """The agent graph, with chat history stored in Postgres (production) or SQLite (local)."""
    async with history.checkpointer() as saver:
        yield build_graph(saver)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_ready()  # warm up when the platform runs startup hooks (local, containers)
    yield


app = FastAPI(title="TravelGenie", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def block_cross_site_writes(request: Request, call_next):
    """CSRF guard (on top of SameSite=Lax cookies): reject state-changing requests
    that a browser sends from any other site. Also makes sure setup has run."""
    if request.url.path.startswith("/api/"):
        await ensure_ready()
    if request.method in _UNSAFE and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if origin:
            # Compare hosts, not schemes: behind a proxy (Vercel) the app may see http
            # while the browser's Origin says https.
            own_hosts = {h for h in (request.headers.get("host"), request.headers.get("x-forwarded-host"),
                                     request.url.netloc) if h}
            allowed = {*settings.cors_origins, *settings.public_origins}
            if urlparse(origin).netloc not in own_hosts and origin not in allowed:
                return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
    return await call_next(request)
app.include_router(account_router)


# ------------------------------------------------------------------ fair use
IST = timezone(timedelta(hours=5, minutes=30))


def _today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")  # limits reset at midnight India time


def use_ai_request(user) -> None:
    """Count one AI request for this user today; refuse once the daily limit is reached."""
    limit = settings.daily_ai_limit
    if limit <= 0:
        return
    if db.usage_get(user["id"], _today(), "ai") >= limit:
        raise HTTPException(429, f"You've used all {limit} AI requests for today. "
                                 "They reset at midnight (India time). Your saved trips still work.")
    db.usage_add(user["id"], _today(), "ai")


@app.get("/api/usage")
def usage(user=Depends(auth.current_user)):
    used = db.usage_get(user["id"], _today(), "ai")
    return {"used": used, "limit": settings.daily_ai_limit,
            "remaining": max(settings.daily_ai_limit - used, 0) if settings.daily_ai_limit > 0 else None}


def _owned_trip(user, trip_id: str) -> dict:
    trip = db.get_trip(user["id"], trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found.")
    return trip


# ------------------------------------------------------------------ chat
class ChatRequest(BaseModel):
    trip_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=4000)


def _sse(event: str, data) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    if "429" in text or "rate limit" in text.lower():
        return ("Groq's free-tier rate limit was reached (about 8,000 tokens per minute). "
                "Wait a minute and try again.")
    if "401" in text or "invalid api key" in text.lower():
        return "Groq rejected the API key. Check GROQ_API_KEY in .env and restart the API."
    return f"Something went wrong: {type(exc).__name__}: {text}"[:500]


@app.post("/api/chat")
async def chat(req: ChatRequest, user=Depends(auth.current_user)):
    if not settings.groq_api_key:
        raise HTTPException(503, "GROQ_API_KEY is not set on the server. Add it to .env and restart.")
    owner = db.trip_owner(req.trip_id)
    if owner is not None and owner != user["id"]:
        raise HTTPException(404, "Trip not found.")
    await asyncio.to_thread(use_ai_request, user)
    if owner is None:
        db.create_trip(user["id"], req.trip_id, _title_from(req.message))

    profile = {**db.get_settings(user["id"]), "name": user["name"], "user_id": user["id"]}
    config = {"configurable": {"thread_id": req.trip_id}}

    async def events():
        try:
            async with graph_session() as graph:
                async for mode, payload in graph.astream(
                    {"messages": [HumanMessage(req.message)], "profile": profile}, config,
                    stream_mode=["custom", "messages"],
                ):
                    if mode == "custom":
                        yield _sse("agent", payload)
                    elif mode == "messages":
                        chunk, meta = payload
                        if meta.get("langgraph_node") == "writer" and chunk.type == "AIMessageChunk":
                            text = text_of(chunk.content)
                            if text:
                                yield _sse("token", {"text": text})
                state = (await graph.aget_state(config)).values
                plan = state.get("plan")
                trip = state.get("trip") or {}
                updates = {"destination": trip.get("destination"), "start_date": trip.get("start_date"),
                           "days": trip.get("days")}
                if plan and state.get("intent") in ("plan", "revise"):
                    updates["plan"] = plan
                    updates["selected_tier"] = plan.get("selected_tier") or ""
                    if trip.get("destination"):
                        updates["title"] = f"{trip['destination']} · {trip.get('days') or len(plan['days'])} days"
                await asyncio.to_thread(db.update_trip, req.trip_id, **{k: v for k, v in updates.items() if v is not None})
                yield _sse("final", {
                    "answer": text_of(state["messages"][-1].content),
                    "intent": state.get("intent"),
                    "plan": plan if state.get("intent") in ("plan", "revise") else None,
                    "sources": state.get("sources") or [],
                    "trip": trip,
                    "bookings": state.get("bookings") or [],
                    "weather": state.get("weather"),
                    "transport": state.get("transport"),
                    "selected_tier": state.get("selected_tier"),
                })
        except Exception as exc:
            log.exception("chat failed")
            yield _sse("error", {"message": _friendly_error(exc)})

    return EventSourceResponse(events())


def _title_from(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return (t[:46] + "…") if len(t) > 48 else (t or "New trip")


# ------------------------------------------------------------------ trips
@app.get("/api/trips")
def list_trips(user=Depends(auth.current_user)):
    return db.list_trips(user["id"])


@app.get("/api/trips/{trip_id}")
async def get_trip(trip_id: str, user=Depends(auth.current_user)):
    trip = _owned_trip(user, trip_id)
    async with graph_session() as graph:
        snap = await graph.aget_state({"configurable": {"thread_id": trip_id}})
    values = snap.values or {}
    trip["messages"] = [{"role": "user" if m.type == "human" else "assistant", "content": text_of(m.content)}
                        for m in values.get("messages", []) if m.type in ("human", "ai")]
    trip["brief"] = values.get("trip") or {}
    trip["bookings"] = values.get("bookings") or []
    trip["sources"] = values.get("sources") or []
    return trip


class HotelBody(BaseModel):
    tier: Literal["budget", "luxury", "yours"]
    place_id: str | None = Field(None, max_length=20)   # null = "not chosen yet"


@app.post("/api/trips/{trip_id}/hotel")
async def choose_hotel(trip_id: str, body: HotelBody, user=Depends(auth.current_user)):
    """Pick (or clear) the stay for one option; its timestamped schedule is rebuilt around the
    hotel's real location. Pure code + routing, no AI request used."""
    trip = _owned_trip(user, trip_id)
    plan = trip.get("plan")
    if not plan or "schedules" not in plan:
        raise HTTPException(409, "This trip has no plan yet.")
    option = next((o for o in plan["options"] if o["tier"] == body.tier), None)
    if option is None:
        raise HTTPException(404, "Option not found.")
    if body.place_id and body.place_id not in option["stay"]["candidate_ids"]:
        raise HTTPException(404, "That stay isn't one of this option's choices.")
    plan.setdefault("hotels", {})[body.tier] = body.place_id
    plan["schedules"][body.tier] = await asyncio.to_thread(schedule_for, plan, body.tier)
    plan["markers"] = build_markers(plan)
    await asyncio.to_thread(db.update_trip, trip_id, plan=plan)
    async with graph_session() as graph:   # keep the agents' copy of the plan in sync
        await graph.aupdate_state({"configurable": {"thread_id": trip_id}}, {"plan": plan}, as_node="planner")
    return {"plan": plan}


class SelectBody(BaseModel):
    tier: Literal["budget", "luxury", "yours"]


@app.post("/api/trips/{trip_id}/select")
async def select_option(trip_id: str, body: SelectBody, user=Depends(auth.current_user)):
    """Choose one of the three options: builds its detailed plan and focuses the chat on it."""
    trip = _owned_trip(user, trip_id)
    plan = trip.get("plan")
    if not plan:
        raise HTTPException(409, "This trip has no plan yet.")
    option = next((o for o in plan["options"] if o["tier"] == body.tier), None)
    if option is None:
        raise HTTPException(404, "Option not found.")
    if not option.get("details"):
        if not settings.groq_api_key:
            raise HTTPException(503, "GROQ_API_KEY is not set on the server.")
        await asyncio.to_thread(use_ai_request, user)
        try:
            option["details"] = await generate_details(plan, body.tier, db.get_settings(user["id"]))
        except Exception as exc:
            log.exception("details failed")
            raise HTTPException(502, _friendly_error(exc))
    plan["selected_tier"] = body.tier
    await asyncio.to_thread(db.update_trip, trip_id, plan=plan, selected_tier=body.tier)

    cur = plan.get("currency")
    reply = (f"Great choice: **{option['label']} · {option['title']}** "
             f"({money(option['total'], cur)} in total). {option['details']['overview']}\n\n"
             "Ask me anything about it: what to book first, cheaper swaps, food near your stay, "
             "or how to get between places.")
    config = {"configurable": {"thread_id": trip_id}}
    async with graph_session() as graph:
        await graph.aupdate_state(config, {
            "plan": plan, "selected_tier": body.tier,
            "messages": [HumanMessage(f"I choose the {option['label']} option ({option['title']})."), AIMessage(reply)],
        }, as_node="planner")
    return {"plan": plan, "message": reply}


# ------------------------------------------------------------------ public sharing
@app.post("/api/trips/{trip_id}/share")
def share_trip(trip_id: str, user=Depends(auth.current_user)):
    """Create (or return) a read-only public link for this trip's plan."""
    trip = _owned_trip(user, trip_id)
    if not trip.get("plan"):
        raise HTTPException(409, "Plan the trip before sharing it.")
    token = trip.get("share_token") or secrets.token_urlsafe(12)
    db.set_share_token(user["id"], trip_id, token)
    return {"token": token}


@app.delete("/api/trips/{trip_id}/share")
def unshare_trip(trip_id: str, user=Depends(auth.current_user)):
    _owned_trip(user, trip_id)
    db.set_share_token(user["id"], trip_id, None)
    return {"ok": True}


@app.get("/api/public/trips/{token}")
def public_trip(token: str):
    """A shared plan: no login needed. Never includes the chat, the owner's
    identity or text from their private uploads."""
    trip = db.trip_by_share_token(token) if 8 <= len(token) <= 64 else None
    if not trip or not trip.get("plan"):
        raise HTTPException(404, "This shared trip doesn't exist or is no longer shared.")
    plan = dict(trip["plan"])
    plan["sources"] = [s for s in plan.get("sources") or [] if s.get("source_type") != "upload"]
    return {"title": trip["title"], "destination": trip["destination"], "days": trip["days"],
            "start_date": trip["start_date"], "plan": plan}


class TripPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=80)
    favorite: bool | None = None


@app.patch("/api/trips/{trip_id}")
def patch_trip(trip_id: str, body: TripPatch, user=Depends(auth.current_user)):
    _owned_trip(user, trip_id)
    db.update_trip(trip_id, **body.model_dump(exclude_none=True))
    return db.get_trip(user["id"], trip_id)


@app.delete("/api/trips/{trip_id}")
async def delete_trip(trip_id: str, user=Depends(auth.current_user)):
    if not await asyncio.to_thread(db.delete_trip, user["id"], trip_id):
        raise HTTPException(404, "Trip not found.")
    await history.delete_threads([trip_id])  # its chat history too
    return {"deleted": trip_id}


@app.get("/api/trips/{trip_id}/export")
def export_trip(trip_id: str, format: Literal["pdf", "ics", "md"],
                option: Literal["budget", "luxury", "yours"] | None = None,
                user=Depends(auth.current_user)):
    trip = _owned_trip(user, trip_id)
    plan = trip.get("plan")
    if not plan:
        raise HTTPException(409, "This trip has no plan yet.")
    slug = re.sub(r"[^a-z0-9]+", "-", (plan.get("trip", {}).get("destination") or "trip").lower()).strip("-")
    if format == "pdf":
        body, mime, ext = export.pdf(plan, option), "application/pdf", "pdf"
    elif format == "ics":
        body, mime, ext = export.ics(plan, trip_id, option).encode(), "text/calendar; charset=utf-8", "ics"
    else:
        body, mime, ext = export.markdown(plan).encode(), "text/markdown; charset=utf-8", "md"
    name = f"travelgenie-{slug}{'-' + option if option else ''}.{ext}"
    return Response(body, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/health")
async def health():
    return {"ok": True, "missing_keys": settings.missing_keys(), "chunks": get_store().count(),
            "skills": [s["name"] for s in skills_catalog()],
            "model": settings.groq_model, "google_login": bool(settings.google_client_id)}


# ------------------------------------------------------------------ frontend (production build)
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        file = (DIST / path).resolve()
        if path and file.is_file() and file.is_relative_to(DIST.resolve()):
            return FileResponse(file)
        return FileResponse(DIST / "index.html")

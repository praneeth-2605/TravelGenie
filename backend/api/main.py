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
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend import auth, db, export
from backend.agents.graph import build_graph, generate_details
from backend.agents.plan import money
from backend.api.routes_account import router as account_router
from backend.config import ROOT, settings
from backend.llm import text_of
from backend.rag import models
from backend.rag.ingest import chunk_file
from backend.rag.pipeline import retrieve
from backend.rag.seed import seed_guides
from backend.rag.store import get_store

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("travelgenie")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
DIST = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    (ROOT / "storage").mkdir(exist_ok=True)
    db.init()
    await asyncio.to_thread(models.warm_up)
    added = await asyncio.to_thread(seed_guides)
    log.info("knowledge base ready: %d chunks (%d new)", get_store().count(), added)
    if settings.database_url:
        # Chat history in Postgres (Neon). A pool with health checks, because
        # serverless Postgres closes idle connections when it scales to zero.
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(settings.database_url, min_size=1, max_size=6, open=False,
                                   kwargs={"autocommit": True, "prepare_threshold": None, "row_factory": dict_row},
                                   check=AsyncConnectionPool.check_connection)
        await pool.open()
        try:
            saver = AsyncPostgresSaver(pool)
            await saver.setup()
            app.state.graph = build_graph(saver)
            log.info("storage: PostgreSQL (users, trips, chats, knowledge base)")
            yield
        finally:
            await pool.close()
    else:
        async with AsyncSqliteSaver.from_conn_string(str(ROOT / "storage" / "threads.sqlite")) as saver:
            app.state.graph = build_graph(saver)
            log.info("storage: local files in storage/")
            yield


app = FastAPI(title="TravelGenie", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def block_cross_site_writes(request: Request, call_next):
    """CSRF guard: the session cookie is SameSite=None in production (so login works
    inside Hugging Face's embedded page), so reject state-changing requests that a
    browser sends from any other site."""
    if request.method in _UNSAFE and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if origin:
            own = f"{request.url.scheme}://{request.url.netloc}"
            forwarded = request.headers.get("x-forwarded-host")
            allowed = {own, *settings.cors_origins, *settings.public_origins}
            if forwarded:
                allowed.add(f"https://{forwarded}")
            if origin not in allowed:
                return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
    return await call_next(request)
app.include_router(account_router)


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
    if owner is None:
        db.create_trip(user["id"], req.trip_id, _title_from(req.message))
    elif owner != user["id"]:
        raise HTTPException(404, "Trip not found.")

    profile = {**db.get_settings(user["id"]), "name": user["name"]}
    graph = app.state.graph
    config = {"configurable": {"thread_id": req.trip_id}}

    async def events():
        try:
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
    snap = await app.state.graph.aget_state({"configurable": {"thread_id": trip_id}})
    values = snap.values or {}
    trip["messages"] = [{"role": "user" if m.type == "human" else "assistant", "content": text_of(m.content)}
                        for m in values.get("messages", []) if m.type in ("human", "ai")]
    trip["brief"] = values.get("trip") or {}
    trip["bookings"] = values.get("bookings") or []
    trip["sources"] = values.get("sources") or []
    return trip


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
    await app.state.graph.aupdate_state(config, {
        "plan": plan, "selected_tier": body.tier,
        "messages": [HumanMessage(f"I choose the {option['label']} option ({option['title']})."), AIMessage(reply)],
    }, as_node="planner")
    return {"plan": plan, "message": reply}


class TripPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=80)
    favorite: bool | None = None


@app.patch("/api/trips/{trip_id}")
def patch_trip(trip_id: str, body: TripPatch, user=Depends(auth.current_user)):
    _owned_trip(user, trip_id)
    db.update_trip(trip_id, **body.model_dump(exclude_none=True))
    return db.get_trip(user["id"], trip_id)


@app.delete("/api/trips/{trip_id}")
def delete_trip(trip_id: str, user=Depends(auth.current_user)):
    if not db.delete_trip(user["id"], trip_id):
        raise HTTPException(404, "Trip not found.")
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
        body, mime, ext = export.ics(plan, trip_id).encode(), "text/calendar; charset=utf-8", "ics"
    else:
        body, mime, ext = export.markdown(plan).encode(), "text/markdown; charset=utf-8", "md"
    name = f"travelgenie-{slug}{'-' + option if option else ''}.{ext}"
    return Response(body, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ------------------------------------------------------------------ knowledge
@app.get("/api/documents")
async def list_documents(user=Depends(auth.current_user)):
    return await asyncio.to_thread(get_store().documents)


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...), destination: str = Form(""),
                          user=Depends(auth.current_user)):
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 20MB.")
    try:
        chunks = await asyncio.to_thread(chunk_file, file.filename or "upload", data, "upload",
                                         destination=destination or None, title=file.filename)
    except ValueError as exc:
        raise HTTPException(415, str(exc))
    except Exception as exc:
        raise HTTPException(422, f"Could not read file: {exc}")
    if not chunks:
        raise HTTPException(422, "No text could be extracted (scanned PDFs need OCR first).")
    await asyncio.to_thread(get_store().upsert, chunks)
    return {"doc_id": chunks[0].metadata["doc_id"], "chunks": len(chunks), "filename": file.filename}


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str, user=Depends(auth.current_user)):
    await asyncio.to_thread(get_store().delete_document, doc_id)
    return {"deleted": doc_id}


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    destination: str | None = None
    allow_web: bool = False


@app.post("/api/search")
async def search(req: SearchRequest, user=Depends(auth.current_user)):
    r = await asyncio.to_thread(retrieve, req.query, 6, req.allow_web, req.destination,
                                bool(settings.groq_api_key))
    return {"queries": r.queries, "destination": r.destination, "used_web": r.used_web,
            "trace": r.trace, "sources": [s.to_dict() for s in r.sources]}


@app.get("/api/health")
async def health():
    return {"ok": True, "missing_keys": settings.missing_keys(), "chunks": get_store().count(),
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

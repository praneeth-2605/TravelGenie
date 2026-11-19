"""TravelGenie API.

POST /api/chat           – run the agent team, streamed as Server-Sent Events
GET  /api/threads/{id}   – restore a conversation
GET  /api/documents      – list indexed knowledge
POST /api/documents      – upload PDF / Markdown / text into the vector DB
DELETE /api/documents/{doc_id}
POST /api/search         – inspect the RAG pipeline directly (queries, scores, trace)
GET  /api/health
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.agents.graph import build_graph
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
    await asyncio.to_thread(models.warm_up)
    added = await asyncio.to_thread(seed_guides)
    log.info("knowledge base ready: %d chunks (%d new)", get_store().count(), added)
    async with AsyncSqliteSaver.from_conn_string(str(ROOT / "storage" / "threads.sqlite")) as saver:
        app.state.graph = build_graph(saver)
        yield


app = FastAPI(title="TravelGenie", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ chat
class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4000)


def _sse(event: str, data) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not settings.groq_api_key:
        raise HTTPException(503, "GROQ_API_KEY is not set on the server. Add it to .env and restart.")
    graph = app.state.graph
    config = {"configurable": {"thread_id": req.thread_id}}

    async def events():
        try:
            async for mode, payload in graph.astream(
                {"messages": [HumanMessage(req.message)]}, config, stream_mode=["custom", "messages"]
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
            yield _sse("final", {
                "answer": text_of(state["messages"][-1].content),
                "sources": state.get("sources") or [],
                "trip": state.get("trip") or {},
                "bookings": state.get("bookings") or [],
                "weather": state.get("weather"),
                "intent": state.get("intent"),
            })
        except Exception as exc:
            log.exception("chat failed")
            text = str(exc)
            if "429" in text or "rate limit" in text.lower():
                message = ("Groq's free-tier rate limit was reached (about 8,000 tokens per minute). "
                           "Wait a minute and try again.")
            elif "401" in text or "invalid api key" in text.lower():
                message = "Groq rejected the API key. Check GROQ_API_KEY in .env and restart the API."
            else:
                message = f"Something went wrong: {type(exc).__name__}: {text}"[:500]
            yield _sse("error", {"message": message})

    return EventSourceResponse(events())


@app.get("/api/threads/{thread_id}")
async def get_thread(thread_id: str):
    snap = await app.state.graph.aget_state({"configurable": {"thread_id": thread_id}})
    values = snap.values or {}
    return {
        "messages": [{"role": "user" if m.type == "human" else "assistant", "content": text_of(m.content)}
                     for m in values.get("messages", []) if m.type in ("human", "ai")],
        "trip": values.get("trip") or {},
        "sources": values.get("sources") or [],
        "bookings": values.get("bookings") or [],
        "weather": values.get("weather"),
    }


# ------------------------------------------------------------------ knowledge
@app.get("/api/documents")
async def list_documents():
    return await asyncio.to_thread(get_store().documents)


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...), destination: str = Form("")):
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
async def delete_document(doc_id: str):
    await asyncio.to_thread(get_store().delete_document, doc_id)
    return {"deleted": doc_id}


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    destination: str | None = None
    allow_web: bool = False


@app.post("/api/search")
async def search(req: SearchRequest):
    r = await asyncio.to_thread(retrieve, req.query, 6, req.allow_web, req.destination,
                                bool(settings.groq_api_key))
    return {"queries": r.queries, "destination": r.destination, "used_web": r.used_web,
            "trace": r.trace, "sources": [s.to_dict() for s in r.sources]}


@app.get("/api/health")
async def health():
    return {"ok": True, "missing_keys": settings.missing_keys(), "chunks": get_store().count(),
            "model": settings.groq_model}


# ------------------------------------------------------------------ frontend (production build)
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        file = (DIST / path).resolve()
        if path and file.is_file() and file.is_relative_to(DIST.resolve()):
            return FileResponse(file)
        return FileResponse(DIST / "index.html")

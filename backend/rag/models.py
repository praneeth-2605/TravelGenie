"""Embedding + reranking for the knowledge base, with two interchangeable backends.

- Jina AI API (when JINA_API_KEY is set): used in production on Vercel, where a
  serverless function can't hold ~150MB of local models. Free key, no card.
- fastembed (local ONNX models, no key): used for local development. The models
  download once (~150MB) into the cache on first use.

Reranker scores are returned on the same "logit" scale in both cases, so the
retrieval thresholds in pipeline.py work unchanged.
"""

from __future__ import annotations

import math
import time
from functools import lru_cache

import requests

from backend.config import settings

JINA_URL = "https://api.jina.ai/v1"


def using_jina() -> bool:
    return bool(settings.jina_api_key)


def index_tag() -> str:
    """Names the search index for the active embedding model, so vectors from
    different models (different sizes) are never mixed in one index."""
    return f"jina_{settings.jina_dimensions}" if using_jina() else "local"


# ------------------------------------------------------------------ Jina API
def _jina(path: str, payload: dict) -> dict:
    headers = {"Authorization": f"Bearer {settings.jina_api_key}", "Content-Type": "application/json"}
    for attempt in range(3):
        r = requests.post(f"{JINA_URL}/{path}", json=payload, headers=headers, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:  # rate limited / transient
            time.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code == 401:
            raise RuntimeError("Jina rejected the API key (check JINA_API_KEY).")
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def _jina_embed(texts: list[str], task: str) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), 64):
        data = _jina("embeddings", {
            "model": settings.jina_embed_model,
            "task": task,
            "dimensions": settings.jina_dimensions,
            "input": texts[i:i + 64],
        })
        out += [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
    return out


def _to_logit(p: float) -> float:
    """Jina returns relevance in (0, 1); convert to the cross-encoder logit scale."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _jina_rerank(query: str, docs: list[str]) -> list[float]:
    data = _jina("rerank", {"model": settings.jina_rerank_model, "query": query,
                            "documents": docs, "top_n": len(docs), "return_documents": False})
    scores = [0.0] * len(docs)
    for r in data["results"]:
        scores[r["index"]] = _to_logit(float(r["relevance_score"]))
    return scores


# ------------------------------------------------------------------ local fastembed
@lru_cache
def _embedder():
    from fastembed import TextEmbedding
    return TextEmbedding(settings.embed_model, cache_dir=settings.model_cache)


@lru_cache
def _reranker():
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    return TextCrossEncoder(settings.rerank_model, cache_dir=settings.model_cache)


# ------------------------------------------------------------------ public API
def embed_documents(texts: list[str]) -> list[list[float]]:
    if using_jina():
        return _jina_embed(texts, "retrieval.passage")
    return [v.tolist() for v in _embedder().embed(texts)]


def embed_query(text: str) -> list[float]:
    if using_jina():
        return _jina_embed([text], "retrieval.query")[0]
    # bge models use an instruction prefix for queries; query_embed adds it.
    return next(iter(_embedder().query_embed(text))).tolist()


def rerank(query: str, docs: list[str]) -> list[float]:
    """Relevance scores (higher = more relevant), one per doc, on a logit scale."""
    if not docs:
        return []
    if using_jina():
        return _jina_rerank(query, docs)
    return [float(s) for s in _reranker().rerank(query, docs)]


def warm_up() -> None:
    """Load local models ahead of time (nothing to do for the Jina API)."""
    if not using_jina():
        embed_query("warm up")
        rerank("warm up", ["warm up"])

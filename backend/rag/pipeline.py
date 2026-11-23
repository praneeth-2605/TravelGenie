"""Advanced retrieval pipeline.

    question
      │ 1. query understanding  – LLM rewrites into multiple search queries
      │                           and extracts the destination (metadata filter)
      │ 2. hybrid retrieval     – dense (Chroma) + keyword (BM25) per query
      │ 3. rank fusion          – Reciprocal Rank Fusion across all result lists
      │ 4. reranking            – cross-encoder scores (query, chunk) pairs
      │ 5. corrective fallback  – weak local evidence → live web search, results
      │                           cached into the vector DB for next time
      │ 6. context expansion    – pull neighbouring chunks of the best hits
      ▼ 7. cited context        – numbered sources the agents must cite as [n]
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field

from backend.config import settings
from backend.rag import models
from backend.rag.ingest import chunk_web_result, normalize_destination
from backend.rag.store import Hit, get_store

log = logging.getLogger(__name__)

RRF_K = 60


def _thresholds() -> tuple[float, float]:
    """(drop below, confident above) on the reranker's logit scale.

    Calibrated per reranker on the bundled guides: the local ms-marco cross-encoder
    spreads scores widely (irrelevant ≈ -8, relevant ≥ 0); Jina's reranker is
    tighter (irrelevant ≈ -2.3 and lower, relevant ≈ -0.4 to +0.6).
    """
    return (-2.0, -1.0) if models.using_jina() else (-4.0, 0.0)


@dataclass
class Source:
    n: int
    title: str
    source: str
    source_type: str
    section: str | None
    page: int | None
    score: float
    text: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class RetrievalResult:
    question: str
    queries: list[str]
    destination: str | None
    sources: list[Source] = field(default_factory=list)
    used_web: bool = False
    web_error: str | None = None
    trace: list[str] = field(default_factory=list)

    def context_block(self) -> str:
        if not self.sources:
            return "No relevant knowledge found."
        parts = []
        for s in self.sources:
            where = s.title + (f" — {s.section}" if s.section else "") + (f" (p.{s.page})" if s.page else "")
            parts.append(f"[{s.n}] {where} <{s.source_type}>\n{s.text}")
        return "\n\n".join(parts)


# ---------------------------------------------------------------- step 1
_REWRITE_PROMPT = """You help a travel search engine. Given the traveller's question,
return JSON only: {{"destination": "<city or country, or empty>",
"queries": ["<3 short, diverse search queries covering different angles>"]}}

Question: {question}"""


def understand_query(question: str) -> tuple[list[str], str | None]:
    try:
        from backend.llm import fast_llm, text_of
        raw = text_of(fast_llm().invoke(_REWRITE_PROMPT.format(question=question)).content)
        data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        queries = [q for q in data.get("queries", []) if isinstance(q, str) and q.strip()][:3]
        dest = normalize_destination(data.get("destination")) or None
        return [question, *queries], dest
    except Exception as exc:  # no key, bad JSON, network – fall back to the raw question
        log.info("query rewrite skipped: %s", exc)
        return [question], None


# ---------------------------------------------------------------- steps 2-3
def _where(destination: str | None, known: set[str]) -> dict | None:
    # Only filter when we actually hold knowledge for that destination;
    # otherwise an unknown place would filter everything out.
    if destination and destination in known:
        return {"destination": destination}
    return None


def _fresh(hit: Hit) -> bool:
    if hit.metadata.get("source_type") != "web":
        return True
    age_days = (time.time() - hit.metadata.get("created_at", 0)) / 86400
    return age_days <= settings.web_cache_ttl_days


def hybrid_retrieve(queries: list[str], where: dict | None, per_list: int = 20,
                    viewer: str | None = None) -> list[Hit]:
    store = get_store()
    fused: dict[str, float] = {}
    hits: dict[str, Hit] = {}
    for q in queries:
        for ranked in (store.dense_search(q, per_list, where, viewer),
                       store.keyword_search(q, per_list, where, viewer)):
            for rank, h in enumerate(ranked):
                if not _fresh(h):
                    continue
                hits[h.id] = h
                fused[h.id] = fused.get(h.id, 0.0) + 1.0 / (RRF_K + rank + 1)
    order = sorted(fused, key=fused.get, reverse=True)
    return [Hit(i, hits[i].text, hits[i].metadata, fused[i]) for i in order]


# ---------------------------------------------------------------- step 4
def rerank(queries: list[str], hits: list[Hit], top_n: int) -> list[Hit]:
    """Score each chunk against every query and keep its best score.

    Cross-encoders score long, multi-part questions poorly ("4 days in Tokyo
    for 2... is the JR pass worth it?"), so a chunk that perfectly answers one
    part gets buried. The focused rewrites ("JR pass value Tokyo") fix that.
    """
    if not hits:
        return []
    docs = [f"{h.metadata.get('section', '')}\n{h.text}" for h in hits]
    best = [float("-inf")] * len(hits)
    for q in dict.fromkeys(queries):
        for i, s in enumerate(models.rerank(q, docs)):
            best[i] = max(best[i], s)
    for h, s in zip(hits, best):
        h.score = s
    ranked = sorted(hits, key=lambda h: h.score, reverse=True)
    return [h for h in ranked if h.score >= _thresholds()[0]][:top_n]


# ---------------------------------------------------------------- step 5
class WebSearchError(RuntimeError):
    pass


def web_search_and_cache(question: str, destination: str | None, max_results: int = 5) -> list[Hit]:
    if not settings.tavily_api_key:
        raise WebSearchError("web search not configured (TAVILY_API_KEY missing)")
    try:
        from langchain_tavily import TavilySearch
        res = TavilySearch(max_results=max_results, tavily_api_key=settings.tavily_api_key).invoke({"query": question})
    except Exception as exc:
        log.warning("web search failed: %s", exc)
        raise WebSearchError(f"web search failed ({type(exc).__name__})") from exc
    # The Tavily tool reports API failures (e.g. a bad key) as {"error": ...} rather than raising.
    if isinstance(res, dict) and res.get("error"):
        msg = str(res["error"])
        log.warning("web search error: %s", msg[:300])
        if "401" in msg or "Unauthorized" in msg or "invalid API key" in msg:
            raise WebSearchError("web search unavailable: Tavily rejected the API key")
        raise WebSearchError("web search returned an error")
    results = res.get("results", []) if isinstance(res, dict) else []
    chunks = []
    for r in results:
        if r.get("content"):
            chunks += chunk_web_result(r.get("url", ""), r.get("title", ""), r["content"], question, destination)
    get_store().upsert(chunks)
    return [Hit(c.id, c.text, c.metadata) for c in chunks]


# ---------------------------------------------------------------- step 6
def expand(hits: list[Hit]) -> list[Hit]:
    """Merge each hit with its neighbours so the LLM sees surrounding context."""
    store = get_store()
    seen = {h.id for h in hits}
    out = []
    for h in hits:
        neighbours = [n for n in store.get_neighbors(h) if n.id not in seen]
        seen.update(n.id for n in neighbours)
        before = [n.text for n in neighbours if n.metadata.get("chunk_index", 0) < h.metadata.get("chunk_index", 0)]
        after = [n.text for n in neighbours if n.metadata.get("chunk_index", 0) > h.metadata.get("chunk_index", 0)]
        text = "\n".join([*before, h.text, *after])
        out.append(Hit(h.id, text[:1500], h.metadata, h.score))
    return out


# ---------------------------------------------------------------- orchestration
def retrieve(question: str, top_n: int = 6, allow_web: bool = True,
             destination: str | None = None, rewrite: bool = True,
             viewer: str | None = None) -> RetrievalResult:
    """`viewer` is the user id: their own uploads are searched along with public content."""
    store = get_store()
    queries, guessed = understand_query(question) if rewrite else ([question], None)
    destination = normalize_destination(destination) or guessed
    result = RetrievalResult(question, queries, destination)
    result.trace.append(f"queries: {queries}")

    where = _where(destination, store.destinations())
    result.trace.append(f"filter: {where or 'none'}")
    candidates = hybrid_retrieve(queries, where, viewer=viewer)
    if where and len(candidates) < top_n:  # filter too narrow — widen
        candidates += [h for h in hybrid_retrieve(queries, None, viewer=viewer) if h.id not in {c.id for c in candidates}]
    result.trace.append(f"fused candidates: {len(candidates)}")

    best = rerank(queries, candidates[:40], top_n)
    top_score = best[0].score if best else float("-inf")
    result.trace.append(f"top rerank score: {top_score:.2f}")

    if allow_web and (top_score < _thresholds()[1] or len(best) < 2):
        try:
            web = web_search_and_cache(question, destination)
        except WebSearchError as exc:
            web = []
            result.web_error = str(exc)
            result.trace.append(str(exc))
        if web:
            result.used_web = True
            result.trace.append(f"corrective web search: {len(web)} chunks cached")
            best = rerank(queries, best + web, top_n)

    for n, h in enumerate(expand(best), start=1):
        m = h.metadata
        result.sources.append(Source(
            n=n,
            title=m.get("title") or m.get("destination", "").title() or m.get("source", "source"),
            source=m.get("source", ""),
            source_type=m.get("source_type", ""),
            section=m.get("section") or None,
            page=m.get("page"),
            score=round(h.score, 2),
            text=h.text,
        ))
    return result

"""Local embedding + reranking models (ONNX via fastembed, no GPU or API key).

Groq has no embeddings endpoint, so embeddings run locally. Models download
once (~150MB total) into the fastembed cache on first use.
"""

from functools import lru_cache

from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

from backend.config import settings


@lru_cache
def _embedder() -> TextEmbedding:
    return TextEmbedding(settings.embed_model, cache_dir=settings.model_cache)


@lru_cache
def _reranker() -> TextCrossEncoder:
    return TextCrossEncoder(settings.rerank_model, cache_dir=settings.model_cache)


def embed_documents(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _embedder().embed(texts)]


def embed_query(text: str) -> list[float]:
    # bge models use an instruction prefix for queries; query_embed adds it.
    return next(iter(_embedder().query_embed(text))).tolist()


def rerank(query: str, docs: list[str]) -> list[float]:
    """Cross-encoder relevance scores (higher = more relevant), one per doc."""
    if not docs:
        return []
    return [float(s) for s in _reranker().rerank(query, docs)]


def warm_up() -> None:
    embed_query("warm up")
    rerank("warm up", ["warm up"])

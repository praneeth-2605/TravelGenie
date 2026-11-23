"""Central configuration, read once from the environment / .env file."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Writable folder for caches and local databases. On Vercel the code directory is
# read-only and only /tmp is writable (and temporary); real data lives in Postgres there.
ON_VERCEL = bool(os.getenv("VERCEL"))
STORAGE = Path(os.getenv("STORAGE_DIR") or ("/tmp/travelgenie" if ON_VERCEL else ROOT / "storage"))


def _key(name: str) -> str | None:
    """Read a secret, forgiving stray spaces or quotes copied along with it."""
    value = (os.getenv(name) or "").strip().strip("\"'").strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    groq_api_key: str | None = _key("GROQ_API_KEY")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    # The writer gets the strongest model. Groq rate limits are per model, so
    # splitting the work across two models also doubles the token budget.
    groq_writer_model: str = os.getenv("GROQ_WRITER_MODEL", "openai/gpt-oss-120b")
    # Model for routing / query rewriting. Point at a smaller Groq model to cut latency.
    groq_fast_model: str = os.getenv("GROQ_FAST_MODEL", os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"))
    tavily_api_key: str | None = _key("TAVILY_API_KEY")
    openweather_api_key: str | None = _key("OPENWEATHERMAP_API_KEY")

    # RAG
    storage_dir: Path = STORAGE
    chroma_dir: Path = STORAGE / "chroma"
    uploads_dir: Path = STORAGE / "uploads"
    guides_dir: Path = ROOT / "data" / "guides"
    collection: str = "travel_knowledge"
    embed_model: str = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
    rerank_model: str = os.getenv("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
    chunk_size: int = 900
    chunk_overlap: int = 150
    # Web results older than this are ignored by the cache (days).
    web_cache_ttl_days: int = 14

    # Storage: PostgreSQL (e.g. Neon) when set; local SQLite + Chroma files otherwise.
    database_url: str | None = _key("DATABASE_URL")
    # Where the local embedding/reranker models are cached (development only).
    model_cache: str | None = os.getenv("MODEL_CACHE_DIR")
    # Jina AI API for embeddings + reranking (production on Vercel). When unset,
    # local fastembed models are used instead.
    jina_api_key: str | None = _key("JINA_API_KEY")
    jina_embed_model: str = os.getenv("JINA_EMBED_MODEL", "jina-embeddings-v3")
    jina_rerank_model: str = os.getenv("JINA_RERANK_MODEL", "jina-reranker-v2-base-multilingual")
    jina_dimensions: int = int(os.getenv("JINA_DIMENSIONS", "512"))

    # Auth
    secret_key: str | None = _key("SECRET_KEY")
    google_client_id: str | None = _key("GOOGLE_CLIENT_ID")
    # Secure (HTTPS-only) session cookie: on by default on Vercel, off locally (http).
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "true" if ON_VERCEL else "false").lower() == "true"
    # Public origin(s) of the deployed site, for the cross-site request check.
    public_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in os.getenv("PUBLIC_ORIGINS", "").split(",") if o.strip()])

    cors_origins: list[str] = field(
        default_factory=lambda: os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
    )

    def missing_keys(self) -> list[str]:
        pairs = {
            "GROQ_API_KEY": self.groq_api_key,
            "TAVILY_API_KEY": self.tavily_api_key,
            "OPENWEATHERMAP_API_KEY": self.openweather_api_key,
        }
        return [k for k, v in pairs.items() if not v]


settings = Settings()

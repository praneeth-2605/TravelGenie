"""Central configuration, read once from the environment / .env file."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


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
    chroma_dir: Path = ROOT / "storage" / "chroma"
    uploads_dir: Path = ROOT / "storage" / "uploads"
    guides_dir: Path = ROOT / "data" / "guides"
    collection: str = "travel_knowledge"
    embed_model: str = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
    rerank_model: str = os.getenv("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
    chunk_size: int = 900
    chunk_overlap: int = 150
    # Web results older than this are ignored by the cache (days).
    web_cache_ttl_days: int = 14

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

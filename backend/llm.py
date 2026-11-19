"""Groq chat models via the OpenAI-compatible endpoint."""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from backend.config import settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class MissingAPIKey(RuntimeError):
    pass


def _make(model: str, temperature: float, max_tokens: int) -> ChatOpenAI:
    if not settings.groq_api_key:
        raise MissingAPIKey("GROQ_API_KEY is not set. Add it to your .env file.")
    return ChatOpenAI(
        model=model,
        api_key=settings.groq_api_key,
        base_url=GROQ_BASE_URL,
        temperature=temperature,
        max_tokens=max_tokens,
        # Free-tier Groq is ~8k tokens/minute per model; the client backs off
        # and honours Retry-After on 429s.
        max_retries=4,
        timeout=90,
    )


@lru_cache
def main_llm() -> ChatOpenAI:
    """Specialist agents (budget, booking)."""
    return _make(settings.groq_model, temperature=0.3, max_tokens=1500)


@lru_cache
def writer_llm() -> ChatOpenAI:
    """The strongest model: writes the final cited itinerary."""
    return _make(settings.groq_writer_model, temperature=0.4, max_tokens=3500)


@lru_cache
def fast_llm() -> ChatOpenAI:
    """The cheap model: routing, query rewriting, extraction."""
    return _make(settings.groq_fast_model, temperature=0.0, max_tokens=800)


def text_of(content) -> str:
    """Models sometimes return a list of content blocks; flatten to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    return str(content)

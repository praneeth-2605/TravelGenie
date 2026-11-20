"""Groq chat models via the OpenAI-compatible endpoint."""

import logging
import re
from functools import lru_cache
from typing import TypeVar

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from backend.config import settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

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
def structured_llm() -> ChatOpenAI:
    """Mid-size JSON answers (e.g. the transport comparison) on the fast model."""
    return _make(settings.groq_fast_model, temperature=0.2, max_tokens=3000)


@lru_cache
def writer_llm() -> ChatOpenAI:
    """The strongest model: writes cited answers to questions."""
    return _make(settings.groq_writer_model, temperature=0.4, max_tokens=3000)


@lru_cache
def planner_llm():
    """The strongest model with light reasoning, so a full three-option plan
    fits inside the free tier's per-minute token budget. (No server-side JSON
    mode: Groq rejects the whole response on any JSON slip; we parse and repair.)"""
    llm = _make(settings.groq_writer_model, temperature=0.3, max_tokens=5000)
    return llm.bind(reasoning_effort="low")


def _extract_json(text: str) -> str | None:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    m = re.search(r"\{.*\}", text, re.S)
    return m.group(0) if m else None


def _failed_generation(exc: Exception) -> str | None:
    """Groq returns the model's (invalid) output in the error body; recover it."""
    for e in (exc, exc.__cause__):
        body = getattr(e, "body", None)
        if isinstance(body, dict):
            gen = (body.get("error") or body).get("failed_generation")
            if gen:
                return gen
    return None


async def ask_json(llm, messages: list, schema: type[T], attempts: int = 3) -> T:
    """Call the model and validate its JSON against `schema`, feeding errors
    back for a corrected answer. Rate-limit errors are raised to the caller."""
    messages = list(messages)
    last_error = "no response"
    for _ in range(attempts):
        try:
            raw = text_of((await llm.ainvoke(messages)).content)
        except Exception as exc:
            text = str(exc)
            if "429" in text or "rate limit" in text.lower() or "401" in text:
                raise
            raw = _failed_generation(exc)
            if raw is None:
                last_error = text[:300]
                log.warning("model call failed: %s", last_error)
                continue
        candidate = _extract_json(raw)
        try:
            if candidate is None:
                raise ValueError("no JSON object found in the reply")
            return schema.model_validate_json(candidate)
        except (ValidationError, ValueError) as exc:
            last_error = str(exc)[:500]
            log.warning("invalid JSON from model: %s", last_error[:200])
            messages += [AIMessage(raw[:6000]),
                         HumanMessage(f"That was not valid: {last_error}. Reply with the corrected, complete JSON object only.")]
    raise RuntimeError(f"The model didn't return a valid plan ({last_error[:120]}). Please try again.")


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

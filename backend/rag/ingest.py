"""Turn files and web results into metadata-rich chunks.

Chunking is structure-aware: markdown is split on headings first so a chunk
never straddles two topics, then long sections are split recursively with
overlap. Each chunk carries its section path ("Goa > Food > Street food"),
which is prepended to the embedded text so retrieval sees the context.
"""

from __future__ import annotations

import hashlib
import io
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from pypdf import PdfReader

from backend.config import settings

SourceType = str  # "guide" | "upload" | "web"


@dataclass
class Chunk:
    id: str
    text: str  # what the LLM reads
    metadata: dict = field(default_factory=dict)

    @property
    def embed_text(self) -> str:
        """Text that gets embedded / BM25-indexed: section path + body."""
        section = self.metadata.get("section")
        return f"{section}\n{self.text}" if section else self.text


_splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
    separators=["\n\n", "\n", ". ", " ", ""],
)
_md_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
    strip_headers=True,
)


def normalize_destination(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _doc_id(source: str, content: str) -> str:
    return hashlib.sha1(f"{source}\n{content}".encode()).hexdigest()[:16]


def _front_matter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    return meta, text[m.end():]


def _base_meta(source: str, source_type: SourceType, doc_id: str, **extra) -> dict:
    meta = {
        "source": source,
        "source_type": source_type,
        "doc_id": doc_id,
        "created_at": int(time.time()),
    }
    for k, v in extra.items():
        if v not in (None, ""):
            meta[k] = v
    if "destination" in meta:
        meta["destination"] = normalize_destination(meta["destination"])
    return meta


def chunk_markdown(text: str, source: str, source_type: SourceType, **meta) -> list[Chunk]:
    front, body = _front_matter(text)
    meta = {**front, **{k: v for k, v in meta.items() if v}}
    doc_id = _doc_id(source, text)
    base = _base_meta(source, source_type, doc_id, **meta)

    chunks: list[Chunk] = []
    for section in _md_splitter.split_text(body):
        path = " > ".join(section.metadata[h] for h in ("h1", "h2", "h3") if h in section.metadata)
        for piece in _splitter.split_text(section.page_content):
            idx = len(chunks)
            chunks.append(Chunk(
                id=f"{doc_id}-{idx}",
                text=piece.strip(),
                metadata={**base, "section": path, "chunk_index": idx},
            ))
    return [c for c in chunks if c.text]


def chunk_plain(text: str, source: str, source_type: SourceType, page: int | None = None,
                doc_id: str | None = None, start_index: int = 0, **meta) -> list[Chunk]:
    doc_id = doc_id or _doc_id(source, text)
    base = _base_meta(source, source_type, doc_id, **meta)
    chunks = []
    for i, piece in enumerate(_splitter.split_text(text)):
        idx = start_index + i
        m = {**base, "chunk_index": idx}
        if page is not None:
            m["page"] = page
        chunks.append(Chunk(id=f"{doc_id}-{idx}", text=piece.strip(), metadata=m))
    return [c for c in chunks if c.text]


def chunk_pdf(data: bytes, source: str, source_type: SourceType = "upload", **meta) -> list[Chunk]:
    reader = PdfReader(io.BytesIO(data))
    doc_id = hashlib.sha1(data).hexdigest()[:16]
    chunks: list[Chunk] = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            chunks += chunk_plain(text, source, source_type, page=page_no, doc_id=doc_id,
                                  start_index=len(chunks), **meta)
    return chunks


def chunk_file(filename: str, data: bytes, source_type: SourceType = "upload", **meta) -> list[Chunk]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return chunk_pdf(data, filename, source_type, **meta)
    text = data.decode("utf-8", errors="replace")
    if suffix in {".md", ".markdown"}:
        return chunk_markdown(text, filename, source_type, **meta)
    if suffix in {".txt", ".csv", ".json", ".html"}:
        return chunk_plain(text, filename, source_type, **meta)
    raise ValueError(f"Unsupported file type: {suffix or filename}")


def chunk_web_result(url: str, title: str, content: str, query: str, destination: str | None) -> list[Chunk]:
    return chunk_plain(content, url, "web", title=title, query=query, destination=destination)

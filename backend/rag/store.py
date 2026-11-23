"""Hybrid knowledge store: dense vectors + BM25 (keywords).

Dense search catches paraphrases ("cheap eats" ~ "budget street food");
BM25 catches exact terms dense models blur (place names, "e-visa", "Line 3").

Two backends with the same interface:
- PgVectorStore: PostgreSQL + pgvector (production, e.g. Neon), when DATABASE_URL is set
- KnowledgeStore: local ChromaDB files in storage/chroma (development)
The BM25 index is rebuilt in memory whenever the chunks change.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from backend.config import settings
from backend.rag import models
from backend.rag.ingest import Chunk

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set("a an the and or of to in on for with at by from is are was be it this that as".split())


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


@dataclass
class Hit:
    id: str
    text: str
    metadata: dict
    score: float = 0.0


class KnowledgeStore:
    def __init__(self) -> None:
        import chromadb  # only needed for the local backend

        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        # One collection per embedding model: vectors from different models (sizes)
        # can't be mixed, so switching between Jina and local models never clashes.
        self._col = self._client.get_or_create_collection(
            (settings.collection if models.index_tag() == "local" else f"{settings.collection}_{models.index_tag()}"), metadata={"hnsw:space": "cosine"}, embedding_function=None
        )
        self._lock = threading.RLock()
        self._bm25: BM25Okapi | None = None
        self._bm25_rows: list[Hit] = []
        self._dirty = True

    # ---------- writes ----------
    def upsert(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        with self._lock:
            for i in range(0, len(chunks), 64):
                batch = chunks[i:i + 64]
                self._col.upsert(
                    ids=[c.id for c in batch],
                    documents=[c.text for c in batch],
                    metadatas=[c.metadata for c in batch],
                    embeddings=models.embed_documents([c.embed_text for c in batch]),
                )
            self._dirty = True
        return len(chunks)

    def delete_document(self, doc_id: str) -> None:
        with self._lock:
            self._col.delete(where={"doc_id": doc_id})
            self._dirty = True

    def delete_where(self, where: dict) -> None:
        with self._lock:
            self._col.delete(where=where)
            self._dirty = True

    # ---------- reads ----------
    def count(self) -> int:
        return self._col.count()

    def has_doc(self, doc_id: str) -> bool:
        return bool(self._col.get(where={"doc_id": doc_id}, limit=1)["ids"])

    def documents(self) -> list[dict]:
        """One row per source document, with chunk counts."""
        rows = self._col.get(include=["metadatas"])
        docs: dict[str, dict] = {}
        for meta in rows["metadatas"]:
            d = docs.setdefault(meta["doc_id"], {
                "doc_id": meta["doc_id"],
                "source": meta.get("source"),
                "title": meta.get("title") or meta.get("source"),
                "source_type": meta.get("source_type"),
                "destination": meta.get("destination"),
                "created_at": meta.get("created_at"),
                "chunks": 0,
            })
            d["chunks"] += 1
        return sorted(docs.values(), key=lambda d: (d["source_type"], d["title"] or ""))

    def destinations(self) -> set[str]:
        rows = self._col.get(include=["metadatas"])
        return {m["destination"] for m in rows["metadatas"] if m.get("destination")}

    def get_neighbors(self, hit: Hit) -> list[Hit]:
        """The chunks immediately before/after a hit in the same document."""
        idx = hit.metadata.get("chunk_index")
        if idx is None:
            return []
        ids = [f"{hit.metadata['doc_id']}-{idx - 1}", f"{hit.metadata['doc_id']}-{idx + 1}"]
        rows = self._col.get(ids=ids, include=["documents", "metadatas"])
        return [Hit(i, d, m) for i, d, m in zip(rows["ids"], rows["documents"], rows["metadatas"])]

    def dense_search(self, query: str, k: int = 20, where: dict | None = None) -> list[Hit]:
        if self.count() == 0:
            return []
        res = self._col.query(
            query_embeddings=[models.embed_query(query)],
            n_results=min(k, self.count()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        return [
            Hit(i, d, m, 1.0 - dist)
            for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])
        ]

    def keyword_search(self, query: str, k: int = 20, where: dict | None = None) -> list[Hit]:
        with self._lock:
            if self._dirty:
                self._rebuild_bm25()
            if not self._bm25:
                return []
            scores = self._bm25.get_scores(tokenize(query))
            rows = self._bm25_rows
        ranked = sorted(zip(scores, rows), key=lambda x: x[0], reverse=True)
        out = []
        for score, row in ranked:
            if score <= 0:
                break
            if where and not _matches(row.metadata, where):
                continue
            out.append(Hit(row.id, row.text, row.metadata, float(score)))
            if len(out) >= k:
                break
        return out

    def _rebuild_bm25(self) -> None:
        rows = self._col.get(include=["documents", "metadatas"])
        self._bm25_rows = [Hit(i, d, m) for i, d, m in zip(rows["ids"], rows["documents"], rows["metadatas"])]
        corpus = [tokenize(f"{h.metadata.get('section', '')} {h.text}") for h in self._bm25_rows]
        self._bm25 = BM25Okapi(corpus) if corpus else None
        self._dirty = False


def _matches(meta: dict, where: dict) -> bool:
    """Evaluate the small subset of Chroma `where` syntax we use."""
    for key, cond in where.items():
        if key == "$and":
            if not all(_matches(meta, c) for c in cond):
                return False
        elif key == "$or":
            if not any(_matches(meta, c) for c in cond):
                return False
        elif isinstance(cond, dict):
            if "$in" in cond and meta.get(key) not in cond["$in"]:
                return False
            if "$eq" in cond and meta.get(key) != cond["$eq"]:
                return False
        elif meta.get(key) != cond:
            return False
    return True


class PgVectorStore:
    """The same store on PostgreSQL + pgvector, so the knowledge base (including
    uploads) lives in the cloud database and survives server restarts."""

    def __init__(self) -> None:
        from backend import db

        self._db = db
        dim = len(models.embed_query("dimension probe"))
        # One table per embedding model (see KnowledgeStore): e.g. kb_chunks_jina_512.
        self._table = f"kb_chunks_{models.index_tag()}"
        with db.tx() as c:
            c.execute("CREATE EXTENSION IF NOT EXISTS vector")
            c.execute(f"""CREATE TABLE IF NOT EXISTS {self._table} (
                id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, text TEXT NOT NULL,
                metadata JSONB NOT NULL, embedding vector({dim}) NOT NULL)""")
            c.execute(f"CREATE INDEX IF NOT EXISTS {self._table}_doc ON {self._table} (doc_id)")
            c.execute(f"CREATE INDEX IF NOT EXISTS {self._table}_hnsw ON {self._table} USING hnsw (embedding vector_cosine_ops)")
        self._lock = threading.RLock()
        self._bm25: BM25Okapi | None = None
        self._bm25_rows: list[Hit] = []
        self._dirty = True

    @staticmethod
    def _vec(v: list[float]) -> str:
        return "[" + ",".join(f"{x:.6f}" for x in v) + "]"

    @staticmethod
    def _where(where: dict | None) -> tuple[str, list]:
        """Translate the small Chroma-style filter subset we use into SQL."""
        if not where:
            return "TRUE", []
        clauses, params = [], []
        for key, cond in where.items():
            if key == "$and":
                for sub in cond:
                    c, p = PgVectorStore._where(sub)
                    clauses.append(c)
                    params += p
            elif key == "doc_id":
                clauses.append("doc_id = ?")
                params.append(cond)
            else:
                clauses.append("metadata->>? = ?")
                params += [key, str(cond)]
        return " AND ".join(clauses) or "TRUE", params

    @staticmethod
    def _meta(value) -> dict:
        return value if isinstance(value, dict) else json.loads(value)

    # ---------- writes ----------
    def upsert(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        for i in range(0, len(chunks), 64):
            batch = chunks[i:i + 64]
            vectors = models.embed_documents([c.embed_text for c in batch])
            with self._db.tx() as tx:
                for c, v in zip(batch, vectors):
                    tx.execute(
                        f"INSERT INTO {self._table} (id, doc_id, text, metadata, embedding) VALUES (?, ?, ?, ?::jsonb, ?::vector) "
                        "ON CONFLICT (id) DO UPDATE SET doc_id = EXCLUDED.doc_id, text = EXCLUDED.text, "
                        "metadata = EXCLUDED.metadata, embedding = EXCLUDED.embedding",
                        (c.id, c.metadata["doc_id"], c.text, json.dumps(c.metadata), self._vec(v)))
        self._dirty = True
        return len(chunks)

    def delete_document(self, doc_id: str) -> None:
        self.delete_where({"doc_id": doc_id})

    def delete_where(self, where: dict) -> None:
        clause, params = self._where(where)
        with self._db.tx() as tx:
            tx.execute(f"DELETE FROM {self._table} WHERE {clause}", params)
        self._dirty = True

    # ---------- reads ----------
    def count(self) -> int:
        return self._db.connect().execute(f"SELECT count(*) AS n FROM {self._table}").fetchone()["n"]

    def has_doc(self, doc_id: str) -> bool:
        return self._db.connect().execute(f"SELECT 1 FROM {self._table} WHERE doc_id = ? LIMIT 1", (doc_id,)).fetchone() is not None

    def _all_meta(self) -> list[dict]:
        return [self._meta(r["metadata"]) for r in self._db.connect().execute(f"SELECT metadata FROM {self._table}").fetchall()]

    def documents(self) -> list[dict]:
        docs: dict[str, dict] = {}
        for meta in self._all_meta():
            d = docs.setdefault(meta["doc_id"], {
                "doc_id": meta["doc_id"], "source": meta.get("source"),
                "title": meta.get("title") or meta.get("source"), "source_type": meta.get("source_type"),
                "destination": meta.get("destination"), "created_at": meta.get("created_at"), "chunks": 0,
            })
            d["chunks"] += 1
        return sorted(docs.values(), key=lambda d: (d["source_type"] or "", d["title"] or ""))

    def destinations(self) -> set[str]:
        rows = self._db.connect().execute(
            f"SELECT DISTINCT metadata->>'destination' AS d FROM {self._table} "
            "WHERE metadata->>'destination' IS NOT NULL").fetchall()
        return {r["d"] for r in rows if r["d"]}

    def get_neighbors(self, hit: Hit) -> list[Hit]:
        idx = hit.metadata.get("chunk_index")
        if idx is None:
            return []
        ids = [f"{hit.metadata['doc_id']}-{idx - 1}", f"{hit.metadata['doc_id']}-{idx + 1}"]
        rows = self._db.connect().execute(f"SELECT id, text, metadata FROM {self._table} WHERE id IN (?, ?)", ids).fetchall()
        return [Hit(r["id"], r["text"], self._meta(r["metadata"])) for r in rows]

    def dense_search(self, query: str, k: int = 20, where: dict | None = None) -> list[Hit]:
        clause, params = self._where(where)
        vec = self._vec(models.embed_query(query))
        rows = self._db.connect().execute(
            f"SELECT id, text, metadata, 1 - (embedding <=> ?::vector) AS score FROM {self._table} "
            f"WHERE {clause} ORDER BY embedding <=> ?::vector LIMIT ?",
            [vec, *params, vec, k]).fetchall()
        return [Hit(r["id"], r["text"], self._meta(r["metadata"]), float(r["score"])) for r in rows]

    def keyword_search(self, query: str, k: int = 20, where: dict | None = None) -> list[Hit]:
        with self._lock:
            if self._dirty:
                rows = self._db.connect().execute(f"SELECT id, text, metadata FROM {self._table}").fetchall()
                self._bm25_rows = [Hit(r["id"], r["text"], self._meta(r["metadata"])) for r in rows]
                corpus = [tokenize(f"{h.metadata.get('section', '')} {h.text}") for h in self._bm25_rows]
                self._bm25 = BM25Okapi(corpus) if corpus else None
                self._dirty = False
            if not self._bm25:
                return []
            scores = self._bm25.get_scores(tokenize(query))
            rows = self._bm25_rows
        ranked = sorted(zip(scores, rows), key=lambda x: x[0], reverse=True)
        out = []
        for score, row in ranked:
            if score <= 0:
                break
            if where and not _matches(row.metadata, where):
                continue
            out.append(Hit(row.id, row.text, row.metadata, float(score)))
            if len(out) >= k:
                break
        return out


_store = None
_store_lock = threading.Lock()


def get_store():
    global _store
    with _store_lock:
        if _store is None:
            _store = PgVectorStore() if settings.database_url else KnowledgeStore()
        return _store

"""Index the curated guides in data/guides into the vector store (idempotent)."""

import logging

from backend.config import settings
from backend.rag.ingest import chunk_markdown
from backend.rag.store import get_store

log = logging.getLogger(__name__)


def seed_guides() -> int:
    store = get_store()
    added = 0
    for path in sorted(settings.guides_dir.glob("*.md")):
        chunks = chunk_markdown(path.read_text(encoding="utf-8"), path.name, "guide")
        if not chunks or store.has_doc(chunks[0].metadata["doc_id"]):
            continue
        # A guide was edited: drop the old version before indexing the new one.
        store.delete_where({"$and": [{"source": path.name}, {"source_type": "guide"}]})
        added += store.upsert(chunks)
        log.info("indexed guide %s (%d chunks)", path.name, len(chunks))
    return added


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Indexed {seed_guides()} new chunks; store holds {get_store().count()}.")

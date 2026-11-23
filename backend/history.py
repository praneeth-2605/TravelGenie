"""Chat history (LangGraph checkpoints): open the store, delete conversations,
and remove conversations whose trip no longer exists.

Each trip's conversation is a checkpoint "thread" whose id is the trip id, so
deleting a trip or an account must delete those threads too.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager

from backend.config import settings

log = logging.getLogger(__name__)


@asynccontextmanager
async def checkpointer():
    """Chat-history store: Postgres in production, SQLite locally. One per request."""
    if settings.database_url:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg import AsyncConnection
        from psycopg.rows import dict_row

        conn = await AsyncConnection.connect(settings.database_url, autocommit=True,
                                             prepare_threshold=None, row_factory=dict_row)
        async with conn:
            yield AsyncPostgresSaver(conn)
    else:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # local development only

        async with AsyncSqliteSaver.from_conn_string(str(settings.storage_dir / "threads.sqlite")) as saver:
            yield saver


async def delete_threads(thread_ids: list[str]) -> None:
    """Delete the chat history of these trips."""
    if not thread_ids:
        return
    async with checkpointer() as saver:
        for tid in thread_ids:
            await saver.adelete_thread(tid)


def purge_orphans() -> int:
    """Delete chat history whose trip no longer exists (e.g. from accounts deleted
    before this cleanup existed). Returns how many conversations were removed."""
    if settings.database_url:
        from backend import db

        tables = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
        with db.tx() as tx:
            n = tx.execute("SELECT count(DISTINCT thread_id) AS n FROM checkpoints "
                           "WHERE thread_id NOT IN (SELECT id FROM trips)").fetchone()["n"]
            for table in tables:
                tx.execute(f"DELETE FROM {table} WHERE thread_id NOT IN (SELECT id FROM trips)")
        return n

    path = settings.storage_dir / "threads.sqlite"
    app_db = settings.storage_dir / "app.sqlite"
    if not path.exists() or not app_db.exists():
        return 0
    conn = sqlite3.connect(path)
    try:
        conn.execute("ATTACH DATABASE ? AS app", (str(app_db),))
        n = conn.execute("SELECT count(DISTINCT thread_id) FROM checkpoints "
                         "WHERE thread_id NOT IN (SELECT id FROM app.trips)").fetchone()[0]
        for table in ("checkpoints", "writes"):
            conn.execute(f"DELETE FROM {table} WHERE thread_id NOT IN (SELECT id FROM app.trips)")
        conn.commit()
        return n
    finally:
        conn.close()

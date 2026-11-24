"""App database: users, settings and trips.

Two backends, same code:
- PostgreSQL when DATABASE_URL is set (production, e.g. Neon): data lives in the cloud
- SQLite in storage/app.sqlite otherwise (local development)

Queries are written once with `?` placeholders; the Postgres adapter converts
them. Conversation messages live in LangGraph's checkpointer (same database).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager

from backend.config import settings

DB_PATH = settings.storage_dir / "app.sqlite"
USE_PG = bool(settings.database_url)
_local = threading.local()

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL,
    name          TEXT NOT NULL,
    password_hash TEXT,
    google_sub    TEXT UNIQUE,
    avatar_url    TEXT,
    token_version INTEGER NOT NULL DEFAULT 0,
    created_at    BIGINT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower ON users (lower(email));
CREATE TABLE IF NOT EXISTS user_settings (
    user_id           TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    home_currency     TEXT NOT NULL DEFAULT 'INR',
    travel_style      TEXT NOT NULL DEFAULT 'balanced',
    default_travelers INTEGER NOT NULL DEFAULT 1,
    budget_min        DOUBLE PRECISION,
    budget_max        DOUBLE PRECISION,
    interests         TEXT NOT NULL DEFAULT '[]',
    dietary           TEXT NOT NULL DEFAULT '',
    pace              TEXT NOT NULL DEFAULT 'moderate',
    theme             TEXT NOT NULL DEFAULT 'system',
    home_city         TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS trips (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title         TEXT NOT NULL,
    destination   TEXT,
    start_date    TEXT,
    days          INTEGER,
    plan          TEXT,
    favorite      INTEGER NOT NULL DEFAULT 0,
    selected_tier TEXT,
    created_at    BIGINT NOT NULL,
    updated_at    BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS trips_by_user ON trips(user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS usage (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day     TEXT NOT NULL,
    kind    TEXT NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day, kind)
);
CREATE TABLE IF NOT EXISTS kv_cache (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    created_at BIGINT NOT NULL
);
"""


# ------------------------------------------------------------------ Postgres adapter
class _Result:
    """Rows fetched eagerly, so the pooled connection can be returned at once."""

    def __init__(self, cur):
        self.rowcount = cur.rowcount
        self._rows = cur.fetchall() if cur.description else []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _PgConn:
    def __init__(self, conn=None):
        self._conn = conn  # set inside a transaction; otherwise borrow per statement

    def execute(self, sql: str, params=()):
        sql = sql.replace("?", "%s")
        if self._conn is not None:
            return _Result(self._conn.execute(sql, params))
        with _pool().connection() as conn:
            return _Result(conn.execute(sql, params))


_pg_pool = None
_pg_lock = threading.Lock()


def _pool():
    global _pg_pool
    with _pg_lock:
        if _pg_pool is None:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
            _pg_pool = ConnectionPool(
                settings.database_url, min_size=1, max_size=6, open=True,
                # prepare_threshold=None: no server-side prepared statements, so Neon's
                # pooled (PgBouncer) connection string works too.
                kwargs={"row_factory": dict_row, "autocommit": True, "prepare_threshold": None},
                # Serverless Postgres (Neon) drops idle connections; check before use.
                check=ConnectionPool.check_connection,
            )
        return _pg_pool


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name          TEXT NOT NULL,
    password_hash TEXT,
    google_sub    TEXT UNIQUE,
    avatar_url    TEXT,
    token_version INTEGER NOT NULL DEFAULT 0,
    created_at    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS user_settings (
    user_id          TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    home_currency    TEXT NOT NULL DEFAULT 'INR',
    travel_style     TEXT NOT NULL DEFAULT 'balanced',
    default_travelers INTEGER NOT NULL DEFAULT 1,
    budget_min       REAL,
    budget_max       REAL,
    interests        TEXT NOT NULL DEFAULT '[]',
    dietary          TEXT NOT NULL DEFAULT '',
    pace             TEXT NOT NULL DEFAULT 'moderate',
    theme            TEXT NOT NULL DEFAULT 'system'
);
CREATE TABLE IF NOT EXISTS trips (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    destination TEXT,
    start_date  TEXT,
    days        INTEGER,
    plan        TEXT,
    favorite    INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS trips_by_user ON trips(user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS usage (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day     TEXT NOT NULL,
    kind    TEXT NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day, kind)
);
CREATE TABLE IF NOT EXISTS kv_cache (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""


def connect():
    if USE_PG:
        return _PgConn()
    conn = getattr(_local, "conn", None)
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        _local.conn = conn
    return conn


@contextmanager
def tx():
    if USE_PG:
        with _pool().connection() as conn:
            with conn.transaction():
                yield _PgConn(conn)
        return
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


MIGRATIONS = [
    # (table, column, SQLite definition, PostgreSQL definition) — added to existing
    # databases on startup, so a deployed database upgrades itself.
    ("user_settings", "home_city", "TEXT NOT NULL DEFAULT ''", "TEXT NOT NULL DEFAULT ''"),
    ("trips", "selected_tier", "TEXT", "TEXT"),
    ("trips", "share_token", "TEXT", "TEXT"),          # public share link
    ("users", "consent_at", "INTEGER", "BIGINT"),      # when terms/privacy were accepted
]
INDEXES = ["CREATE UNIQUE INDEX IF NOT EXISTS trips_share ON trips(share_token)"]


def init() -> None:
    if USE_PG:
        with _pool().connection() as conn:
            conn.execute(PG_SCHEMA)
            for table, column, _, pg_def in MIGRATIONS:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {pg_def}")
            for sql in INDEXES:
                conn.execute(sql)
        return
    with tx() as c:
        c.executescript(SCHEMA)
        for table, column, sqlite_def, _ in MIGRATIONS:
            cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sqlite_def}")
        for sql in INDEXES:
            c.execute(sql)


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> int:
    return int(time.time())


# ------------------------------------------------------------------ users
def user_by_email(email: str) -> sqlite3.Row | None:
    return connect().execute("SELECT * FROM users WHERE lower(email) = lower(?)", (email,)).fetchone()


def user_by_id(user_id: str) -> sqlite3.Row | None:
    return connect().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def user_by_google(sub: str) -> sqlite3.Row | None:
    return connect().execute("SELECT * FROM users WHERE google_sub = ?", (sub,)).fetchone()


def create_user(email: str, name: str, password_hash: str | None = None,
                google_sub: str | None = None, avatar_url: str | None = None) -> sqlite3.Row:
    """New account. Callers only create accounts after the user accepted the terms."""
    uid = new_id()
    with tx() as c:
        c.execute(
            "INSERT INTO users (id, email, name, password_hash, google_sub, avatar_url, created_at, consent_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, email, name, password_hash, google_sub, avatar_url, now(), now()),
        )
        c.execute("INSERT INTO user_settings (user_id) VALUES (?)", (uid,))
    return user_by_id(uid)


def update_user(user_id: str, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with tx() as c:
        c.execute(f"UPDATE users SET {cols} WHERE id = ?", (*fields.values(), user_id))


def delete_user(user_id: str) -> None:
    with tx() as c:
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))


def public_user(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "email": row["email"], "name": row["name"],
        "avatar_url": row["avatar_url"], "has_password": bool(row["password_hash"]),
        "google_linked": bool(row["google_sub"]), "created_at": row["created_at"],
        "consent_at": row["consent_at"],
    }


# ------------------------------------------------------------------ settings
SETTINGS_FIELDS = {"home_currency", "travel_style", "default_travelers", "budget_min", "budget_max",
                   "interests", "dietary", "pace", "theme", "home_city"}


def get_settings(user_id: str) -> dict:
    row = connect().execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    data = dict(row) if row else {}
    data.pop("user_id", None)
    data["interests"] = json.loads(data.get("interests") or "[]")
    return data


def update_settings(user_id: str, values: dict) -> dict:
    values = {k: v for k, v in values.items() if k in SETTINGS_FIELDS}
    if "interests" in values:
        values["interests"] = json.dumps(values["interests"] or [])
    if values:
        cols = ", ".join(f"{k} = ?" for k in values)
        with tx() as c:
            c.execute(f"UPDATE user_settings SET {cols} WHERE user_id = ?", (*values.values(), user_id))
    return get_settings(user_id)


# ------------------------------------------------------------------ trips
def _trip(row: sqlite3.Row, full: bool = False) -> dict:
    d = dict(row)
    plan = json.loads(d.pop("plan") or "null")
    d["favorite"] = bool(d["favorite"])
    if full:
        d["plan"] = plan
    else:
        options = (plan or {}).get("options") or []
        d["summary"] = (plan or {}).get("summary")
        d["options"] = [{"tier": o.get("tier"), "label": o.get("label"), "total": o.get("total"),
                         "stay": (o.get("stay") or {}).get("name")} for o in options]
        d["currency"] = (plan or {}).get("currency")
        d["map_center"] = (plan or {}).get("map_center")
    return d


def list_trips(user_id: str) -> list[dict]:
    rows = connect().execute(
        "SELECT * FROM trips WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)).fetchall()
    return [_trip(r) for r in rows]


def get_trip(user_id: str, trip_id: str) -> dict | None:
    row = connect().execute(
        "SELECT * FROM trips WHERE id = ? AND user_id = ?", (trip_id, user_id)).fetchone()
    return _trip(row, full=True) if row else None


def trip_owner(trip_id: str) -> str | None:
    row = connect().execute("SELECT user_id FROM trips WHERE id = ?", (trip_id,)).fetchone()
    return row["user_id"] if row else None


def create_trip(user_id: str, trip_id: str, title: str) -> None:
    t = now()
    with tx() as c:
        c.execute("INSERT INTO trips (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                  (trip_id, user_id, title, t, t))


def update_trip(trip_id: str, **fields) -> None:
    if "plan" in fields:
        fields["plan"] = json.dumps(fields["plan"], ensure_ascii=False)
    if "favorite" in fields:
        fields["favorite"] = int(bool(fields["favorite"]))
    fields["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with tx() as c:
        c.execute(f"UPDATE trips SET {cols} WHERE id = ?", (*fields.values(), trip_id))


def delete_trip(user_id: str, trip_id: str) -> bool:
    with tx() as c:
        cur = c.execute("DELETE FROM trips WHERE id = ? AND user_id = ?", (trip_id, user_id))
    return cur.rowcount > 0


# ------------------------------------------------------------------ sharing
def set_share_token(user_id: str, trip_id: str, token: str | None) -> None:
    with tx() as c:
        c.execute("UPDATE trips SET share_token = ? WHERE id = ? AND user_id = ?", (token, trip_id, user_id))


def trip_by_share_token(token: str) -> dict | None:
    row = connect().execute("SELECT * FROM trips WHERE share_token = ?", (token,)).fetchone()
    return _trip(row, full=True) if row else None


# ------------------------------------------------------------------ usage limits
def usage_add(user_id: str, day: str, kind: str, amount: int = 1) -> int:
    """Increment today's counter and return the new value."""
    with tx() as c:
        c.execute("INSERT INTO usage (user_id, day, kind, count) VALUES (?, ?, ?, ?) "
                  "ON CONFLICT (user_id, day, kind) DO UPDATE SET count = usage.count + excluded.count",
                  (user_id, day, kind, amount))
        row = c.execute("SELECT count FROM usage WHERE user_id = ? AND day = ? AND kind = ?",
                        (user_id, day, kind)).fetchone()
    return row["count"]


def usage_get(user_id: str, day: str, kind: str) -> int:
    row = connect().execute("SELECT count FROM usage WHERE user_id = ? AND day = ? AND kind = ?",
                            (user_id, day, kind)).fetchone()
    return row["count"] if row else 0


# ------------------------------------------------------------------ shared cache
def cache_get(key: str, ttl_seconds: int):
    """A JSON value cached in the database (shared by every server instance)."""
    row = connect().execute("SELECT value, created_at FROM kv_cache WHERE key = ?", (key,)).fetchone()
    if not row or now() - row["created_at"] > ttl_seconds:
        return None
    return json.loads(row["value"])


def cache_set(key: str, value) -> None:
    with tx() as c:
        c.execute("INSERT INTO kv_cache (key, value, created_at) VALUES (?, ?, ?) "
                  "ON CONFLICT (key) DO UPDATE SET value = excluded.value, created_at = excluded.created_at",
                  (key, json.dumps(value, ensure_ascii=False), now()))

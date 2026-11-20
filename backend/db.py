"""App database (SQLite): users, settings and trips.

Conversation messages live in LangGraph's checkpointer (storage/threads.sqlite);
this database holds everything the dashboard needs.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager

from backend.config import ROOT

DB_PATH = ROOT / "storage" / "app.sqlite"
_local = threading.local()

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
"""


def connect() -> sqlite3.Connection:
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
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


MIGRATIONS = [
    # (table, column, definition) — added to existing databases on startup
    ("user_settings", "home_city", "TEXT NOT NULL DEFAULT ''"),
    ("trips", "selected_tier", "TEXT"),
]


def init() -> None:
    with tx() as c:
        c.executescript(SCHEMA)
        for table, column, definition in MIGRATIONS:
            cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> int:
    return int(time.time())


# ------------------------------------------------------------------ users
def user_by_email(email: str) -> sqlite3.Row | None:
    return connect().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def user_by_id(user_id: str) -> sqlite3.Row | None:
    return connect().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def user_by_google(sub: str) -> sqlite3.Row | None:
    return connect().execute("SELECT * FROM users WHERE google_sub = ?", (sub,)).fetchone()


def create_user(email: str, name: str, password_hash: str | None = None,
                google_sub: str | None = None, avatar_url: str | None = None) -> sqlite3.Row:
    uid = new_id()
    with tx() as c:
        c.execute(
            "INSERT INTO users (id, email, name, password_hash, google_sub, avatar_url, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, email, name, password_hash, google_sub, avatar_url, now()),
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

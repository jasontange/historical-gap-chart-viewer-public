import json
import sqlite3
import time
from pathlib import Path

_DB_PATH = Path(__file__).parent / "cache.db"
_FOREVER = 0
_24_HOURS = 86400


def _connect():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            created_at REAL NOT NULL,
            ttl        REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def cache_get(key: str):
    """Return the cached value (as a Python object) or None on miss/expiry."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT value, created_at, ttl FROM cache WHERE key = ?", (key,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    value_json, created_at, ttl = row
    if ttl != _FOREVER and (time.time() - created_at) >= ttl:
        return None

    return json.loads(value_json)


def cache_set(key: str, value, ttl: float = _FOREVER):
    """Store value (any JSON-serializable object) under key with given TTL."""
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO cache (key, value, created_at, ttl)
            VALUES (?, ?, ?, ?)
            """,
            (key, json.dumps(value), time.time(), ttl),
        )
        conn.commit()
    finally:
        conn.close()


def make_key(*parts) -> str:
    """Build a deterministic cache key from string parts."""
    return "|".join(str(p) for p in parts)

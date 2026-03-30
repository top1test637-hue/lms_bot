"""
╔══════════════════════════════════════════════════════════════════════╗
║  database/connection.py — إدارة الاتصالات بقاعدة البيانات           ║
║  Thread-safe Connection Pool + Context Manager + Schema Migration    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

# ── Thread-local connection pool ──────────────────────────────────────────────
# Each thread gets its own SQLite connection — safe for multi-threaded bots
# and avoids the overhead of a full connection pool for SQLite workloads.
_local = threading.local()


def _get_raw_connection(db_path: Path) -> sqlite3.Connection:
    """
    Return a thread-local SQLite connection, creating it on first access.

    Args:
        db_path: Absolute path to the SQLite database file.

    Returns:
        sqlite3.Connection: Configured connection with WAL mode and
        foreign-key enforcement.
    """
    if not hasattr(_local, "conn") or _local.conn is None:
        logger.debug("Creating new thread-local SQLite connection for %s", threading.current_thread().name)
        _local.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA foreign_keys = ON")
        _local.conn.execute("PRAGMA journal_mode = WAL")
        _local.conn.execute("PRAGMA synchronous = NORMAL")
        _local.conn.execute("PRAGMA cache_size = -8000")  # 8 MB page cache
        _local.conn.execute("PRAGMA temp_store = MEMORY")
    return _local.conn


@contextmanager
def get_db(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager that yields a thread-local SQLite connection and
    automatically commits on success or rolls back on any exception.

    Args:
        db_path: Absolute path to the SQLite database file.

    Yields:
        sqlite3.Connection: Active database connection.

    Raises:
        sqlite3.DatabaseError: Propagated after rollback on DB errors.
        Exception: Any other exception is re-raised after rollback.

    Examples:
        >>> with get_db(Path("/app/data/lms.db")) as conn:
        ...     conn.execute("INSERT INTO users VALUES (?, ?, ?)", (...))
    """
    conn = _get_raw_connection(db_path)
    try:
        yield conn
        conn.commit()
    except sqlite3.DatabaseError as exc:
        conn.rollback()
        logger.error("Database error — rolled back transaction: %s", exc, exc_info=True)
        raise
    except Exception as exc:
        conn.rollback()
        logger.error("Unexpected error — rolled back transaction: %s", exc, exc_info=True)
        raise


_SCHEMA_SQL = """
-- ── Users ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    first_name  TEXT    NOT NULL,
    username    TEXT,
    joined_at   TEXT    DEFAULT (datetime('now'))
);

-- ── Owners ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS owners (
    user_id     INTEGER PRIMARY KEY,
    added_by    INTEGER,
    added_at    TEXT DEFAULT (datetime('now'))
);

-- ── Admins ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admins (
    user_id     INTEGER PRIMARY KEY
);

-- ── Mandatory subscription channels ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS channels (
    channel_username TEXT PRIMARY KEY,
    channel_title    TEXT,
    invite_link      TEXT
);

-- ── Category tree ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id   INTEGER DEFAULT NULL,
    name        TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories(parent_id, sort_order);

-- ── Contents ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id  INTEGER NOT NULL,
    content_type TEXT    NOT NULL CHECK(content_type IN ('text','photo','video','document','link')),
    content_data TEXT    NOT NULL,
    name         TEXT    NOT NULL,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_contents_category ON contents(category_id, sort_order);

-- ── Content groups ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS content_groups (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id  INTEGER NOT NULL,
    name         TEXT    NOT NULL,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_groups_category ON content_groups(category_id, sort_order);

-- ── Group items ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS group_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id     INTEGER NOT NULL,
    content_type TEXT    NOT NULL CHECK(content_type IN ('photo','video','document','text')),
    content_data TEXT    NOT NULL,
    caption      TEXT    DEFAULT '',
    sort_order   INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (group_id) REFERENCES content_groups(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_group_items_group ON group_items(group_id, sort_order);

-- ── VIP users ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vip_users (
    user_id     INTEGER PRIMARY KEY,
    added_by    INTEGER,
    added_at    TEXT DEFAULT (datetime('now'))
);

-- ── User points ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_points (
    user_id     INTEGER PRIMARY KEY,
    points      INTEGER DEFAULT 0
);
"""


def init_db(db_path: Path) -> None:
    """
    Initialize the database schema (idempotent — safe to call on every startup).

    Creates all tables and indexes if they do not already exist.
    Also ensures the database directory exists.

    Args:
        db_path: Absolute path to the SQLite database file.

    Raises:
        OSError: If the directory cannot be created.
        sqlite3.DatabaseError: If schema execution fails.

    Examples:
        >>> init_db(Path("/app/data/lms.db"))
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_db(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
    logger.info("Database schema initialized at %s", db_path)

"""
╔══════════════════════════════════════════════════════════════════════╗
║  database/repositories.py — Repository Pattern                       ║
║  كل منطق قاعدة البيانات مُغلَّف في كلاسات خاصة قابلة للاختبار      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, List, Optional

from core.models import (
    Category, Channel, Content, ContentGroup, ContentType,
    GroupItem, User, UserPoints, VipUser,
)
from database.connection import get_db

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Abstract Base Repository
# ─────────────────────────────────────────────────────────────────────────────

class BaseRepository(ABC):
    """
    Abstract base for all repositories.

    Provides a shared ``_db`` context manager so subclasses never
    call ``get_db`` directly — making the DB path injectable and the
    repository fully testable with an in-memory SQLite database.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    @contextmanager
    def _db(self) -> Generator:
        with get_db(self._db_path) as conn:
            yield conn


# ─────────────────────────────────────────────────────────────────────────────
# UserRepository
# ─────────────────────────────────────────────────────────────────────────────

class UserRepository(BaseRepository):
    """CRUD operations for the ``users`` table."""

    def upsert(self, user_id: int, first_name: str, username: Optional[str]) -> None:
        """
        Insert or replace a user record (upsert semantics).

        Args:
            user_id: Telegram user ID.
            first_name: User's first name.
            username: Telegram username (may be None).
        """
        with self._db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO users (user_id, first_name, username) VALUES (?, ?, ?)",
                (user_id, first_name, username),
            )
        logger.debug("Upserted user %d (%s)", user_id, first_name)

    def get_all_ids(self) -> List[int]:
        """Return all registered user IDs."""
        with self._db() as conn:
            rows = conn.execute("SELECT user_id FROM users").fetchall()
        return [r["user_id"] for r in rows]

    def count(self) -> int:
        """Return total number of registered users."""
        with self._db() as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


# ─────────────────────────────────────────────────────────────────────────────
# OwnerRepository
# ─────────────────────────────────────────────────────────────────────────────

class OwnerRepository(BaseRepository):
    """Manages dynamic (DB-stored) owner records."""

    def exists(self, user_id: int) -> bool:
        with self._db() as conn:
            return conn.execute(
                "SELECT 1 FROM owners WHERE user_id = ?", (user_id,)
            ).fetchone() is not None

    def add(self, user_id: int, added_by: int) -> None:
        with self._db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO owners (user_id, added_by) VALUES (?, ?)",
                (user_id, added_by),
            )

    def remove(self, user_id: int) -> None:
        with self._db() as conn:
            conn.execute("DELETE FROM owners WHERE user_id = ?", (user_id,))

    def get_all(self) -> List[dict]:
        with self._db() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT user_id, added_by, added_at FROM owners"
            ).fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# AdminRepository
# ─────────────────────────────────────────────────────────────────────────────

class AdminRepository(BaseRepository):
    """Manages admin user records."""

    def exists(self, user_id: int) -> bool:
        with self._db() as conn:
            return conn.execute(
                "SELECT 1 FROM admins WHERE user_id = ?", (user_id,)
            ).fetchone() is not None

    def add(self, user_id: int) -> None:
        with self._db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,)
            )

    def count(self) -> int:
        with self._db() as conn:
            return conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]


# ─────────────────────────────────────────────────────────────────────────────
# VipRepository
# ─────────────────────────────────────────────────────────────────────────────

class VipRepository(BaseRepository):
    """Manages VIP membership records."""

    def exists(self, user_id: int) -> bool:
        with self._db() as conn:
            return conn.execute(
                "SELECT 1 FROM vip_users WHERE user_id = ?", (user_id,)
            ).fetchone() is not None

    def add(self, user_id: int, added_by: int) -> None:
        with self._db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO vip_users (user_id, added_by) VALUES (?, ?)",
                (user_id, added_by),
            )

    def remove(self, user_id: int) -> None:
        with self._db() as conn:
            conn.execute("DELETE FROM vip_users WHERE user_id = ?", (user_id,))

    def count(self) -> int:
        with self._db() as conn:
            return conn.execute("SELECT COUNT(*) FROM vip_users").fetchone()[0]


# ─────────────────────────────────────────────────────────────────────────────
# PointsRepository
# ─────────────────────────────────────────────────────────────────────────────

class PointsRepository(BaseRepository):
    """Manages user gamification points."""

    def get(self, user_id: int) -> int:
        with self._db() as conn:
            row = conn.execute(
                "SELECT points FROM user_points WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row["points"] if row else 0

    def is_first_visit(self, user_id: int) -> bool:
        """Return True if no points record exists for this user (first login)."""
        with self._db() as conn:
            return conn.execute(
                "SELECT 1 FROM user_points WHERE user_id = ?", (user_id,)
            ).fetchone() is None

    def add(self, user_id: int, points: int) -> int:
        """
        Add points to a user's balance (upsert semantics).

        Args:
            user_id: Target user.
            points: Number of points to add (may be negative for deduction).

        Returns:
            int: New total balance.
        """
        with self._db() as conn:
            conn.execute(
                """
                INSERT INTO user_points (user_id, points) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET points = points + ?
                """,
                (user_id, points, points),
            )
            return conn.execute(
                "SELECT points FROM user_points WHERE user_id = ?", (user_id,)
            ).fetchone()["points"]


# ─────────────────────────────────────────────────────────────────────────────
# ChannelRepository
# ─────────────────────────────────────────────────────────────────────────────

class ChannelRepository(BaseRepository):
    """CRUD for mandatory-subscription channels."""

    def get_all(self) -> List[Channel]:
        with self._db() as conn:
            rows = conn.execute("SELECT * FROM channels").fetchall()
        return [Channel(**dict(r)) for r in rows]

    def add(self, username: str, title: str, invite_link: str) -> None:
        with self._db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO channels (channel_username, channel_title, invite_link) VALUES (?, ?, ?)",
                (username, title, invite_link),
            )

    def remove(self, username: str) -> None:
        with self._db() as conn:
            conn.execute(
                "DELETE FROM channels WHERE channel_username = ?", (username,)
            )

    def count(self) -> int:
        with self._db() as conn:
            return conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]


# ─────────────────────────────────────────────────────────────────────────────
# CategoryRepository
# ─────────────────────────────────────────────────────────────────────────────

class CategoryRepository(BaseRepository):
    """Hierarchical category tree operations."""

    def _row_to_category(self, row) -> Category:
        return Category(
            id=row["id"],
            name=row["name"],
            parent_id=row["parent_id"],
            sort_order=row["sort_order"],
        )

    def get_children(self, parent_id: Optional[int]) -> List[Category]:
        """
        Fetch direct children of a category node.

        Args:
            parent_id: Parent category ID, or None for root categories.

        Returns:
            List of Category objects ordered by sort_order, id.
        """
        with self._db() as conn:
            if parent_id is None:
                rows = conn.execute(
                    "SELECT * FROM categories WHERE parent_id IS NULL ORDER BY sort_order, id"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM categories WHERE parent_id = ? ORDER BY sort_order, id",
                    (parent_id,),
                ).fetchall()
        return [self._row_to_category(r) for r in rows]

    def get_by_id(self, cat_id: int) -> Optional[Category]:
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM categories WHERE id = ?", (cat_id,)
            ).fetchone()
        return self._row_to_category(row) if row else None

    def add(self, parent_id: Optional[int], name: str) -> int:
        """
        Insert a new category.

        Returns:
            int: The new category's primary key.
        """
        with self._db() as conn:
            conn.execute(
                "INSERT INTO categories (parent_id, name, sort_order) VALUES (?, ?, 0)",
                (parent_id, name),
            )
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def update_name(self, cat_id: int, name: str) -> None:
        with self._db() as conn:
            conn.execute(
                "UPDATE categories SET name = ? WHERE id = ?", (name, cat_id)
            )

    def delete(self, cat_id: int) -> None:
        with self._db() as conn:
            conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))

    def shift_order(self, item_id: int, direction: int) -> None:
        """Shift sort_order by ``direction`` (+1 or -1)."""
        with self._db() as conn:
            row = conn.execute(
                "SELECT sort_order FROM categories WHERE id = ?", (item_id,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE categories SET sort_order = ? WHERE id = ?",
                    (max(0, row["sort_order"] + direction), item_id),
                )

    def count(self) -> int:
        with self._db() as conn:
            return conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]


# ─────────────────────────────────────────────────────────────────────────────
# ContentRepository
# ─────────────────────────────────────────────────────────────────────────────

class ContentRepository(BaseRepository):
    """CRUD for content items within categories."""

    def _row_to_content(self, row) -> Content:
        return Content(
            id=row["id"],
            category_id=row["category_id"],
            content_type=ContentType(row["content_type"]),
            content_data=row["content_data"],
            name=row["name"],
            sort_order=row["sort_order"],
        )

    def get_by_category(self, category_id: int) -> List[Content]:
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM contents WHERE category_id = ? ORDER BY sort_order, id",
                (category_id,),
            ).fetchall()
        return [self._row_to_content(r) for r in rows]

    def get_by_id(self, content_id: int) -> Optional[Content]:
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM contents WHERE id = ?", (content_id,)
            ).fetchone()
        return self._row_to_content(row) if row else None

    def add(self, category_id: int, content_type: ContentType, content_data: str, name: str) -> int:
        with self._db() as conn:
            conn.execute(
                "INSERT INTO contents (category_id, content_type, content_data, name, sort_order) VALUES (?,?,?,?,0)",
                (category_id, content_type.value, content_data, name),
            )
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def update_name(self, content_id: int, name: str) -> None:
        with self._db() as conn:
            conn.execute(
                "UPDATE contents SET name = ? WHERE id = ?", (name, content_id)
            )

    def update_data(self, content_id: int, content_data: str, content_type: ContentType) -> None:
        with self._db() as conn:
            conn.execute(
                "UPDATE contents SET content_data = ?, content_type = ? WHERE id = ?",
                (content_data, content_type.value, content_id),
            )

    def delete(self, content_id: int) -> None:
        with self._db() as conn:
            conn.execute("DELETE FROM contents WHERE id = ?", (content_id,))

    def count(self) -> int:
        with self._db() as conn:
            return conn.execute("SELECT COUNT(*) FROM contents").fetchone()[0]


# ─────────────────────────────────────────────────────────────────────────────
# ContentGroupRepository
# ─────────────────────────────────────────────────────────────────────────────

class ContentGroupRepository(BaseRepository):
    """Manages media groups and their items."""

    def get_by_category(self, category_id: int) -> List[ContentGroup]:
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM content_groups WHERE category_id = ? ORDER BY sort_order, id",
                (category_id,),
            ).fetchall()
        return [ContentGroup(**dict(r)) for r in rows]

    def get_by_id(self, group_id: int) -> Optional[ContentGroup]:
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM content_groups WHERE id = ?", (group_id,)
            ).fetchone()
        return ContentGroup(**dict(row)) if row else None

    def add(self, category_id: int, name: str) -> int:
        with self._db() as conn:
            conn.execute(
                "INSERT INTO content_groups (category_id, name, sort_order) VALUES (?, ?, 0)",
                (category_id, name),
            )
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def delete(self, group_id: int) -> None:
        with self._db() as conn:
            conn.execute("DELETE FROM content_groups WHERE id = ?", (group_id,))

    def count(self) -> int:
        with self._db() as conn:
            return conn.execute("SELECT COUNT(*) FROM content_groups").fetchone()[0]

    # ── Group Items ────────────────────────────────────────────────────────

    def get_items(self, group_id: int) -> List[GroupItem]:
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM group_items WHERE group_id = ? ORDER BY sort_order, id",
                (group_id,),
            ).fetchall()
        return [
            GroupItem(
                id=r["id"],
                group_id=r["group_id"],
                content_type=ContentType(r["content_type"]),
                content_data=r["content_data"],
                caption=r["caption"] or "",
                sort_order=r["sort_order"],
            )
            for r in rows
        ]

    def add_item(
        self,
        group_id: int,
        content_type: ContentType,
        content_data: str,
        caption: str = "",
    ) -> int:
        with self._db() as conn:
            conn.execute(
                "INSERT INTO group_items (group_id, content_type, content_data, caption, sort_order) VALUES (?,?,?,?,0)",
                (group_id, content_type.value, content_data, caption),
            )
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def count_items(self, group_id: int) -> int:
        with self._db() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM group_items WHERE group_id = ?", (group_id,)
            ).fetchone()[0]

    def count_all_items(self) -> int:
        with self._db() as conn:
            return conn.execute("SELECT COUNT(*) FROM group_items").fetchone()[0]

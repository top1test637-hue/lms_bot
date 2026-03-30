"""
╔══════════════════════════════════════════════════════════════════════╗
║  core/models.py — نماذج المجال (Domain Models / DTOs)               ║
║  كائنات بيانات نقية، بدون منطق، سهلة الاختبار والتسلسل             ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ContentType(str, Enum):
    """Enumeration for all supported content types inside a category."""
    TEXT     = "text"
    PHOTO    = "photo"
    VIDEO    = "video"
    DOCUMENT = "document"
    LINK     = "link"

    @property
    def emoji(self) -> str:
        """Return the display emoji for this content type."""
        return {
            ContentType.TEXT:     "📝",
            ContentType.PHOTO:    "🖼️",
            ContentType.VIDEO:    "🎥",
            ContentType.DOCUMENT: "📄",
            ContentType.LINK:     "🔗",
        }[self]

    @property
    def arabic_name(self) -> str:
        """Return the Arabic label for this content type."""
        return {
            ContentType.TEXT:     "نص",
            ContentType.PHOTO:    "صورة",
            ContentType.VIDEO:    "فيديو",
            ContentType.DOCUMENT: "ملف",
            ContentType.LINK:     "رابط",
        }[self]


@dataclass
class User:
    """Represents a registered Telegram user."""
    user_id:    int
    first_name: str
    username:   Optional[str] = None
    joined_at:  Optional[str] = None


@dataclass
class Category:
    """Hierarchical content category (tree node)."""
    id:         int
    name:       str
    parent_id:  Optional[int] = None
    sort_order: int = 0


@dataclass
class Content:
    """
    A single content item inside a category.

    Attributes:
        id: Primary key.
        category_id: Parent category.
        content_type: One of ContentType enum values.
        content_data: File ID, URL, or raw text depending on type.
        name: Human-readable display name.
        sort_order: Ordering index within the category.
    """
    id:           int
    category_id:  int
    content_type: ContentType
    content_data: str
    name:         str
    sort_order:   int = 0


@dataclass
class ContentGroup:
    """A named collection of media items (displayed as media group)."""
    id:          int
    category_id: int
    name:        str
    sort_order:  int = 0


@dataclass
class GroupItem:
    """Single item inside a ContentGroup."""
    id:           int
    group_id:     int
    content_type: ContentType
    content_data: str
    caption:      str = ""
    sort_order:   int = 0


@dataclass
class Channel:
    """Mandatory subscription channel."""
    channel_username: str   # stored as numeric string for private groups
    channel_title:    str
    invite_link:      str


@dataclass
class VipUser:
    """VIP-tier user record."""
    user_id:  int
    added_by: Optional[int] = None
    added_at: Optional[str] = None


@dataclass
class UserPoints:
    """Gamification points record."""
    user_id: int
    points:  int = 0

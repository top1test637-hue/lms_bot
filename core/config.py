"""
╔══════════════════════════════════════════════════════════════════════╗
║  core/config.py — مركز إعدادات النظام                               ║
║  مسؤول عن تحميل وتحقق جميع الإعدادات من البيئة أو .env             ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import FrozenSet

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class BotConfig:
    """
    Immutable configuration object — loaded once at startup.

    Attributes:
        bot_token: Telegram Bot API token.
        owner_ids: Frozen set of owner Telegram user IDs (env + hardcoded).
        db_path: Absolute path to the SQLite database file.
        gift_points: Points awarded to first-time users.
        vip_category_id: Category ID that serves as the VIP section root.
        free_gift_category_id: Category ID for the free gift section.
        page_size: Number of items per paginated category page.
        group_page_size: Number of items per media-group page.
        log_level: Python logging level string (e.g. "INFO", "DEBUG").
        log_dir: Directory for log files (rotated daily).
        rate_limit_delay: Seconds to sleep between broadcast messages.

    Examples:
        >>> cfg = get_config()
        >>> assert cfg.bot_token  # must not be empty
    """

    bot_token: str
    owner_ids: FrozenSet[int]
    db_path: Path
    gift_points: int
    vip_category_id: int
    free_gift_category_id: int
    page_size: int
    group_page_size: int
    log_level: str
    log_dir: Path
    rate_limit_delay: float

    def __post_init__(self):
        if not self.bot_token or self.bot_token == "YOUR_BOT_TOKEN_HERE":
            raise ValueError("BOT_TOKEN is not set. Please configure your .env file.")
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_config() -> BotConfig:
    """
    Load and cache the application config (singleton pattern via lru_cache).

    Returns:
        BotConfig: Validated, frozen configuration instance.

    Raises:
        ValueError: If critical settings (BOT_TOKEN) are missing.
    """
    raw_owners = os.getenv("OWNER_IDS", "")
    owner_ids = frozenset(
        int(x.strip())
        for x in raw_owners.split(",")
        if x.strip().isdigit()
    )

    return BotConfig(
        bot_token=os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE"),
        owner_ids=owner_ids,
        db_path=Path(os.getenv("DB_PATH", "/app/data/lms_school.db")),
        gift_points=int(os.getenv("GIFT_POINTS", "3")),
        vip_category_id=int(os.getenv("VIP_CATEGORY_ID", "0")),
        free_gift_category_id=int(os.getenv("FREE_GIFT_CATEGORY_ID", "0")),
        page_size=int(os.getenv("PAGE_SIZE", "5")),
        group_page_size=int(os.getenv("GROUP_PAGE_SIZE", "5")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_dir=Path(os.getenv("LOG_DIR", "/app/logs")),
        rate_limit_delay=float(os.getenv("RATE_LIMIT_DELAY", "0.05")),
    )

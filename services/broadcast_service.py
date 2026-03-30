"""
╔══════════════════════════════════════════════════════════════════════╗
║  services/broadcast_service.py — خدمة الإرسال الجماعي              ║
║  Async bulk-send with progress reporting and rate limiting           ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import List

from telegram import Bot
from telegram.error import Forbidden, TelegramError

from database.repositories import UserRepository

logger = logging.getLogger(__name__)


@dataclass
class BroadcastResult:
    """Summary of a broadcast operation."""
    total:   int
    success: int
    failed:  int

    @property
    def success_rate(self) -> float:
        return (self.success / self.total * 100) if self.total else 0.0


class BroadcastService:
    """
    Delivers a message to all registered users using copy_message.

    Handles Forbidden errors (users who blocked the bot) gracefully and
    throttles delivery to avoid Telegram flood limits.

    Args:
        user_repo: Repository supplying all user IDs.
        rate_limit_delay: Seconds between each send (default 0.05 = ~20/s).
    """

    def __init__(self, user_repo: UserRepository, rate_limit_delay: float = 0.05) -> None:
        self._user_repo = user_repo
        self._delay     = rate_limit_delay

    async def send_to_all(
        self,
        bot: Bot,
        from_chat_id: int,
        message_id: int,
    ) -> BroadcastResult:
        """
        Broadcast a message to every registered user.

        Args:
            bot: Telegram Bot instance.
            from_chat_id: Source chat containing the message.
            message_id: Message ID to copy.

        Returns:
            BroadcastResult with success/failure counts.
        """
        user_ids = self._user_repo.get_all_ids()
        total    = len(user_ids)
        success  = 0
        failed   = 0

        logger.info("Starting broadcast to %d users", total)

        for uid in user_ids:
            try:
                await bot.copy_message(
                    chat_id=uid, from_chat_id=from_chat_id, message_id=message_id
                )
                success += 1
            except Forbidden:
                # User blocked the bot — expected, not an error
                failed += 1
            except TelegramError as exc:
                logger.warning("Broadcast failed for user %d: %s", uid, exc)
                failed += 1

            await asyncio.sleep(self._delay)

        result = BroadcastResult(total=total, success=success, failed=failed)
        logger.info(
            "Broadcast complete — success: %d, failed: %d (%.1f%%)",
            success, failed, result.success_rate,
        )
        return result

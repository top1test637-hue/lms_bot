"""
╔══════════════════════════════════════════════════════════════════════╗
║  services/subscription_service.py — خدمة الاشتراكات الإجبارية      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError

from core.models import Channel
from database.repositories import ChannelRepository

logger = logging.getLogger(__name__)


class SubscriptionService:
    """
    Manages mandatory channel subscriptions and builds the subscription
    verification keyboard.

    Args:
        channel_repo: Repository for channel records.

    Examples:
        >>> svc = SubscriptionService(channel_repo)
        >>> ok, missing = await svc.check(bot, user_id=123)
    """

    def __init__(self, channel_repo: ChannelRepository) -> None:
        self._channel_repo = channel_repo

    async def check(self, bot: Bot, user_id: int) -> Tuple[bool, List[Channel]]:
        """
        Verify that a user is subscribed to all mandatory channels.

        Args:
            bot: Telegram Bot instance.
            user_id: ID of the user to verify.

        Returns:
            Tuple of (all_ok: bool, missing_channels: List[Channel]).
            If all_ok is True, missing_channels is an empty list.
        """
        channels = self._channel_repo.get_all()
        if not channels:
            return True, []

        missing: List[Channel] = []
        for ch in channels:
            try:
                raw_id = ch.channel_username
                target = int(raw_id) if raw_id.lstrip("-").isdigit() else f"@{raw_id.lstrip('@')}"
                member = await bot.get_chat_member(chat_id=target, user_id=user_id)
                if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
                    missing.append(ch)
            except TelegramError as exc:
                logger.warning("Could not check subscription for channel %s: %s", ch.channel_username, exc)
                missing.append(ch)

        return len(missing) == 0, missing

    @staticmethod
    def build_keyboard(missing: List[Channel]) -> InlineKeyboardMarkup:
        """
        Build the inline keyboard showing subscription links for missing channels.

        Args:
            missing: Channels the user has not subscribed to.

        Returns:
            InlineKeyboardMarkup with one row per missing channel
            plus a verification button.
        """
        buttons = []
        for ch in missing:
            link = ch.invite_link
            if not link or link == "غير_متوفر":
                link = f"https://t.me/{ch.channel_username.lstrip('@')}"
            title = ch.channel_title or "قناة الاشتراك"
            buttons.append([InlineKeyboardButton(f"📢 {title}", url=link)])

        buttons.append([InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_sub")])
        return InlineKeyboardMarkup(buttons)

"""
╔══════════════════════════════════════════════════════════════════════╗
║  services/content_service.py — خدمة تسليم المحتوى                  ║
║  يتولى: إرسال المحتوى الفردي + صفحات مجموعات الوسائط               ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from telegram import (
    Bot, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaDocument, InputMediaPhoto, InputMediaVideo,
    ReplyMarkup,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

from core.models import Content, ContentGroup, ContentType, GroupItem
from database.repositories import ContentGroupRepository

logger = logging.getLogger(__name__)


class ContentDeliveryService:
    """
    Responsible for delivering content items and media groups to users.

    Separates *what* to send from *where* the data comes from.

    Args:
        group_repo: Repository for content groups and their items.
        group_page_size: Number of items per media-group page.
    """

    def __init__(self, group_repo: ContentGroupRepository, group_page_size: int = 5) -> None:
        self._group_repo = group_repo
        self._page_size  = group_page_size

    async def send_content(
        self,
        bot: Bot,
        chat_id: int,
        content: Content,
        reply_markup: Optional[ReplyMarkup] = None,
    ) -> None:
        """
        Send a single content item to a chat.

        Handles all content types including Telegram link forwarding.

        Args:
            bot: Telegram Bot instance.
            chat_id: Destination chat ID.
            content: Content item to send.
            reply_markup: Optional inline keyboard to attach.

        Raises:
            TelegramError: If the send operation fails.
        """
        ctype, cdata, name = content.content_type, content.content_data, content.name

        try:
            match ctype:
                case ContentType.TEXT:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"<b>{name}</b>\n\n{cdata}",
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup,
                    )

                case ContentType.PHOTO:
                    await bot.send_photo(
                        chat_id=chat_id, photo=cdata,
                        caption=f"<b>{name}</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup,
                    )

                case ContentType.VIDEO:
                    await bot.send_video(
                        chat_id=chat_id, video=cdata,
                        caption=f"<b>{name}</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup,
                    )

                case ContentType.DOCUMENT:
                    await bot.send_document(
                        chat_id=chat_id, document=cdata,
                        caption=f"<b>{name}</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup,
                    )

                case ContentType.LINK:
                    await self._send_link(bot, chat_id, cdata, name, reply_markup)

                case _:
                    logger.error("Unknown content type: %s", ctype)
                    await bot.send_message(chat_id=chat_id, text=f"❓ نوع غير معروف: {ctype}")

        except TelegramError as exc:
            logger.error("Failed to send content %d to %d: %s", content.id, chat_id, exc)
            raise

    async def _send_link(
        self,
        bot: Bot,
        chat_id: int,
        url: str,
        name: str,
        reply_markup: Optional[ReplyMarkup],
    ) -> None:
        """
        Attempt to forward a Telegram message via copy_message,
        falling back to a clickable link button on failure.
        """
        if "t.me/c/" in url or ("t.me/" in url and url.count("/") >= 4):
            try:
                parts = url.rstrip("/").split("/")
                msg_id = int(parts[-1])
                channel_id = (
                    int(f"-100{parts[-2]}") if "t.me/c/" in url else f"@{parts[-2]}"
                )
                await bot.copy_message(
                    chat_id=chat_id, from_chat_id=channel_id,
                    message_id=msg_id, reply_markup=reply_markup,
                )
                return
            except (TelegramError, ValueError) as exc:
                logger.warning("copy_message failed for %s, falling back to link: %s", url, exc)

        await bot.send_message(
            chat_id=chat_id,
            text=f"<b>{name}</b>\n\n🔗 <a href='{url}'>افتح الرابط</a>",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )

    async def send_group_page(
        self,
        bot: Bot,
        chat_id: int,
        group_id: int,
        page: int,
        is_admin: bool = False,
    ) -> None:
        """
        Send one page of a media group to a chat.

        Media items (photos/videos) are batched into Telegram media groups.
        Documents and text items are sent individually.
        A navigation control message is always appended.

        Args:
            bot: Telegram Bot instance.
            chat_id: Destination chat.
            group_id: Content group ID.
            page: Zero-indexed page number.
            is_admin: If True, admin control buttons are added.
        """
        group = self._group_repo.get_by_id(group_id)
        items = self._group_repo.get_items(group_id)

        if not items:
            await bot.send_message(chat_id=chat_id, text="📭 هذه المجموعة فارغة.")
            return

        total       = len(items)
        total_pages = max(1, (total + self._page_size - 1) // self._page_size)
        page        = max(0, min(page, total_pages - 1))
        start       = page * self._page_size
        page_items  = items[start : start + self._page_size]
        group_name  = group.name if group else "مجموعة"

        media_items = [i for i in page_items if i.content_type in (ContentType.PHOTO, ContentType.VIDEO)]
        doc_items   = [i for i in page_items if i.content_type == ContentType.DOCUMENT]
        text_items  = [i for i in page_items if i.content_type == ContentType.TEXT]

        # ── Send photos + videos as media group ──────────────────────────
        if media_items:
            await self._send_media_group(bot, chat_id, media_items, group_name, page, total_pages)

        # ── Send text messages ────────────────────────────────────────────
        for item in text_items:
            await bot.send_message(
                chat_id=chat_id, text=item.content_data, parse_mode=ParseMode.HTML
            )
            await asyncio.sleep(0.1)

        # ── Send documents individually ───────────────────────────────────
        for item in doc_items:
            await bot.send_document(
                chat_id=chat_id, document=item.content_data,
                caption=item.caption or None,
                parse_mode=ParseMode.HTML if item.caption else None,
            )
            await asyncio.sleep(0.1)

        # ── Navigation control message ────────────────────────────────────
        await self._send_group_nav(bot, chat_id, group_id, page, total_pages, total, group_name, is_admin, group)

    async def _send_media_group(
        self,
        bot: Bot,
        chat_id: int,
        items: List[GroupItem],
        group_name: str,
        page: int,
        total_pages: int,
    ) -> None:
        """Batch up to 10 media items into a Telegram media group."""
        media_list = []
        for idx, item in enumerate(items):
            cap = item.caption or ""
            if idx == 0:
                cap = f"<b>{group_name}</b>\n📄 {page + 1}/{total_pages}\n\n{cap}".strip()

            if item.content_type == ContentType.PHOTO:
                media_list.append(InputMediaPhoto(
                    media=item.content_data,
                    caption=cap or None,
                    parse_mode=ParseMode.HTML if cap else None,
                ))
            else:
                media_list.append(InputMediaVideo(
                    media=item.content_data,
                    caption=cap or None,
                    parse_mode=ParseMode.HTML if cap else None,
                ))

        for batch_start in range(0, len(media_list), 10):
            await bot.send_media_group(
                chat_id=chat_id,
                media=media_list[batch_start : batch_start + 10],
            )
            await asyncio.sleep(0.3)

    async def _send_group_nav(
        self, bot, chat_id, group_id, page, total_pages, total, group_name, is_admin, group
    ) -> None:
        """Build and send the navigation keyboard for a media group page."""
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("◀️ السابق", callback_data=f"grp_{group_id}_{page - 1}"))
        nav_row.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}  ({total} ملف)", callback_data="pg_info"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("التالي ▶️", callback_data=f"grp_{group_id}_{page + 1}"))

        nav_buttons = [nav_row]

        if is_admin:
            cat_id = group.category_id if group else 0
            nav_buttons.append([
                InlineKeyboardButton("🗑️ حذف المجموعة", callback_data=f"a_dg_{group_id}"),
                InlineKeyboardButton("➕ إضافة ملفات",   callback_data=f"a_ag_{group_id}"),
            ])
            nav_buttons.append([
                InlineKeyboardButton("🔙 رجوع للفئة", callback_data=f"nav_{cat_id}")
            ])

        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"📦 <b>{group_name}</b>\n"
                f"الصفحة <b>{page+1}</b> من <b>{total_pages}</b> | إجمالي <b>{total}</b> ملف"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(nav_buttons),
        )

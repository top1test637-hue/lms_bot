"""
╔══════════════════════════════════════════════════════════════════════╗
║  utils/message_helpers.py — مساعدات الرسائل                         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

from typing import Optional, Tuple

from telegram import Message

from core.models import ContentType


def extract_content_from_message(
    msg: Message,
) -> Tuple[Optional[ContentType], Optional[str]]:
    """
    Detect the content type and file ID / text from a Telegram message.

    Args:
        msg: Incoming Telegram Message object.

    Returns:
        Tuple of (ContentType | None, data | None).
        Returns (None, None) if no recognizable content is found.

    Examples:
        >>> ctype, cdata = extract_content_from_message(msg)
        >>> if ctype:
        ...     db.add_content(cat_id, ctype, cdata, name)
    """
    if msg.photo:
        return ContentType.PHOTO, msg.photo[-1].file_id
    if msg.video:
        return ContentType.VIDEO, msg.video.file_id
    if msg.document:
        return ContentType.DOCUMENT, msg.document.file_id
    if msg.text:
        text = msg.text.strip()
        if text.startswith("http") or "t.me/" in text:
            return ContentType.LINK, text
        return ContentType.TEXT, text
    return None, None

"""
╔══════════════════════════════════════════════════════════════════════╗
║  utils/keyboards.py — بناة لوحات المفاتيح (Keyboard Builders)       ║
║  مسؤول فقط عن بناء الـ UI — لا منطق أعمال هنا                     ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove,
)

from core.models import Category, Content, ContentGroup, ContentType
from database.repositories import (
    CategoryRepository, ContentGroupRepository, ContentRepository,
)


def truncate(text: str, max_len: int = 28) -> str:
    """Truncate text with ellipsis if it exceeds max_len characters."""
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def build_admin_reply_keyboard(user_id: int, is_owner: bool = False) -> ReplyKeyboardMarkup:
    """
    Build the persistent admin reply keyboard.

    Args:
        user_id: Requesting user (used to conditionally show owner panel).
        is_owner: If True, show the owners management button.

    Returns:
        ReplyKeyboardMarkup for admin users.
    """
    keyboard = [
        ["📂 إدارة المحتوى",        "📢 إدارة القنوات"],
        ["📣 إرسال رسالة جماعية",  "👤 إضافة مشرف"],
        ["⭐ إدارة VIP",            "📊 إحصائيات"],
        ["💾 نسخ احتياطي",          "👁️ وضع الطالب"],
        ["🚪 خروج من لوحة التحكم"],
    ]
    if is_owner:
        keyboard.insert(2, ["👑 إدارة الأونرز"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def build_student_mode_keyboard() -> ReplyKeyboardMarkup:
    """Reply keyboard shown when an admin enters student preview mode."""
    return ReplyKeyboardMarkup([["🔙 العودة إلى لوحة التحكم"]], resize_keyboard=True)


def build_category_page_keyboard(
    parent_id: Optional[int],
    page: int,
    is_admin: bool,
    path_stack: List[int],
    cat_repo: CategoryRepository,
    cont_repo: ContentRepository,
    group_repo: ContentGroupRepository,
    page_size: int = 5,
) -> Tuple[InlineKeyboardMarkup, int, int]:
    """
    Build a paginated inline keyboard for a category node.

    Mixes subcategories, content items, and content groups on the
    same paginated list, ordered by sort_order.

    Args:
        parent_id: Category ID (None or 0 for root).
        page: Requested zero-indexed page number.
        is_admin: Whether to render admin action buttons.
        path_stack: Navigation breadcrumb stack for the back button.
        cat_repo: Category repository.
        cont_repo: Content repository.
        group_repo: ContentGroup repository.
        page_size: Items per page.

    Returns:
        Tuple of (InlineKeyboardMarkup, actual_page, total_pages).
    """
    effective_parent = None if (parent_id is None or parent_id == 0) else parent_id

    subcats  = cat_repo.get_children(effective_parent)
    contents = cont_repo.get_by_category(parent_id or 0)
    groups   = group_repo.get_by_category(parent_id or 0)

    all_items = (
        [("cat",  c) for c in subcats] +
        [("cont", c) for c in contents] +
        [("grp",  g) for g in groups]
    )
    total_items = len(all_items)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page        = max(0, min(page, total_pages - 1))
    page_items  = all_items[page * page_size : (page + 1) * page_size]

    buttons: List[List[InlineKeyboardButton]] = []

    for itype, item in page_items:
        if itype == "cat":
            buttons.append([InlineKeyboardButton(
                f"📁 {truncate(item.name)}", callback_data=f"nav_{item.id}"
            )])
        elif itype == "grp":
            count = group_repo.count_items(item.id)
            buttons.append([InlineKeyboardButton(
                f"📦 {truncate(item.name)}  ({count} ملف)",
                callback_data=f"grp_{item.id}_0",
            )])
        else:
            emoji = item.content_type.emoji
            buttons.append([InlineKeyboardButton(
                f"{emoji} {truncate(item.name)}", callback_data=f"cnt_{item.id}"
            )])

    # Pagination bar
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("◀️ السابق", callback_data=f"pg_{parent_id}_{page - 1}"))
        nav_row.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="pg_info"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("التالي ▶️", callback_data=f"pg_{parent_id}_{page + 1}"))
        buttons.append(nav_row)

    # Admin action buttons
    if is_admin:
        buttons.append([
            InlineKeyboardButton("➕ فئة فرعية",       callback_data=f"a_nc_{parent_id}"),
            InlineKeyboardButton("➕ محتوى",            callback_data=f"a_nx_{parent_id}"),
        ])
        buttons.append([
            InlineKeyboardButton("➕ مجموعة ملفات 📦", callback_data=f"a_ng_{parent_id}"),
        ])
        if parent_id and parent_id != 0:
            buttons.append([
                InlineKeyboardButton("✏️ تعديل الاسم", callback_data=f"a_ec_{parent_id}"),
                InlineKeyboardButton("🗑️ حذف الفئة",   callback_data=f"a_dc_{parent_id}"),
            ])
            buttons.append([InlineKeyboardButton("🔃 إعادة الترتيب", callback_data=f"a_rc_{parent_id}")])

    # Back / home button
    if path_stack:
        buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"back_{path_stack[-1]}")])
    elif parent_id and parent_id != 0:
        buttons.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="back_0")])

    return InlineKeyboardMarkup(buttons), page, total_pages


def build_content_admin_keyboard(content_id: int, category_id: int) -> InlineKeyboardMarkup:
    """
    Build the inline keyboard for admin content actions.

    Args:
        content_id: The content item's primary key.
        category_id: Parent category for the back button.
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ تعديل الاسم", callback_data=f"a_en_{content_id}"),
            InlineKeyboardButton("🔄 تعديل الملف", callback_data=f"a_ed_{content_id}"),
        ],
        [InlineKeyboardButton("🗑️ حذف المحتوى",  callback_data=f"a_dl_{content_id}")],
        [InlineKeyboardButton("🔙 رجوع للفئة",    callback_data=f"nav_{category_id}")],
    ])

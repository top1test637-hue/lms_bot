"""
╔══════════════════════════════════════════════════════════════════════╗
║  handlers/user_handlers.py — معالجات المستخدمين                     ║
║  /start + navigation callbacks + subscription check                 ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import logging
from typing import Optional

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from core.container import Container
from core.models import ContentType
from utils.keyboards import (
    build_admin_reply_keyboard, build_category_page_keyboard,
    build_content_admin_keyboard, build_student_mode_keyboard,
)

logger = logging.getLogger(__name__)


def _is_admin_mode(context: ContextTypes.DEFAULT_TYPE, user_id: int, container: Container) -> bool:
    """Returns True if the user is an admin AND is not in student-preview mode."""
    return (
        container.auth_service.is_admin(user_id)
        and not context.user_data.get("student_test_mode", False)
    )


class UserHandlers:
    """
    Groups all user-facing handlers.

    Args:
        container: Dependency injection container.
    """

    def __init__(self, container: Container) -> None:
        self.c = container

    # ─────────────────────────────────────────────────────────────────────
    # /start
    # ─────────────────────────────────────────────────────────────────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start — registers user, checks subscription, shows main menu."""
        user = update.effective_user
        self.c.user_repo.upsert(user.id, user.first_name, user.username)

        ok, missing = await self.c.subscription_service.check(context.bot, user.id)
        if not ok:
            await update.message.reply_text(
                "🔒 <b>يجب عليك الاشتراك في القنوات التالية للمتابعة:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=self.c.subscription_service.build_keyboard(missing),
            )
            return

        context.user_data.update({"path_stack": [], "current_cat": 0, "current_page": 0})

        if _is_admin_mode(context, user.id, self.c):
            await update.message.reply_text(
                f"👑 <b>مرحباً {user.first_name}!</b>\nلوحة تحكم المشرف جاهزة.",
                parse_mode=ParseMode.HTML,
                reply_markup=build_admin_reply_keyboard(
                    user.id, is_owner=self.c.auth_service.is_owner(user.id)
                ),
            )
        else:
            if self.c.points_repo.is_first_visit(user.id):
                self.c.points_repo.add(user.id, self.c.config.gift_points)
            points = self.c.points_repo.get(user.id)
            await update.message.reply_text(
                f"🔥 <b>أهلاً بك في البوت التقني الأضخم!</b>\n\n"
                f"🎁 لقد حصلت على <b>{points} نقاط</b> هدية في القسم المجاني\n\n"
                f"👇 اختر القسم الذي تريد استكشافه بالأسفل",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardRemove(),
            )
            await self._show_main_menu(update, context, edit=False)

    # ─────────────────────────────────────────────────────────────────────
    # MAIN MENU
    # ─────────────────────────────────────────────────────────────────────

    async def _show_main_menu(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False
    ) -> None:
        user_id = update.effective_user.id
        is_vip  = self.c.auth_service.is_vip(user_id)
        points  = self.c.points_repo.get(user_id)
        admin   = _is_admin_mode(context, user_id, self.c)

        root_cats = self.c.category_repo.get_children(None)
        buttons   = []

        if is_vip:
            buttons.append([InlineKeyboardButton("⭐ قسم الـ VIP (المدفوع) ⭐", callback_data="nav_vip")])
        else:
            buttons.append([InlineKeyboardButton("🔒 قسم الـ VIP (المدفوع)",   callback_data="vip_locked")])

        buttons.append([InlineKeyboardButton(
            f"🎁 القسم المجاني ({points} نقاط هدية)", callback_data="nav_free"
        )])

        for cat in root_cats:
            buttons.append([InlineKeyboardButton(f"📁 {cat.name[:28]}", callback_data=f"nav_{cat.id}")])

        if admin:
            buttons.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="open_admin_panel")])

        msg_text = "🏠 <b>القائمة الرئيسية — اختر قسماً:</b>"
        markup   = InlineKeyboardMarkup(buttons)

        if edit and update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    msg_text, parse_mode=ParseMode.HTML, reply_markup=markup
                )
            except BadRequest:
                pass
        else:
            msg = update.message or (update.callback_query.message if update.callback_query else None)
            if msg:
                await msg.reply_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=markup)

    # ─────────────────────────────────────────────────────────────────────
    # SHOW CATEGORY
    # ─────────────────────────────────────────────────────────────────────

    async def show_category(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        parent_id: Optional[int],
        page: int = 0,
        edit: bool = True,
    ) -> None:
        """
        Render a category page (with pagination).

        Args:
            update: Current update.
            context: Handler context.
            parent_id: Category to render (None / 0 = root).
            page: Page number.
            edit: If True and a callback query exists, edit the existing message.
        """
        user_id    = update.effective_user.id
        admin      = _is_admin_mode(context, user_id, self.c)
        path_stack = context.user_data.get("path_stack", [])
        eff_parent = parent_id if parent_id else 0

        keyboard, cur_page, total_pages = build_category_page_keyboard(
            parent_id=eff_parent,
            page=page,
            is_admin=admin,
            path_stack=path_stack,
            cat_repo=self.c.category_repo,
            cont_repo=self.c.content_repo,
            group_repo=self.c.group_repo,
            page_size=self.c.config.page_size,
        )

        if eff_parent == 0:
            title = "🏠 <b>الرئيسية — اختر فئة:</b>"
        else:
            cat = self.c.category_repo.get_by_id(eff_parent)
            title = f"📂 <b>{cat.name}</b>" if cat else "📂 <b>الفئة</b>"

        total_count = (
            len(self.c.category_repo.get_children(eff_parent if eff_parent else None)) +
            len(self.c.content_repo.get_by_category(eff_parent)) +
            len(self.c.group_repo.get_by_category(eff_parent))
        )

        if total_count == 0:
            title += "\n\n<i>لا يوجد محتوى في هذه الفئة بعد.</i>"
        elif total_pages > 1:
            title += f"\n<i>الصفحة {cur_page+1} من {total_pages} — إجمالي {total_count} عنصر</i>"

        if edit and update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    title, parse_mode=ParseMode.HTML, reply_markup=keyboard
                )
            except BadRequest:
                pass
        else:
            msg = update.message or (update.callback_query.message if update.callback_query else None)
            if msg:
                await msg.reply_text(title, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    # ─────────────────────────────────────────────────────────────────────
    # CALLBACK ROUTER
    # ─────────────────────────────────────────────────────────────────────

    async def callback_router(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Master callback router — dispatches to the appropriate sub-handler."""
        query   = update.callback_query
        await query.answer()
        data    = query.data
        user_id = update.effective_user.id

        # ── Subscription check ────────────────────────────────────────────
        if data == "check_sub":
            ok, missing = await self.c.subscription_service.check(context.bot, user_id)
            if ok:
                self.c.user_repo.upsert(
                    user_id, update.effective_user.first_name, update.effective_user.username
                )
                await query.edit_message_text("✅ تم التحقق! اضغط /start للبدء.")
            else:
                try:
                    await query.edit_message_reply_markup(
                        reply_markup=self.c.subscription_service.build_keyboard(missing)
                    )
                except BadRequest:
                    await query.answer("❌ لم تقم بالاشتراك في جميع القنوات بعد!", show_alert=True)
            return

        if data == "pg_info":
            return

        # Block non-admin callbacks behind subscription gate
        if not data.startswith("a_") and data not in ("check_sub", "open_admin_panel"):
            ok, missing = await self.c.subscription_service.check(context.bot, user_id)
            if not ok:
                await query.edit_message_text(
                    "🔒 <b>يجب الاشتراك في القنوات أولاً:</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=self.c.subscription_service.build_keyboard(missing),
                )
                return

        # ── Route by prefix ───────────────────────────────────────────────
        if data == "main_menu":
            context.user_data.update({"path_stack": [], "current_cat": 0, "current_page": 0})
            await self._show_main_menu(update, context, edit=True)

        elif data == "open_admin_panel":
            if self.c.auth_service.is_admin(user_id):
                await query.message.reply_text(
                    "⚙️ لوحة التحكم:",
                    reply_markup=build_admin_reply_keyboard(
                        user_id, is_owner=self.c.auth_service.is_owner(user_id)
                    ),
                )

        elif data == "vip_locked":
            await query.answer("🔒 هذا القسم حصري للمشتركين VIP!\nتواصل مع الإدارة.", show_alert=True)

        elif data == "nav_vip":
            if self.c.auth_service.is_vip(user_id):
                vip_id = self.c.config.vip_category_id
                if vip_id == 0:
                    await query.answer("⭐ لم يتم تحديد قسم VIP بعد.", show_alert=True)
                else:
                    context.user_data.update({"path_stack": [0], "current_cat": vip_id, "current_page": 0})
                    await self.show_category(update, context, parent_id=vip_id, page=0, edit=True)
            else:
                await query.answer("🔒 هذا القسم للـ VIP فقط!", show_alert=True)

        elif data == "nav_free":
            free_id = self.c.config.free_gift_category_id
            if free_id == 0:
                await query.answer("🎁 لم يتم تحديد القسم المجاني بعد.", show_alert=True)
            else:
                context.user_data.update({"path_stack": [0], "current_cat": free_id, "current_page": 0})
                await self.show_category(update, context, parent_id=free_id, page=0, edit=True)

        elif data.startswith("pg_"):
            parts = data.split("_")
            if len(parts) == 3:
                cat_id = int(parts[1])
                pg     = int(parts[2])
                context.user_data["current_page"] = pg
                await self.show_category(update, context, parent_id=cat_id, page=pg, edit=True)

        elif data.startswith("grp_"):
            parts = data.split("_")
            if len(parts) == 3:
                admin = _is_admin_mode(context, user_id, self.c)
                await self.c.content_delivery_service.send_group_page(
                    context.bot, query.message.chat_id,
                    int(parts[1]), int(parts[2]), is_admin=admin,
                )

        elif data.startswith("nav_"):
            cat_id = int(data.split("_")[1])
            stack  = context.user_data.get("path_stack", [])
            stack.append(context.user_data.get("current_cat", 0))
            context.user_data.update({"path_stack": stack, "current_cat": cat_id, "current_page": 0})
            await self.show_category(update, context, parent_id=cat_id, page=0, edit=True)

        elif data.startswith("back_"):
            target = int(data.split("_")[1])
            stack  = context.user_data.get("path_stack", [])
            while stack and stack[-1] != target:
                stack.pop()
            if stack:
                stack.pop()
            context.user_data.update({"path_stack": stack, "current_cat": target, "current_page": 0})
            if target == 0:
                await self._show_main_menu(update, context, edit=True)
            else:
                await self.show_category(update, context, parent_id=target, page=0, edit=True)

        elif data.startswith("cnt_"):
            content_id = int(data.split("_")[1])
            content    = self.c.content_repo.get_by_id(content_id)
            if not content:
                await query.answer("❌ المحتوى غير موجود.", show_alert=True)
                return
            admin  = _is_admin_mode(context, user_id, self.c)
            markup = build_content_admin_keyboard(content.id, content.category_id) if admin else None
            await self.c.content_delivery_service.send_content(
                context.bot, query.message.chat_id, content, reply_markup=markup
            )

        elif data.startswith("a_"):
            if not self.c.auth_service.is_admin(user_id):
                await query.answer("⛔ غير مصرح.", show_alert=True)
                return
            # Delegate to admin handlers (registered separately)
            # This decouples user_handlers from admin_handlers
            context.user_data["_pending_admin_cb"] = data

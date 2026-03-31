"""
╔══════════════════════════════════════════════════════════════════════╗
║  handlers/admin_handlers.py — معالجات المشرفين                      ║
║  إدارة المحتوى + القنوات + VIP + الإحصائيات + النسخ الاحتياطي      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

from core.container import Container
from utils.keyboards import (
    build_admin_reply_keyboard, build_student_mode_keyboard,
    build_category_page_keyboard,
)
from utils.message_helpers import extract_content_from_message

logger = logging.getLogger(__name__)


class AdminHandlers:
    """
    All admin-only message and callback handlers.

    Args:
        container: Application DI container.
    """

    def __init__(self, container: Container) -> None:
        self.c = container

    # ─────────────────────────────────────────────────────────────────────
    # ADMIN MENU ROUTER
    # ─────────────────────────────────────────────────────────────────────

    async def menu_router(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Route admin reply keyboard button presses to the correct sub-handler."""
        user_id = update.effective_user.id
        if not self.c.auth_service.is_admin(user_id):
            return

        text = update.message.text

        match text:
            case "👑 إدارة الأونرز":
                if self.c.auth_service.is_owner(user_id):
                    await self._show_owners_panel(update, context)
            case "📂 إدارة المحتوى":
                context.user_data.update({"path_stack": [], "current_cat": 0, "current_page": 0, "student_test_mode": False})
                from handlers.user_handlers import UserHandlers
                await UserHandlers(self.c).show_category(update, context, parent_id=0, page=0, edit=False)
            case "📢 إدارة القنوات":
                await self._show_channels_panel(update, context)
            case "⭐ إدارة VIP":
                await self._show_vip_panel(update, context)
            case "📊 إحصائيات":
                await self._show_statistics(update, context)
            case "💾 نسخ احتياطي":
                await self._send_db_backup(update, context)
            case "👁️ وضع الطالب":
                context.user_data.update({
                    "student_test_mode": True, "path_stack": [],
                    "current_cat": 0, "current_page": 0,
                })
                await update.message.reply_text(
                    "👁️ <b>وضع الطالب مفعّل</b>\n\nالآن ترى البوت كما يراه الطالب.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=build_student_mode_keyboard(),
                )
                from handlers.user_handlers import UserHandlers
                await UserHandlers(self.c)._show_main_menu(update, context, edit=False)
            case "🔙 العودة إلى لوحة التحكم":
                context.user_data["student_test_mode"] = False
                await update.message.reply_text(
                    "✅ عدت إلى لوحة التحكم.",
                    reply_markup=build_admin_reply_keyboard(
                        user_id, is_owner=self.c.auth_service.is_owner(user_id)
                    ),
                )
            case "🚪 خروج من لوحة التحكم":
                await update.message.reply_text("تم الخروج. اضغط /start للبدء.", reply_markup=ReplyKeyboardRemove())

    # ─────────────────────────────────────────────────────────────────────
    # AWAITING INPUT (state machine for multi-step operations)
    # ─────────────────────────────────────────────────────────────────────

    async def handle_awaiting_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle messages when the admin is mid-flow (e.g. adding a category name).
        Reads ``context.user_data["awaiting"]`` to know what to do.
        """
        if not update.effective_user or not update.message:
            return

        user_id = update.effective_user.id
        if not self.c.auth_service.is_admin(user_id):
            return

        awaiting = context.user_data.get("awaiting")
        if not awaiting:
            return

        msg  = update.message
        text = (msg.text or "").strip()

        match awaiting:
            case "new_category_name":
                await self._handle_new_category_name(update, context, text)
            case "new_content_name":
                await self._handle_new_content_name(update, context, text)
            case "new_content_data":
                await self._handle_new_content_data(update, context, msg)
            case "new_group_name":
                await self._handle_new_group_name(update, context, text)
            case "add_group_item":
                await self._handle_add_group_item(update, context, msg, text)
            case "edit_category_name":
                await self._handle_edit_category_name(update, context, text)
            case "edit_content_name":
                await self._handle_edit_content_name(update, context, text)
            case "edit_content_data":
                await self._handle_edit_content_data(update, context, msg)

    # ── Step handlers ─────────────────────────────────────────────────────

    async def _handle_new_category_name(self, update, context, text):
        if not text:
            await update.message.reply_text("⚠️ الاسم لا يمكن أن يكون فارغاً."); return
        parent_id = context.user_data.pop("new_cat_parent", 0) or None
        context.user_data.pop("awaiting", None)
        self.c.category_repo.add(parent_id, text)
        await update.message.reply_text(f"✅ تم إضافة الفئة <b>«{text}»</b>.", parse_mode=ParseMode.HTML)
        from handlers.user_handlers import UserHandlers
        await UserHandlers(self.c).show_category(update, context, parent_id=parent_id or 0, page=0, edit=False)

    async def _handle_new_content_name(self, update, context, text):
        if not text:
            await update.message.reply_text("⚠️ الاسم لا يمكن أن يكون فارغاً."); return
        context.user_data.update({"new_cont_name": text, "awaiting": "new_content_data"})
        await update.message.reply_text(
            "📎 <b>الخطوة 2/2 — أرسل المحتوى:</b>\n\nصورة 🖼️ | فيديو 🎥 | ملف 📄 | نص 📝 | رابط 🔗",
            parse_mode=ParseMode.HTML,
        )

    async def _handle_new_content_data(self, update, context, msg):
        cat_id = context.user_data.pop("new_cont_cat", 0)
        name   = context.user_data.pop("new_cont_name", "محتوى")
        context.user_data.pop("awaiting", None)
        if not cat_id or not self.c.category_repo.get_by_id(cat_id):
            await msg.reply_text("❌ الفئة غير موجودة، ابدأ من جديد من إدارة المحتوى.")
            return
        ctype, cdata = extract_content_from_message(msg)
        if not ctype:
            await msg.reply_text("❌ لم أتمكن من استخراج المحتوى."); return
        self.c.content_repo.add(cat_id, ctype, cdata, name)
        await msg.reply_text(f"✅ تم إضافة <b>«{name}»</b> ({ctype.arabic_name}).", parse_mode=ParseMode.HTML)
        from handlers.user_handlers import UserHandlers
        await UserHandlers(self.c).show_category(update, context, parent_id=cat_id, page=0, edit=False)

    async def _handle_new_group_name(self, update, context, text):
        if not text:
            await update.message.reply_text("⚠️ الاسم لا يمكن أن يكون فارغاً."); return
        cat_id   = context.user_data.get("new_group_cat", 0)
        group_id = self.c.group_repo.add(cat_id, text)
        context.user_data.update({"adding_to_group": group_id, "awaiting": "add_group_item"})
        await update.message.reply_text(
            f"✅ تم إنشاء المجموعة <b>«{text}»</b>!\n\n"
            "📎 <b>الآن أضف الملفات:</b>\n\n"
            "أرسل صورة 🖼️ أو فيديو 🎥 أو ملف 📄 أو نص 📝\n"
            "✅ عند الانتهاء أرسل /done",
            parse_mode=ParseMode.HTML,
        )

    async def _handle_add_group_item(self, update, context, msg, text):
        group_id = context.user_data.get("adding_to_group")
        if not group_id:
            context.user_data.pop("awaiting", None); return

        if text == "/done":
            await self._finish_group(update, context, group_id); return

        ctype, cdata = extract_content_from_message(msg)
        if not ctype:
            await msg.reply_text("❌ نوع غير مدعوم. أرسل صورة/فيديو/ملف/نص أو /done للإنهاء."); return
        from core.models import ContentType
        if ctype == ContentType.LINK:
            await msg.reply_text("⚠️ الروابط غير مدعومة في المجموعات.\nأو /done للإنهاء."); return

        caption = msg.caption or ""
        self.c.group_repo.add_item(group_id, ctype, cdata, caption)
        count = self.c.group_repo.count_items(group_id)
        await msg.reply_text(
            f"✅ تمت الإضافة! ({ctype.arabic_name})\n"
            f"إجمالي العناصر الآن: <b>{count}</b>\n\nأرسل المزيد أو /done للإنهاء.",
            parse_mode=ParseMode.HTML,
        )

    async def _handle_edit_category_name(self, update, context, text):
        if not text:
            await update.message.reply_text("⚠️ الاسم لا يمكن أن يكون فارغاً."); return
        cat_id = context.user_data.pop("edit_cat_id", None)
        context.user_data.pop("awaiting", None)
        self.c.category_repo.update_name(cat_id, text)
        await update.message.reply_text(f"✅ تم تحديث الاسم إلى <b>«{text}»</b>.", parse_mode=ParseMode.HTML)
        from handlers.user_handlers import UserHandlers
        await UserHandlers(self.c).show_category(update, context, parent_id=cat_id, page=0, edit=False)

    async def _handle_edit_content_name(self, update, context, text):
        if not text:
            await update.message.reply_text("⚠️ الاسم لا يمكن أن يكون فارغاً."); return
        cont_id = context.user_data.pop("edit_cont_id", None)
        context.user_data.pop("awaiting", None)
        self.c.content_repo.update_name(cont_id, text)
        await update.message.reply_text(f"✅ تم تحديث الاسم إلى <b>«{text}»</b>.", parse_mode=ParseMode.HTML)

    async def _handle_edit_content_data(self, update, context, msg):
        cont_id = context.user_data.pop("edit_cont_id", None)
        context.user_data.pop("awaiting", None)
        ctype, cdata = extract_content_from_message(msg)
        if not ctype:
            await msg.reply_text("❌ لم أتمكن من استخراج المحتوى."); return
        self.c.content_repo.update_data(cont_id, cdata, ctype)
        await msg.reply_text(f"✅ تم تحديث المحتوى ({ctype.arabic_name}).", parse_mode=ParseMode.HTML)

    # ─────────────────────────────────────────────────────────────────────
    # ADMIN CALLBACKS
    # ─────────────────────────────────────────────────────────────────────

    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Dispatch admin inline button actions (a_xx_id pattern)."""
        query   = update.callback_query
        await query.answer()
        data    = query.data
        user_id = update.effective_user.id

        if not self.c.auth_service.is_admin(user_id):
            await query.answer("⛔ غير مصرح.", show_alert=True); return

        parts  = data.split("_")
        action = parts[1]
        item_id = int(parts[2]) if len(parts) > 2 and parts[2].lstrip("-").isdigit() else 0

        match action:
            case "nc":
                context.user_data.update({"new_cat_parent": item_id, "awaiting": "new_category_name"})
                await query.edit_message_text(
                    "📁 <b>إضافة فئة فرعية</b>\n\nأرسل اسم الفئة:", parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data=f"nav_{item_id}")]]),
                )
            case "nx":
                context.user_data.update({"new_cont_cat": item_id, "awaiting": "new_content_name"})
                await query.edit_message_text(
                    "📌 <b>إضافة محتوى — الخطوة 1/2</b>\n\nأرسل <b>اسم</b> المحتوى:", parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data=f"nav_{item_id}")]]),
                )
            case "ng":
                context.user_data.update({"new_group_cat": item_id, "awaiting": "new_group_name"})
                await query.edit_message_text(
                    "📦 <b>إضافة مجموعة ملفات جديدة</b>\n\nالخطوة 1: أرسل <b>اسم المجموعة</b>:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data=f"nav_{item_id}")]]),
                )
            case "ag":
                group = self.c.group_repo.get_by_id(item_id)
                count = self.c.group_repo.count_items(item_id)
                context.user_data.update({"adding_to_group": item_id, "awaiting": "add_group_item"})
                await query.message.reply_text(
                    f"📎 <b>إضافة ملفات للمجموعة «{group.name if group else ''}»</b>\n\n"
                    f"العناصر الحالية: <b>{count}</b>\n\nأرسل صورة/فيديو/ملف/نص\nعند الانتهاء أرسل /done",
                    parse_mode=ParseMode.HTML,
                )
            case "dg":
                group = self.c.group_repo.get_by_id(item_id)
                if not group: await query.answer("❌ المجموعة غير موجودة.", show_alert=True); return
                await query.message.reply_text(
                    f"⚠️ <b>تأكيد الحذف</b>\n\nحذف المجموعة <b>«{group.name}»</b> مع كل محتوياتها؟",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ نعم احذف", callback_data=f"a_dgy_{item_id}"),
                        InlineKeyboardButton("❌ إلغاء",    callback_data=f"nav_{group.category_id}"),
                    ]]),
                )
            case "dgy":
                group = self.c.group_repo.get_by_id(item_id)
                if group:
                    cat_id = group.category_id
                    self.c.group_repo.delete(item_id)
                    await query.answer("✅ تم حذف المجموعة.", show_alert=True)
                    from handlers.user_handlers import UserHandlers
                    await UserHandlers(self.c).show_category(update, context, parent_id=cat_id, page=0, edit=False)
            case "ec":
                cat = self.c.category_repo.get_by_id(item_id)
                if not cat: await query.answer("❌ الفئة غير موجودة.", show_alert=True); return
                context.user_data.update({"edit_cat_id": item_id, "awaiting": "edit_category_name"})
                parent = cat.parent_id or 0
                await query.edit_message_text(
                    f"✏️ <b>تعديل اسم الفئة</b>\n\nالاسم الحالي: <i>{cat.name}</i>\n\nأرسل الاسم الجديد:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data=f"nav_{parent}")]]),
                )
            case "dc":
                cat = self.c.category_repo.get_by_id(item_id)
                if not cat: await query.answer("❌ الفئة غير موجودة.", show_alert=True); return
                parent = cat.parent_id or 0
                await query.edit_message_text(
                    f"⚠️ <b>تأكيد الحذف</b>\n\nحذف <b>«{cat.name}»</b> مع كل محتوياتها؟",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ نعم احذف", callback_data=f"a_cy_{item_id}"),
                        InlineKeyboardButton("❌ إلغاء",    callback_data=f"nav_{parent}"),
                    ]]),
                )
            case "cy":
                cat = self.c.category_repo.get_by_id(item_id)
                if cat:
                    parent = cat.parent_id or 0
                    self.c.category_repo.delete(item_id)
                    await query.answer("✅ تم الحذف.", show_alert=True)
                    context.user_data.update({"current_cat": parent, "current_page": 0})
                    stack = context.user_data.get("path_stack", [])
                    if stack and stack[-1] == item_id: stack.pop()
                    context.user_data["path_stack"] = stack
                    from handlers.user_handlers import UserHandlers
                    uh = UserHandlers(self.c)
                    if parent == 0: await uh._show_main_menu(update, context, edit=True)
                    else:           await uh.show_category(update, context, parent_id=parent, page=0, edit=True)
            case "rc":
                await self._show_reorder_menu(update, context, item_id)
            case "ru":
                self.c.category_repo.shift_order(item_id, -1)
                await self._show_reorder_menu(update, context, context.user_data.get("reorder_parent", 0))
            case "rd":
                self.c.category_repo.shift_order(item_id, +1)
                await self._show_reorder_menu(update, context, context.user_data.get("reorder_parent", 0))
            case "en":
                content = self.c.content_repo.get_by_id(item_id)
                if not content: await query.answer("❌ المحتوى غير موجود.", show_alert=True); return
                context.user_data.update({"edit_cont_id": item_id, "awaiting": "edit_content_name"})
                await query.message.reply_text(
                    f"✏️ <b>تعديل اسم المحتوى</b>\n\nالاسم الحالي: <i>{content.name}</i>\n\nأرسل الاسم الجديد:",
                    parse_mode=ParseMode.HTML,
                )
            case "ed":
                content = self.c.content_repo.get_by_id(item_id)
                if not content: await query.answer("❌ المحتوى غير موجود.", show_alert=True); return
                context.user_data.update({"edit_cont_id": item_id, "awaiting": "edit_content_data"})
                await query.message.reply_text(
                    f"🔄 <b>تعديل المحتوى</b>\n\nالنوع الحالي: <b>{content.content_type.arabic_name}</b>\n\nأرسل المحتوى الجديد:",
                    parse_mode=ParseMode.HTML,
                )
            case "dl":
                content = self.c.content_repo.get_by_id(item_id)
                if not content: await query.answer("❌ المحتوى غير موجود.", show_alert=True); return
                await query.message.reply_text(
                    f"⚠️ <b>تأكيد الحذف</b>\n\nحذف: <b>«{content.name}»</b>؟",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ نعم احذف", callback_data=f"a_dy_{item_id}"),
                        InlineKeyboardButton("❌ إلغاء",    callback_data=f"nav_{content.category_id}"),
                    ]]),
                )
            case "dy":
                content = self.c.content_repo.get_by_id(item_id)
                if content:
                    cat_id = content.category_id
                    self.c.content_repo.delete(item_id)
                    await query.answer("✅ تم حذف المحتوى.", show_alert=True)
                    from handlers.user_handlers import UserHandlers
                    await UserHandlers(self.c).show_category(update, context, parent_id=cat_id, page=0, edit=False)
            case "rch":
                username = "_".join(parts[2:])
                self.c.channel_repo.remove(username)
                await query.answer(f"✅ تم الحذف.", show_alert=True)
                await self._show_channels_panel(update, context)
            case "ach":
                # Entry point for add-channel conversation (handled by ConversationHandler)
                pass
            case _:
                await query.answer("❓ أمر غير معروف.", show_alert=True)

    # ─────────────────────────────────────────────────────────────────────
    # REORDER MENU
    # ─────────────────────────────────────────────────────────────────────

    async def _show_reorder_menu(self, update, context, parent_id):
        query   = update.callback_query
        context.user_data["reorder_parent"] = parent_id
        subcats  = self.c.category_repo.get_children(parent_id if parent_id else None)
        contents = self.c.content_repo.get_by_category(parent_id or 0)
        if not subcats and not contents:
            await query.answer("لا توجد عناصر.", show_alert=True); return
        buttons = []
        for cat in subcats:
            buttons.append([
                InlineKeyboardButton("⬆️", callback_data=f"a_ru_{cat.id}"),
                InlineKeyboardButton(f"📁 {cat.name[:18]}", callback_data="pg_info"),
                InlineKeyboardButton("⬇️", callback_data=f"a_rd_{cat.id}"),
            ])
        for cont in contents:
            buttons.append([
                InlineKeyboardButton("⬆️", callback_data=f"a_rcu_{cont.id}"),
                InlineKeyboardButton(f"{cont.content_type.emoji} {cont.name[:18]}", callback_data="pg_info"),
                InlineKeyboardButton("⬇️", callback_data=f"a_rcd_{cont.id}"),
            ])
        buttons.append([InlineKeyboardButton("✅ تم", callback_data=f"nav_{parent_id}")])
        await query.edit_message_text(
            "🔃 <b>إعادة الترتيب</b>\n\nاضغط ⬆️ / ⬇️:",
            parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons)
        )

    # ─────────────────────────────────────────────────────────────────────
    # CHANNELS PANEL
    # ─────────────────────────────────────────────────────────────────────

    async def _show_channels_panel(self, update, context):
        channels = self.c.channel_repo.get_all()
        text = "📢 <b>إدارة قنوات الاشتراك الإجباري</b>\n\n"
        if channels:
            for ch in channels:
                text += f"• <b>{ch.channel_title}</b>\n🔗 <a href='{ch.invite_link}'>رابط الاشتراك</a>\n\n"
        else:
            text += "<i>لا توجد قنوات حالياً.</i>"

        buttons = [
            [InlineKeyboardButton(f"🗑️ حذف {ch.channel_title[:15]}", callback_data=f"a_rch_{ch.channel_username}")]
            for ch in channels
        ]
        buttons.append([InlineKeyboardButton("➕ إضافة قناة أو جروب", callback_data="a_ach_0")])
        markup = InlineKeyboardMarkup(buttons)

        msg_obj = update.message or (update.callback_query.message if update.callback_query else None)
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    text, parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True, reply_markup=markup,
                )
            except BadRequest:
                await msg_obj.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
        else:
            await msg_obj.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)

    # ─────────────────────────────────────────────────────────────────────
    # VIP PANEL
    # ─────────────────────────────────────────────────────────────────────

    async def _show_vip_panel(self, update, context):
        await update.message.reply_text(
            f"⭐ <b>إدارة VIP</b>\n\nعدد المشتركين: <b>{self.c.vip_repo.count():,}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة مشترك VIP", callback_data="vip_add")],
                [InlineKeyboardButton("🗑️ إزالة مشترك VIP", callback_data="vip_del")],
            ]),
        )

    # ─────────────────────────────────────────────────────────────────────
    # OWNERS PANEL
    # ─────────────────────────────────────────────────────────────────────

    async def _show_owners_panel(self, update, context):
        owners_db = self.c.owner_repo.get_all()
        text = "👑 <b>إدارة الأونرز</b>\n\n<b>ثابتون:</b>\n"
        for oid in self.c.config.owner_ids:
            text += f"• <code>{oid}</code> ⭐\n"
        if owners_db:
            text += "\n<b>مضافون من البوت:</b>\n"
            for row in owners_db:
                text += f"• <code>{row['user_id']}</code> — أضافه <code>{row['added_by']}</code>\n"
        else:
            text += "\n<i>لا يوجد أونرز مضافون.</i>"
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة أونر",  callback_data="owner_add")],
                [InlineKeyboardButton("🗑️ حذف أونر",   callback_data="owner_remove")],
            ]),
        )

    # ─────────────────────────────────────────────────────────────────────
    # STATISTICS
    # ─────────────────────────────────────────────────────────────────────

    async def _show_statistics(self, update, context):
        await update.message.reply_text(
            "📊 <b>إحصائيات البوت</b>\n\n"
            f"👥 المستخدمون: <b>{self.c.user_repo.count():,}</b>\n"
            f"👑 المشرفون: <b>{self.c.admin_repo.count():,}</b>\n"
            f"⭐ مشتركو VIP: <b>{self.c.vip_repo.count():,}</b>\n"
            f"📂 الفئات: <b>{self.c.category_repo.count():,}</b>\n"
            f"📌 المحتويات: <b>{self.c.content_repo.count():,}</b>\n"
            f"📦 المجموعات: <b>{self.c.group_repo.count():,}</b>\n"
            f"🗂️ ملفات المجموعات: <b>{self.c.group_repo.count_all_items():,}</b>\n"
            f"📢 قنوات الاشتراك: <b>{self.c.channel_repo.count():,}</b>\n\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode=ParseMode.HTML,
        )

    # ─────────────────────────────────────────────────────────────────────
    # BACKUP
    # ─────────────────────────────────────────────────────────────────────

    async def _send_db_backup(self, update, context):
        await update.message.reply_text("⏳ جاري إعداد النسخة الاحتياطية...")
        db_path = self.c.config.db_path
        try:
            with open(db_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                    caption="💾 <b>نسخة احتياطية</b>",
                    parse_mode=ParseMode.HTML,
                )
        except OSError as exc:
            logger.error("Backup failed: %s", exc)
            await update.message.reply_text(f"❌ فشل النسخ الاحتياطي: {exc}")

    # ─────────────────────────────────────────────────────────────────────
    # GROUP FINISH
    # ─────────────────────────────────────────────────────────────────────

    async def _finish_group(self, update, context, group_id):
        count = self.c.group_repo.count_items(group_id)
        group = self.c.group_repo.get_by_id(group_id)
        cat_id = group.category_id if group else context.user_data.get("new_group_cat", 0)
        context.user_data.pop("awaiting", None)
        context.user_data.pop("adding_to_group", None)
        context.user_data.pop("new_group_cat", None)
        await update.message.reply_text(
            f"✅ <b>تم حفظ المجموعة!</b>\n\n"
            f"المجموعة: <b>«{group.name if group else ''}»</b>\n"
            f"إجمالي الملفات: <b>{count}</b>",
            parse_mode=ParseMode.HTML,
        )
        from handlers.user_handlers import UserHandlers
        await UserHandlers(self.c).show_category(update, context, parent_id=cat_id, page=0, edit=False)

"""
╔══════════════════════════════════════════════════════════════════════╗
║  handlers/conversation_handlers.py — محادثات متعددة الخطوات        ║
║  Add Admin, Broadcast, Add Channel, Owners, VIP                     ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler,
    MessageHandler, filters,
)

from core.container import Container
from utils.keyboards import build_admin_reply_keyboard

logger = logging.getLogger(__name__)

# Conversation states
(
    ST_ADD_ADMIN_ID,
    ST_ADD_CHANNEL,
    ST_ADD_OWNER_ID, ST_REMOVE_OWNER_ID,
    ST_VIP_ADD, ST_VIP_DEL,
    ST_BROADCAST_MSG, ST_BROADCAST_CONFIRM,
) = range(8)


class ConversationHandlers:
    """
    Factory that creates all ConversationHandler objects, injecting
    the DI container into each step function.

    Args:
        container: Application DI container.
    """

    def __init__(self, container: Container) -> None:
        self.c = container

    # ─────────────────────────────────────────────────────────────────────
    # CANCEL
    # ─────────────────────────────────────────────────────────────────────

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Universal cancel handler — finishes any active group upload first."""
        if context.user_data.get("awaiting") == "add_group_item":
            group_id = context.user_data.get("adding_to_group")
            if group_id:
                from handlers.admin_handlers import AdminHandlers
                await AdminHandlers(self.c)._finish_group(update, context, group_id)
                return ConversationHandler.END

        context.user_data.clear()
        await update.message.reply_text(
            "❌ تم الإلغاء.",
            reply_markup=build_admin_reply_keyboard(
                update.effective_user.id,
                is_owner=self.c.auth_service.is_owner(update.effective_user.id),
            ),
        )
        return ConversationHandler.END

    # ─────────────────────────────────────────────────────────────────────
    # /done command
    # ─────────────────────────────────────────────────────────────────────

    async def done_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/done — finish a media group upload."""
        if context.user_data.get("awaiting") == "add_group_item":
            group_id = context.user_data.get("adding_to_group")
            if group_id:
                from handlers.admin_handlers import AdminHandlers
                await AdminHandlers(self.c)._finish_group(update, context, group_id)
                return
        await update.message.reply_text(
            "لا توجد عملية جارية.",
            reply_markup=build_admin_reply_keyboard(
                update.effective_user.id,
                is_owner=self.c.auth_service.is_owner(update.effective_user.id),
            ),
        )

    # ─────────────────────────────────────────────────────────────────────
    # ADD ADMIN CONVERSATION
    # ─────────────────────────────────────────────────────────────────────

    async def _start_add_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text(
            "👤 <b>إضافة مشرف</b>\n\nأرسل الـ User ID أو /cancel:",
            parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove(),
        )
        return ST_ADD_ADMIN_ID

    async def _receive_admin_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        text = update.message.text.strip()
        if not text.isdigit():
            await update.message.reply_text("❌ أرسل رقم صحيح أو /cancel.")
            return ST_ADD_ADMIN_ID

        new_id = int(text)
        if self.c.auth_service.is_admin(new_id):
            await update.message.reply_text("ℹ️ هذا المستخدم مشرف بالفعل.")
        else:
            self.c.auth_service.add_admin(new_id)
            await update.message.reply_text(f"✅ تم إضافة <code>{new_id}</code> كمشرف.", parse_mode=ParseMode.HTML)

        user_id = update.effective_user.id
        context.user_data.clear()
        await update.message.reply_text(
            "العودة:", reply_markup=build_admin_reply_keyboard(user_id, self.c.auth_service.is_owner(user_id))
        )
        return ConversationHandler.END

    def build_add_admin_conv(self) -> ConversationHandler:
        return ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^👤 إضافة مشرف$"), self._start_add_admin)],
            states={ST_ADD_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._receive_admin_id)]},
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True,
        )

    # ─────────────────────────────────────────────────────────────────────
    # BROADCAST CONVERSATION
    # ─────────────────────────────────────────────────────────────────────

    async def _start_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text(
            f"📣 <b>إرسال جماعي</b>\n\nسيصل إلى <b>{self.c.user_repo.count():,}</b> مستخدم.\n\nأرسل الرسالة أو /cancel:",
            parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove(),
        )
        return ST_BROADCAST_MSG

    async def _receive_broadcast_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        msg = update.message
        context.user_data.update({"broadcast_from_chat": msg.chat_id, "broadcast_msg_id": msg.message_id})
        preview = (
            f"📝 {msg.text[:80]}" if msg.text
            else "🖼️ صورة" if msg.photo
            else "🎥 فيديو" if msg.video
            else "📄 ملف" if msg.document
            else "رسالة"
        )
        await msg.reply_text(
            f"<b>معاينة:</b> {preview}\n\nإرسال إلى <b>{self.c.user_repo.count():,}</b> مستخدم؟",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ إرسال",  callback_data="bc_confirm"),
                InlineKeyboardButton("❌ إلغاء", callback_data="bc_cancel"),
            ]]),
        )
        return ST_BROADCAST_CONFIRM

    async def _broadcast_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id

        if query.data == "bc_cancel":
            context.user_data.clear()
            await query.edit_message_text("❌ تم الإلغاء.")
            await query.message.reply_text(
                "العودة:",
                reply_markup=build_admin_reply_keyboard(user_id, self.c.auth_service.is_owner(user_id))
            )
            return ConversationHandler.END

        from_chat = context.user_data.get("broadcast_from_chat")
        msg_id    = context.user_data.get("broadcast_msg_id")
        total     = self.c.user_repo.count()
        await query.edit_message_text(f"⏳ جاري الإرسال إلى {total:,} مستخدم...")

        result = await self.c.broadcast_service.send_to_all(context.bot, from_chat, msg_id)

        context.user_data.clear()
        await query.message.reply_text(
            f"✅ <b>اكتمل الإرسال</b>\n\n"
            f"✔️ نجح: <b>{result.success:,}</b>\n"
            f"✖️ فشل: <b>{result.failed:,}</b>\n"
            f"📊 معدل النجاح: <b>{result.success_rate:.1f}%</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=build_admin_reply_keyboard(user_id, self.c.auth_service.is_owner(user_id)),
        )
        return ConversationHandler.END

    def build_broadcast_conv(self) -> ConversationHandler:
        return ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^📣 إرسال رسالة جماعية$"), self._start_broadcast)],
            per_message=True,
            states={
                ST_BROADCAST_MSG: [MessageHandler(
                    (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND,
                    self._receive_broadcast_msg,
                )],
                ST_BROADCAST_CONFIRM: [CallbackQueryHandler(self._broadcast_confirm, pattern="^bc_")],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True,
        )

    # ─────────────────────────────────────────────────────────────────────
    # ADD CHANNEL CONVERSATION
    # ─────────────────────────────────────────────────────────────────────

    async def _start_add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "📢 <b>إضافة قناة / جروب</b>\n\n"
            "أرسل الـ username (بدون @) أو الـ ID الرقمي أو /cancel:\n"
            "<i>مثال: mychannel  أو  -100123456789</i>",
            parse_mode=ParseMode.HTML,
        )
        return ST_ADD_CHANNEL

    async def _receive_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        text = update.message.text.strip()
        if text.lower() == "/cancel":
            return await self.cancel(update, context)

        if text.startswith("http"):
            if "+" in text or "joinchat" in text:
                await update.message.reply_text(
                    "⚠️ للجروبات الخاصة أرسل الـ ID الرقمي (مثال: -100123456789)."
                )
                return ST_ADD_CHANNEL
            username = text.split("/")[-1].lstrip("@")
        else:
            username = text.lstrip("@")

        try:
            chat_id = int(username) if username.lstrip("-").isdigit() else f"@{username}"
            chat    = await context.bot.get_chat(chat_id)

            save_id     = str(chat.id)
            title       = chat.title or save_id
            invite_link = chat.invite_link

            if not invite_link:
                if chat.username:
                    invite_link = f"https://t.me/{chat.username}"
                else:
                    try:
                        invite_link = await context.bot.export_chat_invite_link(chat.id)
                    except TelegramError:
                        invite_link = "غير_متوفر"

            self.c.channel_repo.add(save_id, title, invite_link)
            user_id = update.effective_user.id
            context.user_data.clear()

            await update.message.reply_text(
                f"✅ <b>تمت الإضافة بنجاح!</b>\n\n📌 <b>الاسم:</b> {title}\n🔗 <b>الرابط:</b> {invite_link}",
                parse_mode=ParseMode.HTML,
                reply_markup=build_admin_reply_keyboard(user_id, self.c.auth_service.is_owner(user_id)),
            )
            return ConversationHandler.END

        except Exception as exc:
            logger.warning("Failed to add channel %s: %s", username, exc)
            await update.message.reply_text(
                f"❌ <b>فشل الوصول!</b>\nتأكد أن البوت <b>مشرف (Admin)</b> في القناة/الجروب.\n\n<i>تفاصيل: {exc}</i>",
                parse_mode=ParseMode.HTML,
            )
            return ST_ADD_CHANNEL

    def build_add_channel_conv(self) -> ConversationHandler:
        return ConversationHandler(
            entry_points=[CallbackQueryHandler(self._start_add_channel, pattern="^a_ach_0$")],
            states={ST_ADD_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._receive_channel)]},
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True,
        )

    # ─────────────────────────────────────────────────────────────────────
    # OWNERS CONVERSATION
    # ─────────────────────────────────────────────────────────────────────

    async def _owner_panel_cb(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        if not self.c.auth_service.is_owner(update.effective_user.id):
            await query.answer("⛔ غير مصرح.", show_alert=True)
            return ConversationHandler.END
        if query.data == "owner_add":
            await query.edit_message_text("👑 <b>إضافة أونر</b>\n\nأرسل الـ User ID أو /cancel:", parse_mode=ParseMode.HTML)
            return ST_ADD_OWNER_ID
        if query.data == "owner_remove":
            if not self.c.owner_repo.get_all():
                await query.answer("لا يوجد أونرز لحذفهم.", show_alert=True)
                return ConversationHandler.END
            await query.edit_message_text("🗑️ <b>حذف أونر</b>\n\nأرسل الـ User ID أو /cancel:", parse_mode=ParseMode.HTML)
            return ST_REMOVE_OWNER_ID
        return ConversationHandler.END

    async def _receive_new_owner(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        text    = update.message.text.strip()
        if not text.isdigit():
            await update.message.reply_text("❌ أرسل رقم ID صحيح.")
            return ST_ADD_OWNER_ID
        new_owner = int(text)
        if self.c.auth_service.is_owner(new_owner):
            await update.message.reply_text("ℹ️ هذا المستخدم أونر بالفعل.")
        else:
            self.c.auth_service.add_owner(new_owner, added_by=user_id)
            await update.message.reply_text(f"✅ تم إضافة <code>{new_owner}</code> كأونر.", parse_mode=ParseMode.HTML)
            try:
                await context.bot.send_message(new_owner, "🎉 تم منحك صلاحية <b>أونر</b>!\nاضغط /start.", parse_mode=ParseMode.HTML)
            except TelegramError:
                pass
        context.user_data.clear()
        await update.message.reply_text("العودة:", reply_markup=build_admin_reply_keyboard(user_id, True))
        return ConversationHandler.END

    async def _receive_remove_owner(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        text    = update.message.text.strip()
        if not text.isdigit():
            await update.message.reply_text("❌ أرسل رقم ID صحيح.")
            return ST_REMOVE_OWNER_ID
        target = int(text)
        try:
            self.c.auth_service.remove_owner(target)
            await update.message.reply_text(f"✅ تم حذف <code>{target}</code>.", parse_mode=ParseMode.HTML)
        except PermissionError as exc:
            await update.message.reply_text(f"⛔ {exc}")
        context.user_data.clear()
        await update.message.reply_text("العودة:", reply_markup=build_admin_reply_keyboard(user_id, True))
        return ConversationHandler.END

    def build_owners_conv(self) -> ConversationHandler:
        return ConversationHandler(
            entry_points=[CallbackQueryHandler(self._owner_panel_cb, pattern="^owner_(add|remove)$")],
            states={
                ST_ADD_OWNER_ID:    [MessageHandler(filters.TEXT & ~filters.COMMAND, self._receive_new_owner)],
                ST_REMOVE_OWNER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._receive_remove_owner)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True,
        )

    # ─────────────────────────────────────────────────────────────────────
    # VIP CONVERSATION
    # ─────────────────────────────────────────────────────────────────────

    async def _vip_panel_cb(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        if not self.c.auth_service.is_admin(update.effective_user.id):
            return ConversationHandler.END
        if query.data == "vip_add":
            await query.edit_message_text("⭐ <b>إضافة VIP</b>\n\nأرسل الـ User ID أو /cancel:", parse_mode=ParseMode.HTML)
            return ST_VIP_ADD
        if query.data == "vip_del":
            await query.edit_message_text("🗑️ <b>إزالة VIP</b>\n\nأرسل الـ User ID أو /cancel:", parse_mode=ParseMode.HTML)
            return ST_VIP_DEL
        return ConversationHandler.END

    async def _receive_vip_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        text    = update.message.text.strip()
        if not text.isdigit():
            await update.message.reply_text("❌ أرسل رقم ID صحيح.")
            return ST_VIP_ADD
        target = int(text)
        self.c.auth_service.add_vip(target, user_id)
        await update.message.reply_text(f"✅ تم إضافة <code>{target}</code> كمشترك VIP.", parse_mode=ParseMode.HTML)
        try:
            await context.bot.send_message(target, "⭐ تهانينا! تم تفعيل اشتراكك في <b>قسم VIP</b>!\nاضغط /start.", parse_mode=ParseMode.HTML)
        except TelegramError:
            pass
        context.user_data.clear()
        await update.message.reply_text("العودة:", reply_markup=build_admin_reply_keyboard(user_id, self.c.auth_service.is_owner(user_id)))
        return ConversationHandler.END

    async def _receive_vip_del(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        text    = update.message.text.strip()
        if not text.isdigit():
            await update.message.reply_text("❌ أرسل رقم ID صحيح.")
            return ST_VIP_DEL
        target = int(text)
        self.c.auth_service.remove_vip(target)
        await update.message.reply_text(f"✅ تم إلغاء VIP للمستخدم <code>{target}</code>.", parse_mode=ParseMode.HTML)
        context.user_data.clear()
        await update.message.reply_text("العودة:", reply_markup=build_admin_reply_keyboard(user_id, self.c.auth_service.is_owner(user_id)))
        return ConversationHandler.END

    def build_vip_conv(self) -> ConversationHandler:
        return ConversationHandler(
            entry_points=[CallbackQueryHandler(self._vip_panel_cb, pattern="^vip_(add|del)$")],
            states={
                ST_VIP_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._receive_vip_add)],
                ST_VIP_DEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._receive_vip_del)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True,
        )

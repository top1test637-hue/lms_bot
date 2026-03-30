"""
╔══════════════════════════════════════════════════════════════════════╗
║  main.py — نقطة الدخول الرئيسية                                     ║
║  Application Factory Pattern — كل شيء يُبنى هنا ويُشغَّل هنا       ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import logging
import traceback

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

from core.config import get_config
from core.container import Container
from core.logging_config import setup_logging
from database.connection import init_db
from handlers.admin_handlers import AdminHandlers
from handlers.conversation_handlers import ConversationHandlers
from handlers.user_handlers import UserHandlers

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ERROR HANDLER
# ─────────────────────────────────────────────────────────────────────────────

def _build_error_handler(container: Container):
    """
    Factory for the global error handler.

    Sends a truncated traceback to all owner IDs and replies to the user
    with a generic error message.

    Args:
        container: DI container (used to read owner IDs).
    """

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.critical("Unhandled exception", exc_info=context.error)
        tb_str = "".join(
            traceback.format_exception(type(context.error), context.error, context.error.__traceback__)
        )[-2000:]

        for owner_id in container.config.owner_ids:
            try:
                await context.bot.send_message(
                    chat_id=owner_id,
                    text=f"⚠️ <b>خطأ غير متوقع</b>\n\n<pre>{tb_str}</pre>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text("❌ حدث خطأ. تم إشعار المشرف.")
            except Exception:
                pass

    return error_handler


# ─────────────────────────────────────────────────────────────────────────────
# APPLICATION FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def build_application() -> Application:
    """
    Construct and wire the complete Telegram Application.

    Registers all handlers in priority order:
    1. ConversationHandlers (highest priority — own state machines)
    2. CommandHandlers (/start, /done)
    3. Admin reply-keyboard router
    4. Master CallbackQueryHandler
    5. Awaiting-input handler (lowest priority)
    6. Error handler

    Returns:
        Application: Ready-to-run Telegram bot application.
    """
    config    = get_config()
    container = Container(config=config)

    init_db(config.db_path)

    app = Application.builder().token(config.bot_token).build()

    user_handlers = UserHandlers(container)
    admin_handlers = AdminHandlers(container)
    conv_handlers  = ConversationHandlers(container)

    # ── Conversation handlers (registered first for highest priority) ──
    app.add_handler(conv_handlers.build_owners_conv())
    app.add_handler(conv_handlers.build_vip_conv())
    app.add_handler(conv_handlers.build_add_admin_conv())
    app.add_handler(conv_handlers.build_broadcast_conv())
    app.add_handler(conv_handlers.build_add_channel_conv())

    # ── Commands ───────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", user_handlers.cmd_start))
    app.add_handler(CommandHandler("done",  conv_handlers.done_command))

    # ── Admin reply-keyboard router ────────────────────────────────────
    _ADMIN_MENU_PATTERN = (
        "^(📂 إدارة المحتوى|📢 إدارة القنوات|📊 إحصائيات"
        "|💾 نسخ احتياطي|👁️ وضع الطالب|👑 إدارة الأونرز"
        "|⭐ إدارة VIP|📣 إرسال رسالة جماعية|👤 إضافة مشرف"
        "|🔙 العودة إلى لوحة التحكم|🚪 خروج من لوحة التحكم)$"
    )
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(_ADMIN_MENU_PATTERN),
        admin_handlers.menu_router,
    ))

    # ── Master callback router ─────────────────────────────────────────
    # Admin callbacks (a_xx) are delegated from user_handlers to admin_handlers
    async def master_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        data = update.callback_query.data if update.callback_query else ""
        if data.startswith("a_"):
            await admin_handlers.handle_admin_callback(update, context)
        else:
            await user_handlers.callback_router(update, context)

    app.add_handler(CallbackQueryHandler(master_callback_router))

    # ── Awaiting-input (admin multi-step flows) ────────────────────────
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND,
        admin_handlers.handle_awaiting_input,
    ))

    # ── Global error handler ───────────────────────────────────────────
    app.add_error_handler(_build_error_handler(container))

    logger.info("Application built successfully.")
    return app


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Bootstrap and run the LMS bot."""
    config = get_config()

    setup_logging(
        level=config.log_level,
        log_dir=config.log_dir,
        json_format=False,
    )

    logger.info("🚀 Starting LMS Bot (Legendary Edition)...")
    app = build_application()
    logger.info("✅ Bot is running. Press Ctrl+C to stop.")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()

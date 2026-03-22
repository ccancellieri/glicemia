"""Telegram chat platform — python-telegram-bot integration."""

import logging
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from app.chat.platform import ChatPlatform
from app.config import settings
from app.bot.handlers import (
    cmd_start, cmd_menu, cmd_status, cmd_help,
    handle_callback, handle_text, handle_photo,
    handle_voice, handle_document, handle_location,
)

log = logging.getLogger(__name__)


class TelegramPlatform(ChatPlatform):
    """Telegram bot using python-telegram-bot."""

    def __init__(self):
        self._app: Optional[Application] = None

    def _build_app(self) -> Application:
        app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

        # Command handlers
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("menu", cmd_menu))
        app.add_handler(CommandHandler("stato", cmd_status))
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("help", cmd_help))
        app.add_handler(CommandHandler("aiuto", cmd_help))

        # Inline keyboard callbacks
        app.add_handler(CallbackQueryHandler(handle_callback))

        # Message type handlers
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(MessageHandler(filters.VOICE, handle_voice))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(MessageHandler(filters.LOCATION, handle_location))
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, handle_text
        ))

        return app

    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        if self._app:
            await self._app.bot.send_message(
                chat_id=chat_id, text=text,
                reply_markup=reply_markup, parse_mode=parse_mode,
            )

    async def send_photo(self, chat_id, photo, caption=None):
        if self._app:
            await self._app.bot.send_photo(
                chat_id=chat_id, photo=photo, caption=caption,
            )

    async def send_document(self, chat_id, document, caption=None):
        if self._app:
            await self._app.bot.send_document(
                chat_id=chat_id, document=document, caption=caption,
            )

    async def start(self):
        """Start Telegram bot polling."""
        if not settings.TELEGRAM_BOT_TOKEN:
            log.error("TELEGRAM_BOT_TOKEN not set. Cannot start Telegram bot.")
            return

        self._app = self._build_app()
        log.info("Starting Telegram bot...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        log.info("Telegram bot started and polling")

    async def stop(self):
        """Stop Telegram bot."""
        if self._app:
            log.info("Stopping Telegram bot...")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            log.info("Telegram bot stopped")

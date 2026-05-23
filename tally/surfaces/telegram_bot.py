from typing import Any

import structlog

from tally.config import Config, get_config, get_telegram_credentials
from tally.logging_setup import setup_logging

setup_logging()
LOGGER = structlog.get_logger(__name__)


def _is_allowed(update: Any, config: Config) -> bool:
    return bool(update.effective_user and update.effective_user.id == config.telegram_user_id)


def _handlers() -> tuple[Any, Any]:
    from telegram import Update
    from telegram.ext import ContextTypes

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        config: Config = context.application.bot_data["config"]
        if update.message is None:
            return
        if _is_allowed(update, config):
            await update.message.reply_text("Tally CFO bot online. Not implemented yet.")
        else:
            await update.message.reply_text("This bot is locked to a single user.")

    async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        config: Config = context.application.bot_data["config"]
        if update.message is None:
            return
        if _is_allowed(update, config):
            await update.message.reply_text("Not implemented yet. Try /start.")
        else:
            await update.message.reply_text("This bot is locked to a single user.")

    return start, fallback


def run_bot() -> None:
    from telegram.ext import Application, CommandHandler, MessageHandler, filters

    config = get_config()
    start, fallback = _handlers()
    application = Application.builder().token(config.telegram_bot_token).build()
    application.bot_data["config"] = config
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback))
    application.run_polling()


def send_to_user(text: str) -> None:
    from telegram import Bot

    token, user_id = get_telegram_credentials()
    bot = Bot(token=token)
    try:
        import asyncio

        asyncio.run(bot.send_message(chat_id=user_id, text=text))
    except Exception as error:
        LOGGER.warning("telegram_push_failed", error=str(error))
        raise


if __name__ == "__main__":
    run_bot()

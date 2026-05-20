from typing import Any

from tally.config import Config, get_config
from tally.logging_setup import setup_logging

setup_logging()


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


if __name__ == "__main__":
    run_bot()

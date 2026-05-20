from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from tally.config import Config, get_config
from tally.logging_setup import setup_logging

setup_logging()


def _is_allowed(update: Update, config: Config) -> bool:
    return bool(update.effective_user and update.effective_user.id == config.telegram_user_id)


async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config: Config = context.application.bot_data["config"]
    if update.message is None:
        return
    if _is_allowed(update, config):
        await update.message.reply_text("Tally CFO bot online. Not implemented yet.")
    else:
        await update.message.reply_text("This bot is locked to a single user.")


async def _fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config: Config = context.application.bot_data["config"]
    if update.message is None:
        return
    if _is_allowed(update, config):
        await update.message.reply_text("Not implemented yet. Try /start.")
    else:
        await update.message.reply_text("This bot is locked to a single user.")


def run_bot() -> None:
    config = get_config()
    application = Application.builder().token(config.telegram_bot_token).build()
    application.bot_data["config"] = config
    application.add_handler(CommandHandler("start", _start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _fallback))
    application.run_polling()


if __name__ == "__main__":
    run_bot()

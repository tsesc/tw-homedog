"""Entry point for tw_homedog — Telegram Bot mode."""

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from tw_homedog.log import setup_logging

logger = logging.getLogger("tw_homedog")


def bot_main():
    """Bot mode entry point — long-running Telegram Bot process."""
    from tw_homedog.bot import run_bot

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    db_path = os.environ.get("DATABASE_PATH", "data/homedog.db")

    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is required (set via environment variable)")
        sys.exit(1)

    if not chat_id:
        logger.error("TELEGRAM_CHAT_ID is required (set via environment variable)")
        sys.exit(1)

    logger.info("Starting tw-homedog Bot mode")
    run_bot(bot_token, chat_id, db_path)


def main():
    setup_logging(log_dir="logs")
    bot_main()


if __name__ == "__main__":
    main()

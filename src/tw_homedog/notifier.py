"""Telegram notification module."""

import asyncio
import logging
import time

from telegram import Bot
from telegram.error import TelegramError

from tw_homedog.config import Config
from tw_homedog.storage import Storage

logger = logging.getLogger(__name__)

MAX_BATCH_SIZE = 10
MESSAGE_DELAY = 1.0  # seconds between messages


def format_listing_message(listing: dict, mode: str = "buy") -> str:
    """Format a listing into a Telegram message."""
    district = listing.get("district") or "未知"
    price = listing.get("price")
    size = listing.get("size_ping")
    size_str = f"{size} 坪" if size else "未提供"
    title = listing.get("title") or "無標題"
    url = listing.get("url") or ""

    if mode == "buy":
        price_str = f"{price:,} 萬" if price else "未提供"
        lines = [
            "🏠 新物件符合條件",
            f"📌 {title}",
            f"📍 {district}",
            f"💰 {price_str}",
            f"📐 {size_str}",
        ]
        unit_price = listing.get("unit_price")
        if unit_price:
            lines.append(f"💲 單價 {unit_price} 萬/坪")
        houseage = listing.get("houseage")
        if houseage:
            lines.append(f"🏗 屋齡 {houseage}")
        kind_name = listing.get("kind_name")
        if kind_name:
            lines.append(f"🏢 {kind_name}")
        room = listing.get("room")
        if room:
            lines.append(f"🚪 {room}")
    else:
        price_str = f"NT${price:,}/月" if price else "未提供"
        lines = [
            "🏠 新房源符合條件",
            f"📌 {title}",
            f"📍 {district}",
            f"💰 {price_str}",
            f"📐 {size_str}",
        ]

    if url:
        lines.append(f"🔗 {url}")
    return "\n".join(lines)


async def validate_bot_token(bot_token: str) -> bool:
    """Validate Telegram bot token by calling getMe."""
    try:
        bot = Bot(token=bot_token)
        await bot.get_me()
        return True
    except TelegramError as e:
        logger.error("Invalid Telegram bot token: %s", e)
        return False


async def _send_message(bot: Bot, chat_id: str, text: str) -> bool:
    """Send a single Telegram message. Returns True on success."""
    try:
        await bot.send_message(chat_id=chat_id, text=text)
        return True
    except TelegramError as e:
        logger.error("Failed to send Telegram message: %s", e)
        return False


def send_notifications(config: Config, storage: Storage, listings: list[dict]) -> int:
    """Send Telegram notifications for matched listings. Returns count of successfully sent."""
    if not listings:
        return 0

    batch = listings[:MAX_BATCH_SIZE]
    if len(listings) > MAX_BATCH_SIZE:
        logger.warning(
            "Limiting notifications to %d (total matched: %d)", MAX_BATCH_SIZE, len(listings)
        )

    sent_count = 0

    async def _send_all():
        nonlocal sent_count
        bot = Bot(token=config.telegram.bot_token)

        mode = getattr(config.search, 'mode', 'buy')
        for i, listing in enumerate(batch):
            msg = format_listing_message(listing, mode=mode)
            success = await _send_message(bot, config.telegram.chat_id, msg)

            if success:
                storage.record_notification(
                    listing["source"], listing["listing_id"]
                )
                sent_count += 1
                logger.info("Notified: %s (%s)", listing["listing_id"], listing.get("title", ""))
            else:
                logger.error("Failed to notify: %s", listing["listing_id"])

            # Rate limiting between messages
            if i < len(batch) - 1:
                await asyncio.sleep(MESSAGE_DELAY)

    asyncio.run(_send_all())
    logger.info("Sent %d/%d notifications", sent_count, len(batch))
    return sent_count

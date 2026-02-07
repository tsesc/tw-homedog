"""Telegram Bot interactive interface for tw-homedog."""

import asyncio
import logging
from datetime import datetime, timezone

from telegram import (
    Bot,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from tw_homedog.db_config import DbConfig
from tw_homedog.log import set_log_level
from tw_homedog.matcher import find_matching_listings
from tw_homedog.normalizer import normalize_591_listing
from tw_homedog.notifier import send_notifications
from tw_homedog.regions import (
    BUY_SECTION_CODES,
    REGION_CODES,
    RENT_SECTION_CODES,
    resolve_region,
)
from tw_homedog.scraper import scrape_listings, _get_buy_session_headers, enrich_buy_listings
from tw_homedog.storage import Storage
from tw_homedog.templates import TEMPLATES, apply_template

logger = logging.getLogger(__name__)

# ConversationHandler states
(
    SETUP_TEMPLATE,
    SETUP_MODE,
    SETUP_REGION,
    SETUP_DISTRICTS,
    SETUP_PRICE,
    SETUP_CONFIRM,
    SETTINGS_PRICE_INPUT,
    SETTINGS_SIZE_INPUT,
    SETTINGS_MENU,
    SETTINGS_KW_MENU,
    SETTINGS_KW_INCLUDE_INPUT,
    SETTINGS_KW_EXCLUDE_INPUT,
    SETTINGS_SCHEDULE_INPUT,
    SETTINGS_PAGES_INPUT,
) = range(14)

# Reverse lookup: region_id → Chinese name
_REGION_ID_TO_NAME: dict[int, str] = {v: k for k, v in REGION_CODES.items()}

# Pipeline lock
_pipeline_running = False


def _auth_filter(chat_id: str) -> filters.BaseFilter:
    """Create a filter that only allows messages from the configured chat_id."""
    return filters.Chat(chat_id=int(chat_id))


# =============================================================================
# Command handlers
# =============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Handle /start command."""
    db_config: DbConfig = context.bot_data["db_config"]

    if db_config.has_config():
        keyboard = [
            [
                InlineKeyboardButton("重新設定", callback_data="setup_choose:reset"),
            ]
        ]
        await update.message.reply_text(
            "歡迎回來！可用指令：\n"
            "/settings - 修改設定\n"
            "/status - 查看狀態\n"
            "/run - 手動執行\n"
            "/pause - 暫停排程\n"
            "/resume - 恢復排程\n"
            "/loglevel - 調整日誌等級",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SETUP_TEMPLATE

    # First-time setup — choose template or custom
    keyboard = [
        [
            InlineKeyboardButton("快速模板", callback_data="setup_choose:template"),
            InlineKeyboardButton("自訂設定", callback_data="setup_choose:custom"),
        ]
    ]
    await update.message.reply_text(
        "歡迎使用 tw-homedog！\n\n請選擇設定方式：",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SETUP_TEMPLATE


async def setup_choose_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle choice between template and custom setup."""
    query = update.callback_query
    await query.answer()

    choice = query.data.split(":")[1]

    if choice == "template":
        # Show template list
        buttons = []
        for t in TEMPLATES:
            buttons.append([InlineKeyboardButton(
                f"{t['name']} — {t['description']}",
                callback_data=f"setup_tpl:{t['id']}",
            )])
        buttons.append([InlineKeyboardButton("返回", callback_data="setup_choose:back")])
        await query.edit_message_text(
            "選擇一個快速模板：",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return SETUP_TEMPLATE

    elif choice in ("back", "reset"):
        # Go back to (or enter) template/custom choice
        keyboard = [
            [
                InlineKeyboardButton("快速模板", callback_data="setup_choose:template"),
                InlineKeyboardButton("自訂設定", callback_data="setup_choose:custom"),
            ]
        ]
        await query.edit_message_text(
            "請選擇設定方式：",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SETUP_TEMPLATE

    else:
        # Custom setup — go to mode selection
        keyboard = [
            [
                InlineKeyboardButton("買房 (Buy)", callback_data="setup_mode:buy"),
                InlineKeyboardButton("租房 (Rent)", callback_data="setup_mode:rent"),
            ]
        ]
        await query.edit_message_text(
            "開始自訂設定。\n\n請選擇模式：",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SETUP_MODE


async def setup_template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle template selection — apply and show summary for confirmation."""
    query = update.callback_query
    await query.answer()

    template_id = query.data.replace("setup_tpl:", "")
    try:
        config_items = apply_template(template_id)
    except KeyError:
        await query.edit_message_text("模板不存在，請重新選擇。")
        return SETUP_TEMPLATE

    context.user_data["setup"] = config_items

    mode = config_items["search.mode"]
    region_name = _region_names(config_items["search.regions"])
    districts = ", ".join(config_items["search.districts"])
    unit = "萬" if mode == "buy" else "元"
    price_min = config_items["search.price_min"]
    price_max = config_items["search.price_max"]
    min_ping = config_items.get("search.min_ping")
    kw_exclude = config_items.get("search.keywords_exclude", [])

    lines = [
        "模板設定摘要：",
        f"模式：{'買房' if mode == 'buy' else '租房'}",
        f"地區：{region_name}",
        f"區域：{districts}",
        f"價格：{price_min:,}-{price_max:,} {unit}",
    ]
    if min_ping:
        lines.append(f"最小坪數：{min_ping} 坪")
    if kw_exclude:
        lines.append(f"排除關鍵字：{', '.join(kw_exclude)}")
    lines.append("\n確認套用？")

    keyboard = [
        [
            InlineKeyboardButton("確認", callback_data="setup_confirm:yes"),
            InlineKeyboardButton("取消", callback_data="setup_confirm:no"),
        ]
    ]
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SETUP_CONFIRM


async def setup_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle mode selection in setup flow."""
    query = update.callback_query
    await query.answer()

    mode = query.data.split(":")[1]
    context.user_data["setup"] = {"search.mode": mode}

    await query.edit_message_text(
        f"已選擇：{'買房' if mode == 'buy' else '租房'}\n\n"
        "請輸入地區（多個地區用逗號分隔，例如：台北市,新北市）："
    )
    return SETUP_REGION


async def setup_region_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle region input in setup flow. Accepts Chinese name or numeric code."""
    text = update.message.text.strip()
    regions = []
    for part in text.split(","):
        part = part.strip().replace("，", "")
        if not part:
            continue
        try:
            regions.append(resolve_region(int(part) if part.isdigit() else part))
        except (ValueError, TypeError):
            region_list = ", ".join(REGION_CODES.keys())
            await update.message.reply_text(
                f"無效的地區：{part}\n請輸入中文名或代碼，多個地區用逗號分隔。\n支援的地區：{region_list}"
            )
            return SETUP_REGION

    if not regions:
        await update.message.reply_text("請至少輸入一個地區")
        return SETUP_REGION

    setup = context.user_data["setup"]
    setup["search.regions"] = regions

    mode = setup.get("search.mode", "buy")

    # Show district selection
    selected = []
    keyboard = _build_district_keyboard(regions, mode, selected)
    if keyboard is None:
        await update.message.reply_text(
            f"{'租房' if mode == 'rent' else '買房'}模式不支援這些地區的區域選擇。"
        )
        return SETUP_REGION

    region_name = _region_names(regions)
    await update.message.reply_text(
        f"地區：{region_name}\n請選擇區域（點擊切換，完成後按確認）：",
        reply_markup=keyboard,
    )
    setup["_selected_districts"] = selected
    return SETUP_DISTRICTS


async def setup_districts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle district toggle in setup flow."""
    query = update.callback_query
    await query.answer()

    data = query.data
    setup = context.user_data["setup"]
    selected = setup.get("_selected_districts", [])

    if data == "district_confirm":
        if not selected:
            await query.answer("請至少選擇一個區域", show_alert=True)
            return SETUP_DISTRICTS

        setup["search.districts"] = selected
        del setup["_selected_districts"]

        await query.edit_message_text(
            f"已選擇區域：{', '.join(selected)}\n\n"
            "請輸入價格範圍（格式：最低-最高）\n"
            "買房單位：萬，租房單位：元\n"
            "例如買房：1000-3000，租房：10000-30000"
        )
        return SETUP_PRICE

    # Toggle district
    district = data.replace("district_toggle:", "")
    if district in selected:
        selected.remove(district)
    else:
        selected.append(district)

    regions = setup.get("search.regions", [1])
    mode = setup.get("search.mode", "buy")
    keyboard = _build_district_keyboard(regions, mode, selected)
    await query.edit_message_reply_markup(reply_markup=keyboard)
    return SETUP_DISTRICTS


async def setup_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle price range input in setup flow."""
    text = update.message.text.strip()
    parsed = _parse_price_range(text)
    if parsed is None:
        await update.message.reply_text("格式錯誤，請輸入：最低-最高（例如：1000-3000）")
        return SETUP_PRICE

    price_min, price_max = parsed
    setup = context.user_data["setup"]
    setup["search.price_min"] = price_min
    setup["search.price_max"] = price_max

    mode = setup.get("search.mode", "buy")
    unit = "萬" if mode == "buy" else "元"
    regions = setup.get("search.regions", [1])
    region_name = _region_names(regions)

    summary = (
        f"設定摘要：\n"
        f"模式：{'買房' if mode == 'buy' else '租房'}\n"
        f"地區：{region_name}\n"
        f"區域：{', '.join(setup.get('search.districts', []))}\n"
        f"價格：{price_min:,}-{price_max:,} {unit}\n\n"
        f"確認開始？"
    )
    keyboard = [
        [
            InlineKeyboardButton("確認", callback_data="setup_confirm:yes"),
            InlineKeyboardButton("取消", callback_data="setup_confirm:no"),
        ]
    ]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
    return SETUP_CONFIRM


async def setup_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle setup confirmation."""
    query = update.callback_query
    await query.answer()

    if query.data == "setup_confirm:no":
        await query.edit_message_text("已取消設定。隨時輸入 /start 重新開始。")
        context.user_data.pop("setup", None)
        return ConversationHandler.END

    db_config: DbConfig = context.bot_data["db_config"]
    setup = context.user_data.pop("setup", {})

    # Ensure telegram credentials from env are stored in DB
    chat_id = context.bot_data.get("chat_id")
    if chat_id:
        setup["telegram.chat_id"] = chat_id
    bot_token = context.bot.token
    if bot_token:
        setup["telegram.bot_token"] = bot_token

    db_config.set_many(setup)

    await query.edit_message_text(
        "設定完成！已開始自動排程。\n\n"
        "可用指令：\n"
        "/settings - 修改設定\n"
        "/status - 查看狀態\n"
        "/run - 手動執行"
    )

    # Start scheduler if not already running
    _ensure_scheduler(context)

    return ConversationHandler.END


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command."""
    db_config: DbConfig = context.bot_data["db_config"]
    storage: Storage = context.bot_data["storage"]

    if not db_config.has_config():
        await update.message.reply_text("尚未設定，請先執行 /start")
        return

    mode = db_config.get("search.mode", "buy")
    regions = db_config.get("search.regions", [1])
    districts = db_config.get("search.districts", [])
    price_min = db_config.get("search.price_min", 0)
    price_max = db_config.get("search.price_max", 0)
    min_ping = db_config.get("search.min_ping")
    kw_include = db_config.get("search.keywords_include", [])
    kw_exclude = db_config.get("search.keywords_exclude", [])
    interval = db_config.get("scheduler.interval_minutes", 30)
    last_run = db_config.get("scheduler.last_run_at", "未執行")
    last_status = db_config.get("scheduler.last_run_status", "-")

    unit = "萬" if mode == "buy" else "元"
    region_name = _region_names(regions)
    district_names = ", ".join(districts)

    total = storage.get_listing_count()
    unnotified = storage.get_unnotified_count()

    paused = db_config.get("scheduler.paused", False)
    schedule_status = "已暫停" if paused else f"每 {interval} 分鐘"

    lines = [
        f"模式：{'買房' if mode == 'buy' else '租房'}",
        f"地區：{region_name}",
        f"區域：{district_names}",
        f"價格：{price_min:,}-{price_max:,} {unit}",
    ]
    if min_ping:
        lines.append(f"最小坪數：{min_ping} 坪")
    if kw_include:
        lines.append(f"包含關鍵字：{', '.join(kw_include)}")
    if kw_exclude:
        lines.append(f"排除關鍵字：{', '.join(kw_exclude)}")

    lines.extend([
        "",
        f"排程：{schedule_status}",
        f"上次執行：{last_run}",
        f"執行狀態：{last_status}",
        "",
        f"物件總數：{total}",
        f"未通知：{unnotified}",
    ])

    await update.message.reply_text("\n".join(lines))


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /run command — manual pipeline trigger."""
    global _pipeline_running
    if _pipeline_running:
        await update.message.reply_text("Pipeline 正在執行中，請稍候")
        return

    await update.message.reply_text("開始執行...")
    result = await _run_pipeline(context)
    await update.message.reply_text(result)


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pause command."""
    db_config: DbConfig = context.bot_data["db_config"]

    if db_config.get("scheduler.paused", False):
        await update.message.reply_text("已經處於暫停狀態")
        return

    db_config.set("scheduler.paused", True)
    jobs = context.job_queue.get_jobs_by_name("pipeline")
    for job in jobs:
        job.schedule_removal()

    await update.message.reply_text("已暫停自動執行")


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /resume command."""
    db_config: DbConfig = context.bot_data["db_config"]

    if not db_config.get("scheduler.paused", False):
        await update.message.reply_text("排程已在執行中")
        return

    db_config.set("scheduler.paused", False)
    _ensure_scheduler(context)

    interval = db_config.get("scheduler.interval_minutes", 30)
    await update.message.reply_text(f"已恢復自動執行，每 {interval} 分鐘執行一次")


async def cmd_loglevel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /loglevel command."""
    if not context.args:
        current = logging.getLogger().level
        level_name = logging.getLevelName(current)
        await update.message.reply_text(
            f"當前 log level：{level_name}\n"
            "用法：/loglevel DEBUG|INFO|WARNING|ERROR"
        )
        return

    level = context.args[0].upper()
    try:
        set_log_level(level)
        await update.message.reply_text(f"Log level 已更新為: {level}")
    except ValueError:
        await update.message.reply_text(f"無效的 log level：{level}\n可用：DEBUG, INFO, WARNING, ERROR")


# =============================================================================
# Settings handlers
# =============================================================================

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /settings command — show settings menu."""
    keyboard = [
        [
            InlineKeyboardButton("模式", callback_data="settings:mode"),
            InlineKeyboardButton("區域", callback_data="settings:districts"),
        ],
        [
            InlineKeyboardButton("價格", callback_data="settings:price"),
            InlineKeyboardButton("坪數", callback_data="settings:size"),
        ],
        [
            InlineKeyboardButton("關鍵字", callback_data="settings:keywords"),
            InlineKeyboardButton("頁數", callback_data="settings:pages"),
        ],
        [
            InlineKeyboardButton("排程", callback_data="settings:schedule"),
        ],
    ]
    await update.message.reply_text(
        "設定選單：", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SETTINGS_MENU


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Route settings menu button presses."""
    query = update.callback_query
    await query.answer()
    data = query.data

    db_config: DbConfig = context.bot_data["db_config"]

    if data == "settings:mode":
        mode = db_config.get("search.mode", "buy")
        keyboard = [
            [
                InlineKeyboardButton(
                    f"{'✅ ' if mode == 'buy' else ''}買房",
                    callback_data="set_mode:buy",
                ),
                InlineKeyboardButton(
                    f"{'✅ ' if mode == 'rent' else ''}租房",
                    callback_data="set_mode:rent",
                ),
            ]
        ]
        await query.edit_message_text("選擇搜尋模式：", reply_markup=InlineKeyboardMarkup(keyboard))
        return SETTINGS_MENU

    elif data == "settings:districts":
        selected = db_config.get("search.districts", [])
        regions = db_config.get("search.regions", [1])
        mode = db_config.get("search.mode", "buy")
        context.user_data["_selected_districts"] = list(selected)
        keyboard = _build_district_keyboard(regions, mode, selected)
        if keyboard is None:
            await query.edit_message_text("目前地區不支援區域選擇。")
            return ConversationHandler.END
        await query.edit_message_text("點擊切換區域，完成後按確認：", reply_markup=keyboard)
        return SETTINGS_MENU

    elif data == "settings:price":
        mode = db_config.get("search.mode", "buy")
        unit = "萬" if mode == "buy" else "元"
        price_min = db_config.get("search.price_min", 0)
        price_max = db_config.get("search.price_max", 0)
        await query.edit_message_text(
            f"當前價格：{price_min:,}-{price_max:,} {unit}\n"
            f"請輸入新的價格範圍（格式：最低-最高）："
        )
        return SETTINGS_PRICE_INPUT

    elif data == "settings:size":
        min_ping = db_config.get("search.min_ping")
        current = f"{min_ping} 坪" if min_ping else "未設定"
        await query.edit_message_text(
            f"當前最小坪數：{current}\n"
            "請輸入最小坪數（輸入 0 取消限制）："
        )
        return SETTINGS_SIZE_INPUT

    elif data == "settings:keywords":
        logger.info("Entering keyword settings, returning SETTINGS_KW_MENU state")
        kw_include = db_config.get("search.keywords_include", [])
        kw_exclude = db_config.get("search.keywords_exclude", [])
        keyboard = _build_keyword_keyboard(kw_include, kw_exclude)
        await query.edit_message_text(
            "關鍵字設定\n點擊關鍵字可刪除，使用下方按鈕新增：",
            reply_markup=keyboard,
        )
        return SETTINGS_KW_MENU

    elif data == "settings:pages":
        max_pages = db_config.get("search.max_pages", 3)
        await query.edit_message_text(
            f"當前最大查看頁數：{max_pages}\n"
            "請輸入新的頁數（1-20）："
        )
        return SETTINGS_PAGES_INPUT

    elif data == "settings:schedule":
        interval = db_config.get("scheduler.interval_minutes", 30)
        await query.edit_message_text(
            f"當前排程間隔：{interval} 分鐘\n"
            "請輸入新的間隔（分鐘）："
        )
        return SETTINGS_SCHEDULE_INPUT

    return None


async def set_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle mode change from settings."""
    query = update.callback_query
    await query.answer()

    mode = query.data.split(":")[1]
    db_config: DbConfig = context.bot_data["db_config"]
    db_config.set("search.mode", mode)

    label = "買房" if mode == "buy" else "租房"
    summary = _config_summary(db_config)
    await query.edit_message_text(f"已更新搜尋模式為: {label}\n\n{summary}")
    return ConversationHandler.END


async def settings_district_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle district toggle from settings."""
    query = update.callback_query
    await query.answer()

    data = query.data
    selected = context.user_data.get("_selected_districts", [])

    if data == "district_confirm":
        if not selected:
            await query.answer("請至少選擇一個區域", show_alert=True)
            return SETTINGS_MENU

        db_config: DbConfig = context.bot_data["db_config"]
        db_config.set("search.districts", selected)
        context.user_data.pop("_selected_districts", None)

        names = ", ".join(selected)
        summary = _config_summary(db_config)
        await query.edit_message_text(f"已更新區域：{names}\n\n{summary}")
        return ConversationHandler.END

    district = data.replace("district_toggle:", "")
    if district in selected:
        selected.remove(district)
    else:
        selected.append(district)

    db_config: DbConfig = context.bot_data["db_config"]
    regions = db_config.get("search.regions", [1])
    mode = db_config.get("search.mode", "buy")
    keyboard = _build_district_keyboard(regions, mode, selected)
    await query.edit_message_reply_markup(reply_markup=keyboard)
    return SETTINGS_MENU


async def settings_price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle price input from settings."""
    text = update.message.text.strip()
    parsed = _parse_price_range(text)
    if parsed is None:
        await update.message.reply_text("格式錯誤，請輸入：最低-最高（例如：1000-3000）")
        return SETTINGS_PRICE_INPUT

    db_config: DbConfig = context.bot_data["db_config"]
    price_min, price_max = parsed
    db_config.set_many({"search.price_min": price_min, "search.price_max": price_max})

    mode = db_config.get("search.mode", "buy")
    unit = "萬" if mode == "buy" else "元"
    summary = _config_summary(db_config)
    await update.message.reply_text(f"已更新價格範圍：{price_min:,}-{price_max:,} {unit}\n\n{summary}")
    return ConversationHandler.END


async def settings_size_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle size input from settings."""
    text = update.message.text.strip()
    try:
        value = float(text)
    except ValueError:
        await update.message.reply_text("請輸入數字")
        return SETTINGS_SIZE_INPUT

    db_config: DbConfig = context.bot_data["db_config"]
    if value <= 0:
        db_config.set("search.min_ping", None)
        msg = "已取消最小坪數限制"
    else:
        db_config.set("search.min_ping", value)
        msg = f"已更新最小坪數：{value} 坪"

    summary = _config_summary(db_config)
    await update.message.reply_text(f"{msg}\n\n{summary}")
    return ConversationHandler.END


async def settings_kw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle all keyword panel button presses."""
    query = update.callback_query
    await query.answer()
    data = query.data

    logger.info("settings_kw_callback triggered with data: %s", data)
    db_config: DbConfig = context.bot_data["db_config"]

    if data == "kw_add_include":
        await query.edit_message_text("請輸入要包含的關鍵字（多個用逗號分隔，例如：電梯,車位）：")
        return SETTINGS_KW_INCLUDE_INPUT

    elif data == "kw_add_exclude":
        await query.edit_message_text("請輸入要排除的關鍵字（多個用逗號分隔，例如：頂加,工業宅）：")
        return SETTINGS_KW_EXCLUDE_INPUT

    elif data.startswith("kw_del_i:"):
        kw = data.replace("kw_del_i:", "")
        current = db_config.get("search.keywords_include", [])
        if kw in current:
            current.remove(kw)
            db_config.set("search.keywords_include", current)
        kw_exclude = db_config.get("search.keywords_exclude", [])
        keyboard = _build_keyword_keyboard(current, kw_exclude)
        await query.edit_message_text(
            f"已刪除包含關鍵字：{kw}\n\n點擊關鍵字可刪除，使用下方按鈕新增：",
            reply_markup=keyboard,
        )
        return SETTINGS_KW_MENU

    elif data.startswith("kw_del_e:"):
        kw = data.replace("kw_del_e:", "")
        current = db_config.get("search.keywords_exclude", [])
        if kw in current:
            current.remove(kw)
            db_config.set("search.keywords_exclude", current)
        kw_include = db_config.get("search.keywords_include", [])
        keyboard = _build_keyword_keyboard(kw_include, current)
        await query.edit_message_text(
            f"已刪除排除關鍵字：{kw}\n\n點擊關鍵字可刪除，使用下方按鈕新增：",
            reply_markup=keyboard,
        )
        return SETTINGS_KW_MENU

    elif data == "kw_clear":
        db_config.set_many({"search.keywords_include": [], "search.keywords_exclude": []})
        keyboard = _build_keyword_keyboard([], [])
        await query.edit_message_text(
            "已清除所有關鍵字\n\n點擊關鍵字可刪除，使用下方按鈕新增：",
            reply_markup=keyboard,
        )
        return SETTINGS_KW_MENU

    elif data == "kw_done":
        summary = _config_summary(db_config)
        await query.edit_message_text(f"關鍵字設定完成\n\n{summary}")
        return ConversationHandler.END

    # kw_noop — do nothing
    return SETTINGS_KW_MENU


async def settings_kw_include_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle include keyword input — add and return to panel."""
    text = update.message.text.strip()
    db_config: DbConfig = context.bot_data["db_config"]

    keywords = [kw.strip() for kw in text.split(",") if kw.strip()]
    if not keywords:
        await update.message.reply_text("請輸入至少一個關鍵字")
        return SETTINGS_KW_INCLUDE_INPUT

    current = db_config.get("search.keywords_include", [])
    new_kws = [kw for kw in keywords if kw not in current]
    if not new_kws:
        kw_exclude = db_config.get("search.keywords_exclude", [])
        keyboard = _build_keyword_keyboard(current, kw_exclude)
        await update.message.reply_text("此關鍵字已存在", reply_markup=keyboard)
        return SETTINGS_KW_MENU

    current.extend(new_kws)
    db_config.set("search.keywords_include", current)

    kw_exclude = db_config.get("search.keywords_exclude", [])
    keyboard = _build_keyword_keyboard(current, kw_exclude)
    await update.message.reply_text(
        f"已新增包含：{', '.join(new_kws)}\n\n點擊關鍵字可刪除，使用下方按鈕新增：",
        reply_markup=keyboard,
    )
    return SETTINGS_KW_MENU


async def settings_kw_exclude_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle exclude keyword input — add and return to panel."""
    text = update.message.text.strip()
    db_config: DbConfig = context.bot_data["db_config"]

    keywords = [kw.strip() for kw in text.split(",") if kw.strip()]
    if not keywords:
        await update.message.reply_text("請輸入至少一個關鍵字")
        return SETTINGS_KW_EXCLUDE_INPUT

    current = db_config.get("search.keywords_exclude", [])
    new_kws = [kw for kw in keywords if kw not in current]
    if not new_kws:
        kw_include = db_config.get("search.keywords_include", [])
        keyboard = _build_keyword_keyboard(kw_include, current)
        await update.message.reply_text("此關鍵字已存在", reply_markup=keyboard)
        return SETTINGS_KW_MENU

    current.extend(new_kws)
    db_config.set("search.keywords_exclude", current)

    kw_include = db_config.get("search.keywords_include", [])
    keyboard = _build_keyword_keyboard(kw_include, current)
    await update.message.reply_text(
        f"已新增排除：{', '.join(new_kws)}\n\n點擊關鍵字可刪除，使用下方按鈕新增：",
        reply_markup=keyboard,
    )
    return SETTINGS_KW_MENU


async def settings_pages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle max pages input from settings."""
    text = update.message.text.strip()
    try:
        pages = int(text)
        if pages < 1 or pages > 20:
            await update.message.reply_text("請輸入 1-20 之間的數字")
            return SETTINGS_PAGES_INPUT
    except ValueError:
        await update.message.reply_text("請輸入數字（1-20）")
        return SETTINGS_PAGES_INPUT

    db_config: DbConfig = context.bot_data["db_config"]
    db_config.set("search.max_pages", pages)
    summary = _config_summary(db_config)
    await update.message.reply_text(f"已更新最大查看頁數：{pages}\n\n{summary}")
    return ConversationHandler.END


async def settings_schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle schedule interval input from settings."""
    text = update.message.text.strip()
    try:
        minutes = int(text)
        if minutes < 5:
            await update.message.reply_text("最小間隔為 5 分鐘")
            return SETTINGS_SCHEDULE_INPUT
    except ValueError:
        await update.message.reply_text("請輸入數字（分鐘）")
        return SETTINGS_SCHEDULE_INPUT

    db_config: DbConfig = context.bot_data["db_config"]
    db_config.set("scheduler.interval_minutes", minutes)

    # Rebuild scheduler
    jobs = context.job_queue.get_jobs_by_name("pipeline")
    for job in jobs:
        job.schedule_removal()

    if not db_config.get("scheduler.paused", False):
        _ensure_scheduler(context)

    summary = _config_summary(db_config)
    await update.message.reply_text(f"排程已更新：每 {minutes} 分鐘執行一次\n\n{summary}")
    return ConversationHandler.END


# =============================================================================
# Pipeline execution
# =============================================================================

async def _run_pipeline(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Run the scrape → match → notify pipeline. Returns result message."""
    global _pipeline_running
    _pipeline_running = True

    db_config: DbConfig = context.bot_data["db_config"]
    storage: Storage = context.bot_data["storage"]

    try:
        config = db_config.build_config()
    except ValueError as e:
        _pipeline_running = False
        return f"設定不完整：{e}"

    start_time = datetime.now(timezone.utc)
    scraped = 0
    new_count = 0
    matched_count = 0
    sent = 0

    try:
        logger.info("Pipeline started")

        # Scrape
        raw_listings = await asyncio.to_thread(scrape_listings, config)
        scraped = len(raw_listings)
        for raw in raw_listings:
            normalized = normalize_591_listing(raw)
            if storage.insert_listing(normalized):
                new_count += 1

        logger.info("Scrape complete: %d new out of %d", new_count, scraped)

        # Match
        matched = find_matching_listings(config, storage)

        # Enrich buy listings
        if config.search.mode == "buy" and matched:
            matched_ids = [m["listing_id"] for m in matched]
            unenriched = storage.get_unenriched_listing_ids(matched_ids)
            if unenriched:
                logger.info("Enriching %d listings...", len(unenriched))
                session, headers = await asyncio.to_thread(
                    _get_buy_session_headers, config
                )
                details = await asyncio.to_thread(
                    enrich_buy_listings, config, session, headers, unenriched
                )
                for lid, detail in details.items():
                    storage.update_listing_detail("591", lid, detail)
                matched = find_matching_listings(config, storage)

        matched_count = len(matched)

        # Notify
        if matched:
            sent = await send_notifications(config, storage, matched)

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(
            "Pipeline completed: scraped=%d, new=%d, matched=%d, notified=%d, duration=%.1fs",
            scraped, new_count, matched_count, sent, duration,
        )

        db_config.set("scheduler.last_run_at", start_time.isoformat())
        db_config.set("scheduler.last_run_status", "success")

        return f"完成！爬取 {scraped} 筆，新增 {new_count} 筆，符合 {matched_count} 筆，通知 {sent} 筆"

    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)
        db_config.set("scheduler.last_run_at", start_time.isoformat())
        db_config.set("scheduler.last_run_status", f"error: {e}")
        return f"執行失敗：{e}"

    finally:
        _pipeline_running = False


async def _scheduled_pipeline(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job callback for scheduled pipeline execution."""
    logger.info("Scheduled pipeline run starting")
    result = await _run_pipeline(context)
    logger.info("Scheduled pipeline result: %s", result)

    # Send result to chat
    db_config: DbConfig = context.bot_data["db_config"]
    chat_id = db_config.get("telegram.chat_id")
    if chat_id:
        try:
            await context.bot.send_message(chat_id=int(chat_id), text=f"[自動排程] {result}")
        except Exception as e:
            logger.error("Failed to send scheduled result: %s", e)


# =============================================================================
# Helpers
# =============================================================================

def _config_summary(db_config: DbConfig) -> str:
    """Build a short config summary string."""
    mode = db_config.get("search.mode", "buy")
    regions = db_config.get("search.regions", [1])
    districts = db_config.get("search.districts", [])
    price_min = db_config.get("search.price_min", 0)
    price_max = db_config.get("search.price_max", 0)
    min_ping = db_config.get("search.min_ping")
    kw_include = db_config.get("search.keywords_include", [])
    kw_exclude = db_config.get("search.keywords_exclude", [])
    max_pages = db_config.get("search.max_pages", 3)
    interval = db_config.get("scheduler.interval_minutes", 30)
    paused = db_config.get("scheduler.paused", False)

    unit = "萬" if mode == "buy" else "元"
    region_name = _region_names(regions)

    lines = [
        "── 當前設定 ──",
        f"模式：{'買房' if mode == 'buy' else '租房'}",
        f"地區：{region_name}",
        f"區域：{', '.join(districts) if districts else '未設定'}",
        f"價格：{price_min:,}-{price_max:,} {unit}",
    ]
    if min_ping:
        lines.append(f"坪數：≥ {min_ping} 坪")
    if kw_include:
        lines.append(f"包含：{', '.join(kw_include)}")
    if kw_exclude:
        lines.append(f"排除：{', '.join(kw_exclude)}")
    lines.append(f"頁數：{max_pages}")
    schedule_status = "已暫停" if paused else f"每 {interval} 分鐘"
    lines.append(f"排程：{schedule_status}")
    return "\n".join(lines)


def _region_names(region_ids: list[int]) -> str:
    """Convert a list of region IDs to a comma-separated Chinese name string."""
    return ", ".join(_REGION_ID_TO_NAME.get(r, str(r)) for r in region_ids)


def _build_keyword_keyboard(
    kw_include: list[str],
    kw_exclude: list[str],
) -> InlineKeyboardMarkup:
    """Build keyword management inline keyboard.

    Shows existing keywords as deletable buttons, plus action buttons.
    """
    buttons = []

    if not kw_include and not kw_exclude:
        buttons.append([InlineKeyboardButton("尚無關鍵字", callback_data="kw_noop")])
    else:
        for kw in kw_include:
            buttons.append([InlineKeyboardButton(
                f"✅ 包含：{kw}  ✕",
                callback_data=f"kw_del_i:{kw}",
            )])
        for kw in kw_exclude:
            buttons.append([InlineKeyboardButton(
                f"🚫 排除：{kw}  ✕",
                callback_data=f"kw_del_e:{kw}",
            )])

    action_row = [
        InlineKeyboardButton("➕ 包含", callback_data="kw_add_include"),
        InlineKeyboardButton("➖ 排除", callback_data="kw_add_exclude"),
    ]
    buttons.append(action_row)

    bottom_row = []
    if kw_include or kw_exclude:
        bottom_row.append(InlineKeyboardButton("🗑 清除", callback_data="kw_clear"))
    bottom_row.append(InlineKeyboardButton("✅ 完成", callback_data="kw_done"))
    buttons.append(bottom_row)

    return InlineKeyboardMarkup(buttons)


def _build_district_keyboard(
    region_ids: list[int],
    mode: str,
    selected: list[str],
) -> InlineKeyboardMarkup | None:
    """Build district selection inline keyboard for given regions and mode.

    Merges districts from all provided regions.
    Returns None if no districts are available for the region/mode combination.
    """
    section_map: dict[str, int] = {}
    for region_id in region_ids:
        if mode == "buy":
            section_map.update(BUY_SECTION_CODES.get(region_id, {}))
        else:
            section_map.update(RENT_SECTION_CODES.get(region_id, {}))

    if not section_map:
        return None

    all_districts = list(section_map.keys())
    buttons = []
    row = []
    for district in all_districts:
        prefix = "✅ " if district in selected else ""
        label = f"{prefix}{district}"
        row.append(InlineKeyboardButton(label, callback_data=f"district_toggle:{district}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("確認", callback_data="district_confirm")])
    return InlineKeyboardMarkup(buttons)


def _parse_price_range(text: str) -> tuple[int, int] | None:
    """Parse 'min-max' price range text. Returns (min, max) or None."""
    text = text.replace(",", "").replace("，", "").strip()
    parts = text.split("-")
    if len(parts) != 2:
        return None
    try:
        low = int(parts[0].strip())
        high = int(parts[1].strip())
        if low >= high or low < 0:
            return None
        return (low, high)
    except ValueError:
        return None


def _ensure_scheduler(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ensure pipeline scheduler job is running."""
    db_config: DbConfig = context.bot_data["db_config"]
    interval = db_config.get("scheduler.interval_minutes", 30)

    existing = context.job_queue.get_jobs_by_name("pipeline")
    for job in existing:
        job.schedule_removal()

    if not db_config.get("scheduler.paused", False):
        context.job_queue.run_repeating(
            _scheduled_pipeline,
            interval=interval * 60,
            first=10,  # first run 10s after start
            name="pipeline",
        )
        logger.info("Scheduler started: every %d minutes", interval)


# =============================================================================
# Application builder
# =============================================================================

def create_application(
    bot_token: str,
    chat_id: str,
    storage: Storage,
    db_config: DbConfig,
) -> Application:
    """Build and configure the Telegram Bot Application."""

    auth = _auth_filter(chat_id)

    # Setup ConversationHandler for /start first-time flow
    setup_conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start, filters=auth)],
        states={
            SETUP_TEMPLATE: [
                CallbackQueryHandler(setup_choose_callback, pattern=r"^setup_choose:"),
                CallbackQueryHandler(setup_template_callback, pattern=r"^setup_tpl:"),
            ],
            SETUP_MODE: [CallbackQueryHandler(setup_mode_callback, pattern=r"^setup_mode:")],
            SETUP_REGION: [MessageHandler(auth & filters.TEXT & ~filters.COMMAND, setup_region_input)],
            SETUP_DISTRICTS: [CallbackQueryHandler(setup_districts_callback, pattern=r"^district_")],
            SETUP_PRICE: [MessageHandler(auth & filters.TEXT & ~filters.COMMAND, setup_price_input)],
            SETUP_CONFIRM: [CallbackQueryHandler(setup_confirm_callback, pattern=r"^setup_confirm:")],
        },
        fallbacks=[CommandHandler("start", cmd_start, filters=auth)],
    )

    # Settings ConversationHandler for text input states
    settings_conv = ConversationHandler(
        entry_points=[CommandHandler("settings", cmd_settings, filters=auth)],
        states={
            SETTINGS_MENU: [
                CallbackQueryHandler(settings_callback, pattern=r"^settings:"),
                CallbackQueryHandler(set_mode_callback, pattern=r"^set_mode:"),
                CallbackQueryHandler(settings_district_callback, pattern=r"^district_"),
            ],
            SETTINGS_PRICE_INPUT: [
                MessageHandler(auth & filters.TEXT & ~filters.COMMAND, settings_price_handler),
            ],
            SETTINGS_SIZE_INPUT: [
                MessageHandler(auth & filters.TEXT & ~filters.COMMAND, settings_size_handler),
            ],
            SETTINGS_KW_MENU: [
                CallbackQueryHandler(settings_kw_callback, pattern=r"^kw_"),
            ],
            SETTINGS_KW_INCLUDE_INPUT: [
                MessageHandler(auth & filters.TEXT & ~filters.COMMAND, settings_kw_include_handler),
            ],
            SETTINGS_KW_EXCLUDE_INPUT: [
                MessageHandler(auth & filters.TEXT & ~filters.COMMAND, settings_kw_exclude_handler),
            ],
            SETTINGS_SCHEDULE_INPUT: [
                MessageHandler(auth & filters.TEXT & ~filters.COMMAND, settings_schedule_handler),
            ],
            SETTINGS_PAGES_INPUT: [
                MessageHandler(auth & filters.TEXT & ~filters.COMMAND, settings_pages_handler),
            ],
        },
        fallbacks=[CommandHandler("settings", cmd_settings, filters=auth)],
        map_to_parent={},
    )

    app = Application.builder().token(bot_token).build()

    # Store shared objects
    app.bot_data["storage"] = storage
    app.bot_data["db_config"] = db_config
    app.bot_data["chat_id"] = chat_id

    # Register handlers
    app.add_handler(setup_conv)
    app.add_handler(settings_conv)
    # settings_callback, set_mode_callback, and settings_district_callback are now in settings_conv
    app.add_handler(CommandHandler("status", cmd_status, filters=auth))
    app.add_handler(CommandHandler("run", cmd_run, filters=auth))
    app.add_handler(CommandHandler("pause", cmd_pause, filters=auth))
    app.add_handler(CommandHandler("resume", cmd_resume, filters=auth))
    app.add_handler(CommandHandler("loglevel", cmd_loglevel, filters=auth))

    return app


def run_bot(bot_token: str, chat_id: str, db_path: str) -> None:
    """Start the bot with long-polling."""
    storage = Storage(db_path)
    db_config = DbConfig(storage.conn)

    # Always sync telegram credentials from env to DB
    db_config.set_many({
        "telegram.bot_token": bot_token,
        "telegram.chat_id": chat_id,
    })

    app = create_application(bot_token, chat_id, storage, db_config)

    # Start scheduler if config exists and not paused
    if db_config.has_config() and not db_config.get("scheduler.paused", False):
        # Will be started in post_init
        pass

    async def post_init(application: Application) -> None:
        await application.bot.set_my_commands([
            BotCommand("start", "開始設定 / 重新設定"),
            BotCommand("settings", "修改設定"),
            BotCommand("status", "查看狀態"),
            BotCommand("run", "手動執行"),
            BotCommand("pause", "暫停排程"),
            BotCommand("resume", "恢復排程"),
            BotCommand("loglevel", "調整日誌等級"),
        ])
        _ensure_scheduler(application)
        logger.info("Bot started")

    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

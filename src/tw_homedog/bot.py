"""Telegram Bot interactive interface for tw-homedog."""

import asyncio
import json
import logging
import re
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
from tw_homedog.notifier import format_listing_message
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
    SETTINGS_YEAR_INPUT,
    CONFIG_IMPORT_INPUT,
    SETTINGS_MENU,
    SETTINGS_KW_MENU,
    SETTINGS_KW_INCLUDE_INPUT,
    SETTINGS_KW_EXCLUDE_INPUT,
    SETTINGS_SCHEDULE_INPUT,
    SETTINGS_PAGES_INPUT,
    SETTINGS_REGION_INPUT,
) = range(17)

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
            "/list - 瀏覽未讀物件\n"
            "/settings - 修改設定\n"
            "/status - 查看狀態\n"
            "/favorites - 查看最愛\n"
            "/run - 手動執行\n"
            "/pause - 暫停排程\n"
            "/resume - 恢復排程\n"
            "/loglevel - 調整日誌等級\n"
            "/config_export - 匯出設定\n"
            "/config_import - 匯入設定",
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
    max_ping = db_config.get("search.max_ping")
    room_counts = db_config.get("search.room_counts", [])
    bath_counts = db_config.get("search.bathroom_counts", [])
    year_min = db_config.get("search.year_built_min")
    year_max = db_config.get("search.year_built_max")
    kw_include = db_config.get("search.keywords_include", [])
    kw_exclude = db_config.get("search.keywords_exclude", [])
    interval = db_config.get("scheduler.interval_minutes", 30)
    last_run = db_config.get("scheduler.last_run_at", "未執行")
    last_status = db_config.get("scheduler.last_run_status", "-")

    unit = "萬" if mode == "buy" else "元"
    region_name = _region_names(regions)
    district_names = ", ".join(districts)

    total = storage.get_listing_count()
    unread = storage.get_unread_count()

    paused = db_config.get("scheduler.paused", False)
    schedule_status = "已暫停" if paused else f"每 {interval} 分鐘"

    lines = [
        f"模式：{'買房' if mode == 'buy' else '租房'}",
        f"地區：{region_name}",
        f"區域：{district_names}",
        f"價格：{price_min:,}-{price_max:,} {unit}",
    ]
    if min_ping or max_ping:
        if min_ping and max_ping:
            lines.append(f"坪數：{min_ping}-{max_ping} 坪")
        elif min_ping:
            lines.append(f"坪數：≥ {min_ping} 坪")
        elif max_ping:
            lines.append(f"坪數：≤ {max_ping} 坪")
    if room_counts:
        lines.append(f"房數：{', '.join(str(x) for x in room_counts)} 房")
    if bath_counts:
        lines.append(f"衛數：{', '.join(str(x) for x in bath_counts)} 衛")
    if year_min or year_max:
        if year_min and year_max:
            lines.append(f"屋齡：{year_min}-{year_max} 年建")
        elif year_min:
            lines.append(f"屋齡：≥ {year_min} 年建")
        elif year_max:
            lines.append(f"屋齡：≤ {year_max} 年建")
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
        f"未讀：{unread}",
    ])

    await update.message.reply_text("\n".join(lines))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show command summary."""
    await update.message.reply_text(
        "可用指令：\n"
        "/start - 引導/重新設定\n"
        "/list - 瀏覽未讀物件\n"
        "/settings - 修改設定\n"
        "/status - 查看狀態\n"
        "/run - 手動執行\n"
        "/pause - 暫停排程\n"
        "/resume - 恢復排程\n"
        "/loglevel - 調整日誌等級\n"
        "/config_export - 匯出設定\n"
        "/config_import - 匯入設定"
    )


async def cmd_config_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Export current config as JSON for backup."""
    db_config: DbConfig = context.bot_data["db_config"]
    data = db_config.get_all()
    text = json.dumps(data, ensure_ascii=False, indent=2)
    await update.message.reply_text(
        "設定匯出（JSON）：\n```json\n" + text + "\n```",
        parse_mode="Markdown",
    )


async def cmd_config_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to paste JSON config to import."""
    await update.message.reply_text(
        "請貼上由 /config_export 產出的 JSON（會覆蓋同名鍵）。"
    )
    return CONFIG_IMPORT_INPUT


async def config_import_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle pasted JSON config import."""
    db_config: DbConfig = context.bot_data["db_config"]
    text = update.message.text.strip()
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("需為 JSON 物件")
    except Exception as e:
        await update.message.reply_text(f"解析失敗：{e}\n請重新輸入或取消。")
        return CONFIG_IMPORT_INPUT

    try:
        db_config.set_many(data)
    except Exception as e:
        await update.message.reply_text(f"寫入失敗：{e}")
        return CONFIG_IMPORT_INPUT

    await update.message.reply_text("設定已匯入完成。")
    return ConversationHandler.END


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
            InlineKeyboardButton("地區", callback_data="settings:region"),
        ],
        [
            InlineKeyboardButton("區域", callback_data="settings:districts"),
        ],
        [
            InlineKeyboardButton("價格", callback_data="settings:price"),
            InlineKeyboardButton("坪數", callback_data="settings:size"),
        ],
        [
            InlineKeyboardButton("格局", callback_data="settings:layout"),
            InlineKeyboardButton("屋齡", callback_data="settings:year"),
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

    elif data == "settings:region":
        regions = db_config.get("search.regions", [])
        current = _region_names(regions) if regions else "未設定"
        region_list = ", ".join(REGION_CODES.keys())
        await query.edit_message_text(
            f"當前地區：{current}\n"
            f"請輸入地區（多個地區用逗號分隔，例如：台北市,新北市）：\n\n"
            f"支援的地區：{region_list}"
        )
        return SETTINGS_REGION_INPUT

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
        max_ping = db_config.get("search.max_ping")
        if min_ping and max_ping:
            current = f"{min_ping}-{max_ping} 坪"
        elif min_ping:
            current = f"≥ {min_ping} 坪"
        elif max_ping:
            current = f"≤ {max_ping} 坪"
        else:
            current = "未設定"
        await query.edit_message_text(
            f"當前坪數範圍：{current}\n"
            "請輸入坪數範圍（格式：最小-最大，0 代表不限，僅輸入一個數值表示最小值）："
        )
        return SETTINGS_SIZE_INPUT

    elif data == "settings:year":
        year_min = db_config.get("search.year_built_min")
        year_max = db_config.get("search.year_built_max")
        if year_min and year_max:
            current = f"{year_min}-{year_max} 年"
        elif year_min:
            current = f"≥ {year_min} 年"
        elif year_max:
            current = f"≤ {year_max} 年"
        else:
            current = "未設定"
        await query.edit_message_text(
            f"當前屋齡（建造年份）範圍：{current}\n"
            "請輸入年份範圍（格式：YYYY-YYYY，0 代表不限，僅輸入一個年份表示最小值）："
        )
        return SETTINGS_YEAR_INPUT

    elif data == "settings:layout":
        room_counts = db_config.get("search.room_counts", [])
        bath_counts = db_config.get("search.bathroom_counts", [])
        keyboard = _build_layout_keyboard(room_counts, bath_counts)
        await query.edit_message_text("選擇房/衛數（可多選）：", reply_markup=keyboard)
        return SETTINGS_MENU

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


async def settings_region_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle region text input from settings."""
    text = update.message.text.strip()
    parts = [p.strip() for p in text.split(",") if p.strip()]

    regions = []
    for part in parts:
        try:
            regions.append(resolve_region(int(part) if part.isdigit() else part))
        except (ValueError, TypeError):
            region_list = ", ".join(REGION_CODES.keys())
            await update.message.reply_text(
                f"無效的地區：{part}\n請輸入中文名或代碼，多個地區用逗號分隔。\n支援的地區：{region_list}"
            )
            return SETTINGS_REGION_INPUT

    if not regions:
        await update.message.reply_text("請至少輸入一個地區")
        return SETTINGS_REGION_INPUT

    db_config: DbConfig = context.bot_data["db_config"]
    db_config.set("search.regions", regions)

    region_name = _region_names(regions)
    summary = _config_summary(db_config)
    await update.message.reply_text(f"已更新地區：{region_name}\n\n{summary}")
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


def _parse_range(text: str) -> tuple[float | None, float | None] | None:
    """Parse 'min-max' ranges; allows single value (treated as min), 0 for no bound."""
    text = text.replace("，", "-").replace(" ", "")
    parts = text.split("-")
    if len(parts) == 1:
        try:
            val = float(parts[0])
        except ValueError:
            return None
        min_val = None if val == 0 else val
        return (min_val, None)
    if len(parts) != 2:
        return None
    try:
        low = float(parts[0]) if parts[0] else 0.0
        high = float(parts[1]) if parts[1] else 0.0
    except ValueError:
        return None
    min_val = None if low == 0 else low
    max_val = None if high == 0 else high
    if min_val is not None and max_val is not None and min_val > max_val:
        return None
    return (min_val, max_val)


async def settings_size_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle size input from settings (min-max)."""
    text = update.message.text.strip()
    parsed = _parse_range(text)
    if parsed is None:
        await update.message.reply_text("格式錯誤，請輸入：最小-最大（0 表示不限，例如 20-40 或 25 或 0-35）")
        return SETTINGS_SIZE_INPUT

    min_ping, max_ping = parsed
    db_config: DbConfig = context.bot_data["db_config"]
    db_config.set_many({"search.min_ping": min_ping, "search.max_ping": max_ping})

    if min_ping and max_ping:
        msg = f"已更新坪數：{min_ping}-{max_ping} 坪"
    elif min_ping:
        msg = f"已更新坪數下限：{min_ping} 坪"
    elif max_ping:
        msg = f"已更新坪數上限：{max_ping} 坪"
    else:
        msg = "已取消坪數限制"

    summary = _config_summary(db_config)
    await update.message.reply_text(f"{msg}\n\n{summary}")
    return ConversationHandler.END


async def settings_year_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle build year input from settings (min-max)."""
    text = update.message.text.strip()
    parsed = _parse_range(text)
    if parsed is None:
        await update.message.reply_text("格式錯誤，請輸入：YYYY-YYYY（0 表示不限，例如 2000-2015 或 2010 或 0-2005）")
        return SETTINGS_YEAR_INPUT

    year_min, year_max = parsed
    # Ensure integers
    if year_min is not None:
        year_min = int(year_min)
    if year_max is not None:
        year_max = int(year_max)
    if year_min is not None and year_max is not None and year_min > year_max:
        await update.message.reply_text("最小年份需小於或等於最大年份，請重新輸入")
        return SETTINGS_YEAR_INPUT

    db_config: DbConfig = context.bot_data["db_config"]
    db_config.set_many({"search.year_built_min": year_min, "search.year_built_max": year_max})

    if year_min and year_max:
        msg = f"已更新屋齡（建造年份）：{year_min}-{year_max}"
    elif year_min:
        msg = f"已更新屋齡下限（建造年份）：≥ {year_min}"
    elif year_max:
        msg = f"已更新屋齡上限（建造年份）：≤ {year_max}"
    else:
        msg = "已取消屋齡限制"

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


async def layout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle layout (room/bath) toggles."""
    query = update.callback_query
    await query.answer()
    data = query.data

    db_config: DbConfig = context.bot_data["db_config"]
    rooms = set(db_config.get("search.room_counts", []) or [])
    baths = set(db_config.get("search.bathroom_counts", []) or [])

    if data == "layout:clear":
        rooms.clear()
        baths.clear()
    elif data == "layout:done":
        summary = _config_summary(db_config)
        await query.edit_message_text(f"格局設定完成\n\n{summary}")
        return ConversationHandler.END
    else:
        parts = data.split(":")
        if len(parts) == 3:
            kind, val = parts[1], parts[2]
            try:
                num = int(val)
            except ValueError:
                num = None
            if num:
                if kind == "r":
                    if num in rooms:
                        rooms.remove(num)
                    else:
                        rooms.add(num)
                elif kind == "b":
                    if num in baths:
                        baths.remove(num)
                    else:
                        baths.add(num)

    db_config.set_many(
        {
            "search.room_counts": sorted(rooms),
            "search.bathroom_counts": sorted(baths),
        }
    )
    keyboard = _build_layout_keyboard(sorted(rooms), sorted(baths))
    await query.edit_message_text("選擇房/衛數（可多選）：", reply_markup=keyboard)
    return SETTINGS_MENU


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
# Listing browser (/list)
# =============================================================================

LIST_PAGE_SIZE = 5


def _filter_matched(listings: list[dict], config, district_filter: str | None = None) -> list[dict]:
    """Apply matcher filters to listings."""
    from tw_homedog.matcher import (
        match_price,
        match_district,
        match_size,
        match_keywords,
        match_room,
        match_bathroom,
        match_build_year,
    )

    result = []
    for listing in listings:
        if not match_price(listing, config):
            continue
        if not match_district(listing, config):
            continue
        if not match_size(listing, config):
            continue
        if not match_room(listing, config):
            continue
        if not match_bathroom(listing, config):
            continue
        if not match_build_year(listing, config):
            continue
        if not match_keywords(listing, config):
            continue
        if district_filter and listing.get("district") != district_filter:
            continue
        result.append(listing)
    return result


def _get_matched(
    storage: Storage,
    db_config: DbConfig,
    district_filter: str | None = None,
    include_read: bool = False,
    only_favorites: bool = False,
) -> list[dict]:
    """Get listings for list/favorites with optional read/favorite flags."""
    try:
        config = db_config.build_config()
    except ValueError:
        return []

    if only_favorites:
        listings = storage.get_favorites()
        # 可選擇用 district 篩選，其他條件不過濾，方便「收藏即保留」
        if district_filter:
            listings = [l for l in listings if (l.get("district") or "") == district_filter]
    else:
        if include_read:
            listings = storage.get_listings_with_read_status()
        else:
            listings = storage.get_unread_listings()
            for l in listings:
                l["is_read"] = False
        listings = _filter_matched(listings, config, district_filter)

    # Enrich buy listings on the fly so community/age fields are available in list view
    if not only_favorites and config.search.mode == "buy" and listings:
        matched_ids = [m["listing_id"] for m in listings]
        unenriched = storage.get_unenriched_listing_ids(matched_ids)
        if unenriched:
            try:
                session, headers = _get_buy_session_headers(config)
                details = enrich_buy_listings(config, session, headers, unenriched)
                for lid, detail in details.items():
                    storage.update_listing_detail("591", lid, detail)
                # re-fetch to reflect enrichment & read status
                if include_read:
                    listings = storage.get_listings_with_read_status()
                    listings = _filter_matched(listings, config, district_filter)
                else:
                    listings = storage.get_unread_listings()
                    for l in listings:
                        l["is_read"] = False
                    listings = _filter_matched(listings, config, district_filter)
            except Exception as e:
                logger.warning("Enrich failed during list retrieval: %s", e)

    # Mark favorites flag if needed for general lists
    if not only_favorites:
        for l in listings:
            l["is_favorite"] = storage.is_favorite("591", l["listing_id"])

    return listings


def _build_list_keyboard(
    listings: list[dict],
    offset: int,
    total: int,
    mode: str,
    district_filter: str | None = None,
    show_read: bool = False,
    context: str = "list",
) -> InlineKeyboardMarkup:
    """Build paginated listing list inline keyboard."""
    buttons = []
    def _fill_location_fields(listing: dict):
        if not listing.get("community_name"):
            title = listing.get("title") or ""
            m = re.search(r"([\w\u4e00-\u9fff]+社區)", title)
            if m:
                listing["community_name"] = m.group(1)
    for listing in listings:
        _fill_location_fields(listing)
        district = listing.get("district") or "?"
        price = listing.get("price")
        size = listing.get("size_ping")
        if mode == "buy":
            price_str = f"{price:,}萬" if price else "?"
        else:
            price_str = f"{price:,}元" if price else "?"
        size_str = f"{size}坪" if size else ""
        community = listing.get("community_name") or ""
        address = listing.get("address") or listing.get("address_zh") or ""
        layout = listing.get("room") or listing.get("shape_name") or ""
        age = listing.get("houseage") or ""
        title = listing.get("title") or ""

        location_str = " / ".join([p for p in (community, address) if p])
        label_parts = [
            district,
            price_str,
            size_str,
            location_str,
            layout,
            age,
        ]
        label_main = " · ".join([p for p in label_parts if p])
        prefix = ""
        if listing.get("is_favorite"):
            prefix += "⭐ "
        if listing.get("is_read"):
            prefix += "✅ "
        label_main = prefix + label_main
        buttons.append([InlineKeyboardButton(
            label_main, callback_data=f"{context}:d:{listing['listing_id']}"
        )])
        if title:
            title_btn_text = title if len(title) <= 60 else title[:57] + "..."
            buttons.append([InlineKeyboardButton(
                title_btn_text, callback_data=f"{context}:d:{listing['listing_id']}"
            )])

    # Navigation row
    nav_row = []
    page = offset // LIST_PAGE_SIZE + 1
    total_pages = max(1, (total + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE)

    if offset > 0:
        nav_row.append(InlineKeyboardButton("◀ 上一頁", callback_data=f"list:p:{offset - LIST_PAGE_SIZE}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="list:noop"))
    if offset + LIST_PAGE_SIZE < total:
        nav_row.append(InlineKeyboardButton("下一頁 ▶", callback_data=f"list:p:{offset + LIST_PAGE_SIZE}"))
    if total_pages > 1 or total > 0:
        buttons.append(nav_row)

    # Action row
    toggle_label = "顯示已讀" if not show_read else "隱藏已讀"
    action_row = [
        InlineKeyboardButton("篩選", callback_data=f"{context}:filter"),
        InlineKeyboardButton(toggle_label, callback_data=f"{context}:toggle_read"),
    ]
    if context == "list":
        action_row.append(InlineKeyboardButton("全部已讀", callback_data="list:ra"))
    elif context == "fav":
        action_row.append(InlineKeyboardButton("清空最愛", callback_data="fav:clear"))
    buttons.append(action_row)

    return InlineKeyboardMarkup(buttons)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /list command — show paginated unread matched listings."""
    db_config: DbConfig = context.bot_data["db_config"]
    storage: Storage = context.bot_data["storage"]

    show_read = bool(context.user_data.get("_list_show_read", False))
    matched = _get_matched(storage, db_config, include_read=show_read)
    if not matched:
        await update.message.reply_text("目前沒有符合條件的物件")
        return

    mode = db_config.get("search.mode", "buy")
    page = matched[:LIST_PAGE_SIZE]
    keyboard = _build_list_keyboard(page, 0, len(matched), mode, show_read=show_read)

    context.user_data["_list_filter"] = None
    context.user_data["_list_show_read"] = show_read
    await update.message.reply_text(
        f"{'含已讀，' if show_read else ''}物件數：{len(matched)} 筆",
        reply_markup=keyboard,
    )


async def list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all list: callback queries."""
    query = update.callback_query
    await query.answer()

    data = query.data
    db_config: DbConfig = context.bot_data["db_config"]
    storage: Storage = context.bot_data["storage"]
    mode = db_config.get("search.mode", "buy")

    if data == "list:noop":
        return

    district_filter = context.user_data.get("_list_filter")
    show_read = bool(context.user_data.get("_list_show_read", False))

    # Pagination
    if data.startswith("list:p:"):
        offset = int(data.split(":")[2])
        if offset < 0:
            offset = 0
        matched = _get_matched(storage, db_config, district_filter, include_read=show_read)
        if not matched:
            await query.edit_message_text("目前沒有符合條件的物件")
            return
        page = matched[offset:offset + LIST_PAGE_SIZE]
        keyboard = _build_list_keyboard(page, offset, len(matched), mode, district_filter, show_read)
        label = f"{'含已讀，' if show_read else ''}物件數：{len(matched)} 筆"
        if district_filter:
            label += f"（{district_filter}）"
        await query.edit_message_text(label, reply_markup=keyboard)
        return

    # Show detail
    if data.startswith("list:d:"):
        listing_id = data.split(":")[2]
        listing = storage.get_listing_by_id("591", listing_id)
        if not listing:
            await query.edit_message_text("找不到此物件")
            return

        # Auto-mark as read
        storage.mark_as_read("591", listing_id)

        is_fav = storage.is_favorite("591", listing_id)
        msg = format_listing_message(listing, mode=mode)
        buttons = [
            [
                InlineKeyboardButton("◀ 返回列表", callback_data="list:back"),
                InlineKeyboardButton("🔗 開啟連結", url=listing.get("url")) if listing.get("url") else None,
            ]
        ]
        fav_btn = InlineKeyboardButton("⭐ 加入最愛", callback_data=f"list:fav:add:{listing_id}") if not is_fav else InlineKeyboardButton("🗑 取消最愛", callback_data=f"list:fav:del:{listing_id}")
        buttons.append([fav_btn])
        # Clean None
        buttons = [[b for b in row if b] for row in buttons]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons))
        return

    # Back to list
    if data == "list:back":
        matched = _get_matched(storage, db_config, district_filter, include_read=show_read)
        if not matched:
            await query.edit_message_text("目前沒有符合條件的物件")
            return
        page = matched[:LIST_PAGE_SIZE]
        keyboard = _build_list_keyboard(page, 0, len(matched), mode, district_filter, show_read)
        label = f"{'含已讀，' if show_read else ''}物件數：{len(matched)} 筆"
        if district_filter:
            label += f"（{district_filter}）"
        await query.edit_message_text(label, reply_markup=keyboard)
        return

    # Show filter options
    if data == "list:filter":
        matched = _get_matched(storage, db_config, include_read=show_read)
        districts = sorted(set(l.get("district") or "?" for l in matched))
        buttons = [[InlineKeyboardButton("全部", callback_data="list:f:all")]]
        row = []
        for d in districts:
            row.append(InlineKeyboardButton(d, callback_data=f"list:f:{d}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        await query.edit_message_text("選擇區域篩選：", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # Apply filter
    if data.startswith("list:f:"):
        filter_val = data.split(":", 2)[2]
        if filter_val == "all":
            context.user_data["_list_filter"] = None
            district_filter = None
        else:
            context.user_data["_list_filter"] = filter_val
            district_filter = filter_val

        matched = _get_matched(storage, db_config, district_filter, include_read=show_read)
        if not matched:
            msg = "目前沒有符合條件的物件"
            if district_filter:
                msg += f"（{district_filter}）"
            await query.edit_message_text(msg)
            return
        page = matched[:LIST_PAGE_SIZE]
        keyboard = _build_list_keyboard(page, 0, len(matched), mode, district_filter, show_read)
        label = f"{'含已讀，' if show_read else ''}物件數：{len(matched)} 筆"
        if district_filter:
            label += f"（{district_filter}）"
        await query.edit_message_text(label, reply_markup=keyboard)
        return

    # Toggle show read
    if data == "list:toggle_read":
        show_read = not show_read
        context.user_data["_list_show_read"] = show_read
        matched = _get_matched(storage, db_config, district_filter, include_read=show_read)
        if not matched:
            await query.edit_message_text("目前沒有符合條件的物件")
            return
        page = matched[:LIST_PAGE_SIZE]
        keyboard = _build_list_keyboard(page, 0, len(matched), mode, district_filter, show_read)
        label = f"{'含已讀，' if show_read else ''}物件數：{len(matched)} 筆"
        if district_filter:
            label += f"（{district_filter}）"
        await query.edit_message_text(label, reply_markup=keyboard)
        return

    # Mark all as read
    if data == "list:ra":
        matched = _get_matched(storage, db_config, district_filter, include_read=show_read)
        if not matched:
            await query.edit_message_text("沒有可標記的物件")
            return
        listing_ids = [l["listing_id"] for l in matched]
        storage.mark_many_as_read("591", listing_ids)
        await query.edit_message_text(f"已將 {len(listing_ids)} 筆物件標記為已讀")
        return

    # Favorites toggle from list detail
    if data.startswith("list:fav:add:"):
        listing_id = data.split(":")[3]
        storage.add_favorite("591", listing_id)
        listing = storage.get_listing_by_id("591", listing_id) or {}
        await query.edit_message_text(
            "已加入最愛",
            reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("◀ 返回列表", callback_data="list:back"),
                    InlineKeyboardButton("🔗 開啟連結", url=listing.get("url")) if listing.get("url") else None
                ],
                 [InlineKeyboardButton("🗑 取消最愛", callback_data=f"list:fav:del:{listing_id}")]
                ])
        )
        return

    if data.startswith("list:fav:del:"):
        listing_id = data.split(":")[3]
        storage.remove_favorite("591", listing_id)
        listing = storage.get_listing_by_id("591", listing_id) or {}
        await query.edit_message_text(
            "已從最愛移除",
            reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("◀ 返回列表", callback_data="list:back"),
                    InlineKeyboardButton("🔗 開啟連結", url=listing.get("url")) if listing.get("url") else None
                ],
                 [InlineKeyboardButton("⭐ 加入最愛", callback_data=f"list:fav:add:{listing_id}")]
                ])
        )
        return


# =============================================================================
# Favorites (/favorites)
# =============================================================================


def _favorite_dataset(storage: Storage, show_read: bool = True) -> list[dict]:
    favs = storage.get_favorites()
    if not show_read:
        favs = [f for f in favs if not f.get("is_read")]
    return favs


async def cmd_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db_config: DbConfig = context.bot_data["db_config"]
    storage: Storage = context.bot_data["storage"]
    show_read = context.user_data.get("_fav_show_read", True)

    favs = _favorite_dataset(storage, show_read=show_read)
    if not favs:
        await update.message.reply_text("尚無最愛（或全部已讀被隱藏）。在列表詳情按「⭐ 加入最愛」即可收藏。")
        return

    mode = db_config.get("search.mode", "buy")
    page = favs[:LIST_PAGE_SIZE]
    keyboard = _build_list_keyboard(page, 0, len(favs), mode, show_read=show_read, context="fav")
    label = f"最愛：{len(favs)} 筆" + ("（含已讀）" if show_read else "")
    await update.message.reply_text(label, reply_markup=keyboard)


async def favorites_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    db_config: DbConfig = context.bot_data["db_config"]
    storage: Storage = context.bot_data["storage"]
    mode = db_config.get("search.mode", "buy")
    show_read = context.user_data.get("_fav_show_read", True)

    if data == "fav:noop":
        return

    if data.startswith("fav:p:"):
        offset = int(data.split(":")[2])
        if offset < 0:
            offset = 0
        favs = _favorite_dataset(storage, show_read=show_read)
        if not favs:
            await query.edit_message_text("沒有最愛可顯示")
            return
        page = favs[offset:offset + LIST_PAGE_SIZE]
        keyboard = _build_list_keyboard(page, offset, len(favs), mode, show_read=show_read, context="fav")
        await query.edit_message_text(f"最愛：{len(favs)} 筆" + ("（含已讀）" if show_read else ""), reply_markup=keyboard)
        return

    if data.startswith("fav:d:"):
        listing_id = data.split(":")[2]
        listing = storage.get_listing_by_id("591", listing_id)
        if not listing:
            await query.edit_message_text("找不到此物件（可能已被刪除）")
            return
        storage.mark_as_read("591", listing_id)
        msg = format_listing_message(listing, mode=mode)
        buttons = [
            [InlineKeyboardButton("◀ 返回最愛", callback_data="fav:back"),
             InlineKeyboardButton("🔗 開啟連結", url=listing.get("url")) if listing.get("url") else None],
            [InlineKeyboardButton("🗑 取消最愛", callback_data=f"fav:del:{listing_id}")]
        ]
        buttons = [[b for b in row if b] for row in buttons]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data == "fav:back":
        favs = _favorite_dataset(storage, show_read=show_read)
        if not favs:
            await query.edit_message_text("沒有最愛可顯示")
            return
        page = favs[:LIST_PAGE_SIZE]
        keyboard = _build_list_keyboard(page, 0, len(favs), mode, show_read=show_read, context="fav")
        await query.edit_message_text(f"最愛：{len(favs)} 筆" + ("（含已讀）" if show_read else ""), reply_markup=keyboard)
        return

    if data == "fav:toggle_read":
        show_read = not show_read
        context.user_data["_fav_show_read"] = show_read
        favs = _favorite_dataset(storage, show_read=show_read)
        if not favs:
            await query.edit_message_text("沒有最愛可顯示")
            return
        page = favs[:LIST_PAGE_SIZE]
        keyboard = _build_list_keyboard(page, 0, len(favs), mode, show_read=show_read, context="fav")
        await query.edit_message_text(f"最愛：{len(favs)} 筆" + ("（含已讀）" if show_read else ""), reply_markup=keyboard)
        return

    if data == "fav:clear":
        storage.clear_favorites()
        await query.edit_message_text("已清空最愛")
        return

    if data.startswith("fav:del:"):
        listing_id = data.split(":")[2]
        storage.remove_favorite("591", listing_id)
        favs = _favorite_dataset(storage, show_read=show_read)
        if not favs:
            await query.edit_message_text("已刪除，現在沒有最愛")
            return
        page = favs[:LIST_PAGE_SIZE]
        keyboard = _build_list_keyboard(page, 0, len(favs), mode, show_read=show_read, context="fav")
        await query.edit_message_text(f"最愛：{len(favs)} 筆" + ("（含已讀）" if show_read else ""), reply_markup=keyboard)
        return
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

    loop = asyncio.get_running_loop()
    bot = context.bot

    def _progress(msg: str):
        """Send lightweight progress message to chat asynchronously."""
        chat_id = db_config.get("telegram.chat_id")
        if not chat_id:
            return
        coro = bot.send_message(chat_id=int(chat_id), text=f"[進度] {msg}")
        try:
            running_loop = asyncio.get_running_loop()
            if running_loop == loop:
                asyncio.create_task(coro)
            else:
                asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError:
            # No running loop in this thread
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as e:  # best-effort
            logger.debug("Progress send failed: %s", e)

    try:
        logger.info("Pipeline started")

        # Scrape
        raw_listings = await asyncio.to_thread(scrape_listings, config, _progress)
        scraped = len(raw_listings)
        _progress(f"爬取完成，共 {scraped} 筆原始物件，開始寫入與過濾")
        for raw in raw_listings:
            normalized = normalize_591_listing(raw)
            if storage.insert_listing(normalized):
                new_count += 1
                if new_count % 10 == 0:
                    _progress(f"已寫入 {new_count} 筆新物件")

        logger.info("Scrape complete: %d new out of %d", new_count, scraped)

        # Match
        matched = find_matching_listings(config, storage)
        _progress(f"過濾後符合條件：{len(matched)} 筆，準備通知")

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

        # Count unread matched (for summary)
        unread_matched = _get_unread_matched(storage, db_config)
        unread_count = len(unread_matched)

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(
            "Pipeline completed: scraped=%d, new=%d, matched=%d, unread=%d, duration=%.1fs",
            scraped, new_count, matched_count, unread_count, duration,
        )

        db_config.set("scheduler.last_run_at", start_time.isoformat())
        db_config.set("scheduler.last_run_status", "success")

        if unread_count > 0:
            return f"完成！爬取 {scraped} 筆，新增 {new_count} 筆，有 {unread_count} 筆未讀物件符合條件，使用 /list 查看"
        else:
            return f"完成！爬取 {scraped} 筆，新增 {new_count} 筆，目前沒有新的未讀物件"

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
    max_ping = db_config.get("search.max_ping")
    room_counts = db_config.get("search.room_counts", [])
    bath_counts = db_config.get("search.bathroom_counts", [])
    year_min = db_config.get("search.year_built_min")
    year_max = db_config.get("search.year_built_max")
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
    if min_ping or max_ping:
        if min_ping and max_ping:
            lines.append(f"坪數：{min_ping}-{max_ping} 坪")
        elif min_ping:
            lines.append(f"坪數：≥ {min_ping} 坪")
        elif max_ping:
            lines.append(f"坪數：≤ {max_ping} 坪")
    if room_counts:
        lines.append(f"房數：{', '.join(str(x) for x in room_counts)} 房")
    if bath_counts:
        lines.append(f"衛數：{', '.join(str(x) for x in bath_counts)} 衛")
    if year_min or year_max:
        if year_min and year_max:
            lines.append(f"屋齡：{year_min}-{year_max} 年建")
        elif year_min:
            lines.append(f"屋齡：≥ {year_min} 年建")
        elif year_max:
            lines.append(f"屋齡：≤ {year_max} 年建")
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


def _build_layout_keyboard(
    room_counts: list[int],
    bath_counts: list[int],
) -> InlineKeyboardMarkup:
    """Build layout selection keyboard for room/bath counts."""
    buttons = []
    room_row = []
    for n in (1, 2, 3):
        prefix = "✅ " if n in room_counts else ""
        room_row.append(InlineKeyboardButton(f"{prefix}{n}房", callback_data=f"layout:r:{n}"))
    buttons.append(room_row)

    bath_row = []
    for n in (1, 2):
        prefix = "✅ " if n in bath_counts else ""
        bath_row.append(InlineKeyboardButton(f"{prefix}{n}衛", callback_data=f"layout:b:{n}"))
    buttons.append(bath_row)

    action_row = [
        InlineKeyboardButton("🗑 清除", callback_data="layout:clear"),
        InlineKeyboardButton("✅ 完成", callback_data="layout:done"),
    ]
    buttons.append(action_row)
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
                CallbackQueryHandler(layout_callback, pattern=r"^layout:"),
            ],
            SETTINGS_PRICE_INPUT: [
                MessageHandler(auth & filters.TEXT & ~filters.COMMAND, settings_price_handler),
            ],
            SETTINGS_SIZE_INPUT: [
                MessageHandler(auth & filters.TEXT & ~filters.COMMAND, settings_size_handler),
            ],
            SETTINGS_YEAR_INPUT: [
                MessageHandler(auth & filters.TEXT & ~filters.COMMAND, settings_year_handler),
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
            SETTINGS_REGION_INPUT: [
                MessageHandler(auth & filters.TEXT & ~filters.COMMAND, settings_region_handler),
            ],
            CONFIG_IMPORT_INPUT: [
                MessageHandler(auth & filters.TEXT & ~filters.COMMAND, config_import_handler),
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
    app.add_handler(CommandHandler("help", cmd_help, filters=auth))
    app.add_handler(CommandHandler("run", cmd_run, filters=auth))
    app.add_handler(CommandHandler("list", cmd_list, filters=auth))
    app.add_handler(CallbackQueryHandler(list_callback, pattern=r"^list:"))
    app.add_handler(CommandHandler("favorites", cmd_favorites, filters=auth))
    app.add_handler(CallbackQueryHandler(favorites_callback, pattern=r"^fav:"))
    app.add_handler(CommandHandler("pause", cmd_pause, filters=auth))
    app.add_handler(CommandHandler("resume", cmd_resume, filters=auth))
    app.add_handler(CommandHandler("loglevel", cmd_loglevel, filters=auth))
    app.add_handler(CommandHandler("config_export", cmd_config_export, filters=auth))

    # Dedicated conversation for config import (command → next message JSON)
    config_conv = ConversationHandler(
        entry_points=[CommandHandler("config_import", cmd_config_import, filters=auth)],
        states={
            CONFIG_IMPORT_INPUT: [
                MessageHandler(auth & filters.TEXT & ~filters.COMMAND, config_import_handler),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_help, filters=auth)],
        map_to_parent={},
    )
    app.add_handler(config_conv)

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
            BotCommand("list", "瀏覽未讀物件"),
            BotCommand("favorites", "查看最愛"),
            BotCommand("settings", "修改設定"),
            BotCommand("status", "查看狀態"),
            BotCommand("help", "指令列表"),
            BotCommand("run", "手動執行"),
            BotCommand("pause", "暫停排程"),
            BotCommand("resume", "恢復排程"),
            BotCommand("loglevel", "調整日誌等級"),
            BotCommand("config_export", "匯出目前設定"),
            BotCommand("config_import", "匯入設定(JSON)"),
        ])
        _ensure_scheduler(application)
        logger.info("Bot started")

    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

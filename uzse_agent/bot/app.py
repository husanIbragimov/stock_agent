"""Telegram bot ilovasi: ruxsat, formalar, xatolar va jadval bo'yicha ishlar.

Bot va jadval bitta jarayonda ishlaydi (`python main.py daemon`). Sinxron
ishlar (scraper, SQLite, Telegram HTTP) asyncio.to_thread ichida bajariladi.
"""
from __future__ import annotations

import asyncio
import logging
import warnings

from telegram import BotCommand, LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    Defaults,
    TypeHandler,
)
from telegram.warnings import PTBUserWarning

from ..config import AppConfig
from ..portfolio import TZ
from ..runner import run_daily_report, run_exclusive, run_news_scan, run_price_check
from . import handlers_add, handlers_admin, handlers_stock, handlers_tx
from .common import BotDeps, cancel, deps

logger = logging.getLogger(__name__)

# per_message=False bilan CallbackQueryHandler ishlatish ataylab qilingan
warnings.filterwarnings("ignore", message=r".*per_message.*", category=PTBUserWarning)

# Har biri HANDLERS, ENTRY_POINTS, STATES ga ega; Task 9/10 yangi modullarni qo'shadi
FORM_MODULES = [handlers_admin, handlers_add, handlers_tx, handlers_stock]

BOT_COMMANDS = [
    BotCommand("list", "Portfel"),
    BotCommand("stock", "Aksiya kartochkasi"),
    BotCommand("add", "Aksiya qo'shish"),
    BotCommand("buy", "Xarid kiritish"),
    BotCommand("sell", "Sotuv kiritish"),
    BotCommand("check", "Narxlarni tekshirish"),
    BotCommand("report", "Kunlik hisobot"),
    BotCommand("news", "Yangiliklarni yig'ish"),
    BotCommand("price", "Jonli narx"),
    BotCommand("settings", "Sozlamalar"),
    BotCommand("cancel", "Formani bekor qilish"),
    BotCommand("help", "Yordam"),
]


def _owner_chat_id(config: AppConfig) -> int:
    try:
        return int(config.telegram_chat_id)
    except ValueError:
        raise RuntimeError("TELEGRAM_CHAT_ID .env faylida raqam bo'lishi kerak (masalan 123456789)") from None


async def _guard(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Faqat egasining chatidan kelgan xabarlarni o'tkazadi."""
    chat = update.effective_chat if isinstance(update, Update) else None
    if chat is None or chat.id != context.bot_data["owner_chat_id"]:
        logger.warning("Ruxsatsiz chatdan kelgan xabar e'tiborsiz qoldirildi: %s", chat.id if chat else None)
        raise ApplicationHandlerStop


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Bot handler'ida xato", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        await update.effective_chat.send_message("Xatolik yuz berdi. Qayta urinib ko'ring yoki /cancel bosing.")


async def _stale_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer("Bu tugma eskirgan. Buyruqni qaytadan boshlang.", show_alert=True)


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands(BOT_COMMANDS)


# ---- jadval bo'yicha ishlar ----
async def _job_price_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    d = deps(context)
    await asyncio.to_thread(run_exclusive, run_price_check, d.repo, d.storage, d.notifier)


async def _job_news_scan(context: ContextTypes.DEFAULT_TYPE) -> None:
    d = deps(context)
    await asyncio.to_thread(run_exclusive, run_news_scan, d.repo, d.storage)


async def _job_daily_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    d = deps(context)
    await asyncio.to_thread(run_daily_report, d.repo, d.storage, d.notifier)


def _schedule_jobs(app: Application) -> None:
    # UZSE savdo kunlari dush-juma, ish soatlarida
    cron = {"trigger": "cron", "timezone": TZ}
    jq = app.job_queue
    jq.run_custom(_job_price_check, name="price_check",
                  job_kwargs={**cron, "day_of_week": "mon-fri", "hour": "9-18", "minute": "*/30"})
    jq.run_custom(_job_news_scan, name="news_scan", job_kwargs={**cron, "hour": "*/2", "minute": 0})
    jq.run_custom(_job_daily_report, name="daily_report",
                  job_kwargs={**cron, "day_of_week": "mon-fri", "hour": 18, "minute": 30})
    # Ishga tushganda bir marta tekshirib qo'yamiz
    jq.run_once(_job_price_check, when=5, name="startup_check")


def build_application(config: AppConfig, bot_deps: BotDeps) -> Application:
    if not config.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN .env faylida ko'rsatilmagan")
    owner = _owner_chat_id(config)

    app = (
        Application.builder()
        .token(config.telegram_bot_token)
        .defaults(Defaults(parse_mode=ParseMode.HTML, tzinfo=TZ,
                           link_preview_options=LinkPreviewOptions(is_disabled=True)))
        .post_init(_post_init)
        .build()
    )
    app.bot_data["deps"] = bot_deps
    app.bot_data["owner_chat_id"] = owner

    app.add_handler(TypeHandler(Update, _guard), group=-1)
    app.add_handler(
        ConversationHandler(
            entry_points=[h for m in FORM_MODULES for h in m.ENTRY_POINTS],
            states={state: handlers for m in FORM_MODULES for state, handlers in m.STATES.items()},
            fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(cancel, pattern=r"^cancel$")],
            allow_reentry=True,
            conversation_timeout=600,
            name="forms",
        )
    )
    for module in FORM_MODULES:
        for handler in module.HANDLERS:
            app.add_handler(handler)
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(cancel, pattern=r"^cancel$"))
    # Eng oxirida: hech qaysi handler ushlamagan tugmalar (masalan, qayta ishga tushirishdan oldingi)
    app.add_handler(CallbackQueryHandler(_stale_button))
    app.add_error_handler(_on_error)

    _schedule_jobs(app)
    return app


def run_bot(config: AppConfig, bot_deps: BotDeps) -> None:
    app = build_application(config, bot_deps)
    logger.info("Bot va jadval ishga tushdi. To'xtatish uchun Ctrl+C.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

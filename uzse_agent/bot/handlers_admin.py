"""Yordam, talab bo'yicha tekshiruvlar (/check, /news, /report, /price) va sozlamalar."""
from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler

from ..runner import build_daily_report, run_exclusive, run_news_scan, run_price_check
from ..scraper import get_quotes
from ..textfmt import split_message
from . import format as fmt
from .common import CANCEL_ROW, END, SETTINGS_VALUE, TEXT, ack, callback_arg, deps, keyboard, send
from .inputs import InputError, parse_positive_int


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send(update, fmt.HELP_TEXT)


async def _run_job(update: Update, label: str, fn, *args) -> None:
    await send(update, f"⏳ {label} boshlandi...")
    ran = await asyncio.to_thread(run_exclusive, fn, *args)
    if ran:
        await send(update, f"✅ {label} tugadi.")
    else:
        await send(update, "⏳ Boshqa tekshiruv hozir ishlayapti, birozdan keyin qayta urinib ko'ring.")


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    d = deps(context)
    await _run_job(update, "Narx tekshiruvi", run_price_check, d.repo, d.storage, d.notifier)


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    d = deps(context)
    await _run_job(update, "Yangiliklar skaneri", run_news_scan, d.repo, d.storage)


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    d = deps(context)
    text = await asyncio.to_thread(build_daily_report, d.repo, d.storage)
    for part in split_message(text):
        await send(update, part)


async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send(update, "Foydalanish: <code>/price UZ7036271003</code> yoki <code>/price UZNGP</code>")
        return
    code = context.args[0].strip().upper()
    await send(update, "🔎 UZSE'dan qidirilmoqda...")
    quote = (await asyncio.to_thread(get_quotes, [code])).get(code)
    if quote is None:
        await send(update, "Aksiya topilmadi yoki sayt javob bermadi.")
        return
    await send(update, fmt.quote_text(quote))


# ---- sozlamalar ----
def _settings_keyboard():
    return keyboard(*[[(f"✏️ {label}", f"set:{key}")] for key, label in fmt.SETTING_LABELS.items()])


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = deps(context).repo.load_settings()
    await send(update, fmt.settings_text(settings), reply_markup=_settings_keyboard())


async def settings_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    key = callback_arg(update, 1)
    context.user_data["setting_key"] = key
    await send(
        update,
        f"<b>{fmt.SETTING_LABELS[key]}</b> uchun yangi qiymatni yuboring (butun musbat son).",
        reply_markup=keyboard(CANCEL_ROW),
    )
    return SETTINGS_VALUE


async def settings_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        value = parse_positive_int(update.message.text)
    except InputError as exc:
        await send(update, str(exc))
        return SETTINGS_VALUE
    repo = deps(context).repo
    try:
        repo.set_setting(context.user_data["setting_key"], value)
    except ValueError as exc:
        await send(update, str(exc))
        return SETTINGS_VALUE
    context.user_data.pop("setting_key")
    await send(update, "✅ Saqlandi.\n\n" + fmt.settings_text(repo.load_settings()), reply_markup=_settings_keyboard())
    return END


_SETTING_PATTERN = rf"^set:({'|'.join(fmt.SETTING_LABELS)})$"

HANDLERS = [
    CommandHandler(["start", "help"], cmd_help),
    # Tarmoqqa chiqadigan buyruqlar fonda ishlaydi — bot bu vaqtda boshqa xabarlarga javob beradi
    CommandHandler("check", cmd_check, block=False),
    CommandHandler("news", cmd_news, block=False),
    CommandHandler("report", cmd_report, block=False),
    CommandHandler("price", cmd_price, block=False),
    CommandHandler("settings", cmd_settings),
]
ENTRY_POINTS = [CallbackQueryHandler(settings_ask, pattern=_SETTING_PATTERN)]
STATES = {SETTINGS_VALUE: [MessageHandler(TEXT, settings_value)]}

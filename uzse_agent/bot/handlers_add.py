"""/add — yangi aksiyani portfelga (kuzatuvga) qo'shish formasi."""
from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler

from ..repo import Security
from ..scraper import get_quotes
from ..textfmt import esc
from . import format as fmt
from .common import (
    ADD_BUY_OFFER, ADD_CODE, ADD_CONFIRM, ADD_DROP, ADD_KEYWORDS, ADD_TRAIL, CANCEL_ROW, END, TEXT,
    ack, callback_arg, deps, keyboard, send,
)
from .inputs import InputError, parse_keywords, parse_pct

DEFAULT_DROP_PCT = 7.0
DEFAULT_TRAIL_PCT = 10.0


async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["add"] = {}
    await send(
        update,
        "Aksiyaning ISIN kodi yoki birja tikerini yuboring.\n"
        "Masalan: <code>UZ7036271003</code> yoki <code>UZNGP</code>",
        reply_markup=keyboard(CANCEL_ROW),
    )
    return ADD_CODE


async def add_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code = update.message.text.strip().upper()
    await send(update, "🔎 UZSE'dan qidirilmoqda...")
    quote = (await asyncio.to_thread(get_quotes, [code])).get(code)
    if quote is None:
        await send(update, "Aksiya topilmadi yoki sayt javob bermadi. Kodni tekshirib, qayta yuboring.",
                   reply_markup=keyboard(CANCEL_ROW))
        return ADD_CODE
    if deps(context).repo.get_security(quote.isin):
        await send(update, f"{esc(quote.name)} allaqachon portfelda bor. Ko'rish uchun /stock")
        context.user_data.pop("add", None)
        return END
    context.user_data["add"]["quote"] = quote
    await send(update, fmt.quote_text(quote) + "\n\nShu aksiyami?",
               reply_markup=keyboard([("✅ Ha", "add:yes"), ("↩️ Yo'q", "add:no")], CANCEL_ROW))
    return ADD_CONFIRM


async def _ask_pct(update: Update, question: str, default: float) -> None:
    await send(update, f"{question}\nRaqam yuboring yoki tugmani bosing.",
               reply_markup=keyboard([(f"{default:g}%", "pct:default"), ("🚫 O'chirish", "pct:off")], CANCEL_ROW))


def _pct_from_update(update: Update, default: float) -> float | None:
    """Tugma yoki matndan foizni oladi; noto'g'ri matnda InputError."""
    if update.callback_query:
        return default if callback_arg(update, 1) == "default" else None
    return parse_pct(update.message.text)


async def add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    if callback_arg(update, 1) == "no":
        await send(update, "Boshqa ISIN yoki tikerni yuboring.", reply_markup=keyboard(CANCEL_ROW))
        return ADD_CODE
    await _ask_pct(update, "O'rtacha xarid narxidan necha foiz tushsa ogohlantiray?", DEFAULT_DROP_PCT)
    return ADD_DROP


async def add_drop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    try:
        context.user_data["add"]["drop"] = _pct_from_update(update, DEFAULT_DROP_PCT)
    except InputError as exc:
        await send(update, str(exc))
        return ADD_DROP
    await _ask_pct(update, "So'nggi 30 kunlik eng yuqori narxdan necha foiz tushsa ogohlantiray?", DEFAULT_TRAIL_PCT)
    return ADD_TRAIL


async def add_trail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    try:
        context.user_data["add"]["trail"] = _pct_from_update(update, DEFAULT_TRAIL_PCT)
    except InputError as exc:
        await send(update, str(exc))
        return ADD_TRAIL
    await send(update, "Yangiliklarda qidiriladigan qo'shimcha kalit so'zlar (vergul bilan).\n"
                       "Nom va tiker avtomatik qidiriladi.",
               reply_markup=keyboard([("⏭ O'tkazib yuborish", "kw:skip")], CANCEL_ROW))
    return ADD_KEYWORDS


async def add_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    keywords = [] if update.callback_query else parse_keywords(update.message.text)
    form = context.user_data.pop("add")
    quote = form["quote"]
    deps(context).repo.add_security(
        Security(
            isin=quote.isin,
            ticker=quote.ticker or None,
            name=quote.name,
            extra_keywords=keywords,
            drop_alert_pct=form["drop"],
            trailing_drop_pct=form["trail"],
        )
    )
    await send(update, f"✅ {esc(quote.name)} qo'shildi.\n\nHozir xarid ham kiritasizmi?",
               reply_markup=keyboard([("🟢 Ha, xarid kiritish", f"tx:buy:{quote.isin}")],
                                     [("Yo'q, faqat kuzatish", "add:done")]))
    return ADD_BUY_OFFER


async def add_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    await send(update, "Aksiya kuzatuv ro'yxatiga qo'shildi. Ko'rish: /list")
    return END


HANDLERS: list = []
ENTRY_POINTS = [CommandHandler("add", add_start)]
STATES = {
    ADD_CODE: [MessageHandler(TEXT, add_code)],
    ADD_CONFIRM: [CallbackQueryHandler(add_confirm, pattern=r"^add:(yes|no)$")],
    ADD_DROP: [CallbackQueryHandler(add_drop, pattern=r"^pct:(default|off)$"), MessageHandler(TEXT, add_drop)],
    ADD_TRAIL: [CallbackQueryHandler(add_trail, pattern=r"^pct:(default|off)$"), MessageHandler(TEXT, add_trail)],
    ADD_KEYWORDS: [CallbackQueryHandler(add_keywords, pattern=r"^kw:skip$"), MessageHandler(TEXT, add_keywords)],
    # "tx:buy:<ISIN>" tugmasi handlers_tx dagi entry point orqali ushlanadi (allow_reentry)
    ADD_BUY_OFFER: [CallbackQueryHandler(add_done, pattern=r"^add:done$")],
}

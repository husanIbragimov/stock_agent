"""/buy va /sell — xarid/sotuv tranzaksiyasini kiritish formasi."""
from __future__ import annotations

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler

from ..portfolio import NegativePositionError, Transaction, today_local
from ..textfmt import esc, fmt_money, fmt_qty
from . import format as fmt
from .common import (
    CANCEL_ROW, END, TEXT, TX_CONFIRM, TX_DATE, TX_FEE, TX_FEE_MODE, TX_NOTE, TX_PICK, TX_PRICE, TX_QTY,
    ack, callback_arg, deps, keyboard, send,
)
from .inputs import InputError, fee_total, parse_date, parse_fee, parse_note, parse_price, parse_quantity

_VERB = {"buy": "sotib oldingiz", "sell": "sotdingiz"}


async def _pick(update: Update, context: ContextTypes.DEFAULT_TYPE, side: str) -> int:
    context.user_data["tx"] = {"side": side}
    repo = deps(context).repo
    securities = repo.list_securities()
    if side == "sell":
        securities = [s for s in securities if repo.position(s.isin).quantity > 0]
    if not securities:
        await send(update, "Portfelda aksiya yo'q. Avval /add bilan qo'shing." if side == "buy"
                   else "Sotish uchun aksiya yo'q.")
        return END
    rows = [[(fmt.security_button(s), f"pick:{s.isin}")] for s in securities]
    await send(update, f"Qaysi aksiyani {_VERB[side]}?", reply_markup=keyboard(*rows, CANCEL_ROW))
    return TX_PICK


async def buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _pick(update, context, "buy")


async def sell_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _pick(update, context, "sell")


async def tx_direct(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kartochka yoki /add dagi "tx:<side>:<ISIN>" tugmasi."""
    await ack(update)
    _, side, isin = update.callback_query.data.split(":")
    context.user_data["tx"] = {"side": side, "isin": isin}
    return await _ask_quantity(update, context)


async def tx_picked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    context.user_data["tx"]["isin"] = callback_arg(update, 1)
    return await _ask_quantity(update, context)


async def _ask_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    form = context.user_data["tx"]
    repo = deps(context).repo
    sec = repo.get_security(form["isin"])
    if sec is None:
        await send(update, "Aksiya topilmadi (o'chirilgan bo'lishi mumkin).")
        return END
    held = repo.position(sec.isin).quantity
    if form["side"] == "sell" and held == 0:
        await send(update, "Bu aksiyadan sizda yo'q.")
        return END
    await send(update, f"{fmt.security_title(sec)}\n\nNecha dona {_VERB[form['side']]}? "
                       f"(Sizda: {fmt_qty(held)} dona)",
               reply_markup=keyboard(CANCEL_ROW))
    return TX_QTY


async def tx_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    form = context.user_data["tx"]
    d = deps(context)
    try:
        quantity = parse_quantity(update.message.text)
    except InputError as exc:
        await send(update, str(exc))
        return TX_QTY
    if form["side"] == "sell":
        held = d.repo.position(form["isin"]).quantity
        if quantity > held:
            await send(update, f"Sizda faqat {fmt_qty(held)} dona bor. Boshqa miqdor yuboring.")
            return TX_QTY
    form["quantity"] = quantity
    form["last_price"] = d.storage.last_price(form["isin"])
    rows = [[(f"Oxirgi narx: {fmt_money(form['last_price'])}", "price:last")]] if form["last_price"] else []
    await send(update, "Bir dona narxi (UZS)?", reply_markup=keyboard(*rows, CANCEL_ROW))
    return TX_PRICE


async def tx_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    form = context.user_data["tx"]
    if update.callback_query:
        form["price"] = form["last_price"]
    else:
        try:
            form["price"] = parse_price(update.message.text)
        except InputError as exc:
            await send(update, str(exc))
            return TX_PRICE
    await send(update, "Savdo sanasi? <code>YYYY-MM-DD</code> ko'rinishida yuboring yoki tugmani bosing.",
               reply_markup=keyboard([("📅 Bugun", "date:today")], CANCEL_ROW))
    return TX_DATE


async def tx_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    form = context.user_data["tx"]
    today = today_local()
    if update.callback_query:
        form["traded_at"] = today.isoformat()
    else:
        try:
            form["traded_at"] = parse_date(update.message.text, today)
        except InputError as exc:
            await send(update, str(exc))
            return TX_DATE
    await send(update, "Broker komissiyasi? Raqam yuboring — keyin uni qanday hisoblashni tanlaysiz.",
               reply_markup=keyboard([("0", "fee:0")], CANCEL_ROW))
    return TX_FEE


async def _ask_note(update: Update) -> int:
    await send(update, "Izoh (ixtiyoriy)?", reply_markup=keyboard([("⏭ O'tkazib yuborish", "note:skip")], CANCEL_ROW))
    return TX_NOTE


async def tx_fee(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Komissiya raqami; 0 bo'lmasa, uni qanday hisoblashni so'raydi (TX_FEE_MODE)."""
    await ack(update)
    form = context.user_data["tx"]
    form["fee_detail"] = None
    if update.callback_query:
        form["fee"] = 0.0
        return await _ask_note(update)
    try:
        value = parse_fee(update.message.text)
    except InputError as exc:
        await send(update, str(exc))
        return TX_FEE
    if value == 0:
        form["fee"] = 0.0
        return await _ask_note(update)
    form["fee_value"] = value
    rows = [[button] for button in fmt.fee_buttons(value, form["quantity"], form["price"])]
    await send(update, "Komissiya qanday hisoblansin? (Boshqa raqam yozsangiz, qayta hisoblanadi.)",
               reply_markup=keyboard(*rows, CANCEL_ROW))
    return TX_FEE_MODE


async def tx_fee_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    form = context.user_data["tx"]
    mode = callback_arg(update, 1)
    value = form.pop("fee_value")
    form["fee"] = fee_total(value, mode, form["quantity"], form["price"])
    form["fee_detail"] = fmt.fee_detail(value, mode, form["quantity"], form["price"])
    return await _ask_note(update)


def _build_tx(form: dict) -> Transaction:
    return Transaction(None, form["side"], form["quantity"], form["price"], form["fee"],
                       form["traded_at"], form["note"])


async def tx_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    form = context.user_data["tx"]
    if update.callback_query:
        form["note"] = None
    else:
        try:
            form["note"] = parse_note(update.message.text) or None
        except InputError as exc:
            await send(update, str(exc))
            return TX_NOTE
    repo = deps(context).repo
    tx = _build_tx(form)
    try:
        new_pos = repo.preview_transaction(form["isin"], tx)
    except NegativePositionError as exc:
        context.user_data.pop("tx", None)
        await send(update, f"❌ {esc(exc)}")
        return END
    sec = repo.get_security(form["isin"])
    await send(update, fmt.tx_summary(sec, tx, new_pos, fee_detail=form.get("fee_detail")), reply_markup=keyboard([("✅ Saqlash", "tx:save")], CANCEL_ROW))
    return TX_CONFIRM


async def tx_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    form = context.user_data.pop("tx")
    d = deps(context)
    try:
        _, pos = d.repo.add_transaction(form["isin"], _build_tx(form))
    except NegativePositionError as exc:
        await send(update, f"❌ {esc(exc)}")
        return END
    sec = d.repo.get_security(form["isin"])
    await send(update, "✅ Saqlandi.\n\n" + fmt.position_text(sec, pos, d.storage.last_quote(sec.isin)))
    return END


HANDLERS: list = []
ENTRY_POINTS = [
    CommandHandler("buy", buy_start),
    CommandHandler("sell", sell_start),
    CallbackQueryHandler(tx_direct, pattern=r"^tx:(buy|sell):[0-9A-Z]+$"),
]
STATES = {
    TX_PICK: [CallbackQueryHandler(tx_picked, pattern=r"^pick:[0-9A-Z]+$")],
    TX_QTY: [MessageHandler(TEXT, tx_quantity)],
    TX_PRICE: [CallbackQueryHandler(tx_price, pattern=r"^price:last$"), MessageHandler(TEXT, tx_price)],
    TX_DATE: [CallbackQueryHandler(tx_date, pattern=r"^date:today$"), MessageHandler(TEXT, tx_date)],
    TX_FEE: [CallbackQueryHandler(tx_fee, pattern=r"^fee:0$"), MessageHandler(TEXT, tx_fee)],
    TX_FEE_MODE: [CallbackQueryHandler(tx_fee_mode, pattern=r"^feemode:(unit|total|pct)$"), MessageHandler(TEXT, tx_fee)],
    TX_NOTE: [CallbackQueryHandler(tx_note, pattern=r"^note:skip$"), MessageHandler(TEXT, tx_note)],
    TX_CONFIRM: [CallbackQueryHandler(tx_save, pattern=r"^tx:save$")],
}

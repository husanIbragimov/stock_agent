"""/list, /stock: portfel ko'rinishi, aksiya kartochkasi, tarix, o'chirish va tahrirlash."""
from __future__ import annotations

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler

from ..portfolio import NegativePositionError
from ..textfmt import esc, split_message
from . import format as fmt
from .common import CANCEL_ROW, EDIT_VALUE, END, TEXT, ack, callback_arg, deps, keyboard, send
from .inputs import InputError, parse_keywords, parse_pct

HISTORY_LIMIT = 20
EDIT_FIELDS = {"drop": "drop_alert_pct", "trail": "trailing_drop_pct", "kw": "extra_keywords"}
_ISIN = r"[0-9A-Z]+"


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    d = deps(context)
    items = [(s, d.repo.position(s.isin), d.storage.last_quote(s.isin)) for s in d.repo.list_securities()]
    for part in split_message(fmt.portfolio_list(items)):
        await send(update, part)


async def cmd_stock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    securities = deps(context).repo.list_securities()
    if not securities:
        await send(update, "Portfel bo'sh. /add bilan aksiya qo'shing.")
        return
    rows = [[(fmt.security_button(s), f"stock:{s.isin}")] for s in securities]
    await send(update, "Qaysi aksiya?", reply_markup=keyboard(*rows))


async def _send_card(update: Update, context: ContextTypes.DEFAULT_TYPE, isin: str) -> None:
    d = deps(context)
    sec = d.repo.get_security(isin)
    if sec is None:
        await send(update, "Aksiya topilmadi (o'chirilgan bo'lishi mumkin).")
        return
    text = fmt.stock_card(sec, d.repo.position(isin), d.storage.last_quote(isin), d.repo.transactions(isin)[-5:])
    await send(update, text, reply_markup=keyboard(
        [("🟢 Xarid", f"tx:buy:{isin}"), ("🔴 Sotuv", f"tx:sell:{isin}")],
        [("✏️ Tahrirlash", f"editmenu:{isin}"), ("📜 Tarix", f"hist:{isin}")],
        [("🗑 O'chirish", f"secdel:{isin}")],
    ))


async def show_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ack(update)
    await _send_card(update, context, callback_arg(update, 1))


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ack(update)
    isin = callback_arg(update, 1)
    d = deps(context)
    sec = d.repo.get_security(isin)
    txs = d.repo.transactions(isin)[-HISTORY_LIMIT:]
    if sec is None or not txs:
        await send(update, "Tranzaksiyalar yo'q.")
        return
    buttons = [(f"🗑 #{tx.id}", f"txdel:{tx.id}") for tx in txs]
    rows = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    await send(update, fmt.history_text(sec, txs), reply_markup=keyboard(*rows, [("⬅️ Orqaga", f"stock:{isin}")]))


async def ask_delete_tx(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ack(update)
    tx_id = int(callback_arg(update, 1))
    found = deps(context).repo.get_transaction(tx_id)
    if found is None:
        await send(update, "Tranzaksiya topilmadi.")
        return
    isin, tx = found
    await send(update, f"Shu tranzaksiya o'chirilsinmi?\n\n{fmt.tx_line(tx)}",
               reply_markup=keyboard([("✅ Ha, o'chirish", f"txdel:{tx_id}:yes"), ("Yo'q", f"stock:{isin}")]))


async def delete_tx(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ack(update)
    tx_id = int(callback_arg(update, 1))
    repo = deps(context).repo
    found = repo.get_transaction(tx_id)
    if found is None:
        await send(update, "Tranzaksiya topilmadi.")
        return
    try:
        repo.delete_transaction(tx_id)
    except NegativePositionError as exc:
        await send(update, f"❌ O'chirib bo'lmaydi: {esc(exc)}")
        return
    await send(update, "✅ O'chirildi.")
    await _send_card(update, context, found[0])


async def ask_delete_security(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ack(update)
    isin = callback_arg(update, 1)
    repo = deps(context).repo
    sec = repo.get_security(isin)
    if sec is None:
        await send(update, "Aksiya topilmadi.")
        return
    count = len(repo.transactions(isin))
    await send(update, f"{fmt.security_title(sec)} va uning {count} ta tranzaksiyasi o'chiriladi. "
                       "Narx tarixi saqlanib qoladi. Davom etamizmi?",
               reply_markup=keyboard([("🗑 Ha, o'chirish", f"secdel:{isin}:yes"), ("Yo'q", f"stock:{isin}")]))


async def delete_security(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ack(update)
    isin = callback_arg(update, 1)
    repo = deps(context).repo
    sec = repo.get_security(isin)
    if sec is None:
        await send(update, "Aksiya topilmadi.")
        return
    count = repo.delete_security(isin)
    await send(update, f"✅ {esc(sec.name)} va {count} ta tranzaksiya o'chirildi.")


# ---- tahrirlash ----
async def edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ack(update)
    isin = callback_arg(update, 1)
    await send(update, "Nimani o'zgartiramiz?", reply_markup=keyboard(
        [("O'rtacha narxdan %", f"edit:drop:{isin}"), ("Cho'qqidan %", f"edit:trail:{isin}")],
        [("Kalit so'zlar", f"edit:kw:{isin}")],
        [("⬅️ Orqaga", f"stock:{isin}")],
    ))


async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    _, field, isin = update.callback_query.data.split(":")
    context.user_data["edit"] = {"field": EDIT_FIELDS[field], "isin": isin}
    if field == "kw":
        await send(update, "Yangi kalit so'zlarni vergul bilan yuboring (eskilari almashtiriladi).",
                   reply_markup=keyboard([("🧹 Tozalash", "val:off")], CANCEL_ROW))
    else:
        await send(update, "Yangi foizni yuboring (masalan 7).",
                   reply_markup=keyboard([("🚫 O'chirish", "val:off")], CANCEL_ROW))
    return EDIT_VALUE


async def edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    form = context.user_data["edit"]
    is_keywords = form["field"] == "extra_keywords"
    if update.callback_query:
        value = [] if is_keywords else None
    elif is_keywords:
        value = parse_keywords(update.message.text)
    else:
        try:
            value = parse_pct(update.message.text)
        except InputError as exc:
            await send(update, str(exc))
            return EDIT_VALUE
    try:
        deps(context).repo.update_security(form["isin"], **{form["field"]: value})
    except KeyError:
        await send(update, "Aksiya topilmadi (o'chirilgan bo'lishi mumkin).")
        context.user_data.pop("edit", None)
        return END
    context.user_data.pop("edit", None)
    await send(update, "✅ Saqlandi.")
    await _send_card(update, context, form["isin"])
    return END


HANDLERS = [
    CommandHandler("list", cmd_list),
    CommandHandler("stock", cmd_stock),
    CallbackQueryHandler(show_card, pattern=rf"^stock:{_ISIN}$"),
    CallbackQueryHandler(show_history, pattern=rf"^hist:{_ISIN}$"),
    CallbackQueryHandler(ask_delete_tx, pattern=r"^txdel:\d+$"),
    CallbackQueryHandler(delete_tx, pattern=r"^txdel:\d+:yes$"),
    CallbackQueryHandler(ask_delete_security, pattern=rf"^secdel:{_ISIN}$"),
    CallbackQueryHandler(delete_security, pattern=rf"^secdel:{_ISIN}:yes$"),
    CallbackQueryHandler(edit_menu, pattern=rf"^editmenu:{_ISIN}$"),
]
ENTRY_POINTS = [CallbackQueryHandler(edit_start, pattern=rf"^edit:(drop|trail|kw):{_ISIN}$")]
STATES = {EDIT_VALUE: [CallbackQueryHandler(edit_value, pattern=r"^val:off$"), MessageHandler(TEXT, edit_value)]}

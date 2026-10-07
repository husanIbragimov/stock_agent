"""Bot handler'lari uchun umumiy yordamchilar: bog'liqliklar, holatlar, klaviaturalar."""
from __future__ import annotations

from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler, filters

from ..notifier import TelegramNotifier
from ..repo import PortfolioRepo
from ..storage import Storage

END = ConversationHandler.END

# Barcha formalar bitta ConversationHandler ichida, shuning uchun holatlar yagona
(
    ADD_CODE, ADD_CONFIRM, ADD_DROP, ADD_TRAIL, ADD_KEYWORDS, ADD_BUY_OFFER,
    TX_PICK, TX_QTY, TX_PRICE, TX_DATE, TX_FEE, TX_NOTE, TX_CONFIRM,
    EDIT_VALUE, SETTINGS_VALUE,
) = range(15)

# Buyruq bo'lmagan oddiy matn
TEXT = filters.TEXT & ~filters.COMMAND

CANCEL_ROW = [("❌ Bekor qilish", "cancel")]


@dataclass
class BotDeps:
    storage: Storage
    repo: PortfolioRepo
    notifier: TelegramNotifier


def deps(context: ContextTypes.DEFAULT_TYPE) -> BotDeps:
    return context.bot_data["deps"]


def keyboard(*rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """keyboard([("Ha", "add:yes"), ("Yo'q", "add:no")], CANCEL_ROW)"""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text, callback_data=data) for text, data in row] for row in rows]
    )


async def send(update: Update, text: str, reply_markup=None) -> None:
    await update.effective_chat.send_message(text, reply_markup=reply_markup)


async def ack(update: Update) -> None:
    """Tugma bosilgan bo'lsa, Telegram'dagi "soat" belgisini olib tashlaydi."""
    if update.callback_query:
        await update.callback_query.answer()


def callback_arg(update: Update, index: int) -> str:
    return update.callback_query.data.split(":")[index]


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ack(update)
    context.user_data.clear()
    await send(update, "Bekor qilindi.")
    return END

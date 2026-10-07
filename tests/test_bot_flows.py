"""Bot formalarini Telegram'siz sinash: handler funksiyalari soxta Update/Context bilan chaqiriladi.

Har bir yuborilgan xabar Telegram HTML qoidalariga mosligi ham tekshiriladi.
"""
import asyncio
import re
from types import SimpleNamespace

import pytest

from uzse_agent.bot import handlers_add, handlers_tx
from uzse_agent.bot import common as c
from uzse_agent.bot.common import BotDeps
from uzse_agent.notifier import TelegramNotifier
from uzse_agent.portfolio import Transaction
from uzse_agent.repo import Security
from uzse_agent.scraper import PriceQuote

ISIN = "UZ7036271003"
QUOTE = PriceQuote("UZNGP", ISIN, "<O'zbekneftgaz> aksiyadorlik jamiyati", 5250.0, -129.0, -2.4, "2026-10-07")

_TAG = re.compile(r"<(/?)([a-z]+)[^>]*>")
_ALLOWED_TAGS = {"b", "i", "code"}


def assert_telegram_html(text: str) -> None:
    """Faqat ruxsat etilgan teglar; qolgan < va & escape qilingan bo'lishi kerak."""
    stripped = text
    for match in _TAG.finditer(text):
        assert match.group(2) in _ALLOWED_TAGS, f"ruxsat etilmagan teg: {match.group(0)!r} in {text!r}"
    stripped = _TAG.sub("", stripped)
    assert "<" not in stripped and ">" not in stripped, f"escape qilinmagan < yoki >: {text!r}"
    assert not re.search(r"&(?!(lt|gt|amp|quot);)", stripped), f"escape qilinmagan &: {text!r}"


class FakeChat:
    def __init__(self):
        self.sent: list[tuple[str, object]] = []

    async def send_message(self, text, reply_markup=None):
        assert_telegram_html(text)
        self.sent.append((text, reply_markup))

    @property
    def last(self) -> str:
        return self.sent[-1][0]

    def buttons(self) -> list[str]:
        markup = self.sent[-1][1]
        return [b.callback_data for row in markup.inline_keyboard for b in row] if markup else []


class FakeQuery:
    def __init__(self, data):
        self.data = data

    async def answer(self, *args, **kwargs):
        pass


class Bot:
    """Bitta chat bilan suhbatni simulyatsiya qiladi."""

    def __init__(self, repo, storage):
        self.chat = FakeChat()
        self.context = SimpleNamespace(
            bot_data={"deps": BotDeps(storage=storage, repo=repo, notifier=TelegramNotifier("", ""))},
            user_data={},
            args=[],
        )

    def text(self, handler, text):
        update = SimpleNamespace(effective_chat=self.chat, message=SimpleNamespace(text=text), callback_query=None)
        return asyncio.run(handler(update, self.context))

    def press(self, handler, data):
        update = SimpleNamespace(effective_chat=self.chat, message=None, callback_query=FakeQuery(data))
        return asyncio.run(handler(update, self.context))


@pytest.fixture
def bot(repo, storage, monkeypatch):
    monkeypatch.setattr(handlers_add, "get_quotes", lambda codes: {"UZNGP": QUOTE} if codes == ["UZNGP"] else {})
    return Bot(repo, storage)


def test_add_then_buy_flow(bot, repo):
    assert bot.text(handlers_add.add_start, "/add") == c.ADD_CODE
    assert bot.text(handlers_add.add_code, "UZ0000000000") == c.ADD_CODE
    assert "topilmadi" in bot.chat.last
    assert bot.text(handlers_add.add_code, " uzngp ") == c.ADD_CONFIRM
    assert "&lt;O'zbekneftgaz&gt;" in bot.chat.last
    assert bot.press(handlers_add.add_confirm, "add:yes") == c.ADD_DROP
    assert bot.text(handlers_add.add_drop, "abc") == c.ADD_DROP
    assert bot.text(handlers_add.add_drop, "7") == c.ADD_TRAIL
    assert bot.press(handlers_add.add_trail, "pct:off") == c.ADD_KEYWORDS
    assert bot.text(handlers_add.add_keywords, "Neftgaz, НГК") == c.ADD_BUY_OFFER
    assert f"tx:buy:{ISIN}" in bot.chat.buttons()

    sec = repo.get_security(ISIN)
    assert (sec.ticker, sec.drop_alert_pct, sec.trailing_drop_pct, sec.extra_keywords) == ("UZNGP", 7.0, None, ["Neftgaz", "НГК"])

    assert bot.press(handlers_tx.tx_direct, f"tx:buy:{ISIN}") == c.TX_QTY
    assert bot.text(handlers_tx.tx_quantity, "2.5") == c.TX_QTY
    assert bot.text(handlers_tx.tx_quantity, "30") == c.TX_PRICE
    assert bot.text(handlers_tx.tx_price, "6 730,40") == c.TX_DATE
    assert bot.text(handlers_tx.tx_date, "2999-01-01") == c.TX_DATE
    assert "Kelajak" in bot.chat.last
    assert bot.press(handlers_tx.tx_date, "date:today") == c.TX_FEE
    assert bot.press(handlers_tx.tx_fee, "fee:0") == c.TX_NOTE
    assert bot.text(handlers_tx.tx_note, "birinchi <xarid> & test") == c.TX_CONFIRM
    assert "6 730.40" in bot.chat.last and "&lt;xarid&gt; &amp; test" in bot.chat.last
    assert repo.transactions(ISIN) == []  # tasdiqlanmaguncha yozilmaydi
    assert bot.press(handlers_tx.tx_save, "tx:save") == c.END
    assert "Saqlandi" in bot.chat.last

    pos = repo.position(ISIN)
    assert pos.quantity == 30 and pos.avg_cost == pytest.approx(6730.40)
    assert bot.context.user_data == {}


def test_add_existing_security_ends(bot, repo):
    repo.add_security(Security(ISIN, "UZNGP", "N"))
    bot.text(handlers_add.add_start, "/add")
    assert bot.text(handlers_add.add_code, "UZNGP") == c.END
    assert "allaqachon" in bot.chat.last


def _seed_position(repo, day="2026-10-01"):
    repo.add_security(Security(ISIN, "UZNGP", "<O'zbekneftgaz> AJ"))
    repo.add_transaction(ISIN, Transaction(None, "buy", 30, 6000.0, 0.0, day))


def test_sell_flow_limits_quantity_and_realizes(bot, repo, storage):
    _seed_position(repo)
    storage.record_price(ISIN, 7000.0, None)
    assert bot.text(handlers_tx.sell_start, "/sell") == c.TX_PICK
    assert f"pick:{ISIN}" in bot.chat.buttons()
    assert bot.press(handlers_tx.tx_picked, f"pick:{ISIN}") == c.TX_QTY
    assert bot.text(handlers_tx.tx_quantity, "31") == c.TX_QTY
    assert "faqat 30" in bot.chat.last
    assert bot.text(handlers_tx.tx_quantity, "10") == c.TX_PRICE
    assert "price:last" in bot.chat.buttons()
    assert bot.press(handlers_tx.tx_price, "price:last") == c.TX_DATE
    assert bot.text(handlers_tx.tx_date, "2026-10-05") == c.TX_FEE
    assert bot.text(handlers_tx.tx_fee, "500") == c.TX_NOTE
    assert bot.press(handlers_tx.tx_note, "note:skip") == c.TX_CONFIRM
    assert "+9 500" in bot.chat.last  # 10 × (7000 − 6000) − 500
    assert bot.press(handlers_tx.tx_save, "tx:save") == c.END
    assert repo.position(ISIN).quantity == 20


def test_backdated_sell_is_rejected_before_save(bot, repo):
    _seed_position(repo, day="2026-10-05")
    bot.press(handlers_tx.tx_direct, f"tx:sell:{ISIN}")
    bot.text(handlers_tx.tx_quantity, "10")
    bot.text(handlers_tx.tx_price, "7000")
    bot.text(handlers_tx.tx_date, "2026-10-01")
    bot.press(handlers_tx.tx_fee, "fee:0")
    assert bot.press(handlers_tx.tx_note, "note:skip") == c.END
    assert "❌" in bot.chat.last and "2026-10-01" in bot.chat.last
    assert len(repo.transactions(ISIN)) == 1


def test_sell_without_holdings(bot, repo):
    repo.add_security(Security(ISIN, "UZNGP", "N"))
    assert bot.text(handlers_tx.sell_start, "/sell") == c.END
    assert "yo'q" in bot.chat.last


def test_buy_with_empty_portfolio(bot):
    assert bot.text(handlers_tx.buy_start, "/buy") == c.END
    assert "/add" in bot.chat.last


def test_cancel_clears_form(bot):
    bot.text(handlers_add.add_start, "/add")
    assert bot.press(c.cancel, "cancel") == c.END
    assert bot.context.user_data == {} and "Bekor" in bot.chat.last


def test_settings_rejects_huge_value(bot):
    from uzse_agent.bot import handlers_admin

    bot.press(handlers_admin.settings_ask, "set:price_history_days")
    assert bot.text(handlers_admin.settings_value, "1000000") == c.SETTINGS_VALUE
    assert bot.text(handlers_admin.settings_value, "90") == c.END

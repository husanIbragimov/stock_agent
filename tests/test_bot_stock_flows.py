"""/list, /stock kartochkasi, tarix, o'chirish va tahrirlash — Telegram'siz sinov."""
import pytest

from uzse_agent.bot import common as c
from uzse_agent.bot import handlers_stock as hs
from uzse_agent.portfolio import Transaction
from uzse_agent.repo import Security
from uzse_agent.scraper import PriceQuote
from tests.test_bot_flows import Bot

ISIN = "UZ7036271003"
OTHER = "UZ701879K017"


@pytest.fixture
def bot(repo, storage):
    repo.add_security(Security(ISIN, "UZNGP", "<O'zbekneftgaz> AJ", ["<kw>"], 7.0, 10.0))
    repo.add_security(Security(OTHER, "BRBNP", "BRB & Co"))
    repo.add_transaction(ISIN, Transaction(None, "buy", 10, 6000.0, 0.0, "2026-10-01"))
    repo.add_transaction(ISIN, Transaction(None, "sell", 4, 7000.0, 0.0, "2026-10-02", "<izoh>"))
    storage.record_price(ISIN, 5000.0, None)
    return Bot(repo, storage)


def _tx_ids(repo):
    return [tx.id for tx in repo.transactions(ISIN)]


def test_list_sends_one_message_per_stock_with_live_price(bot, storage, monkeypatch):
    requested = []

    def fake_quotes(codes):
        requested.extend(codes)
        return {ISIN: PriceQuote("UZNGP", ISIN, "x", 5250.0, -129.0, -2.4, "2026-10-07")}  # OTHER: sayt javob bermadi

    monkeypatch.setattr(hs, "get_quotes", fake_quotes)
    bot.text(hs.cmd_list, "/list")
    texts = [t for t, _ in bot.chat.sent]
    assert requested == [ISIN, OTHER]
    assert len(texts) == 4  # "olinmoqda", 2 ta aksiya, jami
    assert "olinmoqda" in texts[0]
    assert "5 250 UZS" in texts[1] and "-129" in texts[1] and "6 dona" in texts[1]
    assert "BRB &amp; Co" in texts[2] and "Kuzatuvda" in texts[2] and "noma'lum" in texts[2]
    assert "Jami" in texts[3]
    assert storage.last_price(ISIN) == 5250.0  # jonli narx tarixga yozildi
    owned_buttons = [b.callback_data for row in bot.chat.sent[1][1].inline_keyboard for b in row]
    watch_buttons = [b.callback_data for row in bot.chat.sent[2][1].inline_keyboard for b in row]
    assert owned_buttons == [f"tx:buy:{ISIN}", f"tx:sell:{ISIN}", f"stock:{ISIN}"]
    assert watch_buttons == [f"tx:buy:{OTHER}", f"stock:{OTHER}"]


def test_list_empty(repo, storage):
    bot = Bot(repo, storage)
    bot.text(hs.cmd_list, "/list")
    assert "bo'sh" in bot.chat.last


def test_stock_picker_and_card(bot):
    bot.text(hs.cmd_stock, "/stock")
    assert bot.chat.buttons() == [f"stock:{ISIN}", f"stock:{OTHER}"]
    bot.press(hs.show_card, f"stock:{ISIN}")
    assert "&lt;izoh&gt;" in bot.chat.last and "-7%" in bot.chat.last
    assert {f"tx:buy:{ISIN}", f"tx:sell:{ISIN}", f"editmenu:{ISIN}", f"hist:{ISIN}", f"secdel:{ISIN}"} == set(bot.chat.buttons())


def test_card_for_deleted_security(bot):
    bot.press(hs.show_card, "stock:UZ0000000000")
    assert "topilmadi" in bot.chat.last


def test_history_and_delete_rejected_when_it_breaks_position(bot, repo):
    buy_id, sell_id = _tx_ids(repo)
    bot.press(hs.show_history, f"hist:{ISIN}")
    assert f"txdel:{buy_id}" in bot.chat.buttons() and f"stock:{ISIN}" in bot.chat.buttons()
    bot.press(hs.ask_delete_tx, f"txdel:{buy_id}")
    assert f"txdel:{buy_id}:yes" in bot.chat.buttons()
    bot.press(hs.delete_tx, f"txdel:{buy_id}:yes")
    assert "O'chirib bo'lmaydi" in bot.chat.last
    assert _tx_ids(repo) == [buy_id, sell_id]


def test_delete_transaction(bot, repo):
    buy_id, sell_id = _tx_ids(repo)
    bot.press(hs.delete_tx, f"txdel:{sell_id}:yes")
    assert _tx_ids(repo) == [buy_id]
    assert any("O'chirildi" in text for text, _ in bot.chat.sent)
    bot.press(hs.delete_tx, f"txdel:{sell_id}:yes")
    assert "topilmadi" in bot.chat.last


def test_delete_security(bot, repo):
    bot.press(hs.ask_delete_security, f"secdel:{ISIN}")
    assert "2 ta tranzaksiya" in bot.chat.last
    bot.press(hs.delete_security, f"secdel:{ISIN}:yes")
    assert repo.get_security(ISIN) is None and repo.transactions(ISIN) == []
    assert "2 ta tranzaksiya o'chirildi" in bot.chat.last


def test_edit_pct_and_keywords(bot, repo):
    bot.press(hs.edit_menu, f"editmenu:{ISIN}")
    assert f"edit:drop:{ISIN}" in bot.chat.buttons()
    assert bot.press(hs.edit_start, f"edit:drop:{ISIN}") == c.EDIT_VALUE
    assert bot.text(hs.edit_value, "150") == c.EDIT_VALUE
    assert bot.text(hs.edit_value, "5") == c.END
    assert repo.get_security(ISIN).drop_alert_pct == 5.0

    bot.press(hs.edit_start, f"edit:trail:{ISIN}")
    assert bot.press(hs.edit_value, "val:off") == c.END
    assert repo.get_security(ISIN).trailing_drop_pct is None

    bot.press(hs.edit_start, f"edit:kw:{ISIN}")
    assert bot.text(hs.edit_value, "a, b") == c.END
    assert repo.get_security(ISIN).extra_keywords == ["a", "b"]
    bot.press(hs.edit_start, f"edit:kw:{ISIN}")
    bot.press(hs.edit_value, "val:off")
    assert repo.get_security(ISIN).extra_keywords == []
    assert bot.context.user_data == {}

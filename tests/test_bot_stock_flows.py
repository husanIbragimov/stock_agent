"""/list, /stock kartochkasi, tarix, o'chirish va tahrirlash — Telegram'siz sinov."""
import pytest

from uzse_agent.bot import common as c
from uzse_agent.bot import handlers_stock as hs
from uzse_agent.portfolio import Transaction
from uzse_agent.repo import Security
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


def test_list_shows_owned_and_watch(bot):
    bot.text(hs.cmd_list, "/list")
    text = bot.chat.last
    assert "6 dona" in text and "Kuzatuv" in text and "BRB &amp; Co" in text


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

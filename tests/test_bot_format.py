import html
import re

from uzse_agent.bot import format as fmt
from uzse_agent.config import Settings
from uzse_agent.portfolio import Position, Transaction
from uzse_agent.repo import Security
from uzse_agent.scraper import PriceQuote

SEC = Security("UZ7036271003", "UZNGP", "<O'zbekneftgaz> & Co", ["<kw>"], 7.0, None)
LAST = (5000.0, "2026-10-07T08:30:00+00:00")


def no_raw_html_from_data(text: str) -> bool:
    return "<O'zbekneftgaz>" not in text and "<kw>" not in text and "& Co" not in text


def test_security_title_and_button():
    assert fmt.security_title(SEC) == "<b>UZNGP</b> — &lt;O'zbekneftgaz&gt; &amp; Co"
    assert fmt.security_button(SEC) == "UZNGP — <O'zbekneftgaz> & Co"
    assert len(fmt.security_button(Security("UZ1", None, "x" * 100))) <= 60


def test_fmt_time_converts_to_tashkent():
    assert fmt.fmt_time("2026-10-07T08:30:00+00:00") == "2026-10-07 13:30"


def test_quote_text_escapes():
    q = PriceQuote("UZNGP", "UZ7036271003", "<O'zbekneftgaz>", 5250.0, -129.0, -2.4, "2026-10-07")
    text = fmt.quote_text(q)
    assert "&lt;O'zbekneftgaz&gt;" in text and "5 250 UZS" in text and "-129" in text and "-2.40%" in text


def test_position_text_owned():
    text = fmt.position_text(SEC, Position(10, 6000.0, 0.0), LAST)
    assert "10 dona" in text and "6 000" in text and "-10 000 UZS" in text and "(-16.7%)" in text
    assert "2026-10-07 13:30" in text
    assert no_raw_html_from_data(text)


def test_position_text_watch_and_realized():
    text = fmt.position_text(SEC, Position(0, None, 250.0), None)
    assert "Kuzatuvda" in text and "+250 UZS" in text


def test_portfolio_list():
    other = Security("UZ701879K017", "BRBNP", "BRB")
    text = fmt.portfolio_list([(SEC, Position(10, 6000.0, 0.0), LAST), (other, Position(0, None, 0.0), None)])
    assert "Portfel" in text and "Kuzatuv" in text and "BRB" in text
    assert "Jami" in text and "-10 000" in text
    assert no_raw_html_from_data(text)
    assert "bo'sh" in fmt.portfolio_list([])


def test_tx_line_and_card_escape_note():
    tx = Transaction(5, "sell", 3, 5250.0, 1000.0, "2026-10-07", "<b>izoh</b>")
    line = fmt.tx_line(tx)
    assert line.startswith("#5 2026-10-07 🔴 Sotuv: 3 × 5 250 UZS")
    assert "komissiya 1 000" in line and "&lt;b&gt;izoh&lt;/b&gt;" in line
    card = fmt.stock_card(SEC, Position(10, 6000.0, 0.0), LAST, [tx])
    assert "o'chiq" in card and "-7%" in card and "&lt;kw&gt;" in card
    assert no_raw_html_from_data(card)
    assert "#5" in fmt.history_text(SEC, [tx])


def test_tx_summary():
    tx = Transaction(None, "sell", 10, 7000.0, 0.0, "2026-10-07")
    text = fmt.tx_summary(SEC, tx, Position(0, None, 10000.0))
    assert "#None" not in text and "70 000" in text and "pozitsiya yopiladi" in text and "+10 000" in text


def test_settings_text():
    text = fmt.settings_text(Settings(price_history_days=90))
    assert "90" in text and set(fmt.SETTING_LABELS) == {"max_alerts_per_ticker_per_day", "price_history_days", "news_lookback_hours"}


def test_history_fits_one_telegram_message():
    # 20 ta tranzaksiya, har birida 200 belgilik izoh — xabar 4096 dan oshmasligi kerak
    txs = [Transaction(i, "buy", 1000, 5249.99, 1500.0, "2026-10-07", "<" * 200) for i in range(1, 21)]
    text = fmt.history_text(SEC, txs)
    # Telegram chegarasi entity'lar ochilgandan keyingi (ko'rinadigan) matnga qo'llanadi
    rendered = html.unescape(re.sub(r"</?(b|i|code)>", "", text))
    assert len(rendered) < 4096
    assert "<" * 40 + "…" in rendered

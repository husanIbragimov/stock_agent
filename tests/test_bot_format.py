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


QUOTE = PriceQuote("UZNGP", "UZ7036271003", "<O'zbekneftgaz>", 5250.0, -129.0, -2.4, "2026-10-07")


def test_list_item_live_price():
    text = fmt.list_item(SEC, Position(10, 6000.0, 0.0), QUOTE, LAST)
    assert "5 250 UZS" in text and "-129" in text and "-2.40%" in text and "2026-10-07" in text
    assert "10 dona" in text and "6 000" in text
    assert "Qiymat: 52 500 UZS" in text and "-7 500 UZS" in text and "(-12.5%)" in text
    assert "saqlangan" not in text
    assert no_raw_html_from_data(text)


def test_list_item_falls_back_to_stored_price():
    text = fmt.list_item(SEC, Position(10, 6000.0, 0.0), None, LAST)
    assert "5 000 UZS" in text and "saqlangan" in text and "2026-10-07 13:30" in text
    assert "-10 000 UZS" in text


def test_list_item_watch_without_any_price():
    text = fmt.list_item(SEC, Position(0, None, 0.0), None, None)
    assert "Kuzatuvda" in text and "noma'lum" in text


def test_portfolio_total():
    other = Security("UZ701879K017", "BRBNP", "BRB")
    text = fmt.portfolio_total([
        (SEC, Position(10, 6000.0, 0.0), 5250.0),
        (other, Position(0, None, 0.0), 845.0),
        (Security("UZ1", None, "X"), Position(5, 100.0, 0.0), None),
    ])
    assert "2 ta aksiya portfelda, 1 ta kuzatuvda" in text
    assert "Qiymat: 52 500 UZS" in text and "-7 500 UZS" in text
    assert "1 ta aksiya narxi noma'lum" in text


def test_fee_buttons():
    labels = [label for label, _ in fmt.fee_buttons(5, 30, 6730.0)]
    assert labels == ["Har bir dona uchun: 30 × 5 = 150", "Jami: 5", "Summadan 5%: 10 095"]
    datas = [data for _, data in fmt.fee_buttons(5, 30, 6730.0)]
    assert datas == ["feemode:unit", "feemode:total", "feemode:pct"]
    assert [d for _, d in fmt.fee_buttons(150, 30, 6730.0)] == ["feemode:unit", "feemode:total"]


def test_fee_detail_and_summary():
    assert fmt.fee_detail(5, "unit", 30, 6730.0) == "30 × 5"
    assert fmt.fee_detail(5, "total", 30, 6730.0) is None
    assert fmt.fee_detail(0.5, "pct", 30, 6730.0) == "0.5% × 201 900"
    tx = Transaction(None, "buy", 30, 6730.0, 150.0, "2026-10-07")
    assert "komissiya 150 (30 × 5)" in fmt.tx_summary(SEC, tx, Position(30, 6735.0, 0.0), fee_detail="30 × 5")


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

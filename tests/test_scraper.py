from pathlib import Path

import pytest

from uzse_agent import scraper
from uzse_agent.scraper import PriceQuote, _to_float, parse_stock_page, parse_ticker_index

FIXTURE = Path(__file__).parent / "fixtures" / "uzse_stock_UZ7036271003.html"


@pytest.fixture
def stock_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("5,250", 5250.0),
        ("5,249.99", 5249.99),
        ("14,917,860", 14917860.0),
        ("200,50", 200.5),
        ("3 200,50", 3200.5),
        ("3.200,50", 3200.5),
        ("▼ -129", -129.0),
        ("▼ -1,000", -1000.0),
        ("( ▼ 1000.0 )", 1000.0),
        ("—", None),
        ("", None),
    ],
)
def test_to_float(text, expected):
    assert _to_float(text) == expected


def test_parse_stock_page(stock_html):
    quote = parse_stock_page(stock_html)
    assert quote == PriceQuote(
        ticker="UZNGP",
        isin="UZ7036271003",
        name="<O'zbekneftgaz> aksiyadorlik jamiyati",
        price=5250.0,
        change=-129.0,
        change_pct=-2.4,
        last_trade_date="2026-10-07",
    )


def test_parse_stock_page_returns_none_without_card():
    assert parse_stock_page("<html><body><h1>404</h1></body></html>") is None


def test_parse_ticker_index(stock_html):
    index = parse_ticker_index(stock_html)
    assert index["UPOSP"] == "UZ700528K011"
    assert all(isin.startswith("UZ") and len(isin) == 12 for isin in index.values())


def test_get_quotes_keys_by_requested_code(monkeypatch, stock_html):
    monkeypatch.setattr(scraper, "fetch_html", lambda url, **kw: stock_html)
    monkeypatch.setattr(scraper, "REQUEST_DELAY_SEC", 0)
    quotes = scraper.get_quotes(["uz7036271003"])
    assert list(quotes) == ["UZ7036271003"]
    assert quotes["UZ7036271003"].ticker == "UZNGP"


def test_get_quotes_rejects_page_for_other_isin(monkeypatch, stock_html):
    monkeypatch.setattr(scraper, "fetch_html", lambda url, **kw: stock_html)
    monkeypatch.setattr(scraper, "REQUEST_DELAY_SEC", 0)
    assert scraper.get_quotes(["UZ701879K017"]) == {}

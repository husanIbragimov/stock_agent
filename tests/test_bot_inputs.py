from datetime import date

import pytest

from uzse_agent.bot.inputs import (
    InputError,
    parse_date,
    parse_fee,
    parse_keywords,
    parse_note,
    parse_pct,
    parse_positive_int,
    parse_price,
    parse_quantity,
)


@pytest.mark.parametrize("text, expected", [("30", 30), ("1 000", 1000), ("1,000", 1000), ("1 000", 1000), (" 7 ", 7)])
def test_parse_quantity(text, expected):
    assert parse_quantity(text) == expected


@pytest.mark.parametrize("text", ["0", "-5", "2.5", "abc", "", "²"])
def test_parse_quantity_rejects(text):
    with pytest.raises(InputError):
        parse_quantity(text)


def test_parse_positive_int():
    assert parse_positive_int("90") == 90
    with pytest.raises(InputError):
        parse_positive_int("0")


@pytest.mark.parametrize(
    "text, expected",
    [("5250", 5250.0), ("5 250,50", 5250.5), ("5,250", 5250.0), ("5250 so'm", 5250.0), ("5 250", 5250.0), ("6.46", 6.46)],
)
def test_parse_price(text, expected):
    assert parse_price(text) == expected


@pytest.mark.parametrize("text", ["0", "-1", "abc", ""])
def test_parse_price_rejects(text):
    with pytest.raises(InputError):
        parse_price(text)


def test_parse_fee():
    assert parse_fee("0") == 0.0
    assert parse_fee("1 500") == 1500.0
    with pytest.raises(InputError):
        parse_fee("-1")


@pytest.mark.parametrize("text, expected", [("7", 7.0), ("7.5", 7.5), ("7%", 7.0), ("12,5", 12.5)])
def test_parse_pct(text, expected):
    assert parse_pct(text) == expected


@pytest.mark.parametrize("text", ["0", "100", "150", "abc"])
def test_parse_pct_rejects(text):
    with pytest.raises(InputError):
        parse_pct(text)


def test_parse_date():
    today = date(2026, 10, 7)
    assert parse_date(" 2026-10-07 ", today) == "2026-10-07"
    assert parse_date("2026-01-15", today) == "2026-01-15"
    with pytest.raises(InputError, match="Kelajak"):
        parse_date("2026-10-08", today)
    with pytest.raises(InputError):
        parse_date("07.10.2026", today)


def test_parse_keywords_and_note():
    assert parse_keywords(" a, b ,, a ") == ["a", "b"]
    assert parse_note("  salom ") == "salom"
    with pytest.raises(InputError):
        parse_note("x" * 201)


@pytest.mark.parametrize("text", ["2,5", "1,5", "5 250,50", "1 2 3", "12,34", "9" * 30])
def test_parse_quantity_rejects_comma_decimals_and_garbage(text):
    # "2,5" — o'nlik kasr, 25 dona emas
    with pytest.raises(InputError):
        parse_quantity(text)


@pytest.mark.parametrize("text, expected", [("1,000", 1000), ("12 345 678", 12345678), ("1 000", 1000)])
def test_parse_quantity_accepts_thousands_grouping(text, expected):
    assert parse_quantity(text) == expected

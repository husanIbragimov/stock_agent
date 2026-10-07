from uzse_agent.textfmt import esc, fmt_money, fmt_qty, fmt_signed, split_message


def test_esc_keeps_apostrophe():
    assert esc("<O'zbekneftgaz> & Co") == "&lt;O'zbekneftgaz&gt; &amp; Co"
    assert esc(5) == "5"


def test_fmt_money():
    assert fmt_money(5250.0) == "5 250"
    assert fmt_money(5249.99) == "5 249.99"
    assert fmt_money(6.5) == "6.50"
    assert fmt_money(14917860) == "14 917 860"


def test_fmt_signed_and_qty():
    assert fmt_signed(-10000) == "-10 000"
    assert fmt_signed(200) == "+200"
    assert fmt_qty(1000) == "1 000"
    assert fmt_qty(30.0) == "30"


def test_split_short_message_unchanged():
    assert split_message("salom\ndunyo") == ["salom\ndunyo"]


def test_split_on_line_boundaries():
    lines = [f"{i:03d} " + "x" * 30 for i in range(300)]
    text = "\n".join(lines)
    parts = split_message(text, limit=4000)
    assert len(parts) > 1
    assert all(len(p) <= 4000 for p in parts)
    assert "\n".join(parts) == text


def test_split_very_long_line():
    parts = split_message("a" * 9000, limit=4000)
    assert [len(p) for p in parts] == [4000, 4000, 1000]

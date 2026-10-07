import pytest

from uzse_agent.importer import import_yaml
from uzse_agent.scraper import PriceQuote

YAML = """
holdings:
  - ticker: UZ7036271003
    name: "O'zbekneftgaz AJ"
    quantity: 30
    buy_price: 6730.40
    drop_alert_pct: 7
    trailing_drop_pct: 10
    extra_keywords: ["UZNGP"]
  - ticker: UZNGP
    name: "Takror"
    quantity: 5
    buy_price: 100
  - ticker: NOPE
    name: "Yo'q aksiya"
watchlist:
  - ticker: UZ701879K017
    name: "Biznesni rivojlantirish banki"
settings:
  price_history_days: 90
"""

QUOTES = {
    "UZ7036271003": PriceQuote("UZNGP", "UZ7036271003", "<O'zbekneftgaz>", 5250, None, None, None),
    "UZNGP": PriceQuote("UZNGP", "UZ7036271003", "<O'zbekneftgaz>", 5250, None, None, None),
    "UZ701879K017": PriceQuote("BRBNP", "UZ701879K017", "<BRB>", 845, None, None, None),
}


@pytest.fixture
def yaml_path(tmp_path):
    path = tmp_path / "portfolio.yaml"
    path.write_text(YAML, encoding="utf-8")
    return path


def fake_resolve(codes):
    return {c.strip().upper(): QUOTES[c.strip().upper()] for c in codes if c.strip().upper() in QUOTES}


def test_import(yaml_path, repo):
    result = import_yaml(yaml_path, repo, resolve=fake_resolve, today="2026-10-07")

    assert result.transactions == 1
    assert [s.isin for s in repo.list_securities()] == ["UZ7036271003", "UZ701879K017"]
    sec = repo.get_security("UZ7036271003")
    assert sec.name == "O'zbekneftgaz AJ"  # YAML'dagi nom saqlanadi, saytdagisi emas
    assert sec.ticker == "UZNGP"
    assert (sec.drop_alert_pct, sec.trailing_drop_pct) == (7, 10)
    (tx,) = repo.transactions("UZ7036271003")
    assert (tx.side, tx.quantity, tx.price, tx.traded_at) == ("buy", 30, 6730.40, "2026-10-07")
    assert repo.position("UZ701879K017").quantity == 0
    assert repo.load_settings().price_history_days == 90

    skipped = "\n".join(result.skipped)
    assert "UZNGP" in skipped and "NOPE" in skipped
    assert "Qo'shilgan aksiyalar: 2" in result.summary()


def test_import_refuses_when_transactions_exist(yaml_path, repo):
    import_yaml(yaml_path, repo, resolve=fake_resolve, today="2026-10-07")
    with pytest.raises(RuntimeError):
        import_yaml(yaml_path, repo, resolve=fake_resolve, today="2026-10-07")
    assert len(repo.transactions("UZ7036271003")) == 1


def test_import_rejects_fractional_quantity(tmp_path, repo):
    path = tmp_path / "p.yaml"
    path.write_text(
        "holdings:\n  - ticker: UZ7036271003\n    name: N\n    quantity: 2.5\n    buy_price: 10\n",
        encoding="utf-8",
    )
    result = import_yaml(path, repo, resolve=fake_resolve, today="2026-10-07")
    assert result.transactions == 0
    assert repo.get_security("UZ7036271003") is not None
    assert any("butun" in s for s in result.skipped)

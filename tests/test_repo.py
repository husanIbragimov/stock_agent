import pytest

from uzse_agent.config import Settings
from uzse_agent.portfolio import NegativePositionError, Transaction
from uzse_agent.repo import Security

ISIN = "UZ7036271003"
OTHER = "UZ701879K017"


def sec(isin=ISIN, **kw):
    defaults = dict(ticker="UZNGP", name="<O'zbekneftgaz> AJ", extra_keywords=["Neftgaz"],
                    drop_alert_pct=7.0, trailing_drop_pct=None)
    defaults.update(kw)
    return Security(isin=isin, **defaults)


def buy(qty, price, day="2026-10-01", fee=0.0):
    return Transaction(None, "buy", qty, price, fee, day, "izoh")


def sell(qty, price, day="2026-10-02", fee=0.0):
    return Transaction(None, "sell", qty, price, fee, day)


def test_security_roundtrip(repo):
    repo.add_security(sec(extra_keywords=["O'zbekneftgaz", "Узбекнефтегаз"]))
    assert repo.get_security(ISIN) == sec(extra_keywords=["O'zbekneftgaz", "Узбекнефтегаз"])
    assert repo.get_security(OTHER) is None


def test_list_securities_in_insert_order(repo):
    repo.add_security(sec(OTHER, ticker="BRBNP", name="BRB"))
    repo.add_security(sec())
    assert [s.isin for s in repo.list_securities()] == [OTHER, ISIN]


def test_duplicate_security_rejected(repo):
    repo.add_security(sec())
    with pytest.raises(ValueError):
        repo.add_security(sec())


def test_update_security(repo):
    repo.add_security(sec())
    repo.update_security(ISIN, drop_alert_pct=None, trailing_drop_pct=12.5, extra_keywords=["a", "b"])
    s = repo.get_security(ISIN)
    assert (s.drop_alert_pct, s.trailing_drop_pct, s.extra_keywords) == (None, 12.5, ["a", "b"])


def test_update_security_rejects_unknown_field_and_missing_isin(repo):
    repo.add_security(sec())
    with pytest.raises(ValueError):
        repo.update_security(ISIN, name="boshqa")
    with pytest.raises(KeyError):
        repo.update_security(OTHER, drop_alert_pct=5.0)


def test_add_transaction_returns_id_and_position(repo):
    repo.add_security(sec())
    tx_id, pos = repo.add_transaction(ISIN, buy(10, 6000, fee=100))
    assert isinstance(tx_id, int)
    assert pos.quantity == 10 and pos.avg_cost == pytest.approx(6010)
    assert repo.position(ISIN) == pos
    assert repo.transactions(ISIN)[0].note == "izoh"
    assert repo.get_transaction(tx_id) == (ISIN, repo.transactions(ISIN)[0])
    assert repo.has_transactions()


def test_add_transaction_unknown_isin(repo):
    with pytest.raises(KeyError):
        repo.add_transaction(OTHER, buy(1, 1))


def test_oversell_rejected_and_nothing_written(repo):
    repo.add_security(sec())
    repo.add_transaction(ISIN, buy(5, 100))
    with pytest.raises(NegativePositionError):
        repo.add_transaction(ISIN, sell(6, 100))
    assert len(repo.transactions(ISIN)) == 1


def test_preview_does_not_write(repo):
    repo.add_security(sec())
    repo.add_transaction(ISIN, buy(10, 100))
    pos = repo.preview_transaction(ISIN, sell(4, 150))
    assert pos.quantity == 6
    assert len(repo.transactions(ISIN)) == 1


def test_delete_transaction_that_breaks_history_is_rejected(repo):
    repo.add_security(sec())
    buy_id, _ = repo.add_transaction(ISIN, buy(10, 100))
    repo.add_transaction(ISIN, sell(5, 120))
    with pytest.raises(NegativePositionError):
        repo.delete_transaction(buy_id)
    assert len(repo.transactions(ISIN)) == 2


def test_delete_transaction(repo):
    repo.add_security(sec())
    repo.add_transaction(ISIN, buy(10, 100))
    second_id, _ = repo.add_transaction(ISIN, buy(10, 200, day="2026-10-03"))
    pos = repo.delete_transaction(second_id)
    assert pos.quantity == 10 and pos.avg_cost == pytest.approx(100)
    with pytest.raises(KeyError):
        repo.delete_transaction(second_id)
    assert repo.get_transaction(second_id) is None


def test_delete_security_removes_transactions(repo):
    repo.add_security(sec())
    repo.add_transaction(ISIN, buy(10, 100))
    repo.add_transaction(ISIN, buy(1, 100))
    assert repo.delete_security(ISIN) == 2
    assert repo.get_security(ISIN) is None
    assert repo.transactions(ISIN) == []
    assert not repo.has_transactions()


def test_load_holdings(repo):
    repo.add_security(sec(extra_keywords=["UZNGP", "Neftgaz"]))
    repo.add_security(sec(OTHER, ticker="BRBNP", name="BRB", extra_keywords=[]))
    repo.add_transaction(ISIN, buy(10, 100))
    repo.add_transaction(ISIN, buy(10, 200))
    owned, watch = repo.load_holdings()
    assert owned.ticker == ISIN and owned.name == "<O'zbekneftgaz> AJ"
    assert owned.quantity == 20 and owned.buy_price == pytest.approx(150)
    assert owned.is_owned and owned.drop_alert_pct == 7.0
    assert owned.extra_keywords == ["UZNGP", "Neftgaz"]  # tiker boshida, takrorsiz
    assert watch.quantity == 0 and watch.buy_price is None and not watch.is_owned
    assert watch.extra_keywords == ["BRBNP"]


def test_settings_defaults_and_update(repo):
    assert repo.load_settings() == Settings()
    repo.set_setting("price_history_days", 90)
    assert repo.load_settings().price_history_days == 90
    repo.set_setting("price_history_days", 30)
    assert repo.load_settings().price_history_days == 30


@pytest.mark.parametrize("value", [0, -1, 2.5, True, "5"])
def test_set_setting_rejects_bad_value(repo, value):
    with pytest.raises(ValueError):
        repo.set_setting("price_history_days", value)


def test_set_setting_rejects_unknown_key(repo):
    with pytest.raises(KeyError):
        repo.set_setting("nima", 5)


def test_set_setting_rejects_huge_value(repo):
    # 10**12 kun timedelta'ni buzadi va har bir check/hisobot yiqiladi
    with pytest.raises(ValueError):
        repo.set_setting("price_history_days", 10**12)
    repo.set_setting("price_history_days", 3650)

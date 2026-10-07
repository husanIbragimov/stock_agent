import threading

from uzse_agent import runner
from uzse_agent.config import Holding, Settings
from uzse_agent.portfolio import Transaction
from uzse_agent.repo import Security
from uzse_agent.scraper import PriceQuote

ISIN = "UZ7036271003"
WATCH = "UZ701879K017"
NAME = "<O'zbekneftgaz> AJ"


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)
        return True


def quote(isin, price):
    return PriceQuote(ticker="X", isin=isin, name="x", price=price, change=None,
                      change_pct=None, last_trade_date=None)


def seed(repo):
    repo.add_security(Security(ISIN, "UZNGP", NAME, [], 7.0, None))
    repo.add_security(Security(WATCH, "BRBNP", "BRB", [], 7.0, None))
    repo.add_transaction(ISIN, Transaction(None, "buy", 10, 6000.0, 0.0, "2026-10-01"))


def test_check_thresholds_escapes_name(storage):
    holding = Holding(ticker=ISIN, name=NAME, quantity=10, buy_price=6000, drop_alert_pct=7)
    alerts = runner.check_thresholds(holding, 5000, storage, Settings())
    assert len(alerts) == 1
    assert "&lt;O'zbekneftgaz&gt; AJ" in alerts[0]
    assert NAME not in alerts[0]


def test_run_price_check_alerts_only_owned(monkeypatch, repo, storage):
    seed(repo)
    monkeypatch.setattr(runner, "get_quotes", lambda codes: {ISIN: quote(ISIN, 5000), WATCH: quote(WATCH, 1)})
    notifier = FakeNotifier()
    runner.run_price_check(repo, storage, notifier)
    assert storage.last_price(ISIN) == 5000
    assert storage.last_price(WATCH) == 1  # kuzatuvdagi aksiya narxi ham yoziladi
    assert len(notifier.sent) == 1 and "sotib olingan" in notifier.sent[0]
    assert storage.alerts_today_count(ISIN) == 1


def test_run_price_check_empty_portfolio(monkeypatch, repo, storage):
    monkeypatch.setattr(runner, "get_quotes", lambda codes: (_ for _ in ()).throw(AssertionError))
    runner.run_price_check(repo, storage, FakeNotifier())  # tarmoqqa chiqmaydi


def test_daily_report_uses_db_and_escapes(repo, storage):
    seed(repo)
    storage.record_price(ISIN, 5000, -1.0)
    report = runner.build_daily_report(repo, storage)
    assert "&lt;O'zbekneftgaz&gt; AJ" in report and NAME not in report
    assert "10 dona" in report
    assert "-10 000 UZS" in report
    assert "BRB" in report
    assert "&" not in report.replace("&lt;", "").replace("&gt;", "").replace("&amp;", "")


def test_run_exclusive_skips_when_busy():
    calls = []
    assert runner.run_exclusive(calls.append, 1) is True
    runner._RUN_LOCK.acquire()
    try:
        assert runner.run_exclusive(calls.append, 2) is False
    finally:
        runner._RUN_LOCK.release()
    assert calls == [1]


def test_storage_last_quote(storage):
    assert storage.last_quote(ISIN) is None
    storage.record_price(ISIN, 5000, None)
    price, fetched_at = storage.last_quote(ISIN)
    assert price == 5000 and fetched_at.endswith("+00:00")

from uzse_agent import notifier as notifier_mod
from uzse_agent.notifier import TelegramNotifier


class FakeResponse:
    def raise_for_status(self):
        pass


def test_send_splits_long_text(monkeypatch):
    sent = []
    monkeypatch.setattr(
        notifier_mod.requests, "post",
        lambda url, json, timeout: sent.append(json["text"]) or FakeResponse(),
    )
    text = "\n".join("qator " + "y" * 50 for _ in range(200))  # ~11 600 belgi
    assert TelegramNotifier("token", "42").send(text) is True
    assert len(sent) == 3
    assert all(len(t) <= 4096 for t in sent)


def test_send_without_config_returns_false():
    assert TelegramNotifier("", "").send("x") is False

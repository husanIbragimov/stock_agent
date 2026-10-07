from uzse_agent import news

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>O'zbekneftgaz foyda rekord</title><link>https://ex.uz/1</link><description>x</description></item>
</channel></rss>"""


class FakeResponse:
    content = RSS

    def raise_for_status(self):
        pass


def test_feeds_fetched_with_timeout(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(kwargs)
        return FakeResponse()

    monkeypatch.setattr(news.requests, "get", fake_get)
    monkeypatch.setattr(news, "RSS_FEEDS", ["https://ex.uz/rss"])
    items = news.fetch_news_for_keywords(["O'zbekneftgaz"])
    assert [i.url for i in items] == ["https://ex.uz/1"]
    assert calls and calls[0].get("timeout")


def test_feed_network_error_is_skipped(monkeypatch):
    def fail(url, **kwargs):
        raise news.requests.ConnectionError("down")

    monkeypatch.setattr(news.requests, "get", fail)
    monkeypatch.setattr(news, "RSS_FEEDS", ["https://ex.uz/rss"])
    assert news.fetch_news_for_keywords(["x"]) == []

"""Asosiy ish mantig'i: narxlarni tekshirish, threshold-alert va kunlik hisobot."""
from __future__ import annotations

import logging

from .analyzer import analyze
from .config import AppConfig, Holding
from .news import fetch_news_for_keywords
from .notifier import TelegramNotifier
from .scraper import get_quotes
from .storage import Storage

logger = logging.getLogger(__name__)


def _format_price(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ")


def check_thresholds(holding: Holding, current_price: float, storage: Storage, settings) -> list[str]:
    """Sotib olingan narx va so'nggi eng yuqori narxdan pasayishni tekshiradi.
    Ogohlantirish kerak bo'lsa, xabar matnlari ro'yxatini qaytaradi."""
    alerts: list[str] = []
    if not holding.is_owned:
        return alerts

    if storage.alerts_today_count(holding.ticker) >= settings.max_alerts_per_ticker_per_day:
        return alerts

    if holding.drop_alert_pct:
        drop_from_buy = (current_price - holding.buy_price) / holding.buy_price * 100
        if drop_from_buy <= -abs(holding.drop_alert_pct):
            alerts.append(
                f"⚠️ <b>{holding.ticker}</b> ({holding.name}) sotib olingan narxdan "
                f"<b>{drop_from_buy:.1f}%</b> pastda!\n"
                f"Sotib olingan: {_format_price(holding.buy_price)} UZS → "
                f"Hozir: {_format_price(current_price)} UZS"
            )

    if holding.trailing_drop_pct:
        recent_high = storage.recent_high(holding.ticker, days=30)
        if recent_high and recent_high > 0:
            drop_from_high = (current_price - recent_high) / recent_high * 100
            if drop_from_high <= -abs(holding.trailing_drop_pct):
                alerts.append(
                    f"📉 <b>{holding.ticker}</b> ({holding.name}) so'nggi 30 kunlik "
                    f"eng yuqori narxdan <b>{drop_from_high:.1f}%</b> pastda!\n"
                    f"Eng yuqori: {_format_price(recent_high)} UZS → "
                    f"Hozir: {_format_price(current_price)} UZS"
                )

    return alerts


def run_price_check(config: AppConfig, storage: Storage, notifier: TelegramNotifier) -> None:
    """Bir marta: barcha portfeldagi tikerlar narxini oladi, saqlaydi, threshold tekshiradi."""
    all_holdings = config.holdings  # faqat egalik qilinganlar uchun alert kerak
    tickers = [h.ticker for h in config.all_tickers()]
    if not tickers:
        logger.info("Portfolio/watchlist bo'sh — tekshirish uchun ticker yo'q")
        return

    quotes = get_quotes(tickers)

    for holding in all_holdings:
        quote = quotes.get(holding.ticker.upper())
        if not quote:
            continue
        storage.record_price(holding.ticker, quote.price, quote.change_pct)

        alerts = check_thresholds(holding, quote.price, storage, config.settings)
        for alert_text in alerts:
            if notifier.send(alert_text):
                storage.record_alert(holding.ticker, "threshold_drop", alert_text)

    # watchlist uchun ham narx tarixini yozib boramiz (alert yo'q, faqat kuzatuv)
    for holding in config.watchlist:
        quote = quotes.get(holding.ticker.upper())
        if quote:
            storage.record_price(holding.ticker, quote.price, quote.change_pct)


def run_news_scan(config: AppConfig, storage: Storage) -> None:
    """Barcha portfel/watchlist tikerlari uchun yangiliklarni yig'ib, saqlaydi."""
    for holding in config.all_tickers():
        items = fetch_news_for_keywords(
            holding.keywords(), lookback_hours=config.settings.news_lookback_hours
        )
        for item in items:
            if item.url and not storage.is_news_seen(item.url):
                storage.record_news(item.url, holding.ticker, item.title, item.sentiment, item.published_at)


def build_daily_report(config: AppConfig, storage: Storage) -> str:
    lines = ["📊 <b>Kunlik portfel hisoboti</b>\n"]

    for holding in config.all_tickers():
        current_price = storage.last_price(holding.ticker)
        history = storage.price_history(holding.ticker, days=config.settings.price_history_days)
        news_sentiments = storage.recent_news_sentiment(
            holding.ticker, hours=config.settings.news_lookback_hours
        )
        result = analyze(holding.ticker, current_price, history, news_sentiments)

        owned_note = ""
        if holding.is_owned and current_price:
            pnl_pct = (current_price - holding.buy_price) / holding.buy_price * 100
            owned_note = f" | P&L: {pnl_pct:+.1f}%"

        price_str = _format_price(current_price) if current_price else "noma'lum"
        lines.append(
            f"\n<b>{holding.ticker}</b> ({holding.name}) — {price_str} UZS{owned_note}\n"
            f"Signal: {result.signal}\n"
            f"• " + "\n• ".join(result.reasons)
        )

    lines.append(
        "\n\n<i>Eslatma: bu signal faqat tarixiy narx harakati va yangiliklar "
        "ohangiga asoslangan avtomatik xulosa, moliyaviy maslahat emas. "
        "Qaror qabul qilishdan oldin o'zingiz tekshiring.</i>"
    )
    return "\n".join(lines)


def run_daily_report(config: AppConfig, storage: Storage, notifier: TelegramNotifier) -> None:
    report = build_daily_report(config, storage)
    notifier.send(report)

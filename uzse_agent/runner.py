"""Asosiy ish mantig'i: narxlarni tekshirish, threshold-alert va kunlik hisobot.

Portfel va sozlamalar har chaqiruvda DB'dan (PortfolioRepo) o'qiladi, shuning
uchun bot orqali kiritilgan o'zgarishlar keyingi tekshiruvdayoq hisobga olinadi.
"""
from __future__ import annotations

import logging
import threading

from .analyzer import analyze
from .config import Holding, Settings
from .news import fetch_news_for_keywords
from .notifier import TelegramNotifier
from .repo import PortfolioRepo
from .scraper import get_quotes
from .storage import Storage
from .textfmt import esc, fmt_money, fmt_qty, fmt_signed

logger = logging.getLogger(__name__)

# Narx tekshiruvi va yangiliklar skaneri bir vaqtda ikki marta ishlamasligi uchun
_RUN_LOCK = threading.Lock()


def run_exclusive(fn, *args) -> bool:
    """fn(*args) ni faqat boshqa tekshiruv ishlamayotgan bo'lsa bajaradi.
    Bajarilsa True, band bo'lgani uchun o'tkazib yuborilsa False qaytaradi."""
    if not _RUN_LOCK.acquire(blocking=False):
        logger.info("%s o'tkazib yuborildi: boshqa tekshiruv ishlayapti", getattr(fn, "__name__", fn))
        return False
    try:
        fn(*args)
        return True
    finally:
        _RUN_LOCK.release()


def check_thresholds(holding: Holding, current_price: float, storage: Storage, settings: Settings) -> list[str]:
    """Sotib olingan (o'rtacha) narx va so'nggi eng yuqori narxdan pasayishni tekshiradi.
    Ogohlantirish kerak bo'lsa, xabar matnlari ro'yxatini qaytaradi."""
    alerts: list[str] = []
    if not holding.is_owned:
        return alerts

    if storage.alerts_today_count(holding.ticker) >= settings.max_alerts_per_ticker_per_day:
        return alerts

    name = esc(holding.name)
    if holding.drop_alert_pct:
        drop_from_buy = (current_price - holding.buy_price) / holding.buy_price * 100
        if drop_from_buy <= -abs(holding.drop_alert_pct):
            alerts.append(
                f"⚠️ <b>{name}</b> sotib olingan o'rtacha narxdan "
                f"<b>{drop_from_buy:.1f}%</b> pastda!\n"
                f"O'rtacha narx: {fmt_money(holding.buy_price)} UZS → "
                f"Hozir: {fmt_money(current_price)} UZS"
            )

    if holding.trailing_drop_pct:
        recent_high = storage.recent_high(holding.ticker, days=30)
        if recent_high and recent_high > 0:
            drop_from_high = (current_price - recent_high) / recent_high * 100
            if drop_from_high <= -abs(holding.trailing_drop_pct):
                alerts.append(
                    f"📉 <b>{name}</b> so'nggi 30 kunlik "
                    f"eng yuqori narxdan <b>{drop_from_high:.1f}%</b> pastda!\n"
                    f"Eng yuqori: {fmt_money(recent_high)} UZS → "
                    f"Hozir: {fmt_money(current_price)} UZS"
                )

    return alerts


def run_price_check(repo: PortfolioRepo, storage: Storage, notifier: TelegramNotifier) -> None:
    """Bir marta: portfeldagi barcha aksiyalar narxini oladi, saqlaydi, threshold tekshiradi."""
    holdings = repo.load_holdings()
    if not holdings:
        logger.info("Portfel bo'sh — tekshirish uchun aksiya yo'q")
        return
    settings = repo.load_settings()

    quotes = get_quotes([h.ticker for h in holdings])

    for holding in holdings:
        quote = quotes.get(holding.ticker.upper())
        if not quote:
            continue
        storage.record_price(holding.ticker, quote.price, quote.change_pct)

        # check_thresholds faqat egalik qilingan aksiyalar uchun ogohlantiradi;
        # kuzatuvdagilar uchun faqat narx tarixi yoziladi
        for alert_text in check_thresholds(holding, quote.price, storage, settings):
            if notifier.send(alert_text):
                storage.record_alert(holding.ticker, "threshold_drop", alert_text)


def run_news_scan(repo: PortfolioRepo, storage: Storage) -> None:
    """Portfeldagi barcha aksiyalar uchun yangiliklarni yig'ib, saqlaydi."""
    settings = repo.load_settings()
    for holding in repo.load_holdings():
        items = fetch_news_for_keywords(holding.keywords(), lookback_hours=settings.news_lookback_hours)
        for item in items:
            if item.url and not storage.is_news_seen(item.url):
                storage.record_news(item.url, holding.ticker, item.title, item.sentiment, item.published_at)


def build_daily_report(repo: PortfolioRepo, storage: Storage) -> str:
    settings = repo.load_settings()
    lines = ["📊 <b>Kunlik portfel hisoboti</b>\n"]

    for holding in repo.load_holdings():
        current_price = storage.last_price(holding.ticker)
        history = storage.price_history(holding.ticker, days=settings.price_history_days)
        news_sentiments = storage.recent_news_sentiment(holding.ticker, hours=settings.news_lookback_hours)
        result = analyze(holding.ticker, current_price, history, news_sentiments)

        owned_note = ""
        if holding.is_owned and current_price:
            pnl = (current_price - holding.buy_price) * holding.quantity
            pnl_pct = (current_price - holding.buy_price) / holding.buy_price * 100
            owned_note = (
                f"\n{fmt_qty(holding.quantity)} dona, o'rtacha {fmt_money(holding.buy_price)} UZS | "
                f"Foyda/zarar: {fmt_signed(pnl)} UZS ({pnl_pct:+.1f}%)"
            )

        price_str = fmt_money(current_price) if current_price else "noma'lum"
        lines.append(
            f"\n<b>{esc(holding.name)}</b> — {price_str} UZS{owned_note}\n"
            f"Signal: {esc(result.signal)}\n"
            "• " + "\n• ".join(esc(r) for r in result.reasons)
        )

    lines.append(
        "\n\n<i>Eslatma: bu signal faqat tarixiy narx harakati va yangiliklar "
        "ohangiga asoslangan avtomatik xulosa, moliyaviy maslahat emas. "
        "Qaror qabul qilishdan oldin o'zingiz tekshiring.</i>"
    )
    return "\n".join(lines)


def run_daily_report(repo: PortfolioRepo, storage: Storage, notifier: TelegramNotifier) -> None:
    notifier.send(build_daily_report(repo, storage))

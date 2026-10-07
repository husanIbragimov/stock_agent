"""RSS orqali O'zbekiston iqtisodiyot yangiliklarini yig'ish va oddiy
lug'atga asoslangan (lexicon-based) sentiment baholash.

Bu sentiment baholash SODDA va cheklangan — kalit so'zlarni sanaydi, xolos.
Ancha aniqroq tahlil kerak bo'lsa, `score_sentiment` funksiyasini kattaroq
til modeli (masalan Claude/OpenAI API) chaqiruvi bilan almashtirish oson:
funksiya imzosi (matn -> -1..+1 float) saqlanib qolsa, qolgan kod
o'zgarishsiz ishlayveradi.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser
import requests

logger = logging.getLogger(__name__)

# Javob bermay qolgan RSS server skanerni (va narx tekshiruvini) to'xtatib qo'ymasligi uchun
RSS_TIMEOUT_SEC = 15

# O'zbekiston iqtisodiyot/moliya yangiliklari bo'yicha ma'lum RSS manbalar.
# Kerak bo'lsa bu ro'yxatga o'zingiz manba qo'shishingiz mumkin.
RSS_FEEDS = [
    "https://www.gazeta.uz/ru/rss",
    "https://uzreport.news/feed/rss/ru",
    "https://nuz.uz/feed/",
    "https://daryo.uz/rss",
    "https://uza.uz/uz/rss",
]

POSITIVE_WORDS = [
    # uzbek
    "o'sdi", "o'sish", "ko'tarildi", "rekord", "foyda", "daromad oshdi",
    "investitsiya jalb", "kengaytirish", "yangi shartnoma", "ijobiy",
    # russian
    "вырос", "выросла", "рост", "прибыль", "рекорд", "подорожал",
    "инвестиции", "увеличил", "положительн", "укрепил",
]

NEGATIVE_WORDS = [
    # uzbek
    "tushdi", "pasaydi", "zarar", "inqiroz", "bankrot", "jarima",
    "sud", "ishdan bo'shatish", "to'xtatildi", "salbiy", "kamaydi",
    # russian
    "упал", "снизил", "убыток", "кризис", "банкрот", "штраф", "суд",
    "остановил", "сократил", "негативн", "подешевел",
]


@dataclass
class NewsItem:
    url: str
    title: str
    summary: str
    published_at: str | None
    source: str
    sentiment: float  # -1.0 (salbiy) .. +1.0 (ijobiy)


def score_sentiment(text: str) -> float:
    """Juda oddiy kalit-so'z asosidagi baholash. -1..+1 oralig'ida qaytaradi."""
    text_lower = text.lower()
    pos = sum(text_lower.count(w) for w in POSITIVE_WORDS)
    neg = sum(text_lower.count(w) for w in NEGATIVE_WORDS)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)


def _entry_matches(entry, keywords: list[str]) -> bool:
    haystack = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
    return any(kw.lower() in haystack for kw in keywords if kw)


def fetch_news_for_keywords(keywords: list[str], lookback_hours: int = 48) -> list[NewsItem]:
    """Barcha RSS manbalarni o'qib, berilgan kalit so'zlarga mos maqolalarni qaytaradi."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    items: list[NewsItem] = []

    for feed_url in RSS_FEEDS:
        try:
            resp = requests.get(feed_url, timeout=RSS_TIMEOUT_SEC)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RSS o'qib bo'lmadi %s: %s", feed_url, exc)
            continue

        for entry in parsed.entries:
            if not _entry_matches(entry, keywords):
                continue

            published_at = None
            if getattr(entry, "published_parsed", None):
                published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                if published_at < cutoff:
                    continue
                published_at = published_at.isoformat()

            title = entry.get("title", "")
            summary = entry.get("summary", "")
            items.append(
                NewsItem(
                    url=entry.get("link", ""),
                    title=title,
                    summary=summary,
                    published_at=published_at,
                    source=feed_url,
                    sentiment=score_sentiment(f"{title} {summary}"),
                )
            )

    return items

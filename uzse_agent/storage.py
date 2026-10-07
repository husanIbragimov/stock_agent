"""SQLite orqali narx tarixi, yuborilgan ogohlantirishlar va yangiliklarni saqlash."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    price REAL NOT NULL,
    change_pct REAL,
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_ticker_time ON price_history(ticker, fetched_at);

CREATE TABLE IF NOT EXISTS alerts_sent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    message TEXT NOT NULL,
    sent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_seen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    ticker TEXT,
    title TEXT,
    sentiment REAL,
    published_at TEXT,
    seen_at TEXT NOT NULL
);
"""


class Storage:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- narxlar ----
    def record_price(self, ticker: str, price: float, change_pct: float | None) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO price_history (ticker, price, change_pct, fetched_at) VALUES (?, ?, ?, ?)",
                (ticker, price, change_pct, datetime.now(timezone.utc).isoformat()),
            )

    def price_history(self, ticker: str, days: int) -> list[tuple[str, float]]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT fetched_at, price FROM price_history "
                "WHERE ticker = ? AND fetched_at >= ? ORDER BY fetched_at ASC",
                (ticker, since),
            ).fetchall()
        return rows

    def recent_high(self, ticker: str, days: int) -> float | None:
        rows = self.price_history(ticker, days)
        if not rows:
            return None
        return max(p for _, p in rows)

    def last_price(self, ticker: str) -> float | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT price FROM price_history WHERE ticker = ? ORDER BY fetched_at DESC LIMIT 1",
                (ticker,),
            ).fetchone()
        return row[0] if row else None

    # ---- alertlar (spam bo'lmasligi uchun) ----
    def alerts_today_count(self, ticker: str) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM alerts_sent WHERE ticker = ? AND sent_at >= ?",
                (ticker, today),
            ).fetchone()
        return row[0] if row else 0

    def record_alert(self, ticker: str, alert_type: str, message: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO alerts_sent (ticker, alert_type, message, sent_at) VALUES (?, ?, ?, ?)",
                (ticker, alert_type, message, datetime.now(timezone.utc).isoformat()),
            )

    # ---- yangiliklar ----
    def is_news_seen(self, url: str) -> bool:
        with self._conn() as conn:
            row = conn.execute("SELECT 1 FROM news_seen WHERE url = ?", (url,)).fetchone()
        return row is not None

    def record_news(self, url: str, ticker: str, title: str, sentiment: float, published_at: str | None) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO news_seen (url, ticker, title, sentiment, published_at, seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (url, ticker, title, sentiment, published_at, datetime.now(timezone.utc).isoformat()),
            )

    def recent_news_sentiment(self, ticker: str, hours: int) -> list[float]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT sentiment FROM news_seen WHERE ticker = ? AND seen_at >= ? AND sentiment IS NOT NULL",
                (ticker, since),
            ).fetchall()
        return [r[0] for r in rows]

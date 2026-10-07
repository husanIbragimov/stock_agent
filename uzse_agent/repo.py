"""Portfel ma'lumotlari: aksiyalar, xarid/sotuv tranzaksiyalari va sozlamalar (SQLite).

`Storage` bilan bitta DB faylini ishlatadi, lekin o'z jadvallarini o'zi yaratadi.
Pozitsiyani o'zgartiradigan har bir yozuv avval `compute_position` bilan
tekshiriladi: biror sanada miqdor manfiy bo'lsa, hech narsa yozilmaydi.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

from .config import Holding, Settings
from .portfolio import Position, Transaction, compute_position

SCHEMA = """
CREATE TABLE IF NOT EXISTS securities (
    isin TEXT PRIMARY KEY,
    ticker TEXT,
    name TEXT NOT NULL,
    extra_keywords TEXT NOT NULL DEFAULT '[]',
    drop_alert_pct REAL,
    trailing_drop_pct REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    isin TEXT NOT NULL REFERENCES securities(isin),
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price REAL NOT NULL CHECK (price > 0),
    fee REAL NOT NULL DEFAULT 0 CHECK (fee >= 0),
    traded_at TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tx_isin_date ON transactions(isin, traded_at, id);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

EDITABLE_FIELDS = {"extra_keywords", "drop_alert_pct", "trailing_drop_pct"}
SETTING_KEYS = {f.name for f in fields(Settings)}
# Juda katta qiymat timedelta'ni buzadi (har bir check/hisobot yiqiladi)
SETTING_MAX = 10000

_SECURITY_COLS = "isin, ticker, name, extra_keywords, drop_alert_pct, trailing_drop_pct"
_TX_COLS = "id, side, quantity, price, fee, traded_at, note"


@dataclass
class Security:
    isin: str
    ticker: str | None
    name: str
    extra_keywords: list[str] = field(default_factory=list)
    drop_alert_pct: float | None = None
    trailing_drop_pct: float | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_security(row) -> Security:
    isin, ticker, name, keywords, drop, trail = row
    return Security(isin, ticker, name, json.loads(keywords), drop, trail)


def _row_to_tx(row) -> Transaction:
    tx_id, side, quantity, price, fee, traded_at, note = row
    return Transaction(tx_id, side, quantity, price, fee, traded_at, note)


class PortfolioRepo:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- aksiyalar ----
    def add_security(self, security: Security) -> None:
        try:
            with self._conn() as conn:
                conn.execute(
                    f"INSERT INTO securities ({_SECURITY_COLS}, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        security.isin,
                        security.ticker,
                        security.name,
                        json.dumps(security.extra_keywords, ensure_ascii=False),
                        security.drop_alert_pct,
                        security.trailing_drop_pct,
                        _now(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"{security.isin} allaqachon portfelda bor") from exc

    def get_security(self, isin: str) -> Security | None:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT {_SECURITY_COLS} FROM securities WHERE isin = ?", (isin,)
            ).fetchone()
        return _row_to_security(row) if row else None

    def list_securities(self) -> list[Security]:
        with self._conn() as conn:
            rows = conn.execute(
                # rowid — qo'shilish tartibi (created_at bir xil bo'lib qolishi mumkin)
                f"SELECT {_SECURITY_COLS} FROM securities ORDER BY rowid"
            ).fetchall()
        return [_row_to_security(r) for r in rows]

    def update_security(self, isin: str, **changes) -> None:
        unknown = set(changes) - EDITABLE_FIELDS
        if unknown:
            raise ValueError(f"Bu maydonlarni o'zgartirib bo'lmaydi: {', '.join(sorted(unknown))}")
        if not changes:
            return
        if "extra_keywords" in changes:
            changes["extra_keywords"] = json.dumps(changes["extra_keywords"], ensure_ascii=False)
        assignments = ", ".join(f"{key} = ?" for key in changes)
        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE securities SET {assignments} WHERE isin = ?", (*changes.values(), isin)
            )
        if cur.rowcount == 0:
            raise KeyError(isin)

    def delete_security(self, isin: str) -> int:
        """Aksiyani tranzaksiyalari bilan birga o'chiradi. Narx tarixi saqlanib qoladi."""
        with self._conn() as conn:
            deleted = conn.execute("DELETE FROM transactions WHERE isin = ?", (isin,)).rowcount
            conn.execute("DELETE FROM securities WHERE isin = ?", (isin,))
        return deleted

    # ---- tranzaksiyalar ----
    @staticmethod
    def _transactions(conn, isin: str) -> list[Transaction]:
        rows = conn.execute(
            f"SELECT {_TX_COLS} FROM transactions WHERE isin = ? ORDER BY traded_at, id", (isin,)
        ).fetchall()
        return [_row_to_tx(r) for r in rows]

    def transactions(self, isin: str) -> list[Transaction]:
        with self._conn() as conn:
            return self._transactions(conn, isin)

    def get_transaction(self, tx_id: int) -> tuple[str, Transaction] | None:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT isin, {_TX_COLS} FROM transactions WHERE id = ?", (tx_id,)
            ).fetchone()
        return (row[0], _row_to_tx(row[1:])) if row else None

    def has_transactions(self) -> bool:
        with self._conn() as conn:
            return conn.execute("SELECT 1 FROM transactions LIMIT 1").fetchone() is not None

    def position(self, isin: str) -> Position:
        return compute_position(self.transactions(isin))

    def preview_transaction(self, isin: str, tx: Transaction) -> Position:
        """Tranzaksiya qo'shilsa pozitsiya qanday bo'lishini qaytaradi (DB'ga yozmaydi)."""
        return compute_position([*self.transactions(isin), tx])

    def add_transaction(self, isin: str, tx: Transaction) -> tuple[int, Position]:
        with self._conn() as conn:
            if conn.execute("SELECT 1 FROM securities WHERE isin = ?", (isin,)).fetchone() is None:
                raise KeyError(isin)
            position = compute_position([*self._transactions(conn, isin), tx])
            cur = conn.execute(
                "INSERT INTO transactions (isin, side, quantity, price, fee, traded_at, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (isin, tx.side, tx.quantity, tx.price, tx.fee, tx.traded_at, tx.note, _now()),
            )
            return cur.lastrowid, position

    def delete_transaction(self, tx_id: int) -> Position:
        with self._conn() as conn:
            row = conn.execute("SELECT isin FROM transactions WHERE id = ?", (tx_id,)).fetchone()
            if row is None:
                raise KeyError(tx_id)
            remaining = [tx for tx in self._transactions(conn, row[0]) if tx.id != tx_id]
            position = compute_position(remaining)
            conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
            return position

    # ---- runner uchun ----
    def load_holdings(self) -> list[Holding]:
        """Har bir aksiya uchun Holding: miqdor va o'rtacha narx tranzaksiyalardan."""
        holdings: list[Holding] = []
        for sec in self.list_securities():
            pos = self.position(sec.isin)
            keywords = [sec.ticker, *sec.extra_keywords] if sec.ticker else list(sec.extra_keywords)
            holdings.append(
                Holding(
                    ticker=sec.isin,
                    name=sec.name,
                    quantity=pos.quantity,
                    buy_price=pos.avg_cost,
                    drop_alert_pct=sec.drop_alert_pct,
                    trailing_drop_pct=sec.trailing_drop_pct,
                    extra_keywords=list(dict.fromkeys(keywords)),
                )
            )
        return holdings

    # ---- sozlamalar ----
    def load_settings(self) -> Settings:
        with self._conn() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return Settings(**{key: int(value) for key, value in rows if key in SETTING_KEYS})

    def set_setting(self, key: str, value: int) -> None:
        if key not in SETTING_KEYS:
            raise KeyError(key)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= SETTING_MAX:
            raise ValueError(f"Sozlama qiymati 1 dan {SETTING_MAX} gacha butun son bo'lishi kerak")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )

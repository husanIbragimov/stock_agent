"""Xarid/sotuv tranzaksiyalaridan pozitsiyani hisoblash (o'rtacha tortilgan narx usuli).

Sof funksiyalar: DB yoki tarmoqqa murojaat yo'q.

  - xarid: tannarx += miqdor × narx + komissiya; o'rtacha = tannarx / miqdor
  - sotuv: o'rtacha narx o'zgarmaydi; realizatsiya qilingan foyda/zarar
           += miqdor × (narx − o'rtacha) − komissiya
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Tashkent")


def today_local(now: datetime | None = None) -> date:
    """Toshkent vaqti bo'yicha bugungi sana (UTC sanasi emas)."""
    return (now or datetime.now(timezone.utc)).astimezone(TZ).date()


@dataclass
class Transaction:
    id: int | None
    side: str  # 'buy' | 'sell'
    quantity: int
    price: float
    fee: float
    traded_at: str  # 'YYYY-MM-DD'
    note: str | None = None


@dataclass
class Position:
    quantity: int
    avg_cost: float | None  # quantity == 0 bo'lsa None
    realized_pnl: float

    def unrealized_pnl(self, current_price: float) -> float | None:
        if not self.quantity or self.avg_cost is None:
            return None
        return (current_price - self.avg_cost) * self.quantity


class NegativePositionError(ValueError):
    """Sotuv paytida yetarli aksiya bo'lmagan (miqdor manfiyga tushadi)."""

    def __init__(self, tx: Transaction, available: int):
        self.tx = tx
        self.available = available
        super().__init__(
            f"{tx.traded_at} sanasida {tx.quantity} dona sotib bo'lmaydi: "
            f"o'sha paytda faqat {available} dona bor edi"
        )


def _sort_key(tx: Transaction) -> tuple:
    # Sana bo'yicha; bir kunda — id bo'yicha; hali saqlanmagan (id=None) oxirida
    return (tx.traded_at, tx.id is None, tx.id or 0)


def compute_position(transactions: list[Transaction]) -> Position:
    quantity = 0
    cost = 0.0
    realized = 0.0
    for tx in sorted(transactions, key=_sort_key):
        if tx.side == "buy":
            cost += tx.quantity * tx.price + tx.fee
            quantity += tx.quantity
        elif tx.side == "sell":
            if tx.quantity > quantity:
                raise NegativePositionError(tx, quantity)
            avg = cost / quantity
            realized += tx.quantity * (tx.price - avg) - tx.fee
            quantity -= tx.quantity
            cost = avg * quantity
        else:
            raise ValueError(f"Noma'lum tranzaksiya turi: {tx.side!r}")
    return Position(
        quantity=quantity,
        avg_cost=cost / quantity if quantity else None,
        realized_pnl=realized,
    )

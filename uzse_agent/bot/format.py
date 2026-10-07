"""Bot xabarlari matnlari (parse_mode=HTML). Tashqi matn faqat esc() orqali qo'shiladi."""
from __future__ import annotations

from datetime import datetime

from ..config import Settings
from ..portfolio import TZ, Position, Transaction
from ..repo import Security
from ..scraper import PriceQuote
from ..textfmt import esc, fmt_money, fmt_qty, fmt_signed

HELP_TEXT = (
    "🤖 <b>UZSE Portfolio Agent</b>\n\n"
    "<b>Portfel</b>\n"
    "/list — portfel va kuzatuv ro'yxati\n"
    "/stock — aksiya kartochkasi (tahrirlash, tarix, o'chirish)\n"
    "/add — yangi aksiya qo'shish\n"
    "/buy — xarid kiritish\n"
    "/sell — sotuv kiritish\n\n"
    "<b>Tekshiruvlar</b>\n"
    "/check — narxlarni hozir tekshirish\n"
    "/news — yangiliklarni hozir yig'ish\n"
    "/report — kunlik hisobot\n"
    "/price UZ7036271003 — jonli narx\n\n"
    "/settings — sozlamalar\n"
    "/cancel — joriy formani bekor qilish"
)

SETTING_LABELS = {
    "max_alerts_per_ticker_per_day": "Bir aksiya bo'yicha kunlik ogohlantirishlar",
    "price_history_days": "Narx tarixi (kun)",
    "news_lookback_hours": "Yangiliklar oynasi (soat)",
}


def fmt_time(ts_utc_iso: str) -> str:
    return datetime.fromisoformat(ts_utc_iso).astimezone(TZ).strftime("%Y-%m-%d %H:%M")


def security_title(sec: Security) -> str:
    return f"<b>{esc(sec.ticker or sec.isin)}</b> — {esc(sec.name)}"


def security_button(sec: Security) -> str:
    """Inline tugma matni (HTML emas, shuning uchun escape kerak emas)."""
    return f"{sec.ticker or sec.isin} — {sec.name}"[:60]


def quote_text(q: PriceQuote) -> str:
    change = ""
    if q.change is not None:
        pct = f", {q.change_pct:+.2f}%" if q.change_pct is not None else ""
        change = f" ({fmt_signed(q.change)}{pct})"
    return (
        f"<b>{esc(q.ticker)}</b> — {esc(q.name)}\n"
        f"ISIN: <code>{esc(q.isin)}</code>\n"
        f"Narx: {fmt_money(q.price)} UZS{change}\n"
        f"Oxirgi bitim: {esc(q.last_trade_date or '—')}"
    )


def _position_lines(pos: Position, last: tuple[float, str] | None) -> list[str]:
    lines: list[str] = []
    if pos.quantity:
        lines.append(f"{fmt_qty(pos.quantity)} dona, o'rtacha narx {fmt_money(pos.avg_cost)} UZS")
        if last:
            price, ts = last
            pct = (price - pos.avg_cost) / pos.avg_cost * 100
            lines.append(
                f"Joriy: {fmt_money(price)} UZS ({fmt_time(ts)}) | "
                f"Foyda/zarar: {fmt_signed(pos.unrealized_pnl(price))} UZS ({pct:+.1f}%)"
            )
    else:
        lines.append("Kuzatuvda (aksiya yo'q)")
        if last:
            lines.append(f"Joriy: {fmt_money(last[0])} UZS ({fmt_time(last[1])})")
    if pos.realized_pnl:
        lines.append(f"Realizatsiya qilingan foyda/zarar: {fmt_signed(pos.realized_pnl)} UZS")
    return lines


def position_text(sec: Security, pos: Position, last: tuple[float, str] | None) -> str:
    return "\n".join([security_title(sec), *_position_lines(pos, last)])


def portfolio_list(items: list[tuple[Security, Position, tuple[float, str] | None]]) -> str:
    if not items:
        return "Portfel bo'sh. /add bilan aksiya qo'shing."
    owned = [i for i in items if i[1].quantity > 0]
    watch = [i for i in items if i[1].quantity == 0]
    parts = ["💼 <b>Portfel</b>"]
    invested = value = 0.0
    for sec, pos, last in owned:
        parts.append("\n" + position_text(sec, pos, last))
        if last:
            invested += pos.avg_cost * pos.quantity
            value += last[0] * pos.quantity
    if invested:
        parts.append(
            f"\n<b>Jami</b> (narxi ma'lum aksiyalar): {fmt_money(value)} UZS, "
            f"foyda/zarar {fmt_signed(value - invested)} UZS ({(value - invested) / invested * 100:+.1f}%)"
        )
    if watch:
        parts.append("\n👀 <b>Kuzatuv ro'yxati</b>")
        for sec, pos, last in watch:
            price = f" — {fmt_money(last[0])} UZS" if last else ""
            parts.append(security_title(sec) + price)
    return "\n".join(parts)


def tx_line(tx: Transaction) -> str:
    prefix = f"#{tx.id} " if tx.id is not None else ""
    side = "🟢 Xarid" if tx.side == "buy" else "🔴 Sotuv"
    line = f"{prefix}{tx.traded_at} {side}: {fmt_qty(tx.quantity)} × {fmt_money(tx.price)} UZS"
    if tx.fee:
        line += f", komissiya {fmt_money(tx.fee)}"
    if tx.note:
        line += f" — {esc(tx.note)}"
    return line


def _pct(value: float | None) -> str:
    return f"-{value:g}%" if value else "o'chiq"


def stock_card(sec: Security, pos: Position, last: tuple[float, str] | None, recent: list[Transaction]) -> str:
    lines = [
        security_title(sec),
        f"ISIN: <code>{esc(sec.isin)}</code>",
        *_position_lines(pos, last),
        "",
        f"Ogohlantirish: o'rtacha narxdan {_pct(sec.drop_alert_pct)}, "
        f"30 kunlik cho'qqidan {_pct(sec.trailing_drop_pct)}",
    ]
    if sec.extra_keywords:
        lines.append("Kalit so'zlar: " + esc(", ".join(sec.extra_keywords)))
    if recent:
        lines += ["", "<b>So'nggi tranzaksiyalar:</b>", *(tx_line(t) for t in recent)]
    return "\n".join(lines)


def history_text(sec: Security, txs: list[Transaction]) -> str:
    return "\n".join(
        [security_title(sec), "", "<b>Tranzaksiyalar</b> (o'chirish uchun raqamni bosing):", *map(tx_line, txs)]
    )


def tx_summary(sec: Security, tx: Transaction, new_pos: Position) -> str:
    lines = [
        "<b>Tekshiring:</b>",
        security_title(sec),
        tx_line(tx),
        f"Summa: {fmt_money(tx.quantity * tx.price)} UZS",
        "",
        "<b>Saqlangandan keyin:</b>",
    ]
    if new_pos.quantity:
        lines.append(f"{fmt_qty(new_pos.quantity)} dona, o'rtacha narx {fmt_money(new_pos.avg_cost)} UZS")
    else:
        lines.append("0 dona (pozitsiya yopiladi)")
    if tx.side == "sell":
        lines.append(f"Realizatsiya qilingan foyda/zarar (jami): {fmt_signed(new_pos.realized_pnl)} UZS")
    return "\n".join(lines)


def settings_text(settings: Settings) -> str:
    lines = ["⚙️ <b>Sozlamalar</b>"]
    lines += [f"{label}: <b>{getattr(settings, key)}</b>" for key, label in SETTING_LABELS.items()]
    return "\n".join(lines)

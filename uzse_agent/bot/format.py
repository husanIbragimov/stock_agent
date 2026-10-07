"""Bot xabarlari matnlari (parse_mode=HTML). Tashqi matn faqat esc() orqali qo'shiladi."""
from __future__ import annotations

from datetime import datetime

from ..config import Settings
from ..portfolio import TZ, Position, Transaction
from ..repo import Security
from ..scraper import PriceQuote
from ..textfmt import esc, fmt_money, fmt_qty, fmt_signed
from .inputs import fee_total

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

# Tarixda izohlar qisqartiriladi: 20 ta qator bitta xabarga (4096) sig'ishi uchun
HISTORY_NOTE_MAX = 40

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


def _change_text(q: PriceQuote) -> str:
    if q.change is None:
        return ""
    pct = f", {q.change_pct:+.2f}%" if q.change_pct is not None else ""
    return f" ({fmt_signed(q.change)}{pct})"


def quote_text(q: PriceQuote) -> str:
    change = _change_text(q)
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


def tx_line(tx: Transaction, note_max: int | None = None, fee_detail: str | None = None) -> str:
    prefix = f"#{tx.id} " if tx.id is not None else ""
    side = "🟢 Xarid" if tx.side == "buy" else "🔴 Sotuv"
    line = f"{prefix}{tx.traded_at} {side}: {fmt_qty(tx.quantity)} × {fmt_money(tx.price)} UZS"
    if tx.fee:
        line += f", komissiya {fmt_money(tx.fee)}"
        if fee_detail:
            line += f" ({fee_detail})"
    if tx.note:
        note = tx.note if note_max is None or len(tx.note) <= note_max else tx.note[:note_max] + "…"
        line += f" — {esc(note)}"
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
        [security_title(sec), "", "<b>Tranzaksiyalar</b> (o'chirish uchun raqamni bosing):", *(tx_line(t, note_max=HISTORY_NOTE_MAX) for t in txs)]
    )


def tx_summary(sec: Security, tx: Transaction, new_pos: Position, fee_detail: str | None = None) -> str:
    lines = [
        "<b>Tekshiring:</b>",
        security_title(sec),
        tx_line(tx, fee_detail=fee_detail),
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


# ---- /list: har bir aksiya alohida xabar ----
def list_item(sec: Security, pos: Position, quote: PriceQuote | None, last: tuple[float, str] | None) -> str:
    """Bitta aksiya: jonli narx (yoki saqlangan narx) va pozitsiya."""
    lines = [security_title(sec)]
    if quote is not None:
        price = quote.price
        lines.append(
            f"Joriy narx: <b>{fmt_money(price)} UZS</b>{_change_text(quote)}"
            f" · oxirgi bitim {esc(quote.last_trade_date or '—')}"
        )
    elif last is not None:
        price = last[0]
        lines.append(f"Joriy narx: {fmt_money(price)} UZS (saqlangan narx, {fmt_time(last[1])} — jonli narx olinmadi)")
    else:
        price = None
        lines.append("Joriy narx: noma'lum (sayt javob bermadi)")

    if pos.quantity:
        lines.append(f"{fmt_qty(pos.quantity)} dona, o'rtacha narx {fmt_money(pos.avg_cost)} UZS")
        if price is not None:
            pct = (price - pos.avg_cost) / pos.avg_cost * 100
            lines.append(
                f"Qiymat: {fmt_money(price * pos.quantity)} UZS | "
                f"Foyda/zarar: {fmt_signed(pos.unrealized_pnl(price))} UZS ({pct:+.1f}%)"
            )
    else:
        lines.append("Kuzatuvda (aksiya yo'q)")
    if pos.realized_pnl:
        lines.append(f"Realizatsiya qilingan foyda/zarar: {fmt_signed(pos.realized_pnl)} UZS")
    return "\n".join(lines)


def portfolio_total(items: list[tuple[Security, Position, float | None]]) -> str:
    """/list oxiridagi jami xabar. items: (aksiya, pozitsiya, joriy narx yoki None)."""
    owned = [(pos, price) for _, pos, price in items if pos.quantity > 0]
    watch_count = len(items) - len(owned)
    lines = [f"💼 <b>Jami</b>: {len(owned)} ta aksiya portfelda, {watch_count} ta kuzatuvda"]
    priced = [(pos, price) for pos, price in owned if price is not None]
    invested = sum(pos.avg_cost * pos.quantity for pos, _ in priced)
    value = sum(price * pos.quantity for pos, price in priced)
    if invested:
        lines.append(
            f"Qiymat: {fmt_money(value)} UZS | Foyda/zarar: {fmt_signed(value - invested)} UZS "
            f"({(value - invested) / invested * 100:+.1f}%)"
        )
    unknown = len(owned) - len(priced)
    if unknown:
        lines.append(f"({unknown} ta aksiya narxi noma'lum — jamiga kirmadi)")
    return "\n".join(lines)


# ---- komissiya ----
def _fmt_number(value: float) -> str:
    return fmt_money(value).removesuffix(".00")


def fee_buttons(value: float, quantity: int, price: float) -> list[tuple[str, str]]:
    """Komissiya usulini tanlash tugmalari, har birida hisoblangan summa bilan."""
    buttons = [
        (f"Har bir dona uchun: {fmt_qty(quantity)} × {_fmt_number(value)} = "
         f"{fmt_money(fee_total(value, 'unit', quantity, price))}", "feemode:unit"),
        (f"Jami: {fmt_money(value)}", "feemode:total"),
    ]
    if value < 100:
        buttons.append((f"Summadan {value:g}%: {fmt_money(fee_total(value, 'pct', quantity, price))}", "feemode:pct"))
    return buttons


def fee_detail(value: float, mode: str, quantity: int, price: float) -> str | None:
    """Xulosa ekranida komissiya qanday hisoblanganini ko'rsatadi."""
    if mode == "unit":
        return f"{fmt_qty(quantity)} × {_fmt_number(value)}"
    if mode == "pct":
        return f"{value:g}% × {fmt_money(quantity * price)}"
    return None

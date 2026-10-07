"""Telegram xabarlari uchun matn yordamchilari (parse_mode=HTML)."""
from __future__ import annotations

import html

# Telegram chegarasi 4096 belgi; zaxira bilan
TELEGRAM_SAFE_LIMIT = 4000


def esc(text) -> str:
    """Tashqi matnni Telegram HTML uchun xavfsiz qiladi (<, >, &)."""
    return html.escape(str(text), quote=False)


def fmt_money(value: float) -> str:
    """5250.0 -> '5 250', 5249.99 -> '5 249.99'."""
    text = f"{value:,.2f}".replace(",", " ")
    return text[:-3] if text.endswith(".00") else text


def fmt_signed(value: float) -> str:
    return ("+" if value >= 0 else "-") + fmt_money(abs(value))


def fmt_qty(quantity) -> str:
    return f"{int(quantity):,}".replace(",", " ")


def split_message(text: str, limit: int = TELEGRAM_SAFE_LIMIT) -> list[str]:
    """Matnni qatorlar bo'yicha `limit` dan oshmaydigan bo'laklarga ajratadi."""
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                parts.append("\n".join(current))
                current, size = [], 0
            parts.append(line[:limit])
            line = line[limit:]
        extra = len(line) + (1 if current else 0)
        if current and size + extra > limit:
            parts.append("\n".join(current))
            current, size, extra = [], 0, len(line)
        current.append(line)
        size += extra
    if current:
        parts.append("\n".join(current))
    return parts

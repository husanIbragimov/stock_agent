"""Foydalanuvchi botga yozgan qiymatlarni tekshirish va o'qish.

Har bir funksiya noto'g'ri qiymatda InputError ko'taradi; uning matni
to'g'ridan-to'g'ri foydalanuvchiga ko'rsatiladi.
"""
from __future__ import annotations

import re
from datetime import date

from ..scraper import _to_float

NOTE_MAX = 200


class InputError(ValueError):
    pass


def parse_positive_int(text: str) -> int:
    cleaned = re.sub(r"[\s,]", "", text)
    if not re.fullmatch(r"[0-9]+", cleaned) or int(cleaned) <= 0:
        raise InputError("Butun musbat son yuboring (masalan 30).")
    return int(cleaned)


def parse_quantity(text: str) -> int:
    try:
        return parse_positive_int(text)
    except InputError:
        raise InputError("Miqdor butun musbat son bo'lishi kerak (masalan 30).") from None


def parse_price(text: str) -> float:
    value = _to_float(text)
    if value is None or value <= 0:
        raise InputError("Narx musbat son bo'lishi kerak (masalan 5250 yoki 5 250,50).")
    return value


def parse_fee(text: str) -> float:
    value = _to_float(text)
    if value is None or value < 0:
        raise InputError("Komissiya 0 yoki musbat son bo'lishi kerak.")
    return value


def parse_pct(text: str) -> float:
    value = _to_float(text)
    if value is None or not 0 < value < 100:
        raise InputError("Foiz 0 dan katta va 100 dan kichik bo'lishi kerak (masalan 7).")
    return value


def parse_date(text: str, today: date) -> str:
    try:
        value = date.fromisoformat(text.strip())
    except ValueError:
        raise InputError("Sana YYYY-MM-DD ko'rinishida bo'lishi kerak (masalan 2026-10-07).") from None
    if value > today:
        raise InputError("Kelajakdagi sanani kiritib bo'lmaydi.")
    return value.isoformat()


def parse_keywords(text: str) -> list[str]:
    return list(dict.fromkeys(k.strip() for k in text.split(",") if k.strip()))


def parse_note(text: str) -> str:
    note = text.strip()
    if len(note) > NOTE_MAX:
        raise InputError(f"Izoh {NOTE_MAX} belgidan oshmasligi kerak.")
    return note

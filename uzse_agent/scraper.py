"""Toshkent Respublika Fond Birjasi (UZSE, uzse.uz) saytidan narxlarni olish.

MUHIM: UZSE'ning rasmiy ochiq API'si yo'q (2026-yil holatiga ko'ra). Shu sababli
bu modul saytning ochiq HTML sahifalarini o'qib (scraping) narxlarni ajratib oladi.

Har bir aksiya o'z sahifasidan olinadi:

  - https://uzse.uz/isu_infos/STK?isu_cd=<ISIN>&locale=en

`isu_cd` parametri FAQAT ISIN kodini qabul qiladi (masalan UZ7036271003).
Birja tikeri (masalan UZNGP) yoki noto'g'ri kod berilsa, sayt 404 qaytaradi.
Shu sababli portfolio.yaml'da ham ISIN, ham tiker yozish mumkin: tiker berilsa,
u avval sahifadagi aksiyalar ro'yxati (havolalardagi isu_cd) orqali ISIN'ga
aylantiriladi.

Sahifadagi asosiy blok (div.paper > header):
  span.tick  — tiker (UZNGP)
  span.isin  — ISIN (UZ7036271003)
  span.pname — emitent nomi
  div.pprice > b       — oxirgi bitim narxi (UZS)
  div.pprice > span.d  — oldingi kunga nisbatan o'zgarish, UZS'da (foizda emas!)

Sayt dizayni o'zgarsa, shu yerdagi CSS selektorlarni yangilash kerak.

Agar UZSE sizning IP/hudud uchun bloklansa yoki captcha chiqarsa, buni
o'zingizning serveringizda (Uzbekiston ichida yoki VPN bilan) ishga tushirish
kerak bo'lishi mumkin.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://uzse.uz"
STOCKS_URL = f"{BASE_URL}/isu_infos/STK/?locale=en"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en,ru;q=0.9,uz;q=0.8",
}

# ISIN: "UZ" + 10 ta raqam/harf (masalan UZ7036271003, UZ701879K017)
ISIN_RE = re.compile(r"^UZ[0-9A-Z]{10}$")
# Birja tikeri: 2-8 ta lotin bosh harf (masalan UZNGP, HMKB, BRBNP)
TICKER_RE = re.compile(r"^[A-Z]{2,8}$")
ISU_CD_RE = re.compile(r"isu_cd=([0-9A-Z]+)")
# Ketma-ket so'rovlar orasidagi pauza (UZSE tez so'rovlarga 429 qaytaradi)
REQUEST_DELAY_SEC = 2.0


@dataclass
class PriceQuote:
    ticker: str          # birja tikeri, masalan UZNGP
    isin: str            # masalan UZ7036271003
    name: str
    price: float
    change: float | None      # oldingi kunga nisbatan o'zgarish, UZS
    change_pct: float | None  # o'sha o'zgarish foizda
    last_trade_date: str | None


def _to_float(text: str) -> float | None:
    """'3 200,50' / '3,200.50' / '96.67' kabi formatlarni floatga o'giradi."""
    if not text:
        return None
    text = text.strip().replace(" ", " ").replace(" ", "")
    # "▼-1,000" kabi matndan faqat raqam qismini olamiz
    num = re.search(r"-?\d[\d.,]*", text)
    if not num:
        return None
    text = num.group().rstrip(".,")
    # Agar ham vergul, ham nuqta bo'lsa — oxirgisi kasr ajratkich deb hisoblanadi
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        # "5,250" / "14,917,860" — minglik ajratkich (UZSE locale=en formati);
        # "200,50" — kasr ajratkich
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+", text):
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    match = re.search(r"-?\d+(\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def fetch_html(url: str, timeout: int = 20, retries: int = 3) -> str:
    """Sahifani yuklaydi. 429 (juda ko'p so'rov) bo'lsa, kutib qayta urinadi."""
    for attempt in range(retries):
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code == 429 and attempt < retries - 1:
            wait = REQUEST_DELAY_SEC * 2 ** (attempt + 1)
            logger.info("UZSE 429 qaytardi, %.0f soniya kutib qayta urinamiz: %s", wait, url)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.text
    raise AssertionError("unreachable")


def stock_url(isin: str) -> str:
    return f"{BASE_URL}/isu_infos/STK?isu_cd={isin}&locale=en"


def parse_stock_page(html: str) -> PriceQuote | None:
    """Bitta aksiya sahifasidagi (isu_cd=<ISIN>) asosiy blokdan narxni ajratadi."""
    soup = BeautifulSoup(html, "lxml")
    header = soup.select_one("div.paper header")
    if header is None:
        return None

    def text(selector: str) -> str:
        el = header.select_one(selector)
        return el.get_text(" ", strip=True) if el else ""

    isin = text("span.isin")
    price_el = header.select_one("div.pprice > b")
    if not isin or price_el is None:
        return None
    # <b>5,250 <small>UZS</small></b> — faqat birinchi matn qismini olamiz
    price = _to_float(price_el.find(string=True, recursive=False) or "")
    if price is None:
        return None

    change = None
    change_el = header.select_one("div.pprice > span.d")
    if change_el is not None:
        change = _to_float(change_el.get_text(" ", strip=True))
        if change is not None:
            classes = change_el.get("class", [])
            if "price-down" in classes:
                change = -abs(change)
            elif "price-up" in classes:
                change = abs(change)

    change_pct = None
    if change is not None:
        prev_price = price - change
        if prev_price > 0:
            change_pct = round(change / prev_price * 100, 2)

    date_match = re.search(r"\d{4}-\d{2}-\d{2}", text("div.pprice > small"))

    return PriceQuote(
        ticker=text("span.tick"),
        isin=isin,
        name=text("span.pname"),
        price=price,
        change=change,
        change_pct=change_pct,
        last_trade_date=date_match.group() if date_match else None,
    )


def parse_ticker_index(html: str) -> dict[str, str]:
    """Sahifadagi aksiyalar ro'yxatidan tiker -> ISIN lug'atini quradi.

    Har bir havola shunday ko'rinishda: <a href="/isu_infos/STK?isu_cd=UZ700528K011">UPOSP (...)</a>
    """
    soup = BeautifulSoup(html, "lxml")
    index: dict[str, str] = {}
    for a in soup.find_all("a", href=ISU_CD_RE):
        isin = ISU_CD_RE.search(a["href"]).group(1)
        words = a.get_text(" ", strip=True).split()
        if words and TICKER_RE.match(words[0]) and ISIN_RE.match(isin):
            index.setdefault(words[0], isin)
    return index


def get_quotes(codes: list[str]) -> dict[str, PriceQuote]:
    """Berilgan kodlar (ISIN yoki tiker) uchun joriy narxlarni qaytaradi.

    Lug'at kaliti — portfolio.yaml'da yozilgan kod (katta harfda). Topilmagan
    kodlar lug'atda bo'lmaydi.
    """
    wanted = list(dict.fromkeys(c.strip().upper() for c in codes))
    code_to_isin = {c: c for c in wanted if ISIN_RE.match(c)}

    tickers = [c for c in wanted if c not in code_to_isin]
    if tickers:
        try:
            index = parse_ticker_index(fetch_html(STOCKS_URL))
        except requests.RequestException as exc:
            logger.error("UZSE aksiyalar ro'yxatini olib bo'lmadi: %s", exc)
            index = {}
        for t in tickers:
            if t in index:
                code_to_isin[t] = index[t]
            else:
                logger.warning(
                    "%s tikeri uchun ISIN topilmadi. portfolio.yaml'da ISIN kodini "
                    "yozing (masalan UZ7036271003)", t,
                )

    quotes: dict[str, PriceQuote] = {}
    for i, (code, isin) in enumerate(code_to_isin.items()):
        if i > 0 or tickers:
            time.sleep(REQUEST_DELAY_SEC)
        try:
            quote = parse_stock_page(fetch_html(stock_url(isin)))
        except requests.RequestException as exc:
            logger.warning("%s (%s) sahifasini olib bo'lmadi: %s", code, isin, exc)
            continue
        if quote is None:
            logger.warning("%s (%s) sahifasidan narx ajratib bo'lmadi — sayt tuzilishi o'zgargan bo'lishi mumkin", code, isin)
            continue
        if quote.isin != isin:
            logger.warning("%s so'raldi, lekin sahifada %s chiqdi — e'tiborsiz qoldirildi", isin, quote.isin)
            continue
        quotes[code] = quote

    missing = set(wanted) - quotes.keys()
    if missing:
        logger.warning("Quyidagi kodlar uchun narx topilmadi: %s", ", ".join(sorted(missing)))
    return quotes

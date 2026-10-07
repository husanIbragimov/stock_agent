"""Konfiguratsiyani yuklash: .env (token, chat, DB) va bir martalik YAML import uchun o'qish.

Portfel endi SQLite'da (`repo.PortfolioRepo`). YAML faqat `python main.py import-yaml`
orqali bir marta ko'chirish uchun o'qiladi.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PORTFOLIO_PATH = ROOT_DIR / "config" / "portfolio.yaml"


@dataclass
class Holding:
    ticker: str
    name: str
    quantity: float = 0.0
    buy_price: float | None = None
    drop_alert_pct: float | None = None
    trailing_drop_pct: float | None = None
    extra_keywords: list[str] = field(default_factory=list)

    @property
    def is_owned(self) -> bool:
        return self.buy_price is not None and self.quantity > 0

    def keywords(self) -> list[str]:
        return [self.name, self.ticker, *self.extra_keywords]


@dataclass
class Settings:
    max_alerts_per_ticker_per_day: int = 2
    price_history_days: int = 60
    news_lookback_hours: int = 48


@dataclass
class AppConfig:
    telegram_bot_token: str
    telegram_chat_id: str
    db_path: Path
    log_level: str = "INFO"


def load_config(env_path: str | Path | None = None) -> AppConfig:
    load_dotenv(env_path or ROOT_DIR / ".env")

    db_path = Path(os.environ.get("DB_PATH", "./data/agent.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        db_path=db_path,
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )


def load_portfolio_yaml(path: str | Path) -> tuple[list[Holding], list[Holding], Settings]:
    """Eski portfolio.yaml faylini o'qiydi: (holdings, watchlist, settings)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Portfolio fayli topilmadi: {path}")
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    holdings = [Holding(**h) for h in raw.get("holdings") or []]
    watchlist = [Holding(**w) for w in raw.get("watchlist") or []]
    settings = Settings(**(raw.get("settings") or {}))
    return holdings, watchlist, settings

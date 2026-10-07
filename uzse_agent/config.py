"""Konfiguratsiyani (.env va portfolio.yaml) yuklash."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent


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
    holdings: list[Holding]
    watchlist: list[Holding]
    settings: Settings
    log_level: str = "INFO"

    def all_tickers(self) -> list[Holding]:
        return [*self.holdings, *self.watchlist]


def load_config(portfolio_path: str | Path | None = None, env_path: str | Path | None = None) -> AppConfig:
    load_dotenv(env_path or ROOT_DIR / ".env")

    portfolio_path = Path(portfolio_path or ROOT_DIR / "config" / "portfolio.yaml")
    if not portfolio_path.exists():
        raise FileNotFoundError(
            f"Portfolio fayli topilmadi: {portfolio_path}\n"
            "config/portfolio.example.yaml faylidan nusxa oling: "
            "cp config/portfolio.example.yaml config/portfolio.yaml"
        )

    with open(portfolio_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    holdings = [Holding(**h) for h in raw.get("holdings", [])]
    watchlist = [Holding(**w) for w in raw.get("watchlist", [])]
    settings = Settings(**raw.get("settings", {}))

    db_path = Path(os.environ.get("DB_PATH", "./data/agent.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    return AppConfig(
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        db_path=db_path,
        holdings=holdings,
        watchlist=watchlist,
        settings=settings,
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )

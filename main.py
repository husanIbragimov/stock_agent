#!/usr/bin/env python3
"""UZSE Portfolio Agent — CLI kirish nuqtasi.

Foydalanish:
    python main.py daemon         # doimiy ishlaydi: narx, yangiliklar, kunlik hisobot
    python main.py check          # bir marta narxlarni tekshiradi va threshold-alert yuboradi
    python main.py news           # bir marta yangiliklarni yig'adi
    python main.py report         # kunlik hisobotni darhol Telegram'ga yuboradi
    python main.py test-telegram  # Telegram ulanishini tekshirish uchun sinov xabari yuboradi
"""
from __future__ import annotations

import argparse
import logging
import sys

from uzse_agent.config import load_config
from uzse_agent.notifier import TelegramNotifier
from uzse_agent.repo import PortfolioRepo
from uzse_agent.runner import run_daily_report, run_news_scan, run_price_check
from uzse_agent.storage import Storage


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def cmd_check(config, storage, repo, notifier, args) -> None:
    run_price_check(repo, storage, notifier)


def cmd_news(config, storage, repo, notifier, args) -> None:
    run_news_scan(repo, storage)


def cmd_report(config, storage, repo, notifier, args) -> None:
    run_daily_report(repo, storage, notifier)


def cmd_test_telegram(config, storage, repo, notifier, args) -> None:
    ok = notifier.send("✅ UZSE Portfolio Agent Telegram bilan bog'landi.")
    print("Yuborildi" if ok else "XATO: yuborilmadi — .env faylini tekshiring")


def cmd_daemon(config, storage, repo, notifier, args) -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(lambda: run_price_check(repo, storage, notifier),
                      "cron", day_of_week="mon-fri", hour="9-18", minute="*/30",
                      id="price_check")
    scheduler.add_job(lambda: run_news_scan(repo, storage),
                      "cron", hour="*/2", id="news_scan")
    scheduler.add_job(lambda: run_daily_report(repo, storage, notifier),
                      "cron", day_of_week="mon-fri", hour=18, minute=30,
                      id="daily_report")

    logging.getLogger(__name__).info("Daemon ishga tushdi. To'xtatish uchun Ctrl+C.")
    run_price_check(repo, storage, notifier)
    scheduler.start()


COMMANDS = {
    "check": cmd_check,
    "news": cmd_news,
    "report": cmd_report,
    "daemon": cmd_daemon,
    "test-telegram": cmd_test_telegram,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="UZSE Portfolio Agent")
    parser.add_argument("command", choices=COMMANDS.keys())
    parser.add_argument("--env", default=None, help=".env fayli yo'li")
    args = parser.parse_args()

    config = load_config(env_path=args.env)
    setup_logging(config.log_level)

    storage = Storage(config.db_path)
    repo = PortfolioRepo(config.db_path)
    notifier = TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id)

    COMMANDS[args.command](config, storage, repo, notifier, args)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Xato: {exc}", file=sys.stderr)
        sys.exit(1)

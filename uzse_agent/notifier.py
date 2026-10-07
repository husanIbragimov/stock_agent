"""Telegram Bot API orqali xabar yuborish (qo'shimcha kutubxonasiz, oddiy HTTP)."""
from __future__ import annotations

import logging

import requests

from .textfmt import split_message

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, text: str) -> bool:
        if not self.enabled:
            logger.warning(
                "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID sozlanmagan — xabar yuborilmadi:\n%s",
                text,
            )
            return False
        # Uzun matn (masalan, ko'p aksiyali hisobot) bir nechta xabar bo'lib ketadi
        results = [self._send_one(part) for part in split_message(text)]
        return all(results)

    def _send_one(self, text: str) -> bool:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as exc:
            logger.error("Telegram xabar yuborishda xato: %s", exc)
            return False

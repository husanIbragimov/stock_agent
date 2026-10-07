import pytest
from telegram.ext import ConversationHandler

from uzse_agent.bot.app import build_application
from uzse_agent.bot.common import BotDeps
from uzse_agent.config import AppConfig
from uzse_agent.notifier import TelegramNotifier


def make(db_path, token="123456:TEST", chat_id="42"):
    from uzse_agent.repo import PortfolioRepo
    from uzse_agent.storage import Storage

    config = AppConfig(telegram_bot_token=token, telegram_chat_id=chat_id, db_path=db_path)
    deps = BotDeps(storage=Storage(db_path), repo=PortfolioRepo(db_path), notifier=TelegramNotifier(token, chat_id))
    return build_application(config, deps)


def test_build_application_registers_handlers_and_jobs(db_path):
    app = make(db_path)
    assert app.bot_data["owner_chat_id"] == 42
    assert any(isinstance(h, ConversationHandler) for h in app.handlers[0])
    names = {job.name for job in app.job_queue.jobs()}
    assert {"price_check", "news_scan", "daily_report", "startup_check"} <= names


@pytest.mark.parametrize("token, chat_id", [("", "42"), ("123456:TEST", ""), ("123456:TEST", "abc")])
def test_build_application_requires_config(db_path, token, chat_id):
    with pytest.raises(RuntimeError):
        make(db_path, token, chat_id)


def _entry_commands(app):
    conv = next(h for h in app.handlers[0] if isinstance(h, ConversationHandler))
    return {cmd for h in conv.entry_points if hasattr(h, "commands") for cmd in h.commands}


def test_forms_registered(db_path):
    assert {"add", "buy", "sell"} <= _entry_commands(make(db_path))

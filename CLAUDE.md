# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

UZSE Portfolio Agent: monitors stocks on the Tashkent Stock Exchange (uzse.uz), scans Uzbek/Russian economic news via RSS, and sends Telegram alerts and a daily report. The portfolio (stocks, buy/sell history, settings) lives in SQLite and is managed through a Telegram bot. It only monitors and notifies. It never places trades.

Code comments, docstrings, log messages and all user-facing Telegram text are in **Uzbek (Latin script)**. Keep new strings in Uzbek to match. The README is also in Uzbek.

## Commands

The local virtualenv is `venv/` (the README says `.venv/`; `.gitignore` ignores both).

```bash
source venv/bin/activate
pip install -r requirements-dev.txt   # requirements.txt + pytest

pytest                         # full suite, no network (get_quotes / requests.post are monkeypatched)
pytest tests/test_repo.py::test_delete_security_removes_transactions   # single test

python main.py daemon          # Telegram bot (long polling) + PTB JobQueue (Asia/Tashkent): check every 30 min Mon–Fri 9–18, news every 2h at :15 (offset so it never contends with a price check for the shared run lock), report 18:30 Mon–Fri. `/check`, `/news`, `/report`, `/price` use `block=False` so a slow fetch never freezes the bot
python main.py check           # fetch prices once, store them, send threshold alerts
python main.py news            # collect matching RSS news once
python main.py report          # build and send the daily report now
python main.py test-telegram   # send a test message
python main.py import-yaml     # one-time copy of config/portfolio.yaml into the DB

# Optional overrides
python main.py import-yaml --portfolio path/to/portfolio.yaml --env path/to/.env
```

`python main.py daemon` sends real Telegram messages: a `startup_check` job runs a price check 5 seconds after start. No linter config or build step.

## Configuration

- `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `LOG_LEVEL`, `DB_PATH` (default `./data/agent.db`, resolved relative to the CWD, not the repo root). If the Telegram vars are missing, `TelegramNotifier.send` only logs the message and returns `False`, but `daemon` refuses to start (`RuntimeError` → `Xato: ...`, exit 1). The bot answers only updates from `TELEGRAM_CHAT_ID` (`_guard` in `bot/app.py`).
- The portfolio is in SQLite (`securities`, `transactions`, `settings`, owned by `repo.py`). `config/portfolio.yaml` is read only by `import-yaml` (`load_portfolio_yaml` → `Holding(**h)` / `Settings(**s)`), which refuses to run once any transaction exists.

## Architecture

`main.py` builds `Storage`, `PortfolioRepo` (same DB file) and `TelegramNotifier`, then dispatches. `daemon` runs `bot.app.run_bot`; the other commands call the `run_*` functions in `uzse_agent/runner.py` directly.

- **`portfolio.py`**: pure `compute_position(transactions) -> Position` using the weighted-average cost method. A buy adds `qty × price + fee` to cost. A sell leaves the average unchanged and adds `qty × (price − avg) − fee` to `realized_pnl`. Transactions are ordered by `(traded_at, id)`, with unsaved ones (`id=None`) last. Selling more than is held at that date raises `NegativePositionError`. `today_local()` returns the Tashkent date, not the UTC one.
- **`repo.py`**: `PortfolioRepo`. Every write that changes a position (`add_transaction`, `delete_transaction`) first recomputes the whole history and writes nothing if it would go negative. `load_holdings()` adapts the DB to the runner's `Holding`: `ticker=ISIN`, `quantity`/`buy_price` from the position (`buy_price=None` when the quantity is 0, i.e. watchlist), and the exchange ticker prepended to `extra_keywords`. `load_settings()` falls back to `Settings` defaults for missing keys.
- **`runner.py`**: reads holdings and settings from the repo on **every** call, so bot edits apply on the next run. `run_exclusive(fn, *args)` is a non-blocking lock shared by price checks and news scans (scheduled jobs and `/check` / `/news`).
- **`scraper.py`**: UZSE has no public API. `get_quotes(codes)` fetches one page per stock, `/isu_infos/STK?isu_cd=<ISIN>&locale=en` (the site 404s on anything but an ISIN), and `parse_stock_page` reads the `div.paper header` block (`span.tick`, `span.isin`, `div.pprice > b` price, `div.pprice > span.d` change in UZS, from which `change_pct` is computed). Exchange tickers are resolved to ISINs via `parse_ticker_index` (the `isu_cd=` links on the page). Results are keyed by the requested code (uppercased). Requests are spaced by `REQUEST_DELAY_SEC` and retried on 429. `_to_float` treats `5,250` as thousands (the `locale=en` format). If the site layout changes, fix the CSS selectors here. `tests/fixtures/uzse_stock_UZ7036271003.html` is a saved page for offline tests.
- **`news.py`**: `fetch_news_for_keywords` reads the hard-coded `RSS_FEEDS`, keeps entries whose title or summary contains any `Holding.keywords()` (name, ISIN, exchange ticker, `extra_keywords`), and scores them with `score_sentiment(text) -> float in [-1, 1]` (lexicon word counts, Uzbek and Russian). That signature is the intended swap point for an LLM-based scorer.
- **`analyzer.py`**: a pure function `analyze(ticker, current_price, history, news_sentiments)`. It sums ±1 for a price change of ±5% over the stored history window and ±1 for an average sentiment above or below ±0.15, then maps the score to an Uzbek signal label.
- **`storage.py`**: SQLite with `price_history`, `alerts_sent` and `news_seen`. The `ticker` column in all three holds the ISIN. Schemas (here and in `repo.py`) are created with `CREATE TABLE IF NOT EXISTS`, and there are no migrations. Each method opens its own connection. All timestamps are UTC ISO strings and are compared as strings. Trade dates (`transactions.traded_at`) are `YYYY-MM-DD` in Tashkent time.
- **`textfmt.py`**: `esc()` (mandatory for any external text in a Telegram message), money and quantity formatting, and `split_message()`. `TelegramNotifier.send` splits text over 4000 characters into several messages.
- **`bot/`** (python-telegram-bot 22): every form lives in **one** `ConversationHandler` (`allow_reentry=True`, 10-minute timeout). Each `handlers_*` module exports `HANDLERS` (standalone), `ENTRY_POINTS` and `STATES` and is listed in `app.FORM_MODULES`. State ids are in `common.py`. Callback data uses `prefix:arg` (`tx:buy:<ISIN>`, `stock:<ISIN>`, `txdel:<id>:yes`, …). A catch-all handler registered last answers "stale button". Keep logic in `repo`/`portfolio` and keep handlers thin. `inputs.py` validates user input by raising `InputError` with an Uzbek message, and `format.py` builds message texts. Blocking work (scraper, report) runs in `asyncio.to_thread`. `tests/test_bot_flows.py` drives handlers with fake Update/Context objects and checks that every sent message is valid Telegram HTML.

Behaviors that matter when changing the runner:
- Threshold alerts (`check_thresholds`) apply only to **owned** holdings (quantity > 0). Watchlist stocks only get price history recorded. There are two checks: the drop from the average cost (`drop_alert_pct`) and the drop from the 30-day high (`trailing_drop_pct`, with the 30 days hard-coded).
- Alert throttling counts rows in `alerts_sent` since the current **UTC** date, capped by `max_alerts_per_ticker_per_day`. An alert is recorded only if the Telegram send succeeds.
- `news_seen.url` is UNIQUE, so an article that matches several stocks is stored only under the first one processed. `recent_news_sentiment` filters on `seen_at`, not `published_at`.
- The daily report, `/list` and the stock card read only from SQLite and do no live fetching, so `check` must have run beforehand for prices to show.
- Telegram messages use `parse_mode: HTML`. Pass every name, note, signal or other external text through `esc()`, and don't write a bare `&` in templates (that's why the text says "Foyda/zarar", not "P&L").

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

UZSE Portfolio Agent: monitors stocks on the Tashkent Stock Exchange (uzse.uz), scans Uzbek/Russian economic news via RSS, and sends Telegram alerts and a daily report. It only monitors and notifies. It never places trades.

Code comments, docstrings, log messages and all user-facing Telegram text are in **Uzbek (Latin script)**. Keep new strings in Uzbek to match. The README is also in Uzbek.

## Commands

The local virtualenv is `venv/`. The README says `.venv/`, and `.gitignore` only ignores `.venv/`.

```bash
source venv/bin/activate
pip install -r requirements.txt

python main.py check           # fetch prices once, store them, send threshold alerts
python main.py news            # collect matching RSS news once
python main.py report          # build and send the daily report now
python main.py daemon          # APScheduler loop (Asia/Tashkent): check every 30 min Mon–Fri 9–18, news every 2h, report 18:30 Mon–Fri
python main.py test-telegram   # send a test message

# Optional overrides
python main.py check --portfolio path/to/portfolio.yaml --env path/to/.env
```

There is no test suite, linter config or build step. To exercise the scraper without the network, call `scraper.parse_stock_page(html)` on a saved stock page.

## Configuration

- `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `LOG_LEVEL`, `DB_PATH` (default `./data/agent.db`, resolved relative to the CWD, not the repo root). If the Telegram vars are missing, `TelegramNotifier.send` only logs the message and returns `False`. It does not raise.
- `config/portfolio.yaml` (gitignored; template in `config/portfolio.example.yaml`) has `holdings`, `watchlist` and `settings`. YAML entries are passed straight to `Holding(**h)` / `Settings(**s)` dataclasses in `uzse_agent/config.py`, so any new YAML field must be added to those dataclasses as well.

## Architecture

`main.py` loads `AppConfig`, builds `Storage` (SQLite) and `TelegramNotifier`, and dispatches to the three `run_*` functions in `uzse_agent/runner.py`. The runner is the only module that ties the others together:

- **`scraper.py`**: UZSE has no public API. `get_quotes(codes)` fetches one page per stock, `/isu_infos/STK?isu_cd=<ISIN>&locale=en` (the site 404s on anything but an ISIN), and `parse_stock_page` reads the `div.paper header` block (`span.tick`, `span.isin`, `div.pprice > b` price, `div.pprice > span.d` change in UZS, from which `change_pct` is computed). A `ticker` in the YAML may be an ISIN or an exchange ticker; tickers are resolved to ISINs via `parse_ticker_index` (the `isu_cd=` links on the page). Results are keyed by the code as written in the YAML. Requests are spaced by `REQUEST_DELAY_SEC` and retried on 429. `_to_float` treats `5,250` as thousands (the `locale=en` format). If the site layout changes, fix the CSS selectors here.
- **`news.py`**: `fetch_news_for_keywords` reads the hard-coded `RSS_FEEDS`, keeps entries whose title or summary contains any `Holding.keywords()` (name, ticker, `extra_keywords`), and scores them with `score_sentiment(text) -> float in [-1, 1]` (lexicon word counts, Uzbek and Russian). That signature is the intended swap point for an LLM-based scorer.
- **`analyzer.py`**: a pure function `analyze(ticker, current_price, history, news_sentiments)`. It sums ±1 for a price change of ±5% over the stored history window and ±1 for an average sentiment above or below ±0.15, then maps the score to an Uzbek signal label.
- **`storage.py`**: SQLite with three tables: `price_history`, `alerts_sent` and `news_seen`. The schema is created on startup with `CREATE TABLE IF NOT EXISTS`, and there are no migrations. Each method opens its own connection. All timestamps are UTC ISO strings and are compared as strings.

Behaviors that matter when changing the runner:
- Threshold alerts (`check_thresholds`) apply only to **owned** holdings (`buy_price` set and `quantity > 0`). Watchlist tickers only get price history recorded. There are two checks: the drop from `buy_price` (`drop_alert_pct`) and the drop from the 30-day high (`trailing_drop_pct`, with the 30 days hard-coded).
- Alert throttling counts rows in `alerts_sent` since the current **UTC** date, capped by `max_alerts_per_ticker_per_day`. An alert is recorded only if the Telegram send succeeds.
- `news_seen.url` is UNIQUE, so an article that matches several tickers is stored only under the first ticker processed. `recent_news_sentiment` filters on `seen_at`, not `published_at`.
- The daily report reads only from SQLite and does no live fetching, so `check`/`news` must have run beforehand for it to have data.
- Telegram messages use `parse_mode: HTML`, so text inserted into them (for example, news titles) must be valid within Telegram's HTML subset.

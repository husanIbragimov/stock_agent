"""Eski config/portfolio.yaml faylini DB'ga bir marta ko'chirish."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import load_portfolio_yaml
from .portfolio import Transaction, today_local
from .repo import PortfolioRepo, Security
from .scraper import get_quotes


@dataclass
class ImportResult:
    added: list[str] = field(default_factory=list)
    transactions: int = 0
    skipped: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Qo'shilgan aksiyalar: {len(self.added)}", *(f"  + {a}" for a in self.added)]
        lines.append(f"Qo'shilgan xaridlar: {self.transactions}")
        if self.skipped:
            lines.append("O'tkazib yuborildi:")
            lines.extend(f"  - {s}" for s in self.skipped)
        return "\n".join(lines)


def import_yaml(path: str | Path, repo: PortfolioRepo, resolve=get_quotes, today: str | None = None) -> ImportResult:
    """YAML'dagi holdings va watchlist'ni DB'ga yozadi.

    Har bir egalik qilingan aksiya uchun bitta "boshlang'ich xarid" tranzaksiyasi
    yaratiladi. Dublikat xaridlar bo'lmasligi uchun DB'da tranzaksiya bo'lsa, rad etadi.
    """
    if repo.has_transactions():
        raise RuntimeError(
            "DB'da allaqachon tranzaksiyalar bor — import takroriy xaridlar yaratmasligi uchun to'xtatildi"
        )
    holdings, watchlist, settings = load_portfolio_yaml(path)
    entries = [*holdings, *watchlist]
    traded_at = today or today_local().isoformat()
    quotes = resolve([h.ticker for h in entries])
    result = ImportResult()

    for h in entries:
        code = h.ticker.strip().upper()
        quote = quotes.get(code)
        if quote is None:
            result.skipped.append(f"{code}: UZSE'da topilmadi")
            continue
        if repo.get_security(quote.isin):
            result.skipped.append(f"{code}: {quote.isin} allaqachon qo'shilgan")
            continue
        repo.add_security(
            Security(
                isin=quote.isin,
                ticker=quote.ticker or None,
                name=h.name,
                extra_keywords=list(h.extra_keywords),
                drop_alert_pct=h.drop_alert_pct,
                trailing_drop_pct=h.trailing_drop_pct,
            )
        )
        result.added.append(f"{quote.isin} ({h.name})")

        if h.quantity > 0 and h.buy_price:
            if h.quantity != int(h.quantity):
                result.skipped.append(f"{code}: miqdor butun son emas ({h.quantity}) — xarid yozilmadi")
                continue
            repo.add_transaction(
                quote.isin,
                Transaction(None, "buy", int(h.quantity), float(h.buy_price), 0.0, traded_at, "YAML'dan import"),
            )
            result.transactions += 1

    for key, value in asdict(settings).items():
        repo.set_setting(key, value)
    return result
